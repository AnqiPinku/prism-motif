"""Gateway 终帧监督回归：卡死回合的取消/断线/硬超时都必须准时收口，且整流恰好一个 done。

Batch 2 背景：run_turn 曾在请求线程上直跑，工具卡死时终帧代码永远走不到——取消、
断线、同线程抢占全部失效。现在 worker 线程跑回合，请求线程监督并独占 done。
"""

import http.client
import json
import threading
import time
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


class GatewayTerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_token = auth.SESSION_TOKEN
        cls.original_instance = auth.INSTANCE_ID
        cls.original_origins = auth.ALLOWED_ORIGINS
        auth.SESSION_TOKEN = "terminal-test-token"
        auth.INSTANCE_ID = "terminal-test-instance"
        auth.ALLOWED_ORIGINS = {"http://tauri.localhost"}
        # 全部超时调小：宽限 1s、心跳 0.3s，套件保持秒级
        cls.patchers = [patch.object(server, "KILL_GRACE_S", 1.0),
                        patch.object(server, "HEARTBEAT_IDLE_S", 0.3),
                        patch.object(server, "TURN_DEADLINE_S", 30.0)]
        for p in cls.patchers:
            p.start()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        for p in cls.patchers:
            p.stop()
        auth.SESSION_TOKEN = cls.original_token
        auth.INSTANCE_ID = cls.original_instance
        auth.ALLOWED_ORIGINS = cls.original_origins

    HEADERS = {"Origin": "http://tauri.localhost",
               "X-Prism-Session": "terminal-test-token",
               "Content-Type": "application/json"}

    def open_stream(self, thread_id, goal="test"):
        """发起 /api/chat 并等到响应头；正文留给调用方流式消费。"""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        conn.request("POST", "/api/chat",
                     body=json.dumps({"goal": goal, "thread_id": thread_id}),
                     headers=self.HEADERS)
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        return conn, resp

    def post_json(self, path, payload):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", path, body=json.dumps(payload), headers=self.HEADERS)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, json.loads(body)

    def read_events(self, resp):
        """读到 EOF（服务端发完 done 会关连接）并解析整流。"""
        return parse_sse(resp.read())

    def wait_running(self, thread_id, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with server.RUNNING_LOCK:
                entry = server.RUNNING.get(thread_id)
            if entry is not None:
                return entry
            time.sleep(0.05)
        self.fail("回合 %s 未注册进 RUNNING" % thread_id)

    def wait_gone(self, thread_id, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with server.RUNNING_LOCK:
                if thread_id not in server.RUNNING:
                    return
            time.sleep(0.1)
        self.fail("回合 %s 未从 RUNNING 清理" % thread_id)

    def dones(self, events):
        return [e for e in events if e.get("type") == "done"]

    def test_cancel_kills_hung_turn_and_sends_done(self):
        """(a) 永久卡死的回合 + /api/chat/cancel → 数秒内收到 cancelled done 并清场。"""
        release = threading.Event()
        self.addCleanup(release.set)

        def hung(*_a, **_k):
            release.wait(30)          # 无视取消信号，模拟卡死在不可中断调用里

        tid = "term-cancel"
        with patch("gateway.server.runner.run_turn", side_effect=hung):
            conn, resp = self.open_stream(tid)
            entry = self.wait_running(tid)
            started = time.monotonic()
            status, payload = self.post_json("/api/chat/cancel", {"thread_id": tid})
            self.assertEqual(status, 200)
            self.assertTrue(payload["cancel_requested"])
            events = self.read_events(resp)
            conn.close()
        self.assertLess(time.monotonic() - started, 5)
        done = self.dones(events)
        self.assertEqual(len(done), 1)
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(done[0]["cancelled"])
        self.assertEqual(done[0]["reason"], "cancelled")
        self.assertTrue(entry["finished"].is_set())
        self.wait_gone(tid, timeout=2)

    def test_toolhub_close_lever_unblocks_worker(self):
        """(b) 取消时监督者必须拉 toolhub.close() 杆，卡在工具里的 worker 立即解卡。"""
        class Hub:
            def __init__(self):
                self.closed = threading.Event()
                self.failed = [("srv", "启动失败")]
                self.circuit_open = ["srv"]

            def close(self):
                self.closed.set()

        hub = Hub()

        def stub(_goal, on_event=None, on_toolhub=None, **_k):
            on_toolhub(hub)
            hub.closed.wait(30)                          # 卡死，直到监督者拉杆
            on_event({"type": "delta", "text": "x"})     # 取消后必抛 TurnCancelled

        tid = "term-lever"
        with patch("gateway.server.runner.run_turn", side_effect=stub):
            conn, resp = self.open_stream(tid)
            self.wait_running(tid)
            self.post_json("/api/chat/cancel", {"thread_id": tid})
            events = self.read_events(resp)
            conn.close()
        self.assertTrue(hub.closed.is_set(), "监督者未调用 toolhub.close()")
        done = self.dones(events)
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["reason"], "cancelled")
        self.assertEqual(done[0]["degraded"], ["srv"])       # 验尸信息随终帧上报
        self.assertEqual(done[0]["circuit_open"], ["srv"])
        self.wait_gone(tid, timeout=2)

    def test_deadline_terminates_hung_turn(self):
        """(c) 整轮硬超时：卡死回合到点收到 reason=deadline 的 done。"""
        release = threading.Event()
        self.addCleanup(release.set)
        tid = "term-deadline"
        with patch.object(server, "TURN_DEADLINE_S", 0.6), \
                patch("gateway.server.runner.run_turn",
                      side_effect=lambda *_a, **_k: release.wait(30)):
            started = time.monotonic()
            conn, resp = self.open_stream(tid)
            events = self.read_events(resp)
            conn.close()
        self.assertLess(time.monotonic() - started, 8)
        done = self.dones(events)
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["reason"], "deadline")
        self.assertFalse(done[0]["cancelled"])
        self.wait_gone(tid, timeout=2)

    def test_client_disconnect_cleans_running(self):
        """(d) 客户端中途断开 SSE：心跳探测到断线，数秒内 RUNNING 清理、finished 置位。"""
        release = threading.Event()
        self.addCleanup(release.set)
        tid = "term-disconnect"
        with patch("gateway.server.runner.run_turn",
                   side_effect=lambda *_a, **_k: release.wait(30)):
            conn, resp = self.open_stream(tid)
            entry = self.wait_running(tid)
            resp.close()                       # 模拟前端刷新/关窗：response + socket 一起关
            conn.close()                       # 只关 conn 不够——response 还握着 socket 引用
            self.assertTrue(entry["finished"].wait(8), "断线后 finished 未置位")
            self.wait_gone(tid, timeout=2)

    def test_worker_error_emits_error_then_single_done(self):
        """(e) worker 抛异常：error 事件浮出，整流恰好一个 done（reason=error）。"""
        def stub(_goal, on_event=None, **_k):
            on_event({"type": "turn_start", "provider": "fake"})
            on_event({"type": "delta", "text": "hi", "step": 1})
            raise RuntimeError("boom")

        tid = "term-error"
        with patch("gateway.server.runner.run_turn", side_effect=stub):
            conn, resp = self.open_stream(tid)
            events = self.read_events(resp)
            conn.close()
        types = [e["type"] for e in events]
        self.assertIn("error", types)
        self.assertTrue(any("boom" in e.get("message", "") for e in events))
        done = self.dones(events)
        self.assertEqual(len(done), 1)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(done[0]["reason"], "error")
        self.assertFalse(done[0]["cancelled"])
        self.wait_gone(tid, timeout=2)

    def test_preempt_hung_turn_starts_quickly(self):
        """(f) 卡死回合被同线程新请求抢占：新回合数秒内起流（不再 30s 干等），各自一个 done。"""
        release = threading.Event()
        self.addCleanup(release.set)

        def dispatch(goal, on_event=None, **_k):
            if goal == "hang":
                release.wait(30)
            else:
                on_event({"type": "delta", "text": "B", "step": 1})

        tid = "term-preempt"
        with patch("gateway.server.runner.run_turn", side_effect=dispatch):
            conn_a, resp_a = self.open_stream(tid, goal="hang")
            self.wait_running(tid)
            started = time.monotonic()
            conn_b, resp_b = self.open_stream(tid, goal="fast")
            events_b = self.read_events(resp_b)
            elapsed = time.monotonic() - started
            events_a = self.read_events(resp_a)   # 旧流被服务端终结（done + EOF）
            conn_b.close()
            conn_a.close()
        self.assertLess(elapsed, 6, "抢占后新回合 %.1fs 才收尾，旧闸门还在干等" % elapsed)
        done_b = self.dones(events_b)
        self.assertEqual(len(done_b), 1)
        self.assertEqual(events_b[-1]["type"], "done")
        self.assertEqual(done_b[0]["reason"], "ok")
        done_a = self.dones(events_a)
        self.assertEqual(len(done_a), 1)
        self.assertTrue(done_a[0]["cancelled"])
        self.wait_gone(tid, timeout=2)


if __name__ == "__main__":
    unittest.main()
