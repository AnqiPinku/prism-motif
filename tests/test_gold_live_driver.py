"""Offline lifecycle tests for the live REAPER Gold Task driver."""

import copy
import json
import threading
import time
import unittest
from unittest.mock import patch

from tests.gold.live_driver import (
    ChatResult,
    GatewayChatClient,
    GoldLiveError,
    GoldTurnActiveError,
    _declared_success,
    _decode_sse_block,
    _same_path,
    execute_live_run,
    measurements_from_events,
)


PROJECT = r"X:\workspace\prism-motif\build\gold-runs\test\project.rpp"


def snapshot(tracks=None, project=PROJECT):
    return {
        "project": project,
        "tempo_bpm": 120,
        "time_signature": [4, 4],
        "tracks": copy.deepcopy(tracks or []),
        "markers": [],
        "measurements": {},
    }


def chat_result():
    return ChatResult(
        events=[
            {"type": "final", "text": "done"},
            {"type": "loop_done", "reason": "final"},
            {"type": "done", "cancelled": False, "elapsed_ms": 25},
        ],
        authorizations=[],
        final_text="done",
        declared_success=True,
        duration_seconds=0.025,
    )


class FakeHTTPResponse:
    def __init__(self, *, payload=None, lines=None):
        self.payload = payload
        self.lines = list(lines or [])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.lines)

    def read(self):
        return json.dumps(self.payload or {"ok": True}).encode("utf-8")

    def close(self):
        return None


class BlockingHTTPResponse(FakeHTTPResponse):
    def __init__(self):
        super().__init__()
        self.closed = threading.Event()

    def __iter__(self):
        while not self.closed.wait(0.01):
            yield b": heartbeat\n"

    def close(self):
        self.closed.set()


