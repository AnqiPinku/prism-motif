"""Phase 2.4 稳定性 Soak（ROADMAP 2.4）：对真实 Gateway 进程连续施压，全程离线。

跑法：仓库根目录 python tests/soak_test.py
门禁内容（一次运行全覆盖）：
- 20 个完整聊天回合（流式 / 工具调用 / 一次 503 重试恢复 / 慢速流）；
- 中途取消 5 次（慢速流里断开 SSE socket）+ 1 次同线程抢占；
- Provider 失败 5 次（3 次持续 503 + 2 次流式空断连），错误必须浮出且回合正常收尾；
- MCP 超时 3 次（hang 工具 + 3s 工具超时，走权限确认流）；
- 每个操作后 /api/state 必须秒回（历史上连接泄漏 6 回合后全站卡死，这里是回归闸）；
- 无遗留 MCP 子进程、线程存档始终可解析、TCP 连接不累积、Gateway 内存无线性增长。

不进 unittest discover（文件名刻意不匹配 test*.py），由 CI 显式一步执行。
"""

from __future__ import annotations

import ctypes
import http.client
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fixtures.fake_provider import FakeProvider  # noqa: E402

TOKEN = "soak-session-token"
TURN_LIMIT_S = 30          # 单回合硬上限，防挂死
RSS_GROWTH_LIMIT = 25 * 1024 * 1024


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def rss_bytes(pid: int) -> int:
    class PMC(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return 0
    counters = PMC()
    counters.cb = ctypes.sizeof(counters)
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    ctypes.windll.kernel32.CloseHandle(handle)
    return counters.WorkingSetSize if ok else 0


def established_count(port: int) -> int:
    out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True)
    needle = ":%d" % port
    return sum(1 for line in out.stdout.splitlines()
               if needle in line and "ESTABLISHED" in line)


def fake_mcp_count() -> int:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object { $_.CommandLine -like '*fake_mcp_server.py*' }).Count"],
        capture_output=True, text=True)
    try:
        return int(out.stdout.strip() or "0")
    except ValueError:
        return -1


