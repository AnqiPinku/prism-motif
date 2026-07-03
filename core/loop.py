"""ReAct 循环：想 → 做 → 看 → 重复。领域无关、模型无关。
可选 permission 钩子拦截危险动作；on_event 把每步推给上层（命令行/前端）。"""
import time

from .contracts import Message
try:
    from .reasoners.openai_compat import RetriableStreamError
except ImportError:                                              # 单元测试里可能不带默认 reasoner
    class RetriableStreamError(Exception): pass

MAX_STREAM_RETRIES = 3   # 中途瞬时错误重试次数（含首次），前置条件：还没吐 delta / 工具


class AgentLoop:
    def __init__(self, reasoner, toolhub, max_steps=64, on_event=None, permission=None):
        self.reasoner = reasoner
        self.toolhub = toolhub
        self.max_steps = max_steps
        self.on_event = on_event or (lambda e: None)
        self.permission = permission

    def run(self, messages):
        """跑完一个回合，返回最终回答文本。"""
        specs = self.toolhub.specs() if self.toolhub else []
        turn_start = time.time()
        self.on_event({"type": "loop_start", "max_steps": self.max_steps,
                       "tool_count": len(specs)})
        for step in range(1, self.max_steps + 1):
            model_start = time.time()
            delta_stats = {"chars": 0, "chunks": 0, "first": False}

            def on_delta(t):
                if not delta_stats["first"]:
                    delta_stats["first"] = True
                    self.on_event({"type": "model_first_delta", "step": step,
                                   "ttft_ms": int((time.time() - model_start) * 1000)})
                    # 三段式：首个 delta 前发 content_start，前端建立一个 streaming 文本块
                    self.on_event({"type": "content_start", "step": step, "block_type": "text"})
                    self.on_event({"type": "status", "state": "streaming"})
                delta_stats["chars"] += len(t or "")
                delta_stats["chunks"] += 1
                self.on_event({"type": "delta", "text": t, "step": step})

            self.on_event({"type": "status", "state": "thinking",
                           "verb": "请求模型 · 第 %d 步" % step})
            self.on_event({"type": "model_start", "step": step,
                           "message_count": len(messages), "tool_count": len(specs)})

            # 中途瞬时错误（provider 500/429 等）+ 前置条件（未吐字/未调工具）→ 整轮重跑
            decision = None
            for attempt in range(1, MAX_STREAM_RETRIES + 1):
                try:
                    decision = self.reasoner.decide(messages, specs, on_delta=on_delta)
                    break
                except RetriableStreamError as e:
                    if attempt >= MAX_STREAM_RETRIES:
                        raise
                    self.on_event({"type": "retry", "attempt": attempt,
                                   "max": MAX_STREAM_RETRIES, "kind": "stream",
                                   "content": "流内错误重试：" + str(e.why)})
                    model_start = time.time()
                    delta_stats = {"chars": 0, "chunks": 0, "first": False}

            # 首个 delta 之后有 content_start，此处配对 content_end（tool 决策没吐字则跳过）
            if delta_stats["first"]:
                self.on_event({"type": "content_end", "step": step, "block_type": "text"})
            self.on_event({"type": "model_done", "step": step,
                           "kind": decision.kind,
                           "duration_ms": int((time.time() - model_start) * 1000),
                           "delta_chars": delta_stats["chars"],
                           "delta_chunks": delta_stats["chunks"]})

            if decision.kind == "final":
                # 把最终回答也存进历史，否则线程里看不到、多轮也记不住自己的回复
                messages.append(Message(role="assistant", content=decision.text or ""))
                self.on_event({"type": "final", "text": decision.text})
                self.on_event({"type": "message_complete", "step": step,
                               "delta_chars": delta_stats["chars"]})
                self.on_event({"type": "status", "state": "idle"})
                self.on_event({"type": "loop_done", "steps": step,
                               "duration_ms": int((time.time() - turn_start) * 1000),
                               "reason": "final"})
                return decision.text or ""

            # decision.kind == "tools"
            messages.append(Message(role="assistant", content=None,
                                    tool_calls=decision.tool_calls))
            calls = decision.tool_calls or []
            self.on_event({"type": "tool_batch", "step": step, "count": len(calls)})
            self.on_event({"type": "status", "state": "tool_executing",
                           "verb": "调用 %d 个工具" % len(calls)})
            for index, call in enumerate(calls, start=1):
                tool_start = time.time()
                self.on_event({"type": "tool_call", "id": call.id, "name": call.name,
                               "arguments": call.arguments, "step": step,
                               "index": index, "count": len(calls)})

                if self.permission and not self.permission(call):
                    txt = "用户拒绝了该操作。"
                    messages.append(Message(role="tool", tool_call_id=call.id, content=txt))
                    self.on_event({"type": "tool_result", "id": call.id, "name": call.name,
                                   "content": txt, "is_error": True,
                                   "duration_ms": int((time.time() - tool_start) * 1000),
                                   "content_chars": len(txt), "permission": "denied"})
                    continue

                result = self.toolhub.execute(call)
                content = result.content if isinstance(result.content, str) else str(result.content)
                messages.append(Message(role="tool", tool_call_id=call.id, content=content))
                self.on_event({"type": "tool_result", "id": call.id, "name": call.name,
                               "content": content, "is_error": result.is_error,
                               "duration_ms": int((time.time() - tool_start) * 1000),
                               "content_chars": len(content)})

        fallback = "（已达到最大步数，未能完成。）"
        self.on_event({"type": "final", "text": fallback})
        self.on_event({"type": "loop_done", "steps": self.max_steps,
                       "duration_ms": int((time.time() - turn_start) * 1000),
                       "reason": "max_steps"})
        return fallback
