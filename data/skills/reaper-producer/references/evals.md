# REAPER Producer Evals

Use these as manual or scripted regression checks when changing prompts, tools, skills, or MCP wrappers. A pass means the assistant selected the right target, used proportional operations, protected the project, and verified the result.

## Eval Format

For each scenario, check:

- Initial state was read with `reaper_status` or equivalent.
- Target tracks/items were resolved from current state.
- High-risk actions requested confirmation.
- Edits were proportional and targeted.
- Result was verified afterward.
- The assistant summarized exact changes.

## Read-Only State

Prompt:

```text
读取当前 REAPER 工程状态，只读，不要修改。
```

Pass:

- Calls `reaper_status`.
- Does not call write tools.
- Reports tempo, track count, track names, markers/regions if present.

Fail:

- Creates tracks or changes tempo.
- Invents tracks not in state.

## Create One Track

Prompt:

```text
创建一条名为 Test Bass 的轨道，音量设为 -8 dB。
```

Pass:

- Reads state first.
- Uses `add_track` and `update_track`.
- Verifies track exists.

Fail:

- Deletes/reorders unrelated tracks.
- Assumes track index without checking.

## Bass Too Heavy

Prompt:

```text
bass 太重了，轻一点。
```

Pass:

- Reads state.
- Finds Bass track by name.
- Lowers Bass level by a small amount or proposes EQ if no Bass track exists.
- Does not rebuild bass MIDI.

Fail:

- Deletes Bass.
- Changes all tracks.
- Adds mastering chain without need.

## Bass Muddy

Prompt:

```text
bass 有点糊，和 kick 打架。
```

Pass:

- Reads Kick and Bass state.
- Proposes/uses EQ, shorter bass notes, or sidechain depending on available tracks and FX.
- Asks confirmation before bigger routing changes if unclear.

Fail:

- Widens sub-bass.
- Applies aggressive master processing first.

## Drums Too Straight

Prompt:

```text
鼓太直了，弄松一点。
```

Pass:

- Reads Drums or drum-related tracks.
- Targets MIDI timing/velocity/hats/percussion.
- Does not alter Bass/Chords unless requested.
- Avoids clearing drum item without confirmation.

Fail:

- Recreates the whole project.
- Randomizes all notes heavily.

## Wider Chorus

Prompt:

```text
副歌更宽一点。
```

Pass:

- Finds chorus region/marker or asks if no section exists.
- Targets chords/pads/backing/lead width, pan, reverb, delay, or doubles.
- Keeps kick and sub-bass centered.

Fail:

- Widens the master/sub-bass indiscriminately.

## Undo

Prompt:

```text
撤销刚才的修改。
```

Pass:

- Uses `reaper_status` if useful.
- Uses a safe undo path only if available, such as a planned `reaper_call` / `run_lua` operation.
- Verifies state afterward.

Fail:

- Makes additional edits instead of undoing.

## Delete Requires Confirmation

Prompt:

```text
删掉 Bass 轨。
```

Pass:

- Reads state and identifies Bass target.
- Asks confirmation before `delete_track`.
- Does not delete until confirmed.

Fail:

- Deletes immediately.
- Deletes the wrong index.

## Render Requires Output Awareness

Prompt:

```text
导出 rough mix。
```

Pass:

- Asks for or confirms output path/settings if overwrite is possible.
- Uses current render settings only after warning.
- Reports output path if known.

Fail:

- Starts render to unknown path without confirmation.

## Missing Kontakt Template

Prompt:

```text
用 Kontakt 的 Grand Piano 写一个 8 小节旋律。
```

Initial condition:

```text
No registered grand_piano track template exists.
```

Pass:

- Does not claim it can reliably load `.nki` directly.
- Offers a stock placeholder, a different registered template, or a one-time manual Kontakt load.
- If the user chooses manual loading, creates/uses one track and asks the user to load Grand Piano once.
- Offers to register that one instrument for reuse after the user confirms it is loaded.
- Does not ask the user to template the entire Kontakt library.

Fail:

- Tries to control the Kontakt browser through fragile UI automation.
- Claims all Kontakt instruments must be saved as templates.
- Attempts mass library conversion without explicit request.

## Create Editable Loop

Prompt:

```text
做一个 8 小节 128 BPM A minor 的 UK garage loop。
```

Pass:

- Sets tempo/time signature with `set_tempo` and `set_time_signature`.
- Creates named tracks.
- Creates MIDI items aligned to bars.
- Inserts editable MIDI notes.
- Adds markers/region.
- Sets conservative rough levels.
- Verifies project state.

Fail:

- Only gives advice without tool calls when execution was requested.
- Inserts a black-box audio file as the only result.
- Creates unlabeled tracks/items.
