---
name: pitch-correction
disclosure: lazy
mode: composition
tags: [pitch-correction, quantize, melody, scale, midi, transcribe, key-lock, diatonic]
description: 用户把哼唱/口琴/吉他 solo 用 music-perception-mcp 的 transcribe_melody 转成 MIDI 后,音高经常飘半音或落在调外(pyin 是单声道 pitch tracker,人声本来就 pitchy)。触发词:"哼的旋律转 MIDI 有几个音不对"、"quantize 到 C 大调"、"锁调"、"把这段旋律吸附到调式"、"transcribe_melody 出来的 MIDI 有蓝调音要不要保留"、"改调外音"、"pitch correction MIDI"、"snap to scale"、"MIDI 音高吸附"、"旋律吸到音阶"。目标:把粗糙 MIDI 吸附到目标 key + scale,同时保留有音乐意义的调外音(蓝调音、半音经过音、导音、二次属),而不是一刀切全对齐。适用作曲阶段,不含音频 Melodyne 修音。
---

# Pitch Correction (MIDI 锁调)

## When to use

transcribe_melody 出了 MIDI,你在 REAPER 里 `get_midi_notes` 一看,几个音落在 C#、F#、Bb —— 但你要的是 C 大调。或者用户自己用 MIDI 键盘飞快弹的 idea,手滑了几个半音。默认动作立刻做:**分三步锁调 —— 先定 key/scale,再逐音分类"错音 vs 色彩音",最后只改错音、留色彩**。不要一键全 snap:pyin 抓到的蓝小三度(Eb in C major)常是这段最好听的东西,quantize 掉就变白开水。

> **key / scale — 调与音阶**:key 是主音(如 C、A);scale 是音阶模式(major = 1 2 3 4 5 6 7,natural minor = 1 2 b3 4 5 b6 b7)。C major 允许音集合 = {C D E F G A B}。
> **diatonic — 调内音**:属于当前 scale 允许集合的音。反义是 non-diatonic(调外音)。

## Step 1 — 先定 key,不猜

直接跑 `analyze_audio`,拿到形如 `"key: C major, confidence: 0.82"` 的返回。confidence(置信度,0-1,越高越可信)阈值规则:

- confidence ≥ 0.7 → 直接用。
- 0.5 ≤ confidence < 0.7 → 用直方图交叉验证(见下)。
- confidence < 0.5 → 忽略返回值,只用直方图。

直方图判定:`get_midi_notes` 拿全部 pitch,每个 `pitch % 12` 计数,取 top 3。举例:C=12、G=9、E=7 → 主音 C、属音 G、三度 E,判 C major。再看**最后一小节最后一个音**落在哪 —— 落 C → C major,落 A → A minor(两者音集相同,靠落音区分)。

## Step 2 — 逐音分类调外音

调外音有 4 种,处理**完全不同**。术语速盲:

> **半音经过音 (chromatic passing tone)**:两个相邻调内音之间填一个半音,如 C→C#→D。
> **导音 (leading tone)**:比目标音低半音、紧接上行到目标音,常见 F# → G(G 的二次属方向)。
> **二次属 (secondary dominant)**:非主和弦的属功能借用,产生 F#、C# 等临时调外音。
> **vibrato — 颤音**:声乐/管乐正常的 ±30-50 cents 音高波动,pyin 有时抓成一串 1/32 长度的相邻半音。

| 类型 | 例子 (C major) | 特征(要三条都满足) | 处理 |
|---|---|---|---|
| **蓝调三度/七度** | Eb, Bb | ①落在拍点 1 或 3 ②时值 ≥ 八分音符 ③前一个音距它是小三度或大二度以内 | **保留** |
| **半音经过音** | C→C#→D | ①时值 ≤ 十六分音符 ②前一个音距它 1 半音 ③后一个音距它 1 半音且是调内 | **保留** |
| **导音/二次属** | F# 在 G 前 | ①时值 ≤ 八分音符 ②紧接的下一个音正好高 1 半音且是调内 5 度或 1 度 | **保留** |
| **孤立随机半音** | 单个 F#,前后 3 度以上跳且无解决 | 不满足以上任何一组三条 | **吸附** |

