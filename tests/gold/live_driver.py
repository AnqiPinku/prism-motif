"""Live REAPER + Gateway driver for deterministic Gold Task evidence.

The structural scorer stays offline.  This module owns the stateful boundary:
it verifies the exact prepared project, captures stable snapshots, and reloads
the disposable project copy without saving after evidence collection.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import ntpath
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from .runner import _write_json, score_run
from .schemas import GoldSchemaError, validate_snapshot


class GoldLiveError(GoldSchemaError):
    """Raised when a live run cannot be isolated or verified safely."""


class GoldTurnActiveError(GoldLiveError):
    """Raised when Gateway cancellation cannot confirm that a turn stopped."""


@dataclass
class ChatResult:
    """Structured result of one Gateway Agent turn."""

    events: list
    authorizations: list
    final_text: str
    declared_success: bool
    duration_seconds: float


@dataclass
class LiveRunResult:
    """Snapshots and diagnostics produced by one isolated live run."""

    chat: ChatResult
    after: dict
    diagnostics: dict


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _project_state(snapshot):
    return {
        key: value
        for key, value in snapshot.items()
        if key not in ("project", "measurements")
    }


def project_states_equal(left, right):
    """Compare stable project state while excluding evidence-only metadata."""
    return _canonical(_project_state(left)) == _canonical(_project_state(right))


def _normalized_path(value):
    """Return a stable path identity, including Windows paths on any test host."""
    value = str(value or "")
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return ntpath.normcase(ntpath.normpath(value))
    return os.path.normcase(os.path.abspath(value))


def _same_path(left, right):
    return bool(left and right) and _normalized_path(left) == _normalized_path(right)


def _number(value, digits=9):
    value = float(value)
    nearest = round(value)
    if abs(value - nearest) < 1e-8:
        return int(nearest)
    return round(value, digits)


def _current_project(bridge):
    result = bridge.call("EnumProjects", [-1, "", 4096])
    if not isinstance(result, list) or len(result) < 2:
        raise GoldLiveError("REAPER did not return the active project handle and path")
    handle, path = result[0], result[1]
    if not path or path == "(unsaved)":
        raise GoldLiveError("REAPER active project is unsaved")
    return handle, str(path)


def _time_to_beats(bridge, project_handle, seconds):
    result = bridge.call(
        "TimeMap2_timeToBeats",
        [project_handle, float(seconds), 0, 0, 0, 0],
    )
    if not isinstance(result, list) or len(result) < 4:
        raise GoldLiveError("REAPER did not return full-beat timing")
    return _number(result[3])


def _normalized_notes(raw_notes):
    notes = []
    for raw in raw_notes or []:
        note = {
            "pitch": int(raw["pitch"]),
            "start_beats": _number(raw["start_beats"]),
            "length_beats": _number(raw["length_beats"]),
            "velocity": int(raw.get("velocity", 96)),
            "channel": int(raw.get("channel", 0)),
        }
        if raw.get("muted") is True:
            note["muted"] = True
        notes.append(note)
    return notes


def _snapshot_markers(bridge, project_handle):
    counts = bridge.call("CountProjectMarkers", [project_handle])
    if not isinstance(counts, list) or len(counts) < 3:
        raise GoldLiveError("REAPER did not return marker counts")
    markers = []
    for index in range(int(counts[1]) + int(counts[2])):
        raw = bridge.call(
            "EnumProjectMarkers3",
            [project_handle, index, False, 0, 0, "", 0, 0],
        )
        if not isinstance(raw, list) or len(raw) < 7 or not raw[0]:
            raise GoldLiveError("REAPER marker enumeration stopped unexpectedly")
        marker = {
            "name": str(raw[4]),
            "position_beats": _time_to_beats(bridge, project_handle, raw[2]),
            "is_region": bool(raw[1]),
            "index": int(raw[5]),
        }
        if raw[1]:
            marker["region_end_beats"] = _time_to_beats(
                bridge, project_handle, raw[3]
            )
        if int(raw[6]):
            marker["color"] = int(raw[6])
        markers.append(marker)
    return markers


def snapshot_project(bridge, measurements=None):
    """Capture a stable, UI-independent snapshot from the active REAPER project."""
    project_handle, project_path = _current_project(bridge)
    summary = bridge.call("get_project_summary")
    if not isinstance(summary, dict) or not _same_path(summary.get("project"), project_path):
        raise GoldLiveError("REAPER project changed while capturing its summary")
    signature = bridge.call(
        "TimeMap_GetTimeSigAtTime", [project_handle, 0, 0, 0, 0]
    )
    if not isinstance(signature, list) or len(signature) < 2:
        raise GoldLiveError("REAPER did not return the project time signature")

    tracks = []
    raw_tracks = bridge.call("list_tracks")
    if not isinstance(raw_tracks, list):
        raise GoldLiveError("REAPER did not return a track list")
    for raw_track in raw_tracks:
        track_index = int(raw_track["index"])
        track_handle = bridge.call("GetTrack", [project_handle, track_index])
        fx = bridge.call("list_track_fx", [track_index])
        if not isinstance(fx, list):
            raise GoldLiveError("REAPER did not return the FX chain for track %d" % track_index)
        normalized_fx = [
            {
                "name": str(item.get("name", "")),
                "enabled": bool(item.get("enabled", True)),
            }
            for item in fx
        ]

        items = []
        for item_index in range(int(raw_track.get("item_count", 0))):
            item_handle = bridge.call(
                "GetTrackMediaItem", [track_handle, item_index]
            )
            position = float(
                bridge.call("GetMediaItemInfo_Value", [item_handle, "D_POSITION"])
            )
            length = float(
                bridge.call("GetMediaItemInfo_Value", [item_handle, "D_LENGTH"])
            )
            start_beats = _time_to_beats(bridge, project_handle, position)
            end_beats = _time_to_beats(bridge, project_handle, position + length)
            take_handle = bridge.call("GetActiveTake", [item_handle])
            is_midi = bool(take_handle and bridge.call("TakeIsMIDI", [take_handle]))
            item = {
                "type": "midi" if is_midi else "audio",
                "position_beats": start_beats,
                "length_beats": _number(float(end_beats) - float(start_beats)),
                "notes": (
                    _normalized_notes(
                        bridge.call("get_midi_notes", [track_index, item_index])
                    )
                    if is_midi
                    else []
                ),
            }
            if not is_midi and take_handle:
                source_handle = bridge.call(
                    "GetMediaItemTake_Source", [take_handle]
                )
                source_path = bridge.call(
                    "GetMediaSourceFileName", [source_handle, "", 4096]
                )
                if isinstance(source_path, list):
                    source_path = source_path[-1] if source_path else ""
                if source_path:
                    item["source"] = ntpath.basename(str(source_path))
            items.append(item)

        tracks.append(
            {
                "name": str(raw_track["name"]),
                "volume_db": float(raw_track["volume_db"]),
                "pan": float(
                    bridge.call(
                        "GetMediaTrackInfo_Value", [track_handle, "D_PAN"]
                    )
                ),
                "mute": bool(raw_track.get("mute", False)),
                "solo": bool(raw_track.get("solo", False)),
                "fx": normalized_fx,
                "items": items,
            }
        )

    snapshot = {
        "project": project_path,
        "tempo_bpm": _number(summary["tempo_bpm"]),
        "time_signature": [int(signature[0]), int(signature[1])],
        "tracks": tracks,
        "markers": _snapshot_markers(bridge, project_handle),
        "measurements": copy.deepcopy(measurements or {}),
    }
    return validate_snapshot(snapshot, "live snapshot")


def load_reaper_bridge(server_path=None):
    """Load the sibling reaper-mcp Bridge client without adding a dependency."""
    if server_path is None:
        prism_home = Path(os.environ.get("PRISM_HOME") or Path(__file__).resolve().parents[3])
        server_path = prism_home / "mcps" / "reaper-mcp" / "server" / "reaper_mcp_server.py"
    server_path = Path(server_path).resolve()
    if not server_path.is_file():
        raise GoldLiveError("reaper-mcp server was not found: %s" % server_path)
    spec = importlib.util.spec_from_file_location("prism_gold_reaper_mcp", server_path)
    if spec is None or spec.loader is None:
        raise GoldLiveError("could not load reaper-mcp Bridge: %s" % server_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Bridge()


def _decode_sse_block(lines):
    data = []
    event_name = ""
    event_id = ""
    for line in lines:
        if not line or line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "data":
            data.append(value)
        elif field == "event":
            event_name = value
        elif field == "id":
            event_id = value
    if not data:
        return None
    payload = json.loads("\n".join(data))
    if not isinstance(payload, dict):
        raise GoldLiveError("Gateway SSE data must decode to an object")
    if not payload.get("type") and event_name:
        payload["type"] = event_name
    if event_id and not payload.get("seq"):
        try:
            payload["seq"] = int(event_id)
        except ValueError:
            pass
    return payload


def _declared_success(events):
    """Use terminal loop state, not the mere presence of final text."""
    finals = [event for event in events if event.get("type") == "final"]
    loop_done = [event for event in events if event.get("type") == "loop_done"]
    done_events = [event for event in events if event.get("type") == "done"]
    if any(event.get("type") == "error" for event in events):
        return False
    if not finals or not loop_done or not done_events:
        return False
    if done_events[-1].get("cancelled"):
        return False
    return loop_done[-1].get("reason") == "final"


class GatewayChatClient:
    """Small authenticated SSE client for the local Prism Motif Gateway."""

    def __init__(
        self,
        base_url,
        session_token,
        timeout=180,
        provider=None,
        permission_decider=None,
    ):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost"):
            raise GoldLiveError("Gold live Gateway must be a local HTTP endpoint")
        if not session_token:
            raise GoldLiveError("Gateway session token is required")
        self.base_url = base_url.rstrip("/")
        self.session_token = session_token
        self.timeout = float(timeout)
        if self.timeout <= 0:
            raise GoldLiveError("Gateway timeout must be positive")
        self.provider = provider
        self.permission_decider = permission_decider

    def _request(self, path, body, timeout=None):
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Prism-Session": self.session_token,
            },
        )
        return urllib.request.urlopen(
            request,
            timeout=self.timeout if timeout is None else float(timeout),
        )

    def switch_mode(self, required_mode):
        """Select the task mode before running the prepared Gold task."""
        if required_mode not in ("composition", "arrangement", "mix"):
            raise GoldLiveError("invalid required Gold mode: %s" % required_mode)
        try:
            with self._request(
                "/api/mode/switch",
                {"mode": required_mode},
                timeout=min(self.timeout, 10.0),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
            raise GoldLiveError("Gateway mode switch failed: %s" % exc) from exc
        if not isinstance(payload, dict) or payload.get("current") != required_mode:
            raise GoldLiveError(
                "Gateway did not activate required mode %s" % required_mode
            )
        return payload

    def cancel(self, thread_id):
        """Request cancellation of one running Gateway turn."""
        try:
            with self._request(
                "/api/chat/cancel",
                {"thread_id": thread_id},
                timeout=min(self.timeout, 5.0),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            return {"ok": False, "cancel_requested": False}
        return payload if isinstance(payload, dict) else {
            "ok": False,
            "cancel_requested": False,
        }

    def wait_for_turn_stop(self, thread_id, timeout=None):
        """Poll the cancellation endpoint until Gateway removes the turn."""
        wait_seconds = (
            min(max(self.timeout, 0.1), 5.0)
            if timeout is None
            else max(float(timeout), 0.0)
        )
        deadline = time.monotonic() + wait_seconds
        while True:
            status = self.cancel(thread_id)
            if status.get("ok") is True and status.get("found") is False:
                return True
            if status.get("found") is not True or time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    @staticmethod
    def _matching_call_id(events, permission_event):
        target_name = permission_event.get("name")
        target_arguments = permission_event.get("arguments") or {}
        for event in reversed(events):
            if event.get("type") != "tool_call":
                continue
            if event.get("name") != target_name:
                continue
            if (event.get("arguments") or {}) == target_arguments:
                return event.get("id") or event.get("call_id")
        return None

    def run(self, goal, thread_id, trust_mode, required_mode):
        """Run one Agent turn and return all SSE evidence."""
        body = {
            "goal": goal,
            "provider": self.provider,
            "thread_id": thread_id,
            "bypass": bool(trust_mode),
        }
        started = time.time()
        deadline = time.monotonic() + self.timeout
        events = []
        authorizations = []
        pending_permissions = {}
        block = []
        deadline_reached = threading.Event()
        finished = threading.Event()
        response_box = {"response": None}

        def enforce_deadline():
            remaining = max(0.0, deadline - time.monotonic())
            if finished.wait(remaining):
                return
            deadline_reached.set()
            self.cancel(thread_id)
            response = response_box.get("response")
            if response is not None:
                try:
                    response.close()
                except OSError:
                    pass

        watcher = threading.Thread(target=enforce_deadline, daemon=True)
        watcher.start()
        try:
            with self._request(
                "/api/chat",
                body,
                timeout=min(self.timeout, 10.0),
            ) as response:
                response_box["response"] = response
                for raw_line in response:
                    if deadline_reached.is_set() or time.monotonic() >= deadline:
                        raise GoldLiveError(
                            "Gateway turn exceeded %.1f second overall deadline"
                            % self.timeout
                        )
                    line = raw_line.decode("utf-8", "replace").rstrip("\r\n")
                    if line:
                        block.append(line)
                        continue
                    event = _decode_sse_block(block)
                    block = []
                    if event is None:
                        continue
                    events.append(event)
                    if event.get("type") == "mode_active":
                        if event.get("mode") != required_mode:
                            raise GoldLiveError(
                                "Gateway turn activated mode %r instead of %r"
                                % (event.get("mode"), required_mode)
                            )
                    if event.get("type") == "permission_request":
                        allow = bool(
                            self.permission_decider(event)
                            if self.permission_decider is not None
                            else False
                        )
                        with self._request(
                            "/api/permission",
                            {"id": event.get("id"), "allow": allow},
                            timeout=min(self.timeout, 5.0),
                        ) as permission_response:
                            permission_response.read()
                        call_id = self._matching_call_id(events, event)
                        if call_id and event.get("id"):
                            pending_permissions[event["id"]] = call_id
                    elif event.get("type") == "permission_result":
                        call_id = pending_permissions.pop(event.get("id"), None)
                        outcome = event.get("outcome")
                        if call_id and outcome in ("allow", "deny"):
                            authorizations.append(
                                {
                                    "call_id": call_id,
                                    "decision": outcome,
                                }
                            )
                if block:
                    event = _decode_sse_block(block)
                    if event is not None:
                        events.append(event)
                if deadline_reached.is_set() or time.monotonic() >= deadline:
                    raise GoldLiveError(
                        "Gateway turn exceeded %.1f second overall deadline"
                        % self.timeout
                    )
        except GoldLiveError as exc:
            self.cancel(thread_id)
            if not self.wait_for_turn_stop(thread_id):
                raise GoldTurnActiveError(
                    "Gateway turn did not confirm cancellation; automatic project "
                    "reload is unsafe"
                ) from exc
            raise
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
            self.cancel(thread_id)
            if not self.wait_for_turn_stop(thread_id):
                raise GoldTurnActiveError(
                    "Gateway turn did not confirm cancellation; automatic project "
                    "reload is unsafe"
                ) from exc
            if deadline_reached.is_set() or time.monotonic() >= deadline:
                raise GoldLiveError(
                    "Gateway turn exceeded %.1f second overall deadline"
                    % self.timeout
                ) from exc
            raise GoldLiveError("Gateway turn failed: %s" % exc) from exc
        finally:
            finished.set()
            response_box["response"] = None

        terminals = [event for event in events if event.get("type") in ("done", "error")]
        if not terminals or terminals[-1].get("type") not in ("done", "error"):
            raise GoldLiveError("Gateway SSE ended without a terminal event")
        finals = [event.get("text", "") for event in events if event.get("type") == "final"]
        mode_events = [event for event in events if event.get("type") == "mode_active"]
        if not mode_events:
            raise GoldLiveError("Gateway turn did not report its active mode")
        elapsed = max(
            [float(event.get("elapsed_ms", 0)) for event in events] or [0]
        ) / 1000.0
        return ChatResult(
            events=events,
            authorizations=authorizations,
            final_text=finals[-1] if finals else "",
            declared_success=_declared_success(events),
            duration_seconds=max(elapsed, time.time() - started),
        )


def _assert_active_project(bridge, expected_path, expected_handle=None):
    handle, path = _current_project(bridge)
    if not _same_path(path, expected_path):
        raise GoldLiveError(
            "REAPER active project changed: expected %s, got %s"
            % (expected_path, path)
        )
    if expected_handle is not None and handle != expected_handle:
        raise GoldLiveError("REAPER active project handle changed during the live run")
    return handle, path


def _reload_prepared_project(bridge, expected_project, before, snapshotter):
    """Discard the disposable copy's live edits and verify its on-disk baseline."""
    _assert_active_project(bridge, expected_project)
    bridge.call("Main_openProject", ["noprompt:" + str(expected_project)])
    project_handle, _ = _assert_active_project(bridge, expected_project)
    restored = snapshotter(bridge)
    if not project_states_equal(restored, before):
        raise GoldLiveError(
            "reloading the prepared project did not restore before.json"
        )
    if int(bridge.call("IsProjectDirty", [project_handle])):
        raise GoldLiveError("reloaded prepared project is still modified")
    return restored


