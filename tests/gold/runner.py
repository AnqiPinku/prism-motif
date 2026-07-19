"""CLI for preparing, validating, and scoring REAPER Gold Task runs."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import re
import shutil
import struct
import sys
import uuid
import wave
from pathlib import Path

from .schemas import (
    FIXTURES_DIR,
    GoldSchemaError,
    load_fixture_manifest,
    load_task_catalog,
)
from .scorer import load_reports, score_task, summarize_reports


def _write_json(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_rpp(path, expected_track_names=(), expected_audio=()):
    """Perform a conservative text-level fixture check without launching REAPER."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or not lines[0].startswith("<REAPER_PROJECT "):
        raise GoldSchemaError("%s lacks a REAPER_PROJECT root" % path)
    depth = 0
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("<"):
            depth += 1
        elif stripped == ">":
            depth -= 1
            if depth < 0:
                raise GoldSchemaError("%s closes a chunk too early at line %d" % (path, number))
    if depth != 0:
        raise GoldSchemaError("%s has unbalanced REAPER chunks" % path)
    for name in expected_track_names:
        if 'NAME "%s"' % name not in text:
            raise GoldSchemaError("%s is missing track %s" % (path, name))
    referenced = set(re.findall(r'^\s*FILE\s+"([^"]+)"', text, flags=re.MULTILINE))
    for filename in expected_audio:
        if filename not in referenced:
            raise GoldSchemaError("%s does not reference generated audio %s" % (path, filename))
    return {"path": str(path), "track_names": list(expected_track_names), "audio_files": sorted(referenced)}


def verify_catalog():
    tasks = load_task_catalog()
    fixtures = load_fixture_manifest()
    errors = []
    for name, fixture in fixtures.items():
        path = FIXTURES_DIR / name
        try:
            validate_rpp(
                path,
                [track["name"] for track in fixture["snapshot"]["tracks"]],
                [audio["filename"] for audio in fixture.get("generated_audio", [])],
            )
        except (OSError, GoldSchemaError) as exc:
            errors.append(str(exc))
    for task in tasks.values():
        if task["fixture"] not in fixtures:
            errors.append("task %s references unknown fixture %s" % (task["id"], task["fixture"]))
    if errors:
        raise GoldSchemaError("; ".join(errors))
    return {"tasks": len(tasks), "fixtures": len(fixtures)}


def _materialize_audio(path, spec):
    sample_rate = int(spec.get("sample_rate", 48000))
    duration = float(spec.get("duration_seconds", 4.0))
    frames = int(sample_rate * duration)
    kind = spec["kind"]
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        block = bytearray()
        for index in range(frames):
            t = index / sample_rate
            if kind == "hard_clipped_sine":
                sample = max(-1.0, min(1.0, 1.45 * math.sin(2 * math.pi * 440 * t)))
            elif kind == "muddy_two_tone":
                sample = 0.78 * math.sin(2 * math.pi * 320 * t)
                sample += 0.07 * math.sin(2 * math.pi * 3200 * t)
                sample = max(-0.98, min(0.98, sample))
            else:  # validated before this point
                raise GoldSchemaError("unknown generated audio kind: %s" % kind)
            pcm = int(round(sample * 32767))
            block.extend(struct.pack("<hh", pcm, pcm))
        stream.writeframes(block)


def _safe_run_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise GoldSchemaError("run id may only contain letters, digits, dot, underscore, and hyphen")
    return value


