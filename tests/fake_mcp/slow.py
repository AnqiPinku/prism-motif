"""slow 假 server：slow_echo 工具先睡 --sleep 秒再应答（制造超时+迟到响应）；echo 秒回。
收到的每一行（含超时后客户端补发的 notifications/cancelled）记进 --log 文件。"""
import json
import sys
import time

SLEEP = float(sys.argv[sys.argv.index("--sleep") + 1]) if "--sleep" in sys.argv else 2.0
LOG = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else None


def log(raw):
    if LOG:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(raw if raw.endswith("\n") else raw + "\n")


def send(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


TOOLS = [
    {"name": "slow_echo", "description": "Echo after a long sleep",
     "inputSchema": {"type": "object", "properties": {"value": {}}}},
    {"name": "echo", "description": "Echo immediately",
     "inputSchema": {"type": "object", "properties": {"value": {}}}},
]

for raw in sys.stdin:
    log(raw)
    msg = json.loads(raw)
    method, rid = msg.get("method"), msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": msg.get("params", {}).get("protocolVersion"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-slow", "version": "1"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = msg.get("params", {})
        if params.get("name") == "slow_echo":
            time.sleep(SLEEP)
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text",
                         "text": json.dumps(params.get("arguments") or {}, sort_keys=True)}],
            "isError": False}})