吸附规则:改到**距离最近的调内音**。距离相等(如 C# 到 C 和 D 都 1 半音)时向下取(人声/呼吸类乐器抓歪时更常偏高,向下概率对)—— 例:pyin 报 C#4(pitch=61),吸到 C4(60),不吸到 D4(62)。

## Step 3 — REAPER 实操命令序列

以 C major、track 1 为例,严格按顺序:

```
1. add_marker(position_beats=<段落起点>, name="pre-pitch-fix")     # 存档,不留死路
2. notes = get_midi_notes(track_index=1, item_index=0)              # 假设第一个 MIDI item;必要时先枚举
3. 本地代码:对每个 note,判 pitch % 12 ∈ {0,2,4,5,7,9,11}(C major)
4. 对判为"吸附"的音,pitch 改为最近调内音(距离相等向下);其余音原样保留在列表里
5. replace_midi_notes(track_index=1, item_index=0, notes=<完整修正列表>)
   # 原子替换整个 item(删旧 + 插新,一个 undo 步)。绝不能用 add_midi_notes——
   # 它是追加,原错音和修正音会一起响成双份。只改 1-2 个音时也可
   # update_midi_note(note_index=…, pitch=…) 逐音改,注意每改一次索引会重排。
6. render_to_wav(source="track:1", out_path=None)                   # 落 %TEMP%/prism-renders
7. 若用户 track 已挂合成器/采样器,直接渲染;若目标是 Kontakt 音色 ——
   **Kontakt / Omnisphere 等重采样器的具体音色库必须在插件窗口内由用户手动加载**——NI 设计如此,MCP 只能 add_track_fx 挂上宿主,选不了具体 patch。
```

**只改 pitch,不动 velocity(力度,0-127,承载强弱线条),不动 note 时值**。强行 quantize 时值会毁掉 groove(节奏律动感,音符相对拍点的微小偏移),那是另一个 skill(rhythm-quantize)。

## Step 4 — 特殊情形速查

- **小调**:C minor 允许集合 {C D Eb F G Ab Bb}。**Eb (bIII) 是调内**,Step 2 表里的"蓝调三度"规则在小调场景不适用,Eb 直接放行。
- **五声音阶 (pentatonic,五音)**:C major pentatonic = {C D E G A}。若旋律明显五声风格(top 5 频次里没有 F 和 B),把 F 和 B 也当调外音走 Step 2 —— 它们出现即"太钢琴腔",按规则决定留删。
- **转调段**:`analyze_audio` 只返回一个 key。如果第 3-4 小节调外音扎堆(≥ 4 个非 pyin 错误的调外音),分段处理:`set_time_selection(start, end)` + `analyze_audio` 分别定 key。
- **人声 vibrato 溢出**:若看到 ≥ 3 个连续时值 < 十六分音符的相邻半音,直接批量删除(不是吸附,是删)——`delete_midi_notes(note_indices=<这些音的 index>)`,一次调用一个 undo 步,返回值会回显删了什么。这些 100% 是 vibrato 被 pyin 拆成阶梯。transcribe_melody 的 beats-native 平滑通常挡掉大部分,漏网的就这么处理。

## Anti-patterns

- **一键全 snap to scale**。删掉所有蓝调音、半音经过、导音、二次属,旋律变成拜厄练习曲。永远按 Step 2 的四条特征逐音判。
- **无脑信 analyze_audio 的 key**。confidence 0.4 时它就是在猜,必须走直方图交叉验证 —— 别让工具替你拍板。
- **改 pitch 顺手改 velocity 和时值**。三个维度独立,一次只碰一个。velocity 一动,力度起伏线条崩,原来 fp<mp<f 的动态变成一条直线。
- **不打 marker 直接改**。`add_marker("pre-pitch-fix")` 永远先跑,出错至少 undo 有锚点。
- **给用户听修完的版本时不 A/B**。永远 `render_to_wav` 修前 + 修后两段,让用户耳朵判决 —— 你判定的"孤立随机半音"可能正是他要的 hook。
- **在小调里把 bIII 当蓝调音处理**。C minor 的 Eb 是主音阶第三级,不是借来的色彩,吸附掉直接改调性。