class Soak:
    def __init__(self):
        self.data_root = Path(tempfile.mkdtemp(prefix="prism-soak-"))
        self.port = free_port()
        self.provider = None
        self.gateway = None
        self.tid = "soak-main"
        self.rss_samples = []
        self.failures = []

    # ---- 环境 ----

    def write_config(self, model: str):
        cfg = self.data_root / "config"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "providers.json").write_text(json.dumps({
            "default": "fake",
            "providers": {"fake": {"base_url": self.provider.base_url, "model": model,
                                   "api_key_env": "NONE", "window_tokens": 16000}},
        }), encoding="utf-8")

    def setup(self):
        cfg = self.data_root / "config"
        cfg.mkdir(parents=True, exist_ok=True)
        (self.data_root / "data" / "skills").mkdir(parents=True, exist_ok=True)
        self.write_config("final")
        (cfg / "settings.json").write_text(json.dumps({
            "max_steps": 6, "request_timeout_s": 20, "tool_timeout_s": 3,
            "retry": {"max_attempts": 3, "base_delay_s": 0.05},
            "base_prompt": "soak", "workspace": "default",
            "context": {"enabled": True, "window_tokens": 128000, "compact_at": 0.6,
                        "keep_recent_turns": 4, "elide_tool_results": True,
                        "elide_over_chars": 2000, "summarize": False},
        }), encoding="utf-8")
        (cfg / "modes.json").write_text(json.dumps({"current": "", "modes": {}}),
                                        encoding="utf-8")
        (cfg / "mcp_servers.json").write_text(json.dumps({"servers": [{
            "name": "fake", "enabled": True, "command": sys.executable,
            "args": [str(ROOT / "tests" / "fixtures" / "fake_mcp_server.py")],
        }]}), encoding="utf-8")

        env = dict(**__import__("os").environ)
        env.update({"PRISM_DATA_DIR": str(self.data_root), "PRISM_PORT": str(self.port),
                    "PRISM_SESSION_TOKEN": TOKEN, "PRISM_INSTANCE_ID": "soak"})
        self.gateway_log = open(self.data_root / "gateway.log", "wb")
        self.gateway = subprocess.Popen(
            [sys.executable, str(ROOT / "gateway" / "server.py")],
            env=env, stdout=self.gateway_log, stderr=subprocess.STDOUT, cwd=str(ROOT))
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                status, _ = self.api("GET", "/health")
                if status == 200:
                    return
            except OSError:
                pass
            time.sleep(0.25)
        raise RuntimeError("gateway did not become healthy in 20s")

    # ---- HTTP ----

    def api(self, method: str, path: str, payload=None, timeout=5):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            body = json.dumps(payload) if payload is not None else None
            conn.request(method, path, body=body,
                         headers={"X-Prism-Session": TOKEN, "Content-Type": "application/json"})
            resp = conn.getresponse()
            return resp.status, json.loads(resp.read() or b"{}")
        finally:
            conn.close()

    def chat(self, model: str, goal: str, mode: str = "full", tid: str = None):
        """驱动一个聊天回合。mode: full=读到 EOF；cancel=首个 delta 后断开 socket。
        返回收到的事件列表。"""
        self.write_config(model)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=TURN_LIMIT_S)
        conn.request("POST", "/api/chat",
                     body=json.dumps({"goal": goal, "thread_id": tid or self.tid}),
                     headers={"X-Prism-Session": TOKEN, "Content-Type": "application/json"})
        resp = conn.getresponse()
        assert resp.status == 200, "chat http %d" % resp.status
        events, block, deadline = [], [], time.time() + TURN_LIMIT_S
        while time.time() < deadline:
            line = resp.readline()
            if not line:
                break
            line = line.decode("utf-8").rstrip("\n").rstrip("\r")
            if line.startswith("data: "):
                block.append(line[6:])
                continue
            if line == "" and block:
                event = json.loads("\n".join(block))
                block = []
                events.append(event)
                if event.get("type") == "permission_request":
                    status, _ = self.api("POST", "/api/permission",
                                         {"id": event["id"], "allow": True})
                    assert status == 200, "permission answer http %d" % status
                if mode == "cancel" and event.get("type") == "delta":
                    conn.close()
                    return events
        conn.close()
        return events

    # ---- 断言 ----

    def check(self, condition: bool, label: str):
        mark = "PASS" if condition else "FAIL"
        print("  [%s] %s" % (mark, label))
        if not condition:
            self.failures.append(label)

    def between_ops(self, label: str):
        """每个操作后的共性验收：gateway 秒回、线程档案可解析、连接不累积、采内存。"""
        t0 = time.time()
        status, _ = self.api("GET", "/api/state")
        self.check(status == 200 and time.time() - t0 < 2.0,
                   "%s 后 /api/state 秒回" % label)
        thread_file = self.data_root / "data" / "threads" / ("%s.json" % self.tid)
        if thread_file.exists():
            try:
                json.loads(thread_file.read_text(encoding="utf-8"))
            except ValueError:
                self.check(False, "%s 后线程存档损坏" % label)
        conns = established_count(self.port)
        self.check(conns <= 3, "%s 后 TCP 连接不累积（当前 %d）" % (label, conns))
        self.rss_samples.append(rss_bytes(self.gateway.pid))

    @staticmethod
    def types(events):
        return [event.get("type") for event in events]

    def seq_ok(self, events):
        seqs = [event["seq"] for event in events if "seq" in event]
        return seqs == sorted(seqs) and len(set(seqs)) == len(seqs)

    # ---- 操作 ----

    def op_turn(self, index: int, model: str):
        events = self.chat(model, "soak 回合 %d" % index)
        kinds = self.types(events)
        ok = kinds and kinds[-1] == "done" and "error" not in kinds and self.seq_ok(events)
        self.check(ok, "回合 %d（%s）完整收尾" % (index, model))
        if model == "tool_once":
            self.check("tool_result" in kinds, "回合 %d 工具调用有结果" % index)
        return ok

    def op_cancel(self, index: int):
        events = self.chat("slow", "soak 取消 %d" % index, mode="cancel")
        self.check(any(event.get("type") == "delta" for event in events),
                   "取消 %d 在首个 delta 后断开" % index)
        recovered = self.op_turn(index, "final")
        self.check(recovered, "取消 %d 后同线程立即恢复" % index)

    def op_provider_failure(self, index: int, model: str):
        events = self.chat(model, "soak 故障 %d" % index)
        kinds = self.types(events)
        self.check("error" in kinds and kinds[-1] == "done",
                   "Provider 故障 %d（%s）错误浮出且回合收尾" % (index, model))

    def op_mcp_timeout(self, index: int):
        events = self.chat("tool_hang_once", "soak 超时 %d" % index)
        kinds = self.types(events)
        tool_error = any(event.get("type") == "tool_result" and event.get("is_error")
                         for event in events)
        self.check("permission_request" in kinds, "MCP 超时 %d 走了权限确认" % index)
        self.check(tool_error and kinds[-1] == "done",
                   "MCP 超时 %d 变成工具错误且回合收尾" % index)

    def op_preempt(self):
        """同线程抢占：慢回合未读完时直接发起新回合，旧回合必须让位。"""
        self.write_config("slow")
        first = http.client.HTTPConnection("127.0.0.1", self.port, timeout=TURN_LIMIT_S)
        first.request("POST", "/api/chat",
                      body=json.dumps({"goal": "被抢占", "thread_id": self.tid}),
                      headers={"X-Prism-Session": TOKEN, "Content-Type": "application/json"})
        first_resp = first.getresponse()
        first_resp.readline()          # 等到流真正开始
        ok = self.op_turn(0, "final")  # 同 tid 立即开新回合 → 触发 RUNNING 闸
        self.check(ok, "同线程抢占后新回合完整收尾")
        try:
            first_resp.read()          # 旧回合的流应被服务端终结（EOF）
        except OSError:
            pass
        first.close()

    def wait_mcp_zero(self, label: str, timeout=15):
        deadline = time.time() + timeout
        count = -1
        while time.time() < deadline:
            count = fake_mcp_count()
            if count == 0:
                break
            time.sleep(1)
        self.check(count == 0, "%s：无遗留 MCP 子进程（当前 %d）" % (label, count))

    # ---- 主流程 ----

    def run(self):
        print("== Soak 开始：gateway pid=%d port=%d data=%s" %
              (self.gateway.pid, self.port, self.data_root))
        completed = 0
        # 20 个完整回合的模型剧本：流式为主，穿插工具、慢速与一次 503 重试恢复
        plan = ["final", "final", "tool_once", "final", "retry",
                "final", "slow", "tool_once", "final", "final",
                "final", "tool_once", "final", "slow", "final",
                "final", "final", "final", "final", "final"]
        cancel_after = {3, 7, 11, 15, 18}          # 这些完整回合之后插一次取消
        fail_after = {5: "down", 9: "down", 12: "disconnect", 16: "down", 19: "disconnect"}
        timeout_after = {6, 13, 17}

        for index, model in enumerate(plan, start=1):
            if self.op_turn(index, model):
                completed += 1
            self.between_ops("回合 %d" % index)
            if index in cancel_after:
                self.op_cancel(index)
                self.between_ops("取消 %d" % index)
                self.wait_mcp_zero("取消 %d" % index)
                completed += 1                      # 取消后的恢复回合也是完整回合
            if index in fail_after:
                self.op_provider_failure(index, fail_after[index])
                self.between_ops("故障 %d" % index)
            if index in timeout_after:
                self.op_mcp_timeout(index)
                self.between_ops("超时 %d" % index)
        self.op_preempt()
        self.between_ops("抢占")

        # ---- 终局验收 ----
        print("== 终局验收")
        self.check(completed >= 20, "完整回合数 %d ≥ 20" % completed)
        self.wait_mcp_zero("终局")
        thread_file = self.data_root / "data" / "threads" / ("%s.json" % self.tid)
        data = json.loads(thread_file.read_text(encoding="utf-8"))
        message_count = len(data.get("messages") or data.get("convo") or [])
        self.check(message_count >= 40, "线程存档完整（%d 条消息）" % message_count)
        mid = self.rss_samples[8:13]
        tail = self.rss_samples[-5:]
        growth = sum(tail) / len(tail) - sum(mid) / len(mid)
        self.check(growth < RSS_GROWTH_LIMIT,
                   "内存无线性增长（中段→尾段 %+.1f MB）" % (growth / 1048576))
        print("   RSS 曲线(MB): %s" %
              ", ".join("%.0f" % (x / 1048576) for x in self.rss_samples))

    def teardown(self):
        if self.gateway and self.gateway.poll() is None:
            self.gateway.terminate()
            try:
                self.gateway.wait(timeout=10)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/PID", str(self.gateway.pid), "/T", "/F"],
                               capture_output=True)
        if getattr(self, "gateway_log", None):
            self.gateway_log.close()
        deadline = time.time() + 10
        while time.time() < deadline and fake_mcp_count() > 0:
            time.sleep(1)
        shutil.rmtree(self.data_root, ignore_errors=True)


def main() -> int:
    soak = Soak()
    with FakeProvider() as provider:
        soak.provider = provider
        try:
            soak.setup()
            started = time.time()
            soak.run()
            print("== 用时 %.1fs" % (time.time() - started))
        finally:
            soak.teardown()
    if soak.failures:
        print("SOAK_FAIL %d 项未过：" % len(soak.failures))
        for item in soak.failures:
            print("  ✗ %s" % item)
        return 1
    print("SOAK_PASS 全部门禁通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
