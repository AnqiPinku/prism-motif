"""Configurable local OpenAI-compatible provider used by offline tests."""

from __future__ import annotations

import json
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeProvider:
    """Run a loopback provider whose model name selects a deterministic scenario."""

    def __init__(self):
        self.requests = []
        self.counts = Counter()
        self.client_disconnects = 0
        self.httpd = None
        self.thread = None

    @property
    def base_url(self):
        return "http://127.0.0.1:%d/v1" % self.httpd.server_address[1]

    def __enter__(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                model = payload.get("model", "final")
                owner.requests.append(payload)
                owner.counts[model] += 1

                if model == "retry" and owner.counts[model] < 3:
                    return self._json({"error": {"message": "busy"}}, 503)
                if model == "down":
                    return self._json({"error": {"message": "provider down"}}, 503)
                if payload.get("stream"):
                    try:
                        return self._stream(model)
                    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                        # Soak 的 cancel 场景会在首个 delta 后主动关闭客户端连接。
                        # 这是测试输入，不应让 ThreadingHTTPServer 打印误导性的异常堆栈。
                        owner.client_disconnects += 1
                        return None
                if model == "tool":
                    return self._json({
                        "choices": [{"message": {"tool_calls": [{
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "echo", "arguments": '{"value":7}'},
                        }]}}],
                        "usage": {"prompt_tokens": 9, "completion_tokens": 2},
                    })
                content = "" if model == "empty" else "ok"
                return self._json({
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 1},
                })

            def _json(self, payload, status=200):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _stream(self, model):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()

                def event(payload):
                    self.wfile.write(("data: " + json.dumps(payload) + "\n\n").encode("utf-8"))
                    self.wfile.flush()

                if model == "disconnect":
                    return
                if model == "partial_disconnect":
                    event({"choices": [{"delta": {"content": "partial"}}]})
                    return
                if model == "stream_error" and owner.counts[model] == 1:
                    event({"error": {"type": "server_error", "message": "retry me"}})
                    return
                if model == "slow":
                    # 慢速流：给"中途取消"的测试留出断开窗口
                    for chunk in ("think", "ing ", "slow", "ly"):
                        event({"choices": [{"delta": {"content": chunk}}]})
                        time.sleep(0.25)
                    event({"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 4}})
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                    return
                if model in ("tool_once", "tool_hang_once"):
                    # 首次请求发一个工具调用，后续请求收尾成普通回答——避免 "tool"
                    # 剧本每步都要工具、把回合拖满 max_steps
                    if owner.counts[model] % 2 == 1:
                        name = "hang" if model == "tool_hang_once" else "echo"
                        arguments = "{}" if model == "tool_hang_once" else '{"value":5}'
                        event({"choices": [{"delta": {"tool_calls": [{
                            "index": 0,
                            "id": "call-%s-%d" % (model, owner.counts[model]),
                            "function": {"name": name, "arguments": arguments},
                        }]}}]})
                    else:
                        event({"choices": [{"delta": {"content": "done"}}]})
                    event({"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 2}})
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                    return
                if model == "tool":
                    event({"choices": [{"delta": {"tool_calls": [{
                        "index": 0,
                        "id": "call-stream",
                        "function": {"name": "echo", "arguments": '{"value":'},
                    }]}}]})
                    event({"choices": [{"delta": {"tool_calls": [{
                        "index": 0,
                        "function": {"arguments": "8}"},
                    }]}}]})
                elif model != "empty":
                    event({"choices": [{"delta": {"content": "hel"}}]})
                    event({"choices": [{"delta": {"content": "lo"}}]})
                event({"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 2}})
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
