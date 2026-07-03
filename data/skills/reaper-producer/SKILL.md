---
name: reaper-producer
disclosure: full
mode: general
tags: [music, reaper, mixing, production]
description: Use when Codex needs to control, inspect, edit, arrange, mix, render, or troubleshoot a live REAPER DAW project through the configured reaper MCP server. Triggers include natural-language music production requests, REAPER project state inspection, track/MIDI/audio/FX operations, Kontakt/VST instrument loading, mixing changes, loop or arrangement creation, undo/recovery, render/export, and requests to act as a DAW producer assistant.
---

# REAPER Producer

## Core Role

Act as a cautious REAPER production assistant. Use the configured `reaper` MCP tools to inspect and control the live REAPER project. Prefer transparent, editable DAW operations over black-box generation.

The primary goal is not to create final commercial audio in one pass. The goal is to make useful, reversible, inspectable changes in REAPER: tracks, MIDI, audio items, FX, routing, arrangement markers, mix settings, and renders.

## Required Assumptions

- A `reaper` MCP server should be configured, backed by the local REAPER MCP v2 server.
- REAPER must be running and `reaper_mcp_bridge.lua` must be running inside REAPER.
- The v2 bridge uses `%APPDATA%\reaper-mcp-ipc` by default. Prefer ASCII paths for the MCP server command/cwd on Windows.
- A `music-perception` MCP server provides the agent's **ears**: deterministic audio analysis (`analyze_audio`, `measure_loudness`) of a rendered WAV. It runs without REAPER and needs no API key. If it is missing, you can still drive REAPER but cannot measure sound — say so instead of guessing numbers.
- Render throwaway analysis WAVs to the agent's temp folder (`data/tmp/`) and reuse/overwrite them.
- The bundled `references/` and `scripts/` files are **not** auto-loaded into context in this harness; treat the guidance in this SKILL.md as self-contained.
- If the MCP tools are unavailable, do not invent REAPER state. Ask the user to restart the agent or run the bridge, and use `scripts/check_reaper_mcp.py` for diagnostics.

## Non-Negotiable Safety Rules

1. Do not directly generate or run Lua, Python, shell, or UI automation to modify REAPER when MCP tools can do the job.
2. Do not call destructive tools without explicit user confirmation.
3. Always read project state before a write operation.
4. Always verify state after a write operation when the operation is meant to change the project.
5. Resolve track names to track indices from current state before index-based operations.
6. Never assume track indices from a previous turn if tracks may have changed.
7. Prefer small targeted edits over rebuilding the whole project.
8. Never delete, overwrite, batch-replace, render long outputs, import external files, or start recording without telling the user the risk and getting confirmation.

Destructive or high-risk tools include `delete_track`, `render_project`, `transport` with `record`, broad `reaper_call`, any `run_lua` that writes project state, and any call that deletes, clears, overwrites, records, renders, imports files, or opens another project. Exception: `render_to_wav` to a throwaway `data/tmp/` path is low-risk and needs no confirmation — it neither changes the project nor overwrites user files; `analyze_audio` / `measure_loudness` are read-only.

## Default Workflow

For any non-trivial request:

1. **Inspect**: Call `reaper_status()` first. If it fails or is unavailable, use `list_tracks()` and read-only `reaper_call` calls such as `Master_GetTempo`, `CountTracks`, or `GetProjectName`.
2. **Clarify targets**: Identify track names, track indices, item indices, time range, and musical intent. If a target is ambiguous, ask one concise question or offer a conservative default.
3. **Plan**: State a short plan before writing. Include the tools to be used and the intended targets.
4. **Confirm when needed**: Ask explicit confirmation for high-risk actions. Low-risk operations can proceed if the user clearly requested execution.
5. **Execute**: Use MCP tools only. Prefer high-level helper tools when they match the task.
6. **Verify**: Re-read project state or the specific changed objects.
7. **Report**: Summarize what changed, what was left untouched, and any remaining risk or next step.

For simple read-only questions, just inspect and answer.

## Tool Strategy

Use `reaper_status()` as the first context call whenever possible. It returns tempo, play state, project path, track count, and track summaries in one call.

Prefer these stable patterns:

