"""默认模型后端：打 OpenAI 兼容的 /chat/completions（只用标准库 urllib）。
改 base_url + model + api_key 即可换成 DeepSeek / Qwen / OpenAI / 本地 Ollama 等。"""
import json
import urllib.request
import urllib.error

from ..reasoner import Reasoner
from ..contracts import ToolCall, Decision


class OpenAICompatReasoner(Reasoner):
    """OpenAI 兼容协议的 Reasoner 实现。"""

    def __init__(self, base_url, model, api_key, timeout=120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key or ""
        self.timeout = timeout
        self.last_prompt_tokens = None        # 最近一次请求的 prompt token 数（来自 API usage）
        self.last_completion_tokens = None

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
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise RuntimeError("LLM HTTP %s: %s" % (e.code, detail)) from None
        except urllib.error.URLError as e:
            raise RuntimeError("连接 LLM 失败: %s" % (e.reason,)) from None

        text_acc = ""
        tool_acc = {}
        with resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
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

    def _post(self, path, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key != "NONE":
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(self.base_url + path, data=body,
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise RuntimeError("LLM HTTP %s: %s" % (e.code, detail)) from None
        except urllib.error.URLError as e:
            raise RuntimeError("连接 LLM 失败: %s" % (e.reason,)) from None
