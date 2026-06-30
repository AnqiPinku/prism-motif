#!/usr/bin/env python3
"""Validate a REAPER Producer instrument registry with standard-library checks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")


def expand_path(value: str, variables: dict[str, str]) -> Path:
    expanded = value
    for key, replacement in variables.items():
        expanded = expanded.replace("${" + key + "}", replacement)
    return Path(expanded).expanduser()


def validate(data: dict, check_paths: bool, variables: dict[str, str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("version") != 1:
        errors.append("version must be 1")

    instruments = data.get("instruments")
    if not isinstance(instruments, list):
        errors.append("instruments must be a list")
        return errors, warnings

    seen_ids: set[str] = set()
    seen_aliases: dict[str, str] = {}

    for index, inst in enumerate(instruments):
        prefix = f"instruments[{index}]"
        if not isinstance(inst, dict):
            errors.append(f"{prefix} must be an object")
            continue

        inst_id = inst.get("id")
        if not isinstance(inst_id, str) or not ID_PATTERN.match(inst_id):
            errors.append(f"{prefix}.id must match {ID_PATTERN.pattern}")
        elif inst_id in seen_ids:
            errors.append(f"duplicate instrument id: {inst_id}")
        else:
            seen_ids.add(inst_id)

        display_name = inst.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            errors.append(f"{prefix}.display_name is required")

        template_path = inst.get("template_path")
        if not isinstance(template_path, str) or not template_path.endswith(".RTrackTemplate"):
            errors.append(f"{prefix}.template_path must end with .RTrackTemplate")
        elif check_paths:
            path = expand_path(template_path, variables)
            if not path.exists():
                errors.append(f"{prefix}.template_path does not exist: {path}")

        aliases = inst.get("aliases", [])
        if aliases is None:
            aliases = []
        if not isinstance(aliases, list):
            errors.append(f"{prefix}.aliases must be a list")
        else:
            for alias in aliases:
                if not isinstance(alias, str):
                    errors.append(f"{prefix}.aliases contains a non-string alias")
                    continue
                normalized = alias.strip().lower()
                if not normalized:
                    continue
                previous = seen_aliases.get(normalized)
                if previous and previous != inst_id:
                    warnings.append(f"alias '{alias}' is used by both {previous} and {inst_id}")
                else:
                    seen_aliases[normalized] = inst_id or prefix

        volume = inst.get("default_volume_db")
        if volume is not None and not isinstance(volume, (int, float)):
            errors.append(f"{prefix}.default_volume_db must be numeric")

        pan = inst.get("default_pan")
        if pan is not None and (not isinstance(pan, (int, float)) or pan < -1 or pan > 1):
            errors.append(f"{prefix}.default_pan must be between -1 and 1")

        midi_channel = inst.get("midi_channel")
        if midi_channel is not None and (
            not isinstance(midi_channel, int) or midi_channel < 1 or midi_channel > 16
        ):
            errors.append(f"{prefix}.midi_channel must be an integer from 1 to 16")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a REAPER Producer instrument registry.")
    parser.add_argument("registry", help="Path to instruments.json")
    parser.add_argument("--check-paths", action="store_true", help="Fail if template files do not exist.")
    parser.add_argument(
        "--var",
        action="append",
        default=[],
        help="Variable expansion KEY=VALUE, e.g. REAPER_RESOURCE_PATH=C:\\Users\\me\\AppData\\Roaming\\REAPER",
    )
    args = parser.parse_args()

    registry_path = Path(args.registry)
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    variables = {}
    for item in args.var:
        if "=" not in item:
            raise SystemExit(f"--var must be KEY=VALUE, got: {item}")
        key, value = item.split("=", 1)
        variables[key] = value

    errors, warnings = validate(data, args.check_paths, variables)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if errors:
        return 1
    print(f"Registry valid: {registry_path} ({len(data.get('instruments', []))} instruments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