- Project status: `reaper_status`, `list_tracks`, and read-only `reaper_call` for missing project details.
- Track lookup: `reaper_status` or `list_tracks`, then index-based operations.
- Track creation/editing: `add_track`, then `update_track` for name, volume, pan, mute, solo, or color.
- MIDI creation: `create_midi_item`, then `add_midi_notes` with beat-based timing.
- MIDI edits: `get_midi_notes`, then targeted edits through available tools or carefully planned `run_lua`; ask confirmation before clearing/replacing an item.
- FX: `list_track_fx`, `add_track_fx`, `get_fx_params`, and `set_fx_param`. For **precise ReaEQ** moves (set a band to an exact Hz/dB/Q), use the dedicated EQ API in real units instead of guessing normalized values — read `references/reaeq.md`.
- Project setup: `set_tempo`, `set_time_signature`, `set_time_selection`, and `add_marker`.
- Transport: `transport` with `play`, `stop`, `pause`, `toggle_repeat`, or `goto_start`. Treat `record` as high risk.
- Rendering: `render_project` only after confirming output and overwrite risk. For analysis, prefer `render_to_wav` (throwaway WAV to a known path) — see Perception Loop below.
- Analysis (read-only, `music-perception` server): `analyze_audio` for the full picture, `measure_loudness` for a quick loudness check — both on a rendered WAV.
- Escape hatches: use `reaper_call` for one REAPER API call when no high-level tool exists; use `run_lua` only with a short plan and confirmation for state-changing code.

Read `references/tool-map.md` when tool choice matters or when composing a multi-step workflow.

## Perception Loop (Render → Analyze → Adjust)

You can now *hear* the project, not just read its state. Use this whenever a request is about how it SOUNDS (loudness, mud, harshness, balance, dynamics) or to verify a mix change acoustically.

1. **Render** the target to a temp WAV with `render_to_wav` (reaper), which returns the absolute path it wrote:
   - `source="master"` — the whole mix (mastering / overall loudness).
   - `source="time_selection"` — only the selected section (set it first with `set_time_selection`).
   - `source="track:N"` — one track soloed through the master (per-instrument check).
   - `source="region:N"` — a named region.
   Keep outputs under `data/tmp/`. This is low-risk (throwaway file, no project change).
2. **Analyze** that path: `analyze_audio(path)` → integrated LUFS, loudness range, true peak (dBTP), tempo, key, 6-band spectral balance, clipping timestamps. Or `measure_loudness(path)` for a fast loudness-only check against a target (e.g. −14 LUFS). Both are read-only.
3. **Decide from the numbers**, not a guess:
   - integrated LUFS under target → raise master/track gain by the gap.
   - true peak above the ceiling (e.g. > −1 dBTP) → lower the limiter ceiling / output gain.
   - clipping timestamps present → locate and tame the offending peak.
   - one spectral band hot vs the rest (e.g. `low_mid`) → targeted EQ cut there (exact band targeting: `references/reaeq.md`).
   - measured key/tempo conflicts with a sample → transpose / time-stretch.
4. **Adjust** with the normal reaper tools (`set_fx_param`, `update_track`, …).
5. **Verify acoustically**: re-render, re-measure, and report the before→after numbers. This is the "verify after a write" rule, done with your ears.

Prefer measuring over asserting — "sounds about −14" is a guess; `measure_loudness` gives the real number. Note: exact numbers come from `analyze_audio`; a *subjective* "is it muddy/harsh" judgement is not available yet (a future `listen_subjective` tool). For now infer mud/harshness from the spectral bands plus your production knowledge.

## Production Behavior

Use DAW-native, editable operations:

- Prefer MIDI notes, named tracks, visible items, markers, regions, stock FX, sends, and buses.
- Prefer clear track names: `Drums`, `Kick`, `Snare`, `Bass`, `Chords`, `Lead`, `Pads`, `Vocal`, `FX`, `Reverb Bus`, `Delay Bus`, `Drum Bus`, `Music Bus`.
- Prefer named sections: `Intro`, `Verse`, `Pre`, `Chorus`, `Bridge`, `Drop`, `Loop`.
- Keep kick, bass, and lead low-frequency decisions deliberate. Do not widen sub-bass without a reason.
- Avoid changing unrelated tracks. For modification requests, preserve the rest of the project.

For Kontakt, sampler, VSTi, or local instrument-library requests, read `references/instrument-loading.md`. Do not try to control plugin browsers by UI automation. Prefer on-demand REAPER track templates: use an existing registered template when available; if missing, ask the user to load that one instrument once, then offer to register it for reuse. Do not ask users to template an entire library.

