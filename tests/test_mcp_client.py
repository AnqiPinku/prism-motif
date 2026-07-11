"""MCP client lifecycle, timeout, error, and large-result tests."""

import sys
import unittest
from pathlib import Path

from core.mcp_client import MCPClient


SERVER = Path(__file__).parent / "fixtures" / "fake_mcp_server.py"


class McpClientTests(unittest.TestCase):
    def client(self, mode="normal", timeout=1):
        return MCPClient(sys.executable, [str(SERVER), "--mode", mode], timeout=timeout)

    def test_handshake_list_call_and_clean_close(self):
        client = self.client()
        client.start()
        process = client.proc
        try:
            self.assertEqual([tool.name for tool in client.list_tools()],
                             ["echo", "long_result", "fail", "hang"])
            result = client.call_tool("echo", {"value": 7})
            self.assertFalse(result.is_error)
            self.assertIn('"value": 7', result.content)
        finally:
            client.close()
        self.assertIsNotNone(process.poll())

    def test_long_result_is_not_corrupted(self):
        client = self.client()
        client.start()
        try:
            result = client.call_tool("long_result", {})
        finally:
            client.close()
        self.assertEqual(len(result.content), 10_000)

    def test_rpc_error_becomes_tool_error(self):
        client = self.client()
        client.start()
        try:
            result = client.call_tool("fail", {})
        finally:
            client.close()
        self.assertTrue(result.is_error)
        self.assertIn("tool failed", result.content)

    def test_timeout_becomes_tool_error_and_close_kills_server(self):
        client = self.client(timeout=0.1)
        client.start()
        process = client.proc
        result = client.call_tool("hang", {})
        client.close()
        self.assertTrue(result.is_error)
        self.assertIn("超时", result.content)
        self.assertIsNotNone(process.poll())

    def test_server_exit_during_initialize_is_observable(self):
        client = self.client("exit_on_init", timeout=0.5)
        with self.assertRaisesRegex(RuntimeError, "退出"):
            client.start()
        self.assertIsNone(client.proc)

    def test_initialize_timeout_cleans_process(self):
        client = self.client("hang_initialize", timeout=0.1)
        with self.assertRaisesRegex(RuntimeError, "超时"):
            client.start()
        self.assertIsNone(client.proc)

    def test_list_tools_rpc_error_cleans_up_when_used_by_hub(self):
        client = self.client("rpc_error")
        client.start()
        try:
            with self.assertRaisesRegex(RuntimeError, "list failed"):
                client.list_tools()
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