def execute_live_run(
    bridge,
    expected_project,
    before,
    run_turn,
    *,
    restore_before=True,
    snapshotter=snapshot_project,
):
    """Run against one clean disposable project copy and optionally reload it."""
    project_handle, project_path = _assert_active_project(bridge, expected_project)
    live_before = snapshotter(bridge)
    if not project_states_equal(live_before, before):
        raise GoldLiveError("live REAPER state does not match before.json")
    dirty_before = int(bridge.call("IsProjectDirty", [project_handle]))
    if dirty_before:
        raise GoldLiveError("prepared REAPER project is already modified")
    change_count_before = int(
        bridge.call("GetProjectStateChangeCount", [project_handle])
    )

    try:
        chat = run_turn()
        if not isinstance(chat, ChatResult):
            raise GoldLiveError("live chat callback did not return ChatResult")
        _assert_active_project(bridge, project_path, project_handle)
        after = snapshotter(bridge)
        change_count_after = int(
            bridge.call("GetProjectStateChangeCount", [project_handle])
        )
        dirty_after = int(bridge.call("IsProjectDirty", [project_handle]))
    except GoldTurnActiveError:
        raise
    except Exception as exc:  # noqa: BLE001 - restore the disposable copy first
        try:
            _reload_prepared_project(bridge, project_path, live_before, snapshotter)
        except Exception as restore_exc:  # noqa: BLE001
            raise GoldLiveError(
                "Agent turn failed and fixture reload also failed: %s" % restore_exc
            ) from exc
        raise GoldLiveError("Agent turn failed: %s" % exc) from exc

    changed = not project_states_equal(after, live_before)
    diagnostics = {
        "project": project_path,
        "changed": changed,
        "change_count_before": change_count_before,
        "change_count_after": change_count_after,
        "dirty_before": dirty_before,
        "dirty_after": dirty_after,
        "reloaded": False,
        "baseline_verified": False,
    }

    if restore_before:
        if changed or dirty_after or change_count_after != change_count_before:
            _reload_prepared_project(bridge, project_path, live_before, snapshotter)
            diagnostics["reloaded"] = True
        diagnostics["baseline_verified"] = True
    return LiveRunResult(chat, after, diagnostics)


