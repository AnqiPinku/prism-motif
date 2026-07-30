"""MCP 故障恢复回归：死进程秒判、写卡死有界、超时取消、陈旧响应丢弃、
ToolHub 降级启动 / 一次性重启 / 只读重试 / 熔断。全离线，假 server 在 tests/fake_mcp/。"""

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from core.contracts import ToolCall
from core.mcp_client import MCPClient
from core.tools import ToolHub


FAKES = Path(__file__).parent / "fake_mcp"


class McpClientResilienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="prism-mcpres-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def client(self, script, *argv, **kw):
        c = MCPClient(sys.executable, [str(FAKES / script), *argv], **kw)
        self.addCleanup(c.close)
        return c

    def test_dead_child_detected_fast(self):
        """握手刚完就死的子进程：poll 探活秒判，远快于 rpc 超时。"""
        c = self.client("dead.py", "--after", "init", timeout=30)
        c.start()
        started = time.monotonic()
        result = c.call_tool("boom", {})
        elapsed = time.monotonic() - started
        self.assertTrue(result.is_error)
        self.assertTrue(getattr(result, "transport_error", False))
        self.assertLess(elapsed, 5)

    def test_wedged_small_payload_times_out(self):
        """不再应答的子进程：小请求在 rpc 超时处干净失败，不挂死。"""
        c = self.client("wedged.py", timeout=2)
        c.start()
        started = time.monotonic()
        result = c.call_tool("anything", {"value": 1})
        self.assertTrue(result.is_error)
        self.assertIn("超时", result.content)
        self.assertLess(time.monotonic() - started, 6)

    def test_wedged_large_payload_write_bounded(self):
        """不再读 stdin 的子进程 + 数 MB 参数：写线程被管道卡住，看门狗按 write_timeout
        判死并杀进程解卡；client 标死后一切调用立刻失败，close() 干净。"""
        c = self.client("wedged.py", timeout=30, write_timeout=3)
        c.start()
        process = c.proc
        started = time.monotonic()
        result = c.call_tool("anything", {"value": "x" * 3_000_000})
        self.assertTrue(result.is_error)
        self.assertTrue(getattr(result, "transport_error", False))
        self.assertLess(time.monotonic() - started, 15)
        started = time.monotonic()
        again = c.call_tool("anything", {})        # 已死 → 秒拒
        self.assertTrue(again.is_error)
        self.assertLess(time.monotonic() - started, 1)
        c.close()
        c.close()                                  # 幂等
        deadline = time.monotonic() + 3
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertIsNotNone(process.poll())

    def test_mute_initialize_times_out_and_kills(self):
        """initialize 永不应答：init_timeout 处失败，close 后无存活子进程。"""
        c = self.client("mute.py", timeout=30, init_timeout=2)
        procs = []
        original_close = c.close

        def spy_close():
            if c.proc is not None:
                procs.append(c.proc)
            original_close()

        c.close = spy_close
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, "超时"):
            c.start()
        self.assertLess(time.monotonic() - started, 6)
        self.assertIsNone(c.proc)
        self.assertEqual(len(procs), 1)
        deadline = time.monotonic() + 3
        while procs[0].poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertIsNotNone(procs[0].poll())

    def test_slow_timeout_sends_cancellation_and_drops_stale_response(self):
        """按请求超时后发 notifications/cancelled；迟到的陈旧响应被丢弃，后续调用不受污染。"""
        log = self.tmp / "slow.log"
        c = self.client("slow.py", "--sleep", "2", "--log", str(log), timeout=10)
        c.start()
        started = time.monotonic()
        result = c.call_tool("slow_echo", {}, timeout=1)   # 请求 id=2（initialize=1）
        self.assertTrue(result.is_error)
        self.assertIn("超时", result.content)
        self.assertLess(time.monotonic() - started, 4)
        # 同一 client 的下一个调用：先收到 id=2 的陈旧响应（丢弃），再收到自己的
        again = c.call_tool("echo", {"value": 9})
        self.assertFalse(again.is_error)
        self.assertIn('"value": 9', again.content)
        text = log.read_text(encoding="utf-8")
        self.assertIn("notifications/cancelled", text)
        self.assertIn('"requestId": 2', text)


class ToolHubResilienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="prism-hubres-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def server(self, name, script, *argv):
        return {"name": name, "command": sys.executable,
                "args": [str(FAKES / script), *argv]}

    def hub(self, servers, **kw):
        h = ToolHub(servers, **kw)
        self.addCleanup(h.close)
        return h

    @staticmethod
    def call(hub, name, arguments=None):
        return hub.execute(ToolCall(id="t1", name=name, arguments=arguments or {}))

    @staticmethod
    def calls_logged(log):
        return sum(1 for line in log.read_text(encoding="utf-8").splitlines()
                   if '"tools/call"' in line)

    def test_start_degrades_on_partial_failure(self):
        """一个 server 哑掉只降级：failed 记一笔，其余 server 的工具照常可用。"""
        log = self.tmp / "good.log"
        h = self.hub([self.server("bad", "mute.py"),
                      self.server("good", "normal.py", "--log", str(log))],
                     tool_timeout=2)
        h.start()
        self.assertEqual([name for name, _ in h.failed], ["bad"])
        self.assertIn("echo", [s.name for s in h.specs()])
        result = self.call(h, "echo", {"value": 7})
        self.assertFalse(result.is_error)
        self.assertIn('"value": 7', result.content)

    def test_start_raises_when_all_fail(self):
        h = self.hub([self.server("bad", "mute.py")], tool_timeout=2)
        with self.assertRaisesRegex(RuntimeError, "所有 MCP server"):
            h.start()

    def test_per_tool_timeout_override_shortens(self):
        """per_tool_timeouts 覆盖默认超时；只影响该工具，后续调用照常。"""
        h = self.hub([self.server("slowsrv", "slow.py", "--sleep", "5")],
                     tool_timeout=30, per_tool_timeouts={"slow_echo": 1})
        h.start()
        started = time.monotonic()
        result = self.call(h, "slow_echo")
        self.assertTrue(result.is_error)
        self.assertIn("超时", result.content)
        self.assertLess(time.monotonic() - started, 4)     # 1s 覆盖生效，而非 30s 默认
        again = self.call(h, "echo", {"value": 3})         # 重启后的 server 秒回
        self.assertFalse(again.is_error)
        self.assertIn('"value": 3', again.content)

    def test_restart_once_then_read_retry_succeeds(self):
        """首调致死的 server：hub 重启一次并（只读策略放行时）重放，调用最终成功。"""
        marker, log = self.tmp / "marker", self.tmp / "dies.log"
        h = self.hub([self.server("fragile", "dies_once.py",
                                  "--marker", str(marker), "--log", str(log))],
                     tool_timeout=5, retryable=lambda name: True)
        h.start()
        result = self.call(h, "echo", {"value": 1})
        self.assertFalse(result.is_error)
        self.assertIn('"value": 1', result.content)
        self.assertEqual(self.calls_logged(log), 2)        # 原始一次 + 重放一次
        self.assertEqual(h.circuit_open, [])

    def test_write_tool_never_retried_but_restart_serves_later_calls(self):
        """retryable=None：绝不重放（写类工具重放 = 重复副作用），但重启后的 server 服务后续调用。"""
        marker, log = self.tmp / "marker", self.tmp / "dies.log"
        h = self.hub([self.server("fragile", "dies_once.py",
                                  "--marker", str(marker), "--log", str(log))],
                     tool_timeout=5, retryable=None)
        h.start()
        result = self.call(h, "echo", {"value": 1})
        self.assertTrue(result.is_error)                   # 不重放 → 原始失败原样返回
        self.assertEqual(self.calls_logged(log), 1)        # 只有那一次 tools/call
        again = self.call(h, "echo", {"value": 2})         # 重启后的 server 正常接客
        self.assertFalse(again.is_error)
        self.assertIn('"value": 2', again.content)
        self.assertEqual(self.calls_logged(log), 2)

    def test_circuit_opens_after_second_death(self):
        """每 hub 生命周期只重启一次：第二次死亡即熔断，之后的调用秒拒。"""
        h = self.hub([self.server("deadsrv", "dead.py", "--after", "call")],
                     tool_timeout=3, retryable=None)
        h.start()
        self.assertEqual(h.failed, [])
        first = self.call(h, "boom")                       # 第一次死 → 用掉唯一重启
        self.assertTrue(first.is_error)
        self.assertEqual(h.circuit_open, [])
        second = self.call(h, "boom")                      # 再死 → 熔断
        self.assertTrue(second.is_error)
        self.assertEqual(h.circuit_open, ["deadsrv"])
        started = time.monotonic()
        third = self.call(h, "boom")
        self.assertTrue(third.is_error)
        self.assertIn("熔断", third.content)
        self.assertLess(time.monotonic() - started, 0.5)


if __name__ == "__main__":
    unittest.main()
