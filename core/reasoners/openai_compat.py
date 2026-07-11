"""默认模型后端：打 OpenAI 兼容的 /chat/completions（只用标准库 urllib）。
改 base_url + model + api_key 即可换成 DeepSeek / Qwen / OpenAI / 本地 Ollama 等。"""
import json
import time
import random
import urllib.request
import urllib.error

from ..reasoner import Reasoner
from ..contracts import ToolCall, Decision


class RetriableStreamError(Exception):
    """流内瞬时错误（provider 中途 500/429 等），且当次 attempt 尚未产生 delta / tool_call
    → 上层可安全地整轮重跑 decide()，不会造成重复吐字或重复调用工具。"""
    def __init__(self, why):
        super().__init__(why)
        self.why = why


# 可重试的流内错误类型（OpenAI 兼容 provider 常见值）
_STREAM_RETRIABLE_TYPES = {"server_error", "api_error", "overloaded_error", "rate_limit_error"}
_STREAM_RETRIABLE_CODES = {"500", "502", "503", "504", "429"}


class OpenAICompatReasoner(Reasoner):
    """OpenAI 兼容协议的 Reasoner 实现。"""

    def __init__(self, base_url, model, api_key, timeout=120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or ""
        self.timeout = timeout
        self.last_prompt_tokens = None        # 最近一次请求的 prompt token 数（来自 API usage）
        self.last_completion_tokens = None
        self.max_attempts = 3                 # 瞬时错误重试总次数（含首次）
        self.retry_base_delay = 1.0           # 指数退避基数（秒）
        self.on_retry = None                  # 可选回调 (attempt, max, why)：流式上报"重试中"

    def _capture_usage(self, usage):
        """从响应 usage 记录 prompt/completion token 数（供上下文占用环 / 压缩触发用）。"""
        if isinstance(usage, dict):
            if usage.get("prompt_tokens") is not None:
                self.last_prompt_tokens = usage["prompt_tokens"]
            if usage.get("completion_tokens") is not None:
                self.last_completion_tokens = usage["completion_tokens"]

    def decide(self, messages, tools, on_delta=None):
        """发一次请求，解析成 Decision。提供 on_delta 时走流式（逐块吐文本）。"""
        payload = {
            "model": self.model,
            "messages": [self._to_openai(m) for m in messages],
        }
        if tools:
            payload["tools"] = [{
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters or {"type": "object", "properties": {}},
                },
            } for t in tools]

        if on_delta is not None:
            return self._decide_stream(payload, on_delta)

        data = self._post("/chat/completions", payload)
        self._capture_usage(data.get("usage"))
        msg = data["choices"][0]["message"]
        tcs = msg.get("tool_calls")
        if tcs:
            calls = []
            for tc in tcs:
                fn = tc.get("function", {})
                raw = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw) if isinstance(raw, str) else (raw or {})
                except json.JSONDecodeError:
                    args = {}
                calls.append(ToolCall(id=tc.get("id") or fn.get("name"),
                                      name=fn.get("name"), arguments=args))
            return Decision(kind="tools", tool_calls=calls)
        return Decision(kind="final", text=msg.get("content") or "")

    def _decide_stream(self, payload, on_delta):
        payload = dict(payload)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}   # 让流式也返回 usage（末尾 chunk）
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "NONE":
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(self.base_url + "/chat/completions",
                                     data=body, headers=headers, method="POST")
        resp = self._open(req)        # 重试只作用于"建连"；开始读流后不再重试，避免重复吐字

        text_acc = ""
        tool_acc = {}
        saw_done = False
        with resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    saw_done = True
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                # 流内错误 chunk（provider 中途报错）：若还没吐 delta/工具，抛可重试异常
                # → 上层 loop 可安全整轮重跑（幂等，不会重复吐字/调工具）；否则致命抛出
                err = obj.get("error")
                if isinstance(err, dict):
                    et = str(err.get("type") or "")
                    ec = str(err.get("code") or err.get("status") or "")
                    msg = str(err.get("message") or "provider stream error")
                    if (not text_acc and not tool_acc
                            and (et in _STREAM_RETRIABLE_TYPES or ec in _STREAM_RETRIABLE_CODES)):
                        raise RetriableStreamError("mid-stream %s: %s" % (et or ec or "error", msg))
                    raise RuntimeError("LLM 流内错误: %s" % msg)
                self._capture_usage(obj.get("usage"))   # usage chunk 通常 choices 为空
                choices = obj.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                c = delta.get("content")
                if c:
                    text_acc += c
                    on_delta(c)
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    acc = tool_acc.setdefault(idx, {"id": None, "name": None, "args": ""})
                    if tc.get("id"):
                        acc["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        acc["name"] = fn["name"]
                    if fn.get("arguments"):
                        acc["args"] += fn["arguments"]

        if not saw_done:
            if not text_acc and not tool_acc:
                raise RetriableStreamError("provider stream ended before [DONE]")
            raise RuntimeError("LLM 流提前结束：未收到 [DONE]")

        if tool_acc:
            calls = []
            for idx in sorted(tool_acc):
                a = tool_acc[idx]
                try:
                    args = json.loads(a["args"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                calls.append(ToolCall(id=a["id"] or a["name"], name=a["name"], arguments=args))
            return Decision(kind="tools", tool_calls=calls)
        return Decision(kind="final", text=text_acc)

    def _to_openai(self, m):
        if m.role == "tool":
            return {"role": "tool", "tool_call_id": m.tool_call_id,
                    "content": self._as_text(m.content)}
        if m.role == "assistant" and m.tool_calls:
            return {"role": "assistant", "content": m.content or "",
                    "tool_calls": [{
                        "id": c.id, "type": "function",
                        "function": {"name": c.name,
                                     "arguments": json.dumps(c.arguments, ensure_ascii=False)},
                    } for c in m.tool_calls]}
        return {"role": m.role, "content": self._as_text(m.content)}

    @staticmethod
    def _as_text(content):
        return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)

    _RETRYABLE = (408, 409, 429, 500, 502, 503, 504)

    def _open(self, req):
        """带重试+指数退避地建立连接；只对 429/5xx/网络/超时 重试。返回 response 或抛 RuntimeError。"""
        for attempt in range(1, self.max_attempts + 1):
            try:
                return urllib.request.urlopen(req, timeout=self.timeout)
            except urllib.error.HTTPError as e:
                try:
                    if e.code not in self._RETRYABLE or attempt == self.max_attempts:
                        detail = e.read().decode("utf-8", "replace")
                        raise RuntimeError("LLM HTTP %s: %s" % (e.code, detail)) from None
                    why = "HTTP %s" % e.code
                finally:
                    e.close()         # 释放失败响应的连接（含可重试分支），不留悬挂 socket
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt == self.max_attempts:
                    raise RuntimeError("连接 LLM 失败: %s" % (getattr(e, "reason", e),)) from None
                why = str(getattr(e, "reason", e))
            delay = self.retry_base_delay * (2 ** (attempt - 1))
            jittered = delay + random.uniform(0, delay * 0.25)
            if self.on_retry:                                     # 上报"重试中…"含 delay，前端可显示倒计时
                self.on_retry(attempt, self.max_attempts, why, int(jittered * 1000))
            time.sleep(jittered)   # 退避 + 抖动
        raise RuntimeError("LLM 重试耗尽")

    def _post(self, path, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "NONE":
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(self.base_url + path, data=body,
                                     headers=headers, method="POST")
        with self._open(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
