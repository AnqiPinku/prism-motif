#!/usr/bin/env python3
"""Check the REAPER MCP v2 file bridge without third-party packages."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path


def default_ipc_dir() -> str:
    env_value = os.environ.get("REAPER_MCP_IPC_DIR")
    if env_value:
        return env_value

    appdata = os.environ.get("APPDATA")
    if appdata:
        return str(Path(appdata) / "reaper-mcp-ipc")

    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return str(Path(xdg) / "reaper-mcp-ipc")

    return str(Path.home() / ".local" / "share" / "reaper-mcp-ipc")


def call_bridge(ipc_dir: Path, func: str, args: list, timeout: float) -> dict:
    ipc_dir.mkdir(parents=True, exist_ok=True)
    request_file = ipc_dir / "request.json"
    response_file = ipc_dir / "response.json"
    tmp_file = ipc_dir / "request.tmp"
    request_id = uuid.uuid4().hex[:12]

    response_file.unlink(missing_ok=True)
    payload = {"id": request_id, "func": func, "args": args}
    tmp_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_file.replace(request_file)

    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            if response_file.exists():
                text = response_file.read_text(encoding="utf-8").strip()
                if text:
                    result = json.loads(text)
                    if result.get("id") != request_id:
                        return {
                            "ok": False,
                            "error": "response_id_mismatch",
                            "expected": request_id,
                            "actual": result.get("id"),
                        }
                    return result
            time.sleep(0.05)
        return {"ok": False, "error": "timeout"}
    finally:
        request_file.unlink(missing_ok=True)
        tmp_file.unlink(missing_ok=True)
        response_file.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check REAPER MCP v2 bridge health.")
    parser.add_argument(
        "--ipc-dir",
        default=None,
        help="IPC directory. Defaults to REAPER_MCP_IPC_DIR, then %APPDATA%/reaper-mcp-ipc.",
    )
    parser.add_argument(
        "--bridge-dir",
        default=None,
        help="Deprecated alias for --ipc-dir, kept for compatibility.",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()

    ipc_dir = Path(args.ipc_dir or args.bridge_dir or default_ipc_dir())
    print(f"IPC dir: {ipc_dir}")

    checks = [
        ("get_project_summary", [], "project_summary"),
        ("get_tempo", [], "tempo"),
        ("list_tracks", [], "tracks"),
    ]

    ok = True
    for func, call_args, label in checks:
        result = call_bridge(ipc_dir, func, call_args, args.timeout)
        status = "PASS" if result.get("ok") else "FAIL"
        print(f"{status} {label}: {json.dumps(result, ensure_ascii=False)}")
        ok = ok and bool(result.get("ok"))

    if not ok:
        print("REAPER MCP v2 bridge is not responding. Open REAPER and run reaper_mcp_bridge.lua.")
        return 1

    print("REAPER MCP v2 bridge is responding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
