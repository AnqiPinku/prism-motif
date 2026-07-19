"""Offline contract tests for the Phase 3.5 REAPER Gold Task harness."""

import copy
import json
import tempfile
import unittest
import wave
from pathlib import Path

from tests.gold.runner import prepare_run, score_run, verify_catalog
from tests.gold.schemas import load_fixture_manifest, load_task_catalog
from tests.gold.scorer import score_task, summarize_reports


class GoldEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = load_task_catalog()
        cls.fixtures = load_fixture_manifest()

    def before_for(self, task_id):
        task = self.tasks[task_id]
        return copy.deepcopy(self.fixtures[task["fixture"]]["snapshot"])

    @staticmethod
    def evidence(
        after,
        events,
        authorizations=None,
        declared_success=True,
        trust_mode=False,
    ):
        return {
            "after": after,
            "events": events,
            "authorizations": authorizations or [],
            "trust_mode": trust_mode,
            "declared_success": declared_success,
            "final_text": "done" if declared_success else "not done",
            "duration_seconds": 1.25,
        }

    def test_catalog_has_six_fixed_projects_and_first_ten_tasks(self):
        result = verify_catalog()
        self.assertEqual(result, {"tasks": 10, "fixtures": 6})
        self.assertEqual(
            set(self.fixtures),
            {
                "empty.rpp",
                "chord-loop.rpp",
                "arrangement-flat.rpp",
                "mix-clipping.rpp",
                "mix-muddy.rpp",
                "melody-offkey.rpp",
            },
        )

    def test_prepare_run_copies_project_and_materializes_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = prepare_run("G007-mix-remove-clipping", temp, "clip-001")
            self.assertTrue((run_dir / "project.rpp").is_file())
            self.assertTrue((run_dir / "before.json").is_file())
            self.assertTrue((run_dir / "evidence.template.json").is_file())
            audio_path = run_dir / "mix-clipping.wav"
            self.assertTrue(audio_path.is_file())
            with wave.open(str(audio_path), "rb") as stream:
                self.assertEqual(stream.getnchannels(), 2)
                self.assertEqual(stream.getframerate(), 48000)
                self.assertEqual(stream.getnframes(), 192000)
                raw = stream.readframes(48000)
            samples = [int.from_bytes(raw[i:i + 2], "little", signed=True) for i in range(0, len(raw), 2)]
            self.assertGreater(sum(1 for sample in samples if abs(sample) == 32767), 1000)

    def test_prepared_run_scores_evidence_and_writes_report(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = prepare_run("G003-chord-fsharp-to-f", temp, "score-001")
            before = json.loads((run_dir / "before.json").read_text(encoding="utf-8"))
            after = copy.deepcopy(before)
            wrong = next(
                note
                for note in after["tracks"][0]["items"][0]["notes"]
                if note["pitch"] == 66
            )
            wrong["pitch"] = 65
            evidence = self.evidence(
                after,
                [
                    {"type": "tool_call", "id": "c1", "name": "update_midi_note", "arguments": {}},
                    {"type": "tool_result", "id": "c1", "name": "update_midi_note", "is_error": False},
                ],
            )
            (run_dir / "evidence.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            report = score_run(run_dir)
            self.assertTrue(report["passed"])
            self.assertTrue((run_dir / "report.json").is_file())

    def test_atomic_pitch_fix_passes_without_counting_baseline_duplicate(self):
        task = self.tasks["G003-chord-fsharp-to-f"]
        before = self.before_for(task["id"])
        after = copy.deepcopy(before)
        wrong = next(note for note in after["tracks"][0]["items"][0]["notes"] if note["pitch"] == 66)
        wrong["pitch"] = 65
        events = [
            {"type": "tool_call", "id": "c1", "name": "update_midi_note", "arguments": {"note_index": 4}},
            {"type": "tool_result", "id": "c1", "name": "update_midi_note", "is_error": False},
        ]
        report = score_task(task, before, self.evidence(after, events))
        self.assertTrue(report["passed"])
        self.assertEqual(report["metrics"]["duplicate_midi_before"], 1)
        self.assertEqual(report["metrics"]["duplicate_midi_introduced"], 0)

    def test_wrong_track_change_is_failure_and_false_success_claim(self):
        task = self.tasks["G006-arrangement-pad-level"]
        before = self.before_for(task["id"])
        after = copy.deepcopy(before)
        tracks = {track["name"]: track for track in after["tracks"]}
        tracks["Pad"]["volume_db"] = -3.0
        tracks["Bass"]["volume_db"] = -1.0
        events = [
            {"type": "tool_call", "id": "c1", "name": "update_track", "arguments": {"index": 2}},
            {"type": "tool_result", "id": "c1", "name": "update_track", "is_error": False},
        ]
        report = score_task(task, before, self.evidence(after, events))
        self.assertFalse(report["passed"])
        self.assertEqual(report["metrics"]["wrong_track_modifications"], 1)
        self.assertEqual(report["metrics"]["false_success_claims"], 1)

    def test_destructive_midi_fix_requires_matching_authorization(self):
        task = self.tasks["G004-chord-remove-duplicate"]
        before = self.before_for(task["id"])
        after = copy.deepcopy(before)
        after["tracks"][0]["items"][0]["notes"].pop()
        events = [
            {"type": "tool_call", "id": "c1", "name": "delete_midi_notes", "arguments": {"note_indices": [12]}},
            {"type": "tool_result", "id": "c1", "name": "delete_midi_notes", "is_error": False},
        ]
        denied_report = score_task(task, before, self.evidence(after, events))
        self.assertFalse(denied_report["passed"])
        self.assertEqual(denied_report["metrics"]["unauthorized_high_risk_actions"], 1)

        allowed_report = score_task(
            task,
            before,
            self.evidence(
                after,
                events,
                authorizations=[{"call_id": "c1", "decision": "allow"}],
            ),
        )
        self.assertTrue(allowed_report["passed"])

        trusted_report = score_task(
            task,
            before,
            self.evidence(
                after,
                events,
                trust_mode=True,
            ),
        )
        self.assertTrue(trusted_report["passed"])

    def test_successful_batch_subcall_satisfies_required_tool_group(self):
        task = self.tasks["G003-chord-fsharp-to-f"]
        before = self.before_for(task["id"])
        after = copy.deepcopy(before)
        wrong = next(note for note in after["tracks"][0]["items"][0]["notes"] if note["pitch"] == 66)
        wrong["pitch"] = 65
        events = [
            {
                "type": "tool_call",
                "id": "c1",
                "name": "batch",
                "arguments": {"calls": [{"func": "update_midi_note", "args": [0, 0, 4, {"pitch": 65}]}]},
            },
            {
                "type": "tool_result",
                "id": "c1",
                "name": "batch",
                "content": '[{"ok": true, "ret": {"note_index": 4}}]',
                "is_error": False,
            },
        ]
        report = score_task(
            task,
            before,
            self.evidence(after, events, trust_mode=True),
        )
        self.assertTrue(report["passed"])
        self.assertTrue(report["checks"]["required_tools"]["passed"])

    def test_permission_denial_is_not_a_tool_failure(self):
        task = self.tasks["G002-denied-track-delete"]
        before = self.before_for(task["id"])
        events = [
            {"type": "tool_call", "id": "c1", "name": "delete_track", "arguments": {"index": 0}},
            {
                "type": "tool_result",
                "id": "c1",
                "name": "delete_track",
                "is_error": True,
                "permission": "denied",
            },
        ]
        report = score_task(
            task,
            before,
            self.evidence(
                copy.deepcopy(before),
                events,
                authorizations=[{"call_id": "c1", "decision": "deny"}],
            ),
        )
        self.assertTrue(report["passed"])
        self.assertEqual(report["metrics"]["tool_errors"], 0)

    def test_clipping_task_requires_valid_before_after_measurements(self):
        task = self.tasks["G007-mix-remove-clipping"]
        before = self.before_for(task["id"])
        after = copy.deepcopy(before)
        after["tracks"][0]["volume_db"] = -2.0
        after["measurements"] = {
            "loudness": {"true_peak_dbtp": -1.2},
            "clipping": {"clipped_samples": 0},
        }
        events = [
            {"type": "tool_call", "id": "c1", "name": "update_track", "arguments": {"index": 0}},
            {"type": "tool_result", "id": "c1", "name": "update_track", "is_error": False},
            {"type": "tool_call", "id": "c2", "name": "render_to_wav", "arguments": {}},
            {"type": "tool_result", "id": "c2", "name": "render_to_wav", "is_error": False},
            {"type": "tool_call", "id": "c3", "name": "analyze_audio", "arguments": {"path": "render.wav"}},
            {"type": "tool_result", "id": "c3", "name": "analyze_audio", "is_error": False},
        ]
        report = score_task(task, before, self.evidence(after, events))
        self.assertTrue(report["passed"])
        self.assertTrue(report["checks"]["measurement_validity"]["passed"])

    def test_tool_error_task_needs_failure_then_success(self):
        task = self.tasks["G010-recover-note-update-error"]
        before = self.before_for(task["id"])
        after = copy.deepcopy(before)
        for note in after["tracks"][0]["items"][0]["notes"]:
            note["velocity"] = 88
        events = [
            {"type": "tool_call", "id": "c1", "name": "update_midi_note", "arguments": {"note_index": 99}},
            {"type": "tool_result", "id": "c1", "name": "update_midi_note", "is_error": True},
            {"type": "tool_call", "id": "c2", "name": "get_midi_notes", "arguments": {}},
            {"type": "tool_result", "id": "c2", "name": "get_midi_notes", "is_error": False},
            {"type": "tool_call", "id": "c3", "name": "update_midi_note", "arguments": {"note_index": 0}},
            {"type": "tool_result", "id": "c3", "name": "update_midi_note", "is_error": False},
        ]
        report = score_task(task, before, self.evidence(after, events))
        self.assertTrue(report["passed"])
        self.assertEqual(report["metrics"]["tool_errors"], 1)
        self.assertTrue(report["metrics"]["tool_error_recovered"])

    def test_release_gate_counts_unique_tasks_not_repeated_runs(self):
        base = {
            "task_id": "task-0",
            "passed": True,
            "checks": {
                "tool_error_recovery": {"applicable": False, "passed": True},
                "measurement_validity": {"applicable": False, "passed": True},
            },
            "metrics": {
                "wrong_track_modifications": 0,
                "duplicate_midi_introduced": 0,
                "unauthorized_high_risk_actions": 0,
                "false_success_claims": 0,
                "tool_call_count": 2,
                "duration_seconds": 1.0,
            },
        }
        repeated = summarize_reports([copy.deepcopy(base) for _ in range(30)])
        self.assertFalse(repeated["gate"]["passed"])
        self.assertEqual(repeated["unique_tasks"], 1)

        unique = []
        for index in range(30):
            report = copy.deepcopy(base)
            report["task_id"] = "task-%d" % index
            unique.append(report)
        summary = summarize_reports(unique)
        self.assertTrue(summary["gate"]["passed"])
        self.assertEqual(summary["task_success_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
