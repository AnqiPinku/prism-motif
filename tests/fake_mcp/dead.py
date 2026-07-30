"""dead 假 server：正常应答握手，然后按 --after 指定时机退出。
--after init（默认）：读到 initialized 通知后立即退出（= 握手刚完就死）；
--after call：应答 tools/list，任何 tools/call 都不应答直接退出（每次 spawn 都死）。"""
import json
import sys

AFTER = sys.argv[sys.argv.index("--after") + 1] if "--after" in sys.argv else "init"


def send(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


TOOLS = [{"name": "boom", "description": "Dies on call",
          "inputSchema": {"type": "object", "properties": {"value": {}}}}]

for raw in sys.stdin:
    msg = json.loads(raw)
    method, rid = msg.get("method"), msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": msg.get("params", {}).get("protocolVersion"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-dead", "version": "1"}}})
    elif method == "notifications/initialized":
        if AFTER == "init":
            raise SystemExit(3)
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        raise SystemExit(3)
