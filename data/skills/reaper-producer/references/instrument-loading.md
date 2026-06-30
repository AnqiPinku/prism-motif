# Instrument Loading

Use this reference for Kontakt, sampler libraries, VST instruments, and requests like "use piano", "load strings", "用古筝", or "use my Kontakt library".

## Core Rule

Do not try to control plugin browsers directly. Prefer REAPER track templates that already contain the loaded instrument.

This is the stable public workflow:

```text
instrument request
-> find registered track template
-> insert template
-> write MIDI / adjust mix
```

If no template exists:

```text
create or select a suitable track
-> add the plugin if useful
-> ask the user to load that one instrument manually
-> after the user confirms it is loaded, offer to register/save it for reuse
```

Do not ask the user to template an entire library. Register instruments on demand.

## Why Templates

Kontakt and many sampler plugins do not reliably expose "load this .nki/.preset" as a normal REAPER FX parameter. A REAPER track template can preserve the plugin state, track name, routing, MIDI channel setup, volume, color, and optional FX.

Track templates do not duplicate the full sample library. They store project/plugin state and references to the library content. They are usually much smaller than the original samples.

## User-Facing Explanation

When a requested instrument is not registered, explain briefly:

```text
I can add Kontakt, but I cannot reliably choose the .nki inside Kontakt through MCP.
Please load this one instrument in the Kontakt window once. After that I can help register the track as a reusable template, so next time I can insert it directly.
```

Keep it practical. Do not give a long lecture unless the user asks.

## Template Registry Concept

A public/open-source setup should use a user-local registry such as:

```json
{
  "version": 1,
  "instruments": [
    {
      "id": "grand_piano",
      "display_name": "Grand Piano",
      "aliases": ["piano", "钢琴", "grand"],
      "family": "keys",
      "roles": ["chords", "melody"],
      "template_path": "${REAPER_RESOURCE_PATH}/TrackTemplates/Kontakt/Grand Piano.RTrackTemplate",
      "default_track_name": "Piano",
      "default_volume_db": -10,
      "tags": ["kontakt", "acoustic", "editable-midi"]
    }
  ]
}
```

Do not hard-code one user's Kontakt library path in the skill. Use user-local config, examples, and variables.

## Loading Existing Templates

When a matching `.RTrackTemplate` is already known:

1. Read project state.
2. Confirm the target instrument/template.
3. Insert the track template through the available MCP/tooling. With REAPER MCP v2, use `scripts/insert_instrument_template.py` or a carefully planned `reaper_call` / `run_lua` call to REAPER's `Main_openProject` for `.RTrackTemplate` paths.
4. Re-read track state and identify the newly inserted track.
5. Rename, color, set volume, and write MIDI as needed.

Use `Main_openProject` only for `.RTrackTemplate` files in this context. Do not use it to open `.RPP` projects unless the user explicitly requests and confirms.

## Missing Template Workflow

If the requested instrument is not registered:

1. Offer a fallback:
   - use a simple stock placeholder such as ReaSynth,
   - create a Kontakt/VSTi track and ask the user to load the instrument manually,
   - or use a different registered instrument.
2. If the user chooses manual loading, create a clearly named track and add the plugin if possible.
3. Ask the user to load the specific instrument in the plugin UI.
4. After the user confirms it is loaded, offer to register/save that one track as a reusable template.
5. Do not attempt broad library scanning or mass template creation without explicit request.

## Registration Policy

Register only instruments that the user actually wants to reuse. Good first choices:

- grand piano
- upright piano
- acoustic/electronic drum kit
- electric bass
- strings ensemble
- choir
- pad
- lead synth
- guzheng
- erhu
- pipa

Avoid creating dozens or hundreds of templates up front.

## Open-Source Guidance

For a GitHub release:

- Ship example registries, not real user paths.
- Do not include commercial `.nki`, samples, `.nicnt`, or proprietary presets.
- Support any plugin through track templates, not only Kontakt.
- Treat direct plugin-internal loading as experimental.
- Prefer "template missing" guidance over fragile UI automation.