def sse_lines(*events):
    lines = []
    for event in events:
        lines.append(
            ("data: " + json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        )
        lines.append(b"\n")
    return lines


class FakeBridge:
    def __init__(self, before, *, project=PROJECT, dirty=False):
        self.before = copy.deepcopy(before)
        self.state = copy.deepcopy(before)
        self.project = project
        self.handle = {"__handle": "project"}
        self.calls = []
        self.dirty = int(dirty)
        self.state_change_count = 10
        self.reload_state = copy.deepcopy(before)
        self.reload_dirty = 0
        self.reload_error = None
        self.change_count_reads = 0
        self.dirty_reads = 0
        self.fail_change_count_read = None
        self.fail_dirty_read = None

    def set_state(self, value):
        self.state = copy.deepcopy(value)
        self.dirty = 1
        self.state_change_count += 1

    def call(self, func, args=None):
        args = args or []
        self.calls.append((func, copy.deepcopy(args)))
        if func == "EnumProjects":
            return [self.handle, self.project]
        if func == "IsProjectDirty":
            self.dirty_reads += 1
            if self.fail_dirty_read == self.dirty_reads:
                raise RuntimeError("dirty state failed")
            return self.dirty
        if func == "GetProjectStateChangeCount":
            self.change_count_reads += 1
            if self.fail_change_count_read == self.change_count_reads:
                raise RuntimeError("state count failed")
            return self.state_change_count
        if func == "Main_openProject":
            if self.reload_error is not None:
                raise self.reload_error
            if len(args) != 1 or not str(args[0]).startswith("noprompt:"):
                raise AssertionError("prepared project must be reloaded without a prompt")
            self.project = str(args[0])[len("noprompt:"):]
            self.state = copy.deepcopy(self.reload_state)
            self.dirty = int(self.reload_dirty)
            return None
        raise AssertionError("unexpected bridge call: %s" % func)


def fake_snapshotter(bridge):
    value = copy.deepcopy(bridge.state)
    value["project"] = bridge.project
    return value


class GoldLiveDriverTests(unittest.TestCase):
    def setUp(self):
        self.before = snapshot()
        self.after = snapshot(
            [
                {
                    "name": "Chords",
                    "volume_db": 0.0,
                    "pan": 0.0,
                    "mute": False,
                    "solo": False,
                    "fx": [],
                    "items": [],
                }
            ]
        )

    def execute(self, bridge, turn, **kwargs):
        return execute_live_run(
            bridge,
            PROJECT,
            self.before,
            turn,
            snapshotter=fake_snapshotter,
            **kwargs,
        )

    @staticmethod
    def call_names(bridge):
        return [name for name, _args in bridge.calls]

    def test_changed_run_captures_after_then_reloads_clean_copy(self):
        bridge = FakeBridge(self.before)

        def turn():
            bridge.set_state(self.after)
            return chat_result()

        result = self.execute(bridge, turn)

        self.assertEqual(result.after, self.after)
        self.assertEqual(bridge.state, self.before)
        self.assertEqual(self.call_names(bridge).count("Main_openProject"), 1)
        self.assertIn(
            ("Main_openProject", ["noprompt:" + PROJECT]),
            bridge.calls,
        )
        self.assertTrue(result.diagnostics["changed"])
        self.assertTrue(result.diagnostics["reloaded"])
        self.assertTrue(result.diagnostics["baseline_verified"])

    def test_leave_after_keeps_agent_result(self):
        bridge = FakeBridge(self.before)

        def turn():
            bridge.set_state(self.after)
            return chat_result()

        result = self.execute(bridge, turn, restore_before=False)

        self.assertEqual(result.after, self.after)
        self.assertEqual(bridge.state, self.after)
        self.assertNotIn("Main_openProject", self.call_names(bridge))
        self.assertFalse(result.diagnostics["reloaded"])
        self.assertFalse(result.diagnostics["baseline_verified"])

    def test_clean_no_change_skips_reload(self):
        bridge = FakeBridge(self.before)

        result = self.execute(bridge, chat_result)

        self.assertFalse(result.diagnostics["changed"])
        self.assertFalse(result.diagnostics["reloaded"])
        self.assertTrue(result.diagnostics["baseline_verified"])
        self.assertNotIn("Main_openProject", self.call_names(bridge))

    def test_hidden_state_count_change_forces_reload(self):
        bridge = FakeBridge(self.before)

        def turn():
            bridge.state_change_count += 1
            return chat_result()

        result = self.execute(bridge, turn)

        self.assertFalse(result.diagnostics["changed"])
        self.assertTrue(result.diagnostics["reloaded"])
        self.assertEqual(self.call_names(bridge).count("Main_openProject"), 1)

    def test_modified_prepared_project_is_rejected_before_turn(self):
        bridge = FakeBridge(self.before, dirty=True)
        ran = []

        with self.assertRaisesRegex(GoldLiveError, "already modified"):
            self.execute(bridge, lambda: ran.append(True) or chat_result())

        self.assertFalse(ran)
        self.assertNotIn("Main_openProject", self.call_names(bridge))

    def test_wrong_project_is_rejected_before_turn(self):
        bridge = FakeBridge(self.before, project=r"A:\Music\user-project.rpp")
        ran = []

        with self.assertRaisesRegex(GoldLiveError, "active project changed"):
            self.execute(bridge, lambda: ran.append(True) or chat_result())

        self.assertFalse(ran)
        self.assertNotIn("Main_openProject", self.call_names(bridge))

    def test_turn_failure_reloads_partial_changes(self):
        bridge = FakeBridge(self.before)

        def turn():
            bridge.set_state(self.after)
            raise RuntimeError("transport broke")

        with self.assertRaisesRegex(GoldLiveError, "Agent turn failed: transport broke"):
            self.execute(bridge, turn)

        self.assertEqual(bridge.state, self.before)
        self.assertEqual(self.call_names(bridge).count("Main_openProject"), 1)

    def test_after_snapshot_failure_reloads_clean_copy(self):
        bridge = FakeBridge(self.before)
        calls = {"count": 0}

        def flaky_snapshotter(current_bridge):
            calls["count"] += 1
            if calls["count"] == 2:
                raise RuntimeError("snapshot bridge failed")
            return fake_snapshotter(current_bridge)

        def turn():
            bridge.set_state(self.after)
            return chat_result()

        with self.assertRaisesRegex(GoldLiveError, "snapshot bridge failed"):
            execute_live_run(
                bridge,
                PROJECT,
                self.before,
                turn,
                snapshotter=flaky_snapshotter,
            )

        self.assertEqual(bridge.state, self.before)
        self.assertEqual(self.call_names(bridge).count("Main_openProject"), 1)

    def test_post_turn_diagnostic_failure_still_reloads(self):
        bridge = FakeBridge(self.before)
        bridge.fail_change_count_read = 2

        def turn():
            bridge.set_state(self.after)
            return chat_result()

        with self.assertRaisesRegex(GoldLiveError, "state count failed"):
            self.execute(bridge, turn)

        self.assertEqual(bridge.state, self.before)
        self.assertEqual(self.call_names(bridge).count("Main_openProject"), 1)

    def test_unconfirmed_active_turn_is_not_reloaded(self):
        bridge = FakeBridge(self.before)

        def turn():
            bridge.set_state(self.after)
            raise GoldTurnActiveError("turn still active")

        with self.assertRaisesRegex(GoldTurnActiveError, "still active"):
            self.execute(bridge, turn)

        self.assertEqual(bridge.state, self.after)
        self.assertNotIn("Main_openProject", self.call_names(bridge))

    def test_project_switch_fails_closed_without_opening_another_project(self):
        bridge = FakeBridge(self.before)

        def turn():
            bridge.set_state(self.after)
            bridge.project = r"A:\Music\other.rpp"
            return chat_result()

        with self.assertRaisesRegex(GoldLiveError, "fixture reload also failed"):
            self.execute(bridge, turn)

        self.assertNotIn("Main_openProject", self.call_names(bridge))
        self.assertEqual(bridge.project, r"A:\Music\other.rpp")

    def test_reload_must_restore_before_snapshot(self):
        bridge = FakeBridge(self.before)
        bridge.reload_state = snapshot(
            [{"name": "Unexpected", "items": [], "fx": []}]
        )

        def turn():
            bridge.set_state(self.after)
            return chat_result()

        with self.assertRaisesRegex(GoldLiveError, "did not restore before.json"):
            self.execute(bridge, turn)

    def test_reloaded_project_must_be_clean(self):
        bridge = FakeBridge(self.before)
        bridge.reload_dirty = 1

        def turn():
            bridge.set_state(self.after)
            return chat_result()

        with self.assertRaisesRegex(GoldLiveError, "still modified"):
            self.execute(bridge, turn)

    def test_declared_success_requires_structured_final_completion(self):
        completed = [
            {"type": "final", "text": "done"},
            {"type": "loop_done", "reason": "final"},
            {"type": "done", "cancelled": False},
        ]
        self.assertTrue(_declared_success(completed))
        self.assertFalse(
            _declared_success(
                [
                    {"type": "final", "text": "not done"},
                    {"type": "loop_done", "reason": "max_steps"},
                    {"type": "done", "cancelled": False},
                ]
            )
        )
        self.assertFalse(
            _declared_success(
                completed[:-1] + [{"type": "done", "cancelled": True}]
            )
        )
        self.assertFalse(_declared_success(completed + [{"type": "error"}]))

    def test_gateway_chat_records_actual_permission_outcome_and_mode(self):
        client = GatewayChatClient(
            "http://127.0.0.1:8770",
            "test-token",
            timeout=2,
            permission_decider=lambda _event: True,
        )
        events = [
            {"type": "mode_active", "mode": "composition"},
            {
                "type": "tool_call",
                "id": "call-1",
                "name": "render_to_wav",
                "arguments": {"out_path": "A:/outside.wav"},
            },
            {
                "type": "permission_request",
                "id": "permission-1",
                "name": "render_to_wav",
                "arguments": {"out_path": "A:/outside.wav"},
            },
            {
                "type": "permission_result",
                "id": "permission-1",
                "outcome": "deny",
            },
            {"type": "final", "text": "stopped safely"},
            {"type": "loop_done", "reason": "final"},
            {"type": "done", "cancelled": False},
        ]

        def fake_request(path, _body, timeout=None):
            del timeout
            if path == "/api/chat":
                return FakeHTTPResponse(lines=sse_lines(*events))
            if path == "/api/permission":
                return FakeHTTPResponse(payload={"ok": True})
            raise AssertionError("unexpected request: %s" % path)

        with patch.object(client, "_request", side_effect=fake_request):
            result = client.run(
                "test",
                "gold-test-thread",
                True,
                "composition",
            )
        self.assertEqual(
            result.authorizations,
            [{"call_id": "call-1", "decision": "deny"}],
        )
        self.assertTrue(result.declared_success)

    def test_gateway_chat_rejects_wrong_active_mode(self):
        client = GatewayChatClient(
            "http://127.0.0.1:8770",
            "test-token",
            timeout=2,
        )
        response = FakeHTTPResponse(
            lines=sse_lines({"type": "mode_active", "mode": "mix"})
        )
        cancelled = []
        with patch.object(client, "_request", return_value=response), patch.object(
            client,
            "cancel",
            side_effect=lambda thread_id: cancelled.append(thread_id) or {
                "ok": True,
                "found": False,
            },
        ):
            with self.assertRaisesRegex(GoldLiveError, "instead of"):
                client.run("test", "wrong-mode", True, "composition")
        self.assertIn("wrong-mode", cancelled)

    def test_gateway_chat_enforces_overall_deadline_despite_heartbeats(self):
        client = GatewayChatClient(
            "http://127.0.0.1:8770",
            "test-token",
            timeout=0.05,
        )
        response = BlockingHTTPResponse()
        cancelled = []
        started = time.monotonic()
        with patch.object(client, "_request", return_value=response), patch.object(
            client,
            "cancel",
            side_effect=lambda thread_id: cancelled.append(thread_id) or {
                "ok": True,
                "found": False,
            },
        ):
            with self.assertRaisesRegex(GoldLiveError, "overall deadline"):
                client.run("test", "deadline-test", True, "composition")
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertIn("deadline-test", cancelled)

    def test_windows_project_paths_compare_case_insensitively(self):
        self.assertTrue(
            _same_path(
                r"X:\workspace\RUN\project.rpp",
                r"x:/workspace/run/project.rpp",
            )
        )
        self.assertFalse(
            _same_path(
                r"X:\workspace\RUN\project.rpp",
                r"X:\workspace\RUN\other.rpp",
            )
        )

    def test_sse_block_parser_preserves_event_name_and_sequence(self):
        event = _decode_sse_block(
            [
                "id: 12",
                "event: tool_result",
                '{"placeholder":"ignored"}',
                'data: {"name":"reaper_status","is_error":false}',
            ]
        )
        self.assertEqual(event["type"], "tool_result")
        self.assertEqual(event["seq"], 12)

    def test_measurement_extraction_merges_supported_analysis_sections(self):
        events = [
            {
                "type": "tool_call",
                "id": "render-1",
                "name": "render_to_wav",
                "arguments": {},
            },
            {
                "type": "tool_result",
                "id": "render-1",
                "name": "render_to_wav",
                "is_error": False,
                "content": r"A:\Temp\gold-after.wav",
            },
            {
                "type": "tool_call",
                "id": "analysis-1",
                "name": "analyze_audio",
                "arguments": {"path": "a:/temp/GOLD-AFTER.wav"},
            },
            {
                "type": "tool_result",
                "id": "analysis-1",
                "name": "analyze_audio",
                "is_error": False,
                "content": json.dumps(
                    {
                        "analysis": {
                            "loudness": {"true_peak_dbtp": -1.2},
                            "clipping": {"clipped_samples": 0},
                        }
                    }
                ),
            },
            {
                "type": "tool_call",
                "id": "loudness-1",
                "name": "measure_loudness",
                "arguments": {"path": r"A:\Temp\gold-after.wav"},
            },
            {
                "type": "tool_result",
                "id": "loudness-1",
                "name": "measure_loudness",
                "is_error": False,
                "content": json.dumps(
                    {"measurements": {"loudness": {"integrated_lufs": -14.1}}}
                ),
            },
        ]
        self.assertEqual(
            measurements_from_events(events),
            {
                "loudness": {
                    "true_peak_dbtp": -1.2,
                    "integrated_lufs": -14.1,
                },
                "clipping": {"clipped_samples": 0},
            },
        )

    def test_measurement_extraction_rejects_truncated_result(self):
        events = [
            {
                "type": "tool_call",
                "id": "render",
                "name": "render_to_wav",
                "arguments": {},
            },
            {
                "type": "tool_result",
                "id": "render",
                "name": "render_to_wav",
                "is_error": False,
                "content": r"A:\Temp\gold.wav",
            },
            {
                "type": "tool_call",
                "id": "analysis",
                "name": "analyze_audio",
                "arguments": {"path": r"A:\Temp\gold.wav"},
            },
            {
                "type": "tool_result",
                "id": "analysis",
                "name": "analyze_audio",
                "is_error": False,
                "truncated": True,
                "content": "{",
            },
        ]
        with self.assertRaisesRegex(GoldLiveError, "truncated"):
            measurements_from_events(events)

    def test_measurement_extraction_ignores_wrong_path_and_pre_edit_render(self):
        events = [
            {
                "type": "tool_call",
                "id": "render",
                "name": "render_to_wav",
                "arguments": {},
            },
            {
                "type": "tool_result",
                "id": "render",
                "name": "render_to_wav",
                "is_error": False,
                "content": r"A:\Temp\before.wav",
            },
            {
                "type": "tool_call",
                "id": "analysis",
                "name": "analyze_audio",
                "arguments": {"path": r"A:\Temp\other.wav"},
            },
            {
                "type": "tool_result",
                "id": "analysis",
                "name": "analyze_audio",
                "is_error": False,
                "content": json.dumps(
                    {"analysis": {"loudness": {"integrated_lufs": -14}}}
                ),
            },
            {
                "type": "tool_call",
                "id": "edit",
                "name": "set_fx_param",
                "arguments": {"track_index": 0},
            },
            {
                "type": "tool_result",
                "id": "edit",
                "name": "set_fx_param",
                "is_error": False,
                "content": "ok",
            },
        ]
        self.assertEqual(measurements_from_events(events), {})


if __name__ == "__main__":
    unittest.main()
