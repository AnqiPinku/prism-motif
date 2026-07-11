"""Agent loop behavior with deterministic reasoners and tools."""

import unittest

from core.contracts import Decision, Message, ToolCall, ToolResult, ToolSpec
from core.loop import AgentLoop


class ScriptedReasoner:
    def __init__(self, decisions):
        self.decisions = iter(decisions)

    def decide(self, _messages, _tools, on_delta=None):
        decision = next(self.decisions)
        if on_delta and decision.kind == "final" and decision.text:
            on_delta(decision.text)
        return decision


class FakeToolHub:
    def specs(self):
        return [ToolSpec("echo", "", {"type": "object", "properties": {}})]

    def execute(self, call):
        return ToolResult(call.id, "echoed:%s" % call.arguments.get("value"))


class AgentLoopTests(unittest.TestCase):
    def test_tool_result_is_fed_back_before_final_answer(self):
        reasoner = ScriptedReasoner([
            Decision(kind="tools", tool_calls=[ToolCall("1", "echo", {"value": 7})]),
            Decision(kind="final", text="完成"),
        ])
        events = []
        messages = [Message(role="user", content="hi")]
        result = AgentLoop(reasoner, FakeToolHub(), on_event=events.append).run(messages)
        self.assertEqual(result, "完成")
        self.assertTrue(any(event["type"] == "tool_call" for event in events))
        self.assertTrue(any(event["type"] == "tool_result" for event in events))
        self.assertTrue(any(message.role == "tool" and "echoed:7" in message.content
                            for message in messages))

    def test_permission_denial_prevents_execution(self):
        reasoner = ScriptedReasoner([
            Decision(kind="tools", tool_calls=[ToolCall("1", "echo", {"value": 7})]),
            Decision(kind="final", text="已处理拒绝"),
        ])

        class ExplodingHub(FakeToolHub):
            def execute(self, _call):
                raise AssertionError("denied tool must not execute")

        messages = [Message(role="user", content="hi")]
        result = AgentLoop(reasoner, ExplodingHub(), permission=lambda _call: False).run(messages)
        self.assertEqual(result, "已处理拒绝")
        self.assertTrue(any(message.role == "tool" and "用户拒绝" in message.content
                            for message in messages))

    def test_max_steps_returns_observable_fallback(self):
        reasoner = ScriptedReasoner([
            Decision(kind="tools", tool_calls=[ToolCall("1", "echo", {})]),
        ])
        events = []
        result = AgentLoop(reasoner, FakeToolHub(), max_steps=1, on_event=events.append).run(
            [Message(role="user", content="hi")]
        )
        self.assertIn("最大步数", result)
        self.assertTrue(any(event.get("reason") == "max_steps" for event in events))


if __name__ == "__main__":
    unittest.main()
