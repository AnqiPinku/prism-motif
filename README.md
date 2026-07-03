# Prism Motif

An offline-friendly desktop AI music-agent that plays with your REAPER project — composes, arranges, mixes, and listens back. Built as a native Windows app on top of Python + Tauri + React, driving REAPER through a Lua bridge and analyzing audio with a permissive DSP stack.

Runs 100% on your machine (no cloud lock-in): a text LLM is the brain, deterministic MIR + Google Gemini's audio model are the ears, and REAPER is the hands.

---

## What it looks like

The main window is a three-mode workspace — Composition / Arrangement / Mix — with a project-style sidebar, an M3-styled title bar, and a chat panel where you talk to a persona shaped by the current mode.

*(Screenshots go here once we have a public build.)*

---

## Features

**Three teaching-style modes.** Click a chip in the title bar; the agent's system persona, skill set, and tool discipline swap to match.

- **Composition** — proposes BPM / key / progression defaults, drops a 4-bar MIDI motif in, then explains the "why" so you learn. Uses `transcribe_melody` for humming→MIDI, `add_midi_notes` to write, `add_marker` to timestamp iterations.
- **Arrangement** — picks a form template (pop / lo-fi / EDM / ambient / ballad), marks sections in the timeline, discovers what instrument plugins you actually have installed (`list_installed_fx`), designs an energy curve.
- **Mix** — measure-then-adjust workflow: renders → `analyze_audio` (LUFS + tempo + key + spectral bands) → `listen_subjective` (Gemini's mood/harshness/muddy verdict) → picks fixes → re-measures. Targets platform LUFS (Spotify -14, EDM -9, classical -18) and never guesses without numbers.

**Ten mode-scoped skills.** Each mode ships with three specialist skills plus a shared `reaper-producer` persona; skills auto-toggle when you switch mode.

**Full REAPER control** via the sibling `reaper-mcp` server + a Lua bridge auto-loaded through `__startup.lua`. Read/write MIDI in beats, render selections, add FX by name, list installed plugins, switch presets — all through a stdio JSON-RPC MCP.

**Deterministic audio perception** (`music-perception-mcp`, permissive DSP):
- `analyze_audio` — integrated LUFS, loudness range, true peak (scipy 4× oversampled), tempo, Krumhansl key, six spectral bands + centroid/rolloff.
- `measure_loudness` — quick LUFS-only pass.
- `transcribe_melody` — monophonic librosa pyin → beats-native MIDI notes at the DAW tempo.
- `listen_subjective` — Google Gemini (or any OpenAI-compatible relay) as an audio LLM: mood, muddy/harsh/sibilant/bright scores, timestamped issues.

**Hard-won reliability work under the hood.** SSE is close-delimited on HTTP/1.0 (fixes the 6-turn wedge), streaming supports real cancellation via `TurnCancelled`, delta events coalesce in a 50 ms window (long replies stop stuttering), mid-stream provider errors retry idempotently, tool_result gets truncated to 2 KB on the wire (full text fetched on demand), permissions timeout cleanly with a `permission_result` event, thread archives are atomic and thread-safe. Details in the commit history.

**Native shell.** Frameless M3-styled titlebar, project-style sidebar with archive, rainbow-arc app icon, single-instance guard, visible startup errors instead of a 45 s hang.

---

## Install

### From an MSI (recommended for non-developers)

Grab `Prism Motif_0.1.0_x64_en-US.msi` from the [Releases](../../releases) page and double-click. About 147 MB. Installs bundled CPython + a frozen perception sidecar + the app itself; API keys stay in Windows Credential Manager (OS-level).

You still need to install REAPER separately (this drives REAPER, it isn't a replacement) and reload the bridge inside REAPER when the app asks — one click in onboarding.

### From source (for hacking on it)

```powershell
# 1. Clone this repo and the two MCP siblings into a shared parent directory
mkdir Prismcode; cd Prismcode
git clone https://github.com/AnqiPinku/prism-motif.git
mkdir mcps; cd mcps
git clone https://github.com/AnqiPinku/reaper-mcp-v2.git reaper-mcp
git clone https://github.com/AnqiPinku/music-perception-mcp.git

# 2. Install the perception stack (permissive, pure pip, no ffmpeg)
cd music-perception-mcp
pip install -r requirements.txt

# 3. Build the frontend
cd ../../prism-motif/frontend
npm ci
npm run build

# 4. Run in dev mode (system Python + repo gateway)
cd src-tauri
cargo run --release
```

Dev mode looks for Python at `A:/Python310/python.exe` and the gateway at `A:/Prismcode/prism-motif/gateway/server.py` — edit `frontend/src-tauri/src/lib.rs` `spawn_gateway` to point at your paths, or drop bundled CPython at `frontend/src-tauri/resources/python/` for the packaged codepath.

### Build a distributable MSI yourself

```powershell
# 1. Stage: pre-clean stage_pkg output + freeze perception + bundle CPython
python packaging/stage_pkg.py
cd ../mcps/music-perception-mcp
python packaging/build_sidecar.py

# 2. Drop python-build-standalone 3.10 install_only at src-tauri/resources/python/
#    (see docs — install keyring into it: python.exe -m pip install keyring)

# 3. Build
cd ../../prism-motif/frontend
npx tauri build
# → target/release/bundle/msi/Prism Motif_0.1.0_x64_en-US.msi
```

---

## Configuration

- **REAPER**: any recent version works; the bridge is auto-loaded through `__startup.lua`.
- **LLM API key**: any OpenAI-compatible endpoint. Configured in the settings dialog; stored in Windows Credential Manager, never in a file.
- **Gemini audio API key**: for `listen_subjective`. Same storage. `GEMINI_BASE_URL` defaults to a placeholder — point it at Google's endpoint or an OpenAI-compatible relay of your choice.

The three system-prompt personas live in `config/modes.json` and are open to edit if you want to tune the voice.

---

## Repository layout

```
prism-motif/
├── gateway/            HTTP + SSE gateway (Python stdlib)
├── core/               ReAct loop, LLM streaming, skill loader, thread archive, keyring
├── config/             MCP server config, mode definitions, settings template
├── data/skills/        10 SKILL.md files driving the three-mode workflow
├── frontend/           React 19 + Vite + Tauri 2 shell
│   └── src-tauri/      Rust shell (frameless titlebar, single-instance, gateway supervisor)
├── packaging/          stage_pkg.py — sanitizes what actually goes into a build
├── AGENTS.md           historical design notes (not the current agent contract)
├── DESIGN.md           architecture snapshot
└── NOTES.md            implementation notes across milestones
```

The sibling MCP servers live in separate repos: **[reaper-mcp-v2](https://github.com/AnqiPinku/reaper-mcp-v2)** (REAPER control + Lua bridge) and **[music-perception-mcp](https://github.com/AnqiPinku/music-perception-mcp)** (audio analysis + transcription + Gemini listening).

---

## License

MIT — see [LICENSE](LICENSE). Use freely, fork freely, sell if you can build something someone will pay for.
