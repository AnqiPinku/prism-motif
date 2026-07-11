"""OpenAI-compatible reasoner tests against a local fake provider."""

import unittest

from core.contracts import Message, ToolSpec
from core.loop import AgentLoop
from core.reasoners.openai_compat import OpenAICompatReasoner, RetriableStreamError
from tests.fixtures.fake_provider import FakeProvider


class ReasonerTests(unittest.TestCase):
    def make_reasoner(self, provider, model):
        reasoner = OpenAICompatReasoner(provider.base_url, model, "test-key", timeout=2)
        reasoner.retry_base_delay = 0
        return reasoner

    def test_non_stream_final_and_usage(self):
        with FakeProvider() as provider:
            reasoner = self.make_reasoner(provider, "final")
            decision = reasoner.decide([Message("user", "hi")], [])
        self.assertEqual((decision.kind, decision.text), ("final", "ok"))
        self.assertEqual(reasoner.last_prompt_tokens, 7)

    def test_retry_then_success(self):
        with FakeProvider() as provider:
            reasoner = self.make_reasoner(provider, "retry")
            decision = reasoner.decide([Message("user", "hi")], [])
            self.assertEqual(provider.counts["retry"], 3)
        self.assertEqual(decision.text, "ok")

    def test_empty_response_is_a_valid_empty_final(self):
        with FakeProvider() as provider:
            decision = self.make_reasoner(provider, "empty").decide(
                [Message("user", "hi")], []
            )
        self.assertEqual((decision.kind, decision.text), ("final", ""))

    def test_non_stream_tool_call(self):
        with FakeProvider() as provider:
            decision = self.make_reasoner(provider, "tool").decide(
                [Message("user", "hi")],
                [ToolSpec("echo", "", {"type": "object", "properties": {}})],
            )
        self.assertEqual(decision.kind, "tools")
        self.assertEqual(decision.tool_calls[0].arguments, {"value": 7})

    def test_stream_text_and_usage(self):
        with FakeProvider() as provider:
            reasoner = self.make_reasoner(provider, "stream")
            chunks = []
            decision = reasoner.decide([Message("user", "hi")], [], on_delta=chunks.append)
        self.assertEqual(decision.text, "hello")
        self.assertEqual(chunks, ["hel", "lo"])
        self.assertEqual(reasoner.last_prompt_tokens, 11)

    def test_stream_tool_call_assembles_arguments(self):
        with FakeProvider() as provider:
            decision = self.make_reasoner(provider, "tool").decide(
                [Message("user", "hi")],
                [ToolSpec("echo", "", {"type": "object", "properties": {}})],
                on_delta=lambda _text: None,
            )
        self.assertEqual(decision.kind, "tools")
        self.assertEqual(decision.tool_calls[0].arguments, {"value": 8})

    def test_empty_disconnect_is_retriable(self):
        with FakeProvider() as provider:
            with self.assertRaises(RetriableStreamError):
                self.make_reasoner(provider, "disconnect").decide(
                    [Message("user", "hi")], [], on_delta=lambda _text: None
                )

    def test_partial_disconnect_is_fatal_to_avoid_duplicate_text(self):
        with FakeProvider() as provider:
            with self.assertRaisesRegex(RuntimeError, "未收到"):
                self.make_reasoner(provider, "partial_disconnect").decide(
                    [Message("user", "hi")], [], on_delta=lambda _text: None
                )

    def test_agent_loop_retries_retriable_mid_stream_error(self):
        with FakeProvider() as provider:
            reasoner = self.make_reasoner(provider, "stream_error")
            result = AgentLoop(reasoner, None, max_steps=1).run([Message("user", "hi")])
            self.assertEqual(provider.counts["stream_error"], 2)
        self.assertEqual(result, "hello")


if __name__ == "__main__":
    unittest.main()
