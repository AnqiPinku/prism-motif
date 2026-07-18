# Precise ReaEQ Band Control

When a request needs an *exact* EQ move — "cut 3 kHz by 4 dB on the vocal",
"high-pass the bass at 40 Hz", "narrow bell at 250 Hz" — drive ReaEQ through
REAPER's dedicated EQ API instead of guessing normalized `set_fx_param` values.
These functions take **real units** (Hz, dB, Q); REAPER does the non-linear
curve conversion internally, so the agent never computes log curves itself.

## Functions (ReaScript, as shipped in this REAPER)

Call via `reaper_call` (one API call) or `run_lua` (many, atomic). Signatures
confirmed against the local binding (`reaper_python.py`):

- `TrackFX_GetEQ(track, instantiate) -> fxidx`
  Index of ReaEQ in the track's FX chain. `instantiate=true` inserts a ReaEQ if
  none exists; returns -1 if absent and not instantiating.
- `TrackFX_SetEQParam(track, fxidx, bandtype, bandidx, paramtype, val, isnorm) -> bool`
  Set one band parameter. Returns false if the FX at `fxidx` is not ReaEQ.
- `TrackFX_GetEQParam(track, fxidx) -> retval, bandtype, bandidx, paramtype, normval`
  Returns a **normalized** value, not Hz/dB. To read a band back in real units,
  read the formatted display string instead (see Verify).
- `TrackFX_SetEQBandEnabled(track, fxidx, bandtype, bandidx, enable) -> bool`
  and `TrackFX_GetEQBandEnabled(track, fxidx, bandtype, bandidx) -> bool`.

`track` is a MediaTrack handle — get it once with
`reaper_call("GetTrack", [0, trackIndex])` and reuse the returned
`{"__handle": "hN"}` in every following call.

## Enumerations (verified)

- **bandtype**: `-1` master gain · `0` hipass · `1` low shelf · `2` band (bell) ·
  `3` notch · `4` high shelf · `5` lopass
- **bandidx**: `0` = first band of that type, `1` = second band of that type, …
- **paramtype**: `0` freq (Hz) · `1` gain (dB) · `2` Q

## Band-addressing gotcha

Bands are addressed by **(bandtype, Nth-of-that-type)** — NOT by the band's
visible left-to-right position in the ReaEQ window. With two bells,
`bandtype=2, bandidx=0` is the first bell and `bandidx=1` the second. A ReaEQ
inserted via `instantiate=true` starts with a default band layout; if you need a
specific layout, inspect or (re)build it rather than assuming positions.

## isnorm

Pass `isnorm=false` to set `val` in real units (Hz / dB / Q). `isnorm=true`
treats `val` as normalized 0..1.

> The real-units meaning of `isnorm=false` is REAPER's long-standing convention
> but is not spelled out in the API docs, and the EQ *getter* returns only
> normalized values. Do not trust the write blindly — always Verify (below).
> A one-time confirmation probe is at the end of this file.

## Efficient pattern (one handle, batched writes)

Once the track handle and the ReaEQ `fxidx` are known (from `list_track_fx`, or
`TrackFX_GetEQ`), set every band parameter in ONE round-trip with `batch`.
Example — on the ReaEQ at `fxidx=0`, set the first bell to 3 kHz / −4 dB / Q 2:

```json
{"func":"batch","args":[[
  {"func":"TrackFX_SetEQParam","args":[{"__handle":"h1"}, 0, 2, 0, 0, 3000, false]},
  {"func":"TrackFX_SetEQParam","args":[{"__handle":"h1"}, 0, 2, 0, 1, -4,   false]},
  {"func":"TrackFX_SetEQParam","args":[{"__handle":"h1"}, 0, 2, 0, 2, 2.0,  false]}
]]}
```

Arg order per call: `track, fxidx, bandtype, bandidx, paramtype, val, isnorm`.

Note: a handle or `fxidx` produced *inside* a batch is not addressable by a
later call in the SAME batch (you don't know its id until it returns). So get
the track handle and `fxidx` in a prior step, then batch the writes. When you
also need to insert the ReaEQ and set it atomically, use a single short
`run_lua` instead (get track → `TrackFX_GetEQ(track, true)` → set bands).

## Verify (mandatory — satisfies the skill's "verify after write" rule)

The EQ getter is normalized, so verify with the formatted display strings of the
underlying params: `get_fx_params(track_index, fx_index)` returns every param with a
`formatted` field (e.g. `"3.0 kHz"`, `"-4.0 dB"`). Scan it to confirm the band
landed where intended, and report the before→after values to the user.

## Safety

Setting EQ params is a reversible mix edit — low risk, no confirmation needed for
a targeted change the user asked for. But instantiating ReaEQ across many tracks,
or sweeping EQ over the whole project, is a large batch edit → confirm first
(see the skill's Confirmation Policy).

## One-time isnorm confirmation probe

Run once with REAPER open and the bridge running; check that the returned
`formatted` for the freq param is ≈ 3 kHz:

```json
{"func":"run_lua","code":"local tr=reaper.GetTrack(0,0); if not tr then return 'no track 0' end; local fx=reaper.TrackFX_GetEQ(tr,true); reaper.TrackFX_SetEQParam(tr,fx,2,0,0,3000,false); local out={}; for i=0,reaper.TrackFX_GetNumParams(tr,fx)-1 do local _,nm=reaper.TrackFX_GetParamName(tr,fx,i,''); local _,fmt=reaper.TrackFX_GetFormattedParamValue(tr,fx,i,''); if nm:lower():find('freq') then out[#out+1]={param=nm, formatted=fmt} end end; return out"}
```

- Formatted ≈ `3000` / `3.0 kHz` → `isnorm=false` is real units. This whole file
  is correct as written.
- Formatted is a normalized number (e.g. `0.6`) → `isnorm=false` is NOT real
  units on this build. Switch to writing normalized values, and a small
  dedicated EQ-band bridge helper (doing the Hz→norm curve conversion) becomes worth
  adding to the bridge after all.
