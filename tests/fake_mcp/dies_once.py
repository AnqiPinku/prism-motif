"""dies_once 假 server：首次 tools/call 写下 --marker 文件后直接退出（不应答）；
marker 已存在（= 第二次 spawn）则表现正常。收到的每一行记进 --log 文件（跨 spawn 追加）。"""
import json
import os
import sys

MARKER = sys.argv[sys.argv.index("--marker") + 1]
LOG = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else None


def log(raw):
    if LOG:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(raw if raw.endswith("\n") else raw + "\n")


def send(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


TOOLS = [{"name": "echo", "description": "Echo arguments (dies on first ever call)",
          "inputSchema": {"type": "object", "properties": {"value": {}}}}]

for raw in sys.stdin:
    log(raw)
    msg = json.loads(raw)
    method, rid = msg.get("method"), msg.get("id")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": msg.get("params", {}).get("protocolVersion"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-dies-once", "version": "1"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        if not os.path.exists(MARKER):
            with open(MARKER, "w", encoding="utf-8") as f:
                f.write("died")
            raise SystemExit(1)
        args = msg.get("params", {}).get("arguments") or {}
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": json.dumps(args, sort_keys=True)}],
            "isError": False}})
