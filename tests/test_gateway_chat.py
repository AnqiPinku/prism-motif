"""Gateway chat SSE tests without a real provider or API key."""

import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from gateway import auth, server
from gateway.server import Handler


def parse_sse(body):
    events = []
    for block in body.decode("utf-8").split("\n\n"):
        data = [line[6:] for line in block.splitlines() if line.startswith("data: ")]
        if data:
            events.append(json.loads("\n".join(data)))
    return events


class GatewayChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_token = auth.SESSION_TOKEN
        cls.original_instance = auth.INSTANCE_ID
        cls.original_origins = auth.ALLOWED_ORIGINS
        auth.SESSION_TOKEN = "chat-test-token"
        auth.INSTANCE_ID = "chat-test-instance"
        auth.ALLOWED_ORIGINS = {"http://tauri.localhost"}
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        auth.SESSION_TOKEN = cls.original_token
        auth.INSTANCE_ID = cls.original_instance
        auth.ALLOWED_ORIGINS = cls.original_origins

    def post_chat(self, thread_id="chat-test"):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request(
            "POST",
            "/api/chat",
            body=json.dumps({"goal": "test", "thread_id": thread_id}),
            headers={
                "Origin": "http://tauri.localhost",
                "X-Prism-Session": "chat-test-token",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        body = response.read()
        connection.close()
        self.assertEqual(response.status, 200)
        return parse_sse(body)

    def tearDown(self):
        self.assertFalse(server.RUNNING)

    def test_success_stream_has_monotonic_ids_and_done(self):
        def fake_run(_goal, provider=None, on_event=None, thread_id=None, permission=None):
            on_event({"type": "turn_start", "provider": provider or "fake"})
            on_event({"type": "delta", "text": "hel", "step": 1})
            on_event({"type": "delta", "text": "lo", "step": 1})
            on_event({"type": "final", "text": "hello"})

        with patch("gateway.server.runner.run_turn", side_effect=fake_run):
            events = self.post_chat()
        self.assertEqual([event["seq"] for event in events], list(range(1, len(events) + 1)))
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual("".join(event.get("text", "") for event in events
                                 if event["type"] == "delta"), "hello")

    def test_runner_failure_emits_error_then_done(self):
        with patch("gateway.server.runner.run_turn", side_effect=RuntimeError("provider failed")):
            events = self.post_chat("chat-error")
        types = [event["type"] for event in events]
        self.assertIn("error", types)
        self.assertEqual(types[-1], "done")
        self.assertTrue(any("provider failed" in event.get("message", "") for event in events))

    def test_large_tool_result_is_truncated_only_on_sse(self):
        def fake_run(_goal, provider=None, on_event=None, thread_id=None, permission=None):
            on_event({
                "type": "tool_result",
                "id": "1",
                "name": "long_result",
                "content": "x" * 5_000,
                "is_error": False,
            })

        with patch("gateway.server.runner.run_turn", side_effect=fake_run):
            events = self.post_chat("chat-long")
        result = next(event for event in events if event["type"] == "tool_result")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["original_chars"], 5_000)
        self.assertEqual(len(result["content"]), 2_048)


if __name__ == "__main__":
    unittest.main()
