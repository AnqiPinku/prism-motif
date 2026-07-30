"""ToolHub：连接多个 MCP server，聚合工具清单，把工具调用路由到对应 server。
core 只跟 ToolHub 打交道，完全不知道具体是 reaper 还是别的。
故障恢复：单 server 启动失败只降级（记入 failed）不拖垮整体；传输层故障每 server
一次重启机会，再故障即熔断（circuit_open）；重启后仅当注入的 retryable 判定该工具
可安全重放（只读）才重试一次——写类工具重放会重复副作用（如重复加音符）。"""
import time
import random

from .mcp_client import MCPClient
from .contracts import ToolResult


class ToolHub:
    def __init__(self, servers, tool_timeout=60, per_tool_timeouts=None, retryable=None):
        # servers: list[dict] {name, command, args, env?}
        self._servers = servers
        self._tool_timeout = tool_timeout    # 每个 MCP 调用的默认超时（秒）
        self._per_tool_timeouts = per_tool_timeouts or {}   # 工具名 -> 覆盖超时（策略由上层注入）
        self._retryable = retryable          # callable(tool_name)->bool；None = 一律不重放
        self._clients = {}                   # server 名 -> MCPClient
        self._index = {}                     # 暴露名 -> (server 名, 原始工具名)
        self._specs = []
        self._restarts = {}                  # server 名 -> 已用重启次数（每 hub 生命周期限 1 次）
        self.failed = []                     # [(server 名, 错误)] 启动失败的降级记录，供上层浮出
        self.circuit_open = []               # 已熔断的 server 名

    def start(self):
        """启动所有 MCP server 并发现工具；单个失败记入 failed 继续，全军覆没才抛。"""
        for s in self._servers:
            try:
                self._connect(s)
            except Exception as e:  # noqa: BLE001
                self.failed.append((s["name"], str(e)))
        if self._servers and not self._clients:
            errs = "；".join("%s: %s" % f for f in self.failed)
            self.close()
            raise RuntimeError("所有 MCP server 均启动失败：%s" % errs)

    def _connect(self, s):
        client = MCPClient(s["command"], s.get("args", []), s.get("env"),
                           timeout=self._tool_timeout)
        client.start()
        try:
            specs = client.list_tools()
        except Exception:
            client.close()
            raise
        self._clients[s["name"]] = client
        for spec in specs:
            original = spec.name
            exposed = original
            if exposed in self._index:           # 重名 → 加 server 前缀消歧
                exposed = "%s__%s" % (s["name"], original)
                spec.name = exposed
            self._index[exposed] = (s["name"], original)
            self._specs.append(spec)

    def _restart(self, name):
        """换一个全新 client（同配置），并只刷新该 server 的 spec（工具名沿用原映射）。"""
        cfg = next(s for s in self._servers if s["name"] == name)
        old = self._clients.get(name)
        if old:
            old.close()
        client = MCPClient(cfg["command"], cfg.get("args", []), cfg.get("env"),
                           timeout=self._tool_timeout)
        client.start()
        try:
            fresh = {sp.name: sp for sp in client.list_tools()}
        except Exception:
            client.close()
            raise
        self._clients[name] = client
        for i, sp in enumerate(self._specs):
            entry = self._index.get(sp.name)
            if entry and entry[0] == name and entry[1] in fresh:
                new_spec = fresh[entry[1]]
                new_spec.name = sp.name
                self._specs[i] = new_spec

    def specs(self):
        return list(self._specs)

    def execute(self, call):
        entry = self._index.get(call.name)
        if not entry:
            return ToolResult(id=call.id, content="未知工具: %s" % call.name, is_error=True)
        server, original = entry
        res = self._resilient_call(server, original, call.name, call.arguments)
        res.id = call.id
        return res

    def _resilient_call(self, server, original, exposed, arguments):
        """一次调用；传输层故障（超时/进程死）时用掉该 server 的一次性重启，只读工具再重放一次。"""
        if server in self.circuit_open:
            return ToolResult(id=exposed, content="服务已熔断: %s" % server, is_error=True)
        timeout = self._per_tool_timeouts.get(
            exposed, self._per_tool_timeouts.get(original))
        res = self._clients[server].call_tool(original, arguments, timeout=timeout)
        if not getattr(res, "transport_error", False):
            return res                       # 工具自身报错不是传输故障，原样返回
        if self._restarts.get(server, 0) >= 1:
            self.circuit_open.append(server)   # 重启机会已用完 → 熔断，后续调用秒拒
            return res
        self._restarts[server] = 1
        try:
            self._restart(server)
        except Exception as e:  # noqa: BLE001
            self.circuit_open.append(server)
            return ToolResult(id=exposed, is_error=True,
                              content="服务已熔断: %s（重启失败: %s）" % (server, e))
        if self._retryable and self._retryable(exposed):
            time.sleep(0.5 + random.random())  # 抖动 0.5~1.5s，避开 server 冷启动竞态
            return self._clients[server].call_tool(original, arguments, timeout=timeout)
        return res

    def close(self):
        for c in self._clients.values():
            c.close()
        self._clients.clear()
        self._index.clear()
        self._specs.clear()
        self._restarts.clear()
        # failed / circuit_open 保留不清：回合"验尸"信息随网关终帧上报，而 close 总在读取前发生