def _merge_dict(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_dict(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


_READ_ONLY_EVIDENCE_TOOLS = frozenset(
    (
        "reaper_status",
        "list_tracks",
        "get_midi_notes",
        "list_track_fx",
        "list_fx_presets",
        "list_installed_fx",
        "get_fx_params",
        "analyze_audio",
        "measure_loudness",
        "transcribe_melody",
        "listen_subjective",
    )
)


def _call_mutates_project(name, arguments):
    if name == "render_to_wav":
        return False
    if name == "batch":
        calls = (arguments or {}).get("calls") or []
        return any(
            _call_mutates_project(call.get("func"), call.get("arguments") or {})
            for call in calls
            if isinstance(call, dict)
        )
    return bool(name) and name not in _READ_ONLY_EVIDENCE_TOOLS


def _rendered_path(content):
    if isinstance(content, str):
        value = content.strip()
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            decoded = value
    else:
        decoded = content
    if isinstance(decoded, str):
        return decoded.strip()
    if isinstance(decoded, dict):
        for key in ("path", "out_path", "output"):
            if isinstance(decoded.get(key), str):
                return decoded[key].strip()
    return ""


def measurements_from_events(events):
    """Extract measurements bound to the latest post-edit analysis render."""
    measurements = {}
    accepted = {"analyze_audio", "measure_loudness"}
    calls = {}
    current_render = ""
    for event in events:
        if event.get("type") == "tool_call":
            call_id = event.get("id") or event.get("call_id")
            if call_id:
                calls[call_id] = event
            continue
        if event.get("type") != "tool_result" or event.get("is_error", False):
            continue
        name = event.get("name")
        call = calls.get(event.get("id") or event.get("call_id"), {})
        arguments = call.get("arguments") or {}
        if _call_mutates_project(name, arguments):
            current_render = ""
            measurements = {}
            continue
        if name == "render_to_wav":
            current_render = _rendered_path(event.get("content"))
            measurements = {}
            continue
        if name not in accepted:
            continue
        if event.get("truncated"):
            raise GoldLiveError(
                "%s result was truncated; full measurement evidence is required"
                % name
            )
        analyzed_path = arguments.get("path")
        if not current_render or not _same_path(analyzed_path, current_render):
            continue
        content = event.get("content")
        try:
            payload = json.loads(content) if isinstance(content, str) else content
        except (TypeError, ValueError) as exc:
            raise GoldLiveError("%s returned invalid JSON evidence" % name) from exc
        if not isinstance(payload, dict):
            raise GoldLiveError("%s returned non-object measurement evidence" % name)
        for wrapper in ("measurements", "analysis", "result"):
            if isinstance(payload.get(wrapper), dict):
                payload = payload[wrapper]
                break
        useful = {
            key: value
            for key, value in payload.items()
            if key in ("loudness", "clipping", "spectral")
        }
        _merge_dict(measurements, useful)
    return measurements


def run_live(
    run_dir,
    bridge,
    chat_client,
    *,
    trust_mode=False,
    restore_before=True,
    thread_id=None,
):
    """Run a prepared Gold task live, write evidence.json, and score it."""
    run_dir = Path(run_dir).resolve()
    task_path = run_dir / "task.json"
    before_path = run_dir / "before.json"
    project_path = run_dir / "project.rpp"
    for path in (task_path, before_path, project_path):
        if not path.is_file():
            raise GoldLiveError("prepared run is missing %s" % path.name)
    task = json.loads(task_path.read_text(encoding="utf-8"))
    before = json.loads(before_path.read_text(encoding="utf-8"))
    if not _same_path(before.get("project"), project_path):
        raise GoldLiveError("before.json does not point at the prepared project")

    required_mode = task.get("required_mode")
    chat_client.switch_mode(required_mode)
    if task.get("require_tool_error_recovery"):
        raise GoldLiveError(
            "task %s requires deterministic fault injection, which this live "
            "driver does not yet provide" % task["id"]
        )

    thread_id = thread_id or (
        "gold-%s-%s" % (task["id"], uuid.uuid4().hex[:12])
    )
    live_run = execute_live_run(
        bridge,
        str(project_path),
        before,
        lambda: chat_client.run(
            task["goal"],
            thread_id,
            bool(trust_mode),
            required_mode,
        ),
        restore_before=restore_before,
    )
    live_run.after["measurements"] = measurements_from_events(
        live_run.chat.events
    )
    evidence = {
        "after": live_run.after,
        "events": live_run.chat.events,
        "authorizations": live_run.chat.authorizations,
        "trust_mode": bool(trust_mode),
        "declared_success": live_run.chat.declared_success,
        "final_text": live_run.chat.final_text,
        "duration_seconds": live_run.chat.duration_seconds,
        "driver": live_run.diagnostics,
    }
    _write_json(run_dir / "evidence.json", evidence)
    report = score_run(run_dir)
    return {"evidence": evidence, "report": report}
