"""wedged 假 server：应答 initialize 后彻底停止读 stdin 并睡死——管道会被写满。"""
import json
import sys
import time

for raw in sys.stdin:
    msg = json.loads(raw)
    if msg.get("method") == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": {
            "protocolVersion": msg.get("params", {}).get("protocolVersion"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-wedged", "version": "1"}}}) + "\n")
        sys.stdout.flush()
        break

time.sleep(3600)          # 从此不再读 stdin，也不再应答
