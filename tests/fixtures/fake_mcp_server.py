"""Small stdio MCP server with deterministic success and failure modes."""

from __future__ import annotations

import json
import sys
import time


MODE = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "normal"


def send(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


TOOLS = [
    {
        "name": "echo",
        "description": "Echo arguments",
        "inputSchema": {"type": "object", "properties": {"value": {}}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "long_result",
        "description": "Return a long deterministic result",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "fail",
        "description": "Return an MCP tool error",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "hang",
        "description": "Never answer within the client timeout",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"destructiveHint": True},
    },
]


for raw in sys.stdin:
    message = json.loads(raw)
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        if MODE == "exit_on_init":
            raise SystemExit(3)
        if MODE == "hang_initialize":
            time.sleep(60)
            continue
        send({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": message.get("params", {}).get("protocolVersion"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-mcp", "version": "1"},
            },
        })
    elif method == "tools/list":
        if MODE == "rpc_error":
            send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": "list failed"}})
        else:
            send({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        name = message.get("params", {}).get("name")
        arguments = message.get("params", {}).get("arguments") or {}
        if name == "hang":
            time.sleep(60)
        elif name == "fail":
            send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32001, "message": "tool failed"}})
        else:
            text = "x" * 10_000 if name == "long_result" else json.dumps(arguments, sort_keys=True)
            send({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": text}], "isError": False},
            })
