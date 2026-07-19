"""Schemas and catalog loading for the REAPER Gold Task harness.

The harness intentionally uses plain JSON-compatible dictionaries.  This keeps
run evidence inspectable and lets a future live REAPER driver produce evidence
without importing test-only Python types.
"""

from __future__ import annotations

import json
from pathlib import Path


GOLD_ROOT = Path(__file__).resolve().parent
REPO_ROOT = GOLD_ROOT.parents[1]
TASKS_PATH = GOLD_ROOT / "tasks" / "gold_tasks.json"
FIXTURES_DIR = GOLD_ROOT / "fixtures"
FIXTURE_MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


class GoldSchemaError(ValueError):
    """Raised when a task, snapshot, or evidence document is malformed."""


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GoldSchemaError("cannot read JSON %s: %s" % (path, exc)) from exc


def _require(value, kind, label):
    if not isinstance(value, kind):
        raise GoldSchemaError("%s must be %s" % (label, kind.__name__))
    return value


def _string_list(value, label):
    _require(value, list, label)
    if not all(isinstance(item, str) and item for item in value):
        raise GoldSchemaError("%s must contain non-empty strings" % label)
    return value


def validate_snapshot(snapshot, label="snapshot"):
    """Validate the stable, UI-independent project snapshot shape."""
    _require(snapshot, dict, label)
    tracks = _require(snapshot.get("tracks"), list, "%s.tracks" % label)
    names = []
    for index, track in enumerate(tracks):
        track_label = "%s.tracks[%d]" % (label, index)
        _require(track, dict, track_label)
        name = track.get("name")
        if not isinstance(name, str) or not name:
            raise GoldSchemaError("%s.name must be a non-empty string" % track_label)
        names.append(name)
        items = track.get("items", [])
        _require(items, list, "%s.items" % track_label)
        for item_index, item in enumerate(items):
            item_label = "%s.items[%d]" % (track_label, item_index)
            _require(item, dict, item_label)
            notes = item.get("notes", [])
            _require(notes, list, "%s.notes" % item_label)
            for note_index, note in enumerate(notes):
                note_label = "%s.notes[%d]" % (item_label, note_index)
                _require(note, dict, note_label)
                for key in ("pitch", "start_beats", "length_beats"):
                    value = note.get(key)
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise GoldSchemaError("%s.%s must be numeric" % (note_label, key))
    if len(set(names)) != len(names):
        raise GoldSchemaError("%s track names must be unique" % label)
    _require(snapshot.get("markers", []), list, "%s.markers" % label)
    _require(snapshot.get("measurements", {}), dict, "%s.measurements" % label)
    return snapshot


def validate_task_spec(task):
    _require(task, dict, "task")
    for key in ("id", "fixture", "goal"):
        if not isinstance(task.get(key), str) or not task[key]:
            raise GoldSchemaError("task.%s must be a non-empty string" % key)
    for key in (
        "allowed_track_names",
        "required_track_names",
        "forbidden_track_names",
        "required_marker_names",
        "allowed_high_risk_tools",
        "required_permission_denials",
    ):
        _string_list(task.get(key, []), "task.%s" % key)

    groups = _require(task.get("required_tool_groups", []), list, "task.required_tool_groups")
    for index, group in enumerate(groups):
        if not group:
            raise GoldSchemaError("task.required_tool_groups[%d] cannot be empty" % index)
        _string_list(group, "task.required_tool_groups[%d]" % index)

    checks = _require(task.get("checks", {}), dict, "task.checks")
    for key in ("track_rules", "note_rules", "measurement_rules"):
        _require(checks.get(key, []), list, "task.checks.%s" % key)
    for rule in checks.get("measurement_rules", []):
        _require(rule, dict, "measurement rule")
        if rule.get("comparison") not in ("decrease", "increase", "equal"):
            raise GoldSchemaError("measurement comparison must be decrease, increase, or equal")
        if not isinstance(rule.get("path"), str) or not rule["path"]:
            raise GoldSchemaError("measurement rule path must be a non-empty string")
    for key in ("expect_no_change", "require_tool_error_recovery"):
        if key in task and not isinstance(task[key], bool):
            raise GoldSchemaError("task.%s must be boolean" % key)
    return task


def validate_evidence(evidence):
    _require(evidence, dict, "evidence")
    validate_snapshot(evidence.get("after"), "evidence.after")
    _require(evidence.get("events"), list, "evidence.events")
    _require(evidence.get("authorizations", []), list, "evidence.authorizations")
    if "trust_mode" in evidence and not isinstance(evidence["trust_mode"], bool):
        raise GoldSchemaError("evidence.trust_mode must be boolean")
    if not isinstance(evidence.get("declared_success"), bool):
        raise GoldSchemaError("evidence.declared_success must be boolean")
    duration = evidence.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
        raise GoldSchemaError("evidence.duration_seconds must be a non-negative number")
    return evidence


def load_task_catalog(path=TASKS_PATH):
    data = _read_json(path)
    _require(data, dict, "task catalog")
    if data.get("schema_version") != 1:
        raise GoldSchemaError("unsupported task catalog schema_version")
    tasks = _require(data.get("tasks"), list, "task catalog.tasks")
    by_id = {}
    for task in tasks:
        validate_task_spec(task)
        if task["id"] in by_id:
            raise GoldSchemaError("duplicate task id: %s" % task["id"])
        by_id[task["id"]] = task
    return by_id


def load_fixture_manifest(path=FIXTURE_MANIFEST_PATH):
    data = _read_json(path)
    _require(data, dict, "fixture manifest")
    if data.get("schema_version") != 1:
        raise GoldSchemaError("unsupported fixture manifest schema_version")
    fixtures = _require(data.get("fixtures"), dict, "fixture manifest.fixtures")
    for name, fixture in fixtures.items():
        if not isinstance(name, str) or not name.endswith(".rpp"):
            raise GoldSchemaError("fixture keys must be .rpp filenames")
        _require(fixture, dict, "fixture %s" % name)
        validate_snapshot(fixture.get("snapshot"), "fixture %s snapshot" % name)
        generated = _require(
            fixture.get("generated_audio", []), list, "fixture %s generated_audio" % name
        )
        for audio in generated:
            _require(audio, dict, "generated audio")
            if audio.get("kind") not in ("hard_clipped_sine", "muddy_two_tone"):
                raise GoldSchemaError("unknown generated audio kind in %s" % name)
            if not isinstance(audio.get("filename"), str) or not audio["filename"].endswith(".wav"):
                raise GoldSchemaError("generated audio filename must end in .wav")
    return fixtures
