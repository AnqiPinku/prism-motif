"""Permission enforcement tests at both policy and loop boundaries."""

import unittest

from core.contracts import Decision, Message, ToolCall, ToolResult, ToolSpec
from core.loop import AgentLoop
from gateway.policy import ToolPolicy


class PermissionBoundaryTests(unittest.TestCase):
    def test_unknown_tool_requires_confirmation_even_in_trust_mode(self):
        policy = ToolPolicy()
        required, risk = policy.requires_confirmation("unknown_tool", {}, trust=True)
        self.assertTrue(required)
        self.assertEqual(risk, "write")

    def test_permission_callback_blocks_side_effect(self):
        calls = []

        class Reasoner:
            count = 0

            def decide(self, _messages, _tools, on_delta=None):
                self.count += 1
                if self.count == 1:
                    return Decision("tools", tool_calls=[ToolCall("1", "danger", {})])
                return Decision("final", text="done")

        class Hub:
            def specs(self):
                return [ToolSpec("danger", "", {"type": "object", "properties": {}})]

            def execute(self, call):
                calls.append(call)
                return ToolResult(call.id, "executed")

        messages = [Message("user", "run it")]
        AgentLoop(Reasoner(), Hub(), permission=lambda _call: False).run(messages)
        self.assertEqual(calls, [])
        self.assertTrue(any(message.role == "tool" and "用户拒绝" in message.content
                            for message in messages))


if __name__ == "__main__":
    unittest.main()
