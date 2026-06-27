"""ToolHub：连接多个 MCP server，聚合工具清单，把工具调用路由到对应 server。
core 只跟 ToolHub 打交道，完全不知道具体是 reaper 还是别的。"""
from .mcp_client import MCPClient
from .contracts import ToolResult


class ToolHub:
    def __init__(self, servers, tool_timeout=60):
        # servers: list[dict] {name, command, args, env?}
        self._servers = servers
        self._tool_timeout = tool_timeout    # 每个 MCP 调用的超时（秒）
        self._clients = []
        self._index = {}    # 暴露名 -> (client, 原始工具名)
        self._specs = []

    def start(self):
        """启动所有 MCP server 并发现工具。"""
        for s in self._servers:
            client = MCPClient(s["command"], s.get("args", []), s.get("env"),
                               timeout=self._tool_timeout)
            client.start()
            self._clients.append(client)
            for spec in client.list_tools():
                original = spec.name
                exposed = original
                if exposed in self._index:           # 重名 → 加 server 前缀消歧
                    exposed = "%s__%s" % (s["name"], original)
                    spec.name = exposed
                self._index[exposed] = (client, original)
                self._specs.append(spec)

    def specs(self):
        return list(self._specs)

    def execute(self, call):
        entry = self._index.get(call.name)
        if not entry:
            return ToolResult(id=call.id, content="未知工具: %s" % call.name, is_error=True)
        client, original = entry
        res = client.call_tool(original, call.arguments)
        res.id = call.id
        return res

    def close(self):
        for c in self._clients:
            c.close()
