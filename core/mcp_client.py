"""手写 MCP stdio 客户端：启动一个 MCP server 子进程，做握手并调用其工具。
与我们写的 reaper-mcp 服务端对称，只用标准库 subprocess + json。"""
import os
import json
import subprocess

from .contracts import ToolSpec, ToolResult

PROTOCOL_VERSION = "2024-11-05"


class MCPClient:
    def __init__(self, command, args, env=None):
        self.command = command
        self.args = args or []
        self.env = env
        self.proc = None
        self._id = 0

    def start(self):
        """起子进程 + initialize 握手 + initialized 通知。"""
        full_env = dict(os.environ)
        if self.env:
            full_env.update(self.env)
        self.proc = subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            bufsize=1, env=full_env,
        )
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

    def _rpc(self, method, params):
        rid = self._next_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            line = self.proc.stdout.readline()
            if line == "":
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
