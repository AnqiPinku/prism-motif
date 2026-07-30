"""生孙假 server：initialize 时孵化长睡孙进程、记下 pid，然后装忙（不再读 stdin）。

模拟"感知服务正跑着 ROSVOT 子任务时被杀"的真实场景，
用于验证 close() 的进程树终杀：杀掉本 server 必须连带孙进程一起死。
"""
import json
import subprocess
import sys
import time

LOG = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else None


def send(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


raw = sys.stdin.readline()
msg = json.loads(raw)
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(120)"],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL)
if LOG:
    with open(LOG, "w", encoding="utf-8") as f:
        f.write(str(child.pid))
send({"jsonrpc": "2.0", "id": msg.get("id"), "result": {
    "protocolVersion": msg.get("params", {}).get("protocolVersion"),
    "capabilities": {"tools": {}},
    "serverInfo": {"name": "fake-spawner", "version": "1"}}})
time.sleep(300)                                    # 装忙：不读 stdin、不退出
