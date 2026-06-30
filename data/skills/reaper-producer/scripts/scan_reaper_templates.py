#!/usr/bin/env python3
"""Scan REAPER .RTrackTemplate files and generate an instrument registry draft."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def slugify(name: str) -> str:
    base = Path(name).stem.lower()
    base = re.sub(r"[^a-z0-9]+", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    return base or "instrument"


def infer_family(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    if len(rel.parts) > 1:
        return rel.parts[0].lower().replace(" ", "_")
    return "unknown"


def build_registry(root: Path) -> dict:
    instruments = []
    seen_ids: dict[str, int] = {}

    for template in sorted(root.rglob("*.RTrackTemplate")):
        instrument_id = slugify(template.stem)
        count = seen_ids.get(instrument_id, 0)
        seen_ids[instrument_id] = count + 1
        if count:
            instrument_id = f"{instrument_id}_{count + 1}"

        display_name = template.stem.replace("_", " ").strip()
        instruments.append(
            {
                "id": instrument_id,
                "display_name": display_name,
                "aliases": [display_name.lower()],
                "family": infer_family(template, root),
                "roles": [],
                "plugin": "",
                "library": "",
                "template_path": str(template),
                "default_track_name": display_name,
                "default_volume_db": -10,
                "default_pan": 0,
                "midi_channel": 1,
                "tags": ["template", "editable-midi"],
            }
        )

    return {"version": 1, "templates_root": str(root), "instruments": instruments}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an instrument registry from REAPER track templates.")
    parser.add_argument("--templates-root", required=True, help="Directory containing .RTrackTemplate files.")
    parser.add_argument("--output", default="instruments.generated.json", help="Output JSON path.")
    args = parser.parse_args()

    root = Path(args.templates_root).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Templates root does not exist: {root}")
    if not root.is_dir():
        raise SystemExit(f"Templates root is not a directory: {root}")

    registry = build_registry(root)
    output = Path(args.output)
    output.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(registry['instruments'])} instruments to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

