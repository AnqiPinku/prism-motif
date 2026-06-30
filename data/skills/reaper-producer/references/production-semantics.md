# Production Semantics

Use this reference to translate user-facing music production language into safe REAPER actions. It is a guide, not a rigid rulebook. Inspect the project first and keep edits targeted.

## General Principles

- Prefer level, pan, EQ, send, MIDI velocity, timing, and arrangement changes before destructive edits.
- Preserve unrelated tracks.
- Keep sub-bass mono/center unless the user explicitly asks for experimental sound design.
- When changing mix balance, use small increments first: 1-3 dB.
- When changing MIDI feel, prefer velocity/timing variation over rewriting all notes.

## Common Chinese Feedback

### "鼓太直了" / "鼓太死" / "不够松"

Likely intent: humanize groove.

Safe actions:

- Read Drums/Kick/Snare/Hats track state.
- Add small velocity variation to hats/percussion.
- Slightly delay or advance hats/ghost notes.
- Add swing/shuffle if the MIDI structure supports it.
- Add ghost snare notes sparingly.
- Avoid moving kick/snare anchors too much unless the style calls for it.

Avoid:

- Replacing the entire drum pattern without confirmation.
- Randomizing all drum notes heavily.

### "鼓跳一点" / "更有律动"

Likely intent: more syncopation and groove.

Safe actions:

- Add offbeat hats/percussion.
- Add syncopated kick or percussion fills.
- Vary velocities.
- Add short fills at section boundaries.

### "bass 太重" / "bass 太大"

Likely intent: reduce low-end dominance.

Safe actions:

- Lower Bass volume by 1-3 dB.
- Add or adjust ReaEQ.
- High-pass unnecessary sub-rumble below roughly 25-35 Hz.
- Slightly reduce low-mid buildup around 120-300 Hz if muddy.
- Check kick/bass relationship before broad changes.

Avoid:

- Removing the bassline.
- Widening sub-bass.
- Heavy compression before level/EQ fixes.

### "bass 糊" / "低频糊" / "低频打架"

Likely intent: low-end clarity.

Safe actions:

- Inspect Kick and Bass tracks.
- Reduce bass low-mid buildup.
- Add sidechain compression from Kick to Bass if appropriate.
- Shorten bass note lengths if MIDI is available.
- Reduce overlapping sustain.

### "副歌更宽" / "更开" / "更大"

Likely intent: width and energy in chorus/drop.

Safe actions:

- Add or raise reverb/delay send on chords, pads, backing, or lead.
- Pan supporting layers.
- Add doubled layer if appropriate.
- Increase stereo width on mid/high elements.
- Add section marker/region if missing.

Avoid:

- Widening kick/sub-bass.
- Raising every track equally.

### "lead 少一点" / "主旋律别抢"

Likely intent: reduce lead prominence.

Safe actions:

- Lower lead volume by 1-3 dB.
- Reduce high-mid harshness.
- Lower delay/reverb send if it clouds the vocal/lead focus.
- Remove or thin notes only with confirmation if the MIDI is user-authored.

### "更暗" / "换成更暗的和弦"

Likely intent: darker harmony/timbre.

Safe actions:

- Prefer minor, sus2/sus4, add9, maj7/min7, modal interchange where suitable.
- Move voicings lower or closer.
- Reduce bright high shelf on chords/pads/leads.
- Use low-pass filtering on bright layers.

Avoid:

- Reharmonizing the whole project without confirmation.

### "更有冲击力" / "更炸"

Likely intent: stronger transient/impact.

Safe actions:

- Raise kick/snare slightly.
- Add or tune compression on drum bus.
- Use parallel compression on drums.
- Add saturation lightly.
- Add mastering limiter only with confirmation if it affects the full mix.

### "人声留空间"

Likely intent: make room for vocals.

Safe actions:

- Lower lead/chords/pads in vocal midrange.
- Reduce 1-5 kHz masking on instruments.
- Lower reverb clutter.
- Pan non-vocal elements away from center where appropriate.

## Style Defaults

### UK Garage

- Tempo often around 128-136 BPM.
- Shuffled hats/percussion.
- Syncopated kick patterns.
- Bassline with groove and gaps.
- Chords often stabs, organ, pad, or short keys.

### House

- Four-on-the-floor kick.
- Offbeat hats.
- Bass often sidechained to kick.
- Reverb/delay sends for space.

### Trap

- Half-time feel.
- 808/sub bass centered.
- Fast hi-hat rolls and velocity changes.
- Snare/clap on strong backbeats.

### Lofi

- Softer drums, swing, lower velocity variation.
- Warm chords, low-pass/filtering.
- Gentle saturation/noise if available.

### Dark Pop

- Sparse drums, moody minor harmony.
- Vocal space is priority.
- Controlled low end and atmospheric layers.

### Cyberpunk / Boss Battle

- Driving tempo, strong pulse.
- Aggressive bass/synth layers.
- Distortion/saturation with control.
- Wide high elements, centered low end.

## Reporting Language

After making changes, report concrete actions:

- "Lowered Bass from -6 dB to -8 dB."
- "Added ReaEQ to Bass and reduced low-mids."
- "Humanized hats with small velocity changes."
- "Left Chords and Lead unchanged."

Avoid vague reports such as "I made it better."
