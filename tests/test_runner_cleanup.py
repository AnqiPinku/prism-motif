"""run_turn 生命周期回归：任何阶段的异常都不得泄漏 MCP 子进程。

背景（2026-07-12 CI Soak 抓到的真 bug）：toolhub.start() 与 mcp_ready 事件曾在
try 块之外，取消信号恰好落在 MCP 启动窗口时，mcp_ready 的 emit 抛出异常而
finally 尚未生效，toolhub.close() 永远不执行——MCP 子进程成孤儿。本机 MCP
启动快难复现，感知 sidecar 冷启动 2.4s 的真实产品必现。
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import runner
from core.tools import ToolHub


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fake_mcp_server.py"


class RunnerCleanupTests(unittest.TestCase):
    def _temp_config(self):
        root = Path(tempfile.mkdtemp(prefix="prism-cleanup-"))
        (root / "providers.json").write_text(json.dumps({
            "default": "mock",
            "providers": {"mock": {"type": "mock", "model": "mock",
                                   "base_url": "", "api_key_env": "NONE"}},
        }), encoding="utf-8")
        (root / "settings.json").write_text(json.dumps({
            "max_steps": 4, "tool_timeout_s": 5,
            "base_prompt": "test", "workspace": "default",
            "context": {"enabled": False},
        }), encoding="utf-8")
        (root / "mcp_servers.json").write_text(json.dumps({"servers": [{
            "name": "fake", "enabled": True, "command": __import__("sys").executable,
            "args": [str(FIXTURE)],
        }]}), encoding="utf-8")
        (root / "modes.json").write_text(json.dumps({"current": "", "modes": {}}),
                                         encoding="utf-8")
        return root

    def test_exception_at_mcp_ready_still_closes_toolhub(self):
        """取消信号（或任何异常）在 mcp_ready 的 emit 中抛出 → close 必须执行。"""
        closed = []

        class SpyHub(ToolHub):
            def close(self):
                closed.append(True)
                super().close()

        def cancel_at_mcp_ready(event):
            if event.get("type") == "mcp_ready":
                raise RuntimeError("simulated cancel during MCP startup")

        config = self._temp_config()
        with patch.object(runner, "CONFIG", config), \
                patch.object(runner, "ToolHub", SpyHub):
            with self.assertRaises(RuntimeError):
                runner.run_turn("hi", on_event=cancel_at_mcp_ready)
        self.assertTrue(closed, "toolhub.close() 未被调用——MCP 子进程会成孤儿")


if __name__ == "__main__":
    unittest.main()
