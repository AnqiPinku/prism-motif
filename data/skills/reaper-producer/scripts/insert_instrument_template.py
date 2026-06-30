#!/usr/bin/env python3
"""Insert a registered REAPER track template through the REAPER MCP v2 file bridge."""

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


def expand_path(value: str, variables: dict[str, str]) -> Path:
    expanded = value
    for key, replacement in variables.items():
        expanded = expanded.replace("${" + key + "}", replacement)
    return Path(expanded).expanduser()


def find_instrument(registry: dict, instrument_id: str) -> dict | None:
    query = instrument_id.strip().lower()
    for inst in registry.get("instruments", []):
        if inst.get("id", "").lower() == query:
            return inst
        aliases = [str(alias).lower() for alias in inst.get("aliases", [])]
        if query in aliases:
            return inst
    return None


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

    try:
        deadline = time.time() + timeout
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
    parser = argparse.ArgumentParser(description="Insert a registered REAPER instrument track template.")
    parser.add_argument("instrument", help="Instrument id or alias from the registry.")
    parser.add_argument("--registry", default="instruments.json", help="Instrument registry path.")
    parser.add_argument("--ipc-dir", default=None, help="REAPER MCP v2 IPC directory.")
    parser.add_argument("--bridge-dir", default=None, help="Deprecated alias for --ipc-dir.")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--var",
        action="append",
        default=[],
        help="Variable expansion KEY=VALUE, e.g. REAPER_RESOURCE_PATH=C:\\Users\\me\\AppData\\Roaming\\REAPER",
    )
    args = parser.parse_args()

    registry_path = Path(args.registry)
    if not registry_path.exists():
        print(f"Registry not found: {registry_path}", file=sys.stderr)
        return 1

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    variables = {}
    for item in args.var:
        if "=" not in item:
            print(f"--var must be KEY=VALUE, got: {item}", file=sys.stderr)
            return 1
        key, value = item.split("=", 1)
        variables[key] = value

    inst = find_instrument(registry, args.instrument)
    if not inst:
        print(f"Instrument not found in registry: {args.instrument}", file=sys.stderr)
        return 1

    template_path = expand_path(inst["template_path"], variables)
    if template_path.suffix != ".RTrackTemplate":
        print(f"Refusing non-track-template path: {template_path}", file=sys.stderr)
        return 1
    if not template_path.exists():
        print(f"Track template not found: {template_path}", file=sys.stderr)
        return 1

    ipc_dir = Path(args.ipc_dir or args.bridge_dir or default_ipc_dir())
    result = call_bridge(ipc_dir, "Main_openProject", [str(template_path)], args.timeout)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