def prepare_run(task_id, runs_dir, run_id=None):
    """Copy a fixed project and create an evidence workspace for one run."""
    verify_catalog()
    tasks = load_task_catalog()
    fixtures = load_fixture_manifest()
    if task_id not in tasks:
        raise GoldSchemaError("unknown task id: %s" % task_id)
    task = tasks[task_id]
    fixture = fixtures[task["fixture"]]
    run_id = _safe_run_id(run_id or (task_id + "-" + uuid.uuid4().hex[:12]))
    runs_dir = Path(runs_dir).resolve()
    run_dir = (runs_dir / run_id).resolve()
    if run_dir.parent != runs_dir:
        raise GoldSchemaError("run directory escaped the requested runs root")
    if run_dir.exists():
        raise GoldSchemaError("run directory already exists: %s" % run_dir)
    run_dir.mkdir(parents=True)

    project_path = run_dir / "project.rpp"
    shutil.copy2(FIXTURES_DIR / task["fixture"], project_path)
    for audio in fixture.get("generated_audio", []):
        _materialize_audio(run_dir / audio["filename"], audio)

    before = copy.deepcopy(fixture["snapshot"])
    before["project"] = str(project_path)
    evidence_template = {
        "after": copy.deepcopy(before),
        "events": [],
        "authorizations": [],
        "trust_mode": False,
        "declared_success": False,
        "final_text": "",
        "duration_seconds": 0.0,
    }
    _write_json(run_dir / "task.json", task)
    _write_json(run_dir / "before.json", before)
    _write_json(run_dir / "evidence.template.json", evidence_template)
    return run_dir


def score_run(run_dir):
    run_dir = Path(run_dir)
    task_path = run_dir / "task.json"
    before_path = run_dir / "before.json"
    evidence_path = run_dir / "evidence.json"
    for path in (task_path, before_path, evidence_path):
        if not path.is_file():
            raise GoldSchemaError("run is missing %s" % path.name)
    task = json.loads(task_path.read_text(encoding="utf-8"))
    before = json.loads(before_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    report = score_task(task, before, evidence)
    _write_json(run_dir / "report.json", report)
    return report


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify", help="validate the task catalog and all fixed RPP files")
    commands.add_parser("list", help="list the first ten Gold Task definitions")

    prepare = commands.add_parser("prepare", help="prepare an isolated run directory")
    prepare.add_argument("--task", required=True, dest="task_id")
    prepare.add_argument("--runs-dir", default="build/gold-runs")
    prepare.add_argument("--run-id")

    score = commands.add_parser("score", help="score evidence.json in a prepared run")
    score.add_argument("--run-dir", required=True)

    live = commands.add_parser(
        "live",
        help="run a prepared task through the local Gateway and live REAPER",
    )
    live.add_argument("--run-dir", required=True)
    live.add_argument("--gateway-url", default="http://127.0.0.1:8770")
    live.add_argument("--session-token-env", default="PRISM_SESSION_TOKEN")
    live.add_argument("--provider")
    live.add_argument("--thread-id")
    live.add_argument("--trust-mode", action="store_true")
    live.add_argument(
        "--leave-after",
        action="store_true",
        help="leave REAPER at the Agent result instead of reloading the clean copy",
    )
    live.add_argument("--timeout", type=float, default=180)
    live.add_argument("--bridge-server")

    summary = commands.add_parser("summary", help="aggregate report.json files and evaluate the gate")
    summary.add_argument("--reports-dir", required=True)
    summary.add_argument("--output")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify":
            output = verify_catalog()
        elif args.command == "list":
            output = [
                {"id": task["id"], "fixture": task["fixture"], "goal": task["goal"]}
                for task in load_task_catalog().values()
            ]
        elif args.command == "prepare":
            output = {"run_dir": str(prepare_run(args.task_id, args.runs_dir, args.run_id))}
        elif args.command == "score":
            output = score_run(args.run_dir)
        elif args.command == "live":
            from .live_driver import GatewayChatClient, load_reaper_bridge, run_live

            token = os.environ.get(args.session_token_env, "")
            bridge = load_reaper_bridge(args.bridge_server)
            chat_client = GatewayChatClient(
                args.gateway_url,
                token,
                timeout=args.timeout,
                provider=args.provider,
            )
            result = run_live(
                args.run_dir,
                bridge,
                chat_client,
                trust_mode=args.trust_mode,
                restore_before=not args.leave_after,
                thread_id=args.thread_id,
            )
            output = result["report"]
        else:
            output = summarize_reports(load_reports(args.reports_dir))
            if args.output:
                _write_json(args.output, output)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (GoldSchemaError, OSError, ValueError) as exc:
        print("gold-eval error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
