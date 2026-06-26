"""Mock 模型：不联网、不需 key，直接回一句话。用于无 LLM/无 REAPER 时测试整条链路。"""
from ..reasoner import Reasoner
from ..contracts import Decision


class MockReasoner(Reasoner):
    def decide(self, messages, tools, on_delta=None):
        last = ""
        for m in reversed(messages):
            if m.role == "user" and isinstance(m.content, str):
                last = m.content
                break
        return Decision(
            kind="final",
            text="（mock 模型）收到目标：%s。当前已连接 %d 个工具。"
                 "换成真模型（如 DeepSeek）后我才会真正调用它们。" % (last, len(tools)),
        )
