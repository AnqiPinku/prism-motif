"""手写 MCP stdio 客户端：启动一个 MCP server 子进程，做握手并调用其工具。
与我们写的 reaper-mcp 服务端对称，只用标准库 subprocess + json。"""
import os
import json
import time
import queue
import threading
import subprocess

from .contracts import ToolSpec, ToolResult
from . import paths
from . import secrets_store

PROTOCOL_VERSION = "2024-11-05"


class MCPClient:
    def __init__(self, command, args, env=None, timeout=60):
        self.command = command
        self.args = args or []
        self.env = env
        self.timeout = float(timeout) if timeout else 60.0   # 单次调用超时（防 MCP 进程挂死）
        self.proc = None
        self._id = 0
        self._q = None        # 读线程把 stdout 行塞进这个队列
        self._reader = None

    def start(self):
        """起子进程 + initialize 握手 + initialized 通知。"""
        full_env = dict(os.environ)
        if self.env:
            full_env.update(self.env)
        # 声明了 GEMINI_* 中转设置的 server（= 感知 sidecar）→ 从钥匙链补 API key。
        # env 已设则不覆盖（环境变量优先），密钥只进这一个子进程、绝不落任何文件。
        if (self.env and any(k.startswith("GEMINI_") for k in self.env)
                and not full_env.get("GEMINI_API_KEY")):
            k = secrets_store.get_secret("GEMINI_API_KEY")
            if k:
                full_env["GEMINI_API_KEY"] = k
        command = paths.expand(self.command)          # 展开 ${PRISM_HOME} 令牌 → 绝对路径
        args = [paths.expand(a) for a in self.args]
        for a in args:   # 缺脚本会因 stderr=DEVNULL 静默失败 → 提前报清楚（安装不完整/兄弟仓缺失）
            if a.endswith(".py") and not os.path.isfile(a):
                raise RuntimeError(
                    "MCP server 脚本不存在：%s（检查 ${PRISM_HOME} 或安装完整性）" % a)
        self.proc = subprocess.Popen(
            [command, *args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            bufsize=1, env=full_env,
        )
        # 后台读线程：把 stdout 逐行塞进队列，让 _rpc 能带超时地等响应（Windows 管道无法 select）。
        self._q = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._rpc("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "prism-core", "version": "0.1"},
        })
        self._notify("notifications/initialized", {})

    def list_tools(self):
        """tools/list → list[ToolSpec]。"""
        result = self._rpc("tools/list", {})
        specs = []
        for t in result.get("tools", []):
            specs.append(ToolSpec(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("inputSchema") or {"type": "object", "properties": {}},
            ))
        return specs

    def call_tool(self, name, arguments):
        """tools/call → ToolResult。"""
        try:
            result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        except Exception as e:  # noqa: BLE001
            return ToolResult(id=name, content="工具调用失败: %s" % (e,), is_error=True)
        blocks = result.get("content", [])
        text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return ToolResult(id=name, content=text, is_error=bool(result.get("isError")))

    def close(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:  # noqa: BLE001
                pass

    # ---------- internal ----------
    def _next_id(self):
        self._id += 1
        return self._id

    def _send(self, obj):
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _notify(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _read_loop(self):
        """后台把子进程 stdout 逐行塞进队列；流关闭（进程退出）后塞一个 "" 哨兵。"""
        try:
            for line in self.proc.stdout:
                self._q.put(line)
        except Exception:  # noqa: BLE001
            pass
        self._q.put("")

    def _rpc(self, method, params):
        rid = self._next_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("MCP 调用超时（method=%s，%.0fs）" % (method, self.timeout))
            try:
                line = self._q.get(timeout=remaining)
            except queue.Empty:
                raise RuntimeError("MCP 调用超时（method=%s，%.0fs）" % (method, self.timeout))
            if line == "":                       # 哨兵：子进程已退出
                raise RuntimeError("MCP server 已退出（method=%s）" % method)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == rid:
                if "error" in msg:
                    raise RuntimeError(str(msg["error"]))
                return msg.get("result", {})
            # 其它 id / 通知 → 忽略，继续读