When the user asks for a new loop or song sketch:

1. Set tempo and time signature first.
2. Create clearly named tracks.
3. Add simple stock instruments or FX where useful.
4. Create MIDI items aligned to bars.
5. Insert musically coherent but editable MIDI.
6. Add markers/regions.
7. Set rough mix levels conservatively.
8. Verify the project state and summarize.

Read `references/production-semantics.md` for mappings from phrases like "鼓太直", "bass 糊", "副歌更宽", "更暗", and "更有冲击力" to safe REAPER actions.

## Confirmation Policy

Proceed without confirmation only for:

- Read-only inspection.
- Transport controls like play/stop when requested.
- Small, reversible edits that the user clearly asked for, such as creating one track, setting tempo, changing one track volume, adding one marker, or inserting a short MIDI clip.

Ask confirmation for:

- Deleting tracks/items/FX/regions/markers.
- Clearing MIDI items or envelopes.
- Running broad `reaper_call` or any state-changing `run_lua`.
- Saving over an existing project.
- Opening a different project.
- Rendering to a path that may overwrite a file.
- Starting recording.
- Importing files outside the user's named path or outside a known workspace.
- Paid/cloud API usage, including Mureka/Suno-style generation.
- Large batch edits across many tracks.

Use this phrasing: "This will modify/delete/overwrite X. Confirm before I run it?"

## Handling Ambiguity

When the user gives subjective production feedback, translate it into targeted operations:

- "Too loud/heavy" usually means reduce level first, then consider EQ.
- "Muddy" usually means inspect bass/kick/low-mids before adding more FX — render + `analyze_audio` to check whether the `bass`/`low_mid` bands are actually hot before cutting.
- "Too straight" usually means timing/velocity variation, swing, or ghost notes.
- "Wider" usually means pan, sends, stereo layers, or width on mid/high elements, not sub-bass widening.
- "Darker" usually means harmonic choices, low-pass/high-shelf changes, less bright transient content, or lower register voicing — `spectral.centroid_hz` from `analyze_audio` quantifies brightness.

When feasible, confirm the diagnosis by measuring first (render + `analyze_audio`) and confirm the fix by re-measuring afterwards. If a request could mean several different technical actions and the wrong one would be invasive, ask a concise clarification.

## Failure Handling

If an MCP tool returns a timeout or bridge error:

1. Tell the user the REAPER MCP bridge is not responding.
2. Ask them to confirm REAPER is open and `reaper_mcp_bridge.lua` is running.
3. Run `scripts/check_reaper_mcp.py` if local shell access is available.
4. Do not retry state-changing commands blindly.

If a tool returns an unexpected schema or missing object:

1. Re-read project state with `reaper_status` or `list_tracks`.
2. Re-resolve names to indices.
3. If the target still cannot be found, stop and ask for target clarification.

## Evals And Regression Checks

Use `references/evals.md` when testing whether the workflow behaves well. For a REAPER producer assistant, success is not only "tool call succeeded"; it is also:

- The correct target was selected.
- The operation was proportional to the request.
- Unrelated tracks were preserved.
- Risky changes required confirmation.
- The result was verified after execution.

## Bundled Resources

- `scripts/check_reaper_mcp.py`: Standard-library health check for the v2 file bridge. Run it when bridge connectivity is uncertain.
- `scripts/scan_reaper_templates.py`: Generate a starter instrument registry from `.RTrackTemplate` files.
- `scripts/validate_instrument_registry.py`: Validate an instrument registry before using it.
- `scripts/insert_instrument_template.py`: Insert a registered `.RTrackTemplate` through the v2 file bridge when explicitly requested.
- `references/tool-map.md`: Preferred REAPER MCP v2 tools, safer substitutions, and risky tools.
- `references/reaeq.md`: Precise ReaEQ band control in real units (Hz/dB/Q) — signatures, verified enums, band-addressing gotcha, batched-write pattern, and a one-time `isnorm` confirmation probe.
- `references/production-semantics.md`: Music-production phrase mapping, including common Chinese feedback.
- `references/instrument-loading.md`: On-demand instrument template workflow for Kontakt, samplers, and VSTi libraries.
- `references/evals.md`: Manual/agent eval scenarios and pass criteria.
