"""ReAct 循环：想 → 做 → 看 → 重复。领域无关、模型无关。
可选 permission 钩子拦截危险动作；on_event 把每步推给上层（命令行/前端）。"""
from .contracts import Message


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
        for _ in range(self.max_steps):
            decision = self.reasoner.decide(
                messages, specs,
                on_delta=lambda t: self.on_event({"type": "delta", "text": t}))

            if decision.kind == "final":
                # 把最终回答也存进历史，否则线程里看不到、多轮也记不住自己的回复
                messages.append(Message(role="assistant", content=decision.text or ""))
                self.on_event({"type": "final", "text": decision.text})
                return decision.text or ""

            # decision.kind == "tools"
            messages.append(Message(role="assistant", content=None,
                                    tool_calls=decision.tool_calls))
            for call in decision.tool_calls or []:
                self.on_event({"type": "tool_call", "name": call.name,
                               "arguments": call.arguments})

                if self.permission and not self.permission(call):
                    txt = "用户拒绝了该操作。"
                    messages.append(Message(role="tool", tool_call_id=call.id, content=txt))
                    self.on_event({"type": "tool_result", "name": call.name,
                                   "content": txt, "is_error": True})
                    continue

                result = self.toolhub.execute(call)
                content = result.content if isinstance(result.content, str) else str(result.content)
                messages.append(Message(role="tool", tool_call_id=call.id, content=content))
                self.on_event({"type": "tool_result", "name": call.name,
                               "content": content, "is_error": result.is_error})

        fallback = "（已达到最大步数，未能完成。）"
        self.on_event({"type": "final", "text": fallback})
        return fallback
