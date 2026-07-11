"""Context elision and summary-compaction tests."""

import unittest

from core.compaction import (
    CompactingReasoner,
    elide_tool_results,
    recent_cut,
    summarize_messages,
)
from core.contracts import Decision, Message, ToolCall
from core import runner


class CapturingReasoner:
    def __init__(self, text="ok", prompt_tokens=123):
        self.text = text
        self.last_prompt_tokens = prompt_tokens
        self.seen = None

    def decide(self, messages, _tools, on_delta=None):
        self.seen = messages
        return Decision(kind="final", text=self.text)


class CompactionTests(unittest.TestCase):
    def messages_with_old_tool_result(self):
        return [
            Message("user", "u1"),
            Message("assistant", None, tool_calls=[ToolCall("a", "t", {})]),
            Message("tool", "x" * 5_000, tool_call_id="a"),
            Message("user", "u2"),
            Message("user", "u3"),
            Message("user", "u4"),
            Message("user", "u5"),
        ]

    def test_old_long_tool_result_is_elided_without_mutation(self):
        messages = self.messages_with_old_tool_result()
        result, count = elide_tool_results(messages, keep_recent_turns=4, elide_over_chars=2_000)
        self.assertEqual(count, 1)
        self.assertIn("已省略", result[2].content)
        self.assertEqual(result[2].tool_call_id, "a")
        self.assertEqual(messages[2].content, "x" * 5_000)

    def test_recent_tool_result_is_preserved(self):
        messages = [
            Message("user", "u1"),
            Message("assistant", None, tool_calls=[ToolCall("a", "t", {})]),
            Message("tool", "x" * 5_000, tool_call_id="a"),
        ]
        _result, count = elide_tool_results(messages, keep_recent_turns=4, elide_over_chars=2_000)
        self.assertEqual(count, 0)

    def test_compacting_reasoner_projects_only_model_input(self):
        messages = self.messages_with_old_tool_result()
        inner = CapturingReasoner()
        events = []
        reasoner = CompactingReasoner(
            inner,
            window_tokens=1_000,
            keep_recent_turns=4,
            elide_over_chars=2_000,
            on_event=events.append,
        )
        decision = reasoner.decide(messages, [])
        self.assertEqual(decision.text, "ok")
        self.assertIn("已省略", inner.seen[2].content)
        self.assertEqual(messages[2].content, "x" * 5_000)
        self.assertTrue(any(event.get("type") == "context"
                            and event.get("prompt_tokens") == 123 for event in events))
        self.assertTrue(any(event.get("type") == "compaction" for event in events))

    def test_recent_cut_uses_user_turns(self):
        messages = [Message("user", "u1"), Message("assistant", "a"),
                    Message("user", "u2"), Message("user", "u3"),
                    Message("user", "u4"), Message("user", "u5")]
        self.assertEqual(recent_cut(messages, 4), 2)
        self.assertEqual(recent_cut([Message("user", "x")], 4), 0)

    def test_summary_request_has_no_tools(self):
        inner = CapturingReasoner("摘要：决定与待办")
        summary = summarize_messages(
            inner,
            "",
            [Message("user", "做X"), Message("assistant", "好的")],
            on_event=lambda _event: None,
        )
        self.assertIn("摘要", summary)
        self.assertEqual(len(inner.seen), 2)

    def test_runner_only_summarizes_new_old_history(self):
        context = {"compact_at": 0.6, "keep_recent_turns": 4, "summarize": True}
        messages = [Message("user", "x" * 300) for _ in range(8)]
        inner = CapturingReasoner("summary")
        first = runner._maybe_summarize(
            messages, "goal", 100, context, inner, None, lambda _event: None
        )
        self.assertEqual(first["upto"], recent_cut(messages, 4))
        second = runner._maybe_summarize(
            messages,
            "goal",
            100,
            context,
            inner,
            {"text": first["text"], "upto": first["upto"]},
            lambda _event: None,
        )
        self.assertEqual(second["upto"], first["upto"])


if __name__ == "__main__":
    unittest.main()
