# REAPER MCP v2 Tool Map

Use this reference when selecting REAPER MCP v2 tools. Prefer project-aware, reversible, high-level workflows over broad escape hatches.

## First Call

Use `reaper_status()` first for almost every production task. It returns the open project path, tempo, play state, track count, and track summaries.

Fallback read-only calls:

- `list_tracks`
- `reaper_call` with safe read-only functions such as `CountTracks`, `Master_GetTempo`, `GetProjectName`, or `GetPlayState`

Do not invent project state if the bridge is unavailable.

## Track Operations

Preferred flow for creating a track:

1. `reaper_status()` or `list_tracks()`.
2. `add_track(name, index)` where `index` is optional.
3. `update_track(index, name, volume_db, pan, mute, solo, color)` for final settings.
4. `list_tracks()` or `reaper_status()` to verify.

For edits, always resolve the current track index from the current state by track name. Do not assume indices from old context.

`delete_track(index)` requires explicit confirmation.

## MIDI Operations

Preferred flow for a new MIDI part:

1. Resolve track index by name.
2. `create_midi_item(track_index, start_beats, length_beats)`.
3. `add_midi_notes(track_index, item_index, notes)`.
4. `get_midi_notes(track_index, item_index)` if verification is needed.

Editing existing notes — pick by scale of change:

- `update_midi_note(track_index, item_index, note_index, ...)`: change one
  note's pitch/timing/velocity in place. Note indices come from
  `get_midi_notes` and may shift after any edit (notes re-sort by time) —
  always re-read before another index-based edit.
- `delete_midi_notes(track_index, item_index, note_indices)`: remove specific
  notes. One undo step; the response echoes what was deleted.
- `replace_midi_notes(track_index, item_index, notes)`: atomically rewrite
  the whole item (delete all + insert the new set, one undo step). Use for
  pitch correction and bulk rewrites.
- `add_midi_notes` APPENDS only — never use it to "overwrite": appending a
  corrected copy leaves the old notes in place and doubles the part.

Use beat-based timing. Keep clips aligned to bar boundaries unless the user asks for loose timing.

## FX Operations

Preferred flow:

1. `list_track_fx(track_index)`.
2. `add_track_fx(track_index, fx_name)` if missing.
3. `get_fx_params(track_index, fx_index)` to discover parameter names/indices.
4. `set_fx_param(track_index, fx_index, param, value)` for targeted changes.

For stock REAPER plugins, prefer:

- `ReaEQ`
- `ReaComp`
- `ReaDelay`
- `ReaVerbate`
- `ReaSynth`
- `ReaSamplOmatic5000`
- `JS: Saturation`

Do not remove FX without confirmation. Prefer bypassing or small parameter changes when testing.

## Project Setup

Use:

- `set_tempo`
- `set_time_signature`
- `set_time_selection`
- `add_marker`

For regions or features not exposed by high-level tools, use `reaper_call` for one safe API call, or `run_lua` only with a short plan. Ask confirmation before state-changing `run_lua` unless the user clearly requested a small reversible edit.

## Transport

Use:

- `transport(action="play")`
- `transport(action="stop")`
- `transport(action="pause")`
- `transport(action="toggle_repeat")`
- `transport(action="goto_start")`

Treat `transport(action="record")` as high risk. Ask confirmation first.

## Rendering

`render_project` can overwrite files depending on REAPER render settings. Confirm:

- output path
- time range
- whether overwrite is acceptable
- whether tails are needed

Do not render long outputs without confirmation.

## Audio Items And Templates

The v2 high-level tool list may not include every audio item or template operation. Use these escalation paths:

- For one REAPER API call: `reaper_call`.
- For a short multi-step operation: `run_lua`, with a plan and confirmation if state-changing.
- For registered track templates: use `scripts/insert_instrument_template.py`, which calls `Main_openProject` through the v2 file bridge.

Do not use broad UI automation to drive plugin browsers.

## Dangerous Tools

Require explicit confirmation before these:

- `delete_track`
- `render_project`
- `transport(action="record")`
- state-changing `run_lua`
- broad `reaper_call`
- any operation that deletes, clears, overwrites, opens another project, records, imports external files, or performs large batch edits

## Safer Substitutions

- Delete track -> mute track or ask confirmation.
- Delete FX -> bypass or ask confirmation.
- Replace MIDI item -> create a new item or ask confirmation before clearing.
- Render -> ask for output path and overwrite confirmation.
- Broad `run_lua` -> use high-level tools where possible, or break the work into explicit smaller steps.
