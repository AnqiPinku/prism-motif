---
name: mix-diagnostics
disclosure: lazy
mode: mix
tags: [mix, diagnostics, loudness, LUFS, spectral, listen-subjective, measure-fix-loop, REAPER]
description: 当用户说"混音听起来浑/糊/刺/闷/薄/响度不够/低频打架/人声出不来/母带不达标"或直接问"帮我诊断这首歌的混音/这段音频有什么问题/为什么不好听/怎么修"时触发。也适用于"帮我看看 mix bus 怎么弄、LUFS 不够怎么办、齿音太重、低频糊、人声埋在伴奏里"这类具体投诉。核心是一个闭环:render_to_wav 出音频 → analyze_audio + measure_loudness 拿客观数(LUFS/谱心/tempo/key)→ listen_subjective 拿主观标签+时间戳(muddy/harsh/sibilant/boxy)→ 对着症状→原因→处方表下一刀 → 再渲染再比对。触发词:诊断、混音问题、听不清、太糊、太刺、响度、LUFS、母带、频段打架、mix bus、bus 处理、齿音、人声埋没、低频打架。
---

# Mix Diagnostics — 测量→定位→处方→复测

## When to use
用户送来一段成品/半成品音频(或 REAPER 工程),想知道"这个 mix 有什么问题、怎么修"。默认动作先说给用户听,然后再执行,永远不采用"你觉得哪里不对?"这种反问。默认目标(流媒体投放):integrated LUFS -14 ±0.5(LUFS = Loudness Units Full Scale,一段音频的"感知平均响度",Spotify/Apple Music 都用这个基准),true peak -1.0 dBTP(dBTP = dB True Peak,重采样后的真实峰值,防爆红),LRA 4-8(LRA = Loudness Range,响度动态范围,单位 LU;流行歌 4-8,古典/电影 >10),人声轨 short-term -18~-16 LUFS,60-100Hz 段 RMS 不高于 -6 dBFS。

## 第 0 步:不问,直接跑三件事
用户丢音频/工程过来,立刻开这句:"先渲染整段,30 秒内给你三行结论——响度差多少 dB、谱心偏哪边、AI 主观贴标。看完再决定第一刀切哪。"然后执行:

1. `render_to_wav(out_path=None)` — 省略路径会自动落 `%TEMP%/prism-renders/`,不污染工程。
2. `measure_loudness(path)` — 拿三个数:integrated LUFS、true peak(dBTP)、LRA。
3. `analyze_audio(path)` — 拿 spectral centroid(谱心,单位 Hz,人声流行歌 1.5-3 kHz 正常,>4 kHz 偏刺、<1.2 kHz 偏闷。可以理解成"频谱重心的位置")、tempo、key、频段能量分布。
4. `listen_subjective(path, question="mix problems")` — Gemini 给带时间戳的标签:`0:34 muddy 200Hz` / `1:12 sibilant 7kHz` / `vocal buried -3dB`。

## 术语速查(第一次出现即用)
- **stem** = 分组导出的一路音频(vocal stem、drum stem),不是单轨也不是最终成品。
- **bell / shelf / high-pass**:EQ 的三种形状。bell 是钟形,只影响中间频段,用参数 Q 控制宽窄(Q=1 宽,Q=2 窄);shelf 是搁架式,某个频点以上/以下整体加减;high-pass 是切掉某频点以下的所有内容。
- **side-chain duck**:一轨的音量被另一轨触发压低。伴奏被人声"侧链闪避",让人声出来。
- **de-esser**:专门吃 5-9 kHz 齿音(S/T 的嘶声)的动态处理器。
- **tilt EQ**:一个滑杆,顺时针整体高频+/低频-,逆时针反过来,像跷跷板。
- **胶水(glue)**:mix bus 上轻压 1-2dB gain reduction,让所有轨"听起来像一起录的",不是压扁。

## 症状 → 原因 → 处方表(照抄参数,不要改)

| 症状(主观/AI 标签) | 客观特征 | 原因 | REAPER 处方 |
|---|---|---|---|
| muddy / 糊 / 浑 | 200-400Hz 能量高,谱心 <1.2 kHz | Bass/Kick/吉他低频堆积 | Bass 高通 40Hz(12dB/oct),200-300Hz bell -3dB Q=1.4;吉他 200Hz 以下 shelf -4dB |
| boxy / 纸箱声 | 400-800Hz 凸起 | 房间录音染色 / 廉价话筒 | 人声 500Hz bell -2~-3dB Q=1.8 |
| harsh / 刺 / 尖 | 谱心 >4kHz,2-5kHz 峰 | Cymbal/合成器/失真吉他过亮 | 2.5-3.5 kHz bell -2dB Q=2;整轨 ReaEQ tilt 高频 -1dB |
| sibilant / 齿音重 | 5-9 kHz 瞬态尖峰 | 人声 S/T 过强 | ReaXComp split mode 5-9kHz,threshold -18dB,ratio 4:1 |
| vocal buried / 人声埋没 | 人声 LUFS 比伴奏低 >4dB | 缺侧链 / 缺中频推进 | 人声 3kHz bell +2dB Q=1.5;伴奏 bus 2-4kHz 侧链 duck -2dB |
| 无力 / 薄 | 60-120Hz 能量 <-12dB | Kick/Bass 基频缺失 | Kick 60Hz bell +3dB Q=2;Bass 80-100Hz shelf +2dB |
| 响度不够 | integrated LUFS < -16 | mastering 缺压 | mix bus:ReaComp 4:1 threshold -12 gain +3;末端 LoudMax ceiling -1.0 dBTP,threshold 每次降 1dB 复测,直到 integrated -14 ±0.5 |
| 立体声塌陷 | LR correlation >0.9(左右声道相似度) | 全部单声道乐器 | 吉他双录 pan L60/R60;pad 用 ReaSurroundPan 宽度 130 |

## 第 1 刀之后:强制复测(硬规矩)
改一个参数就再跑 `render_to_wav → measure_loudness → analyze_audio`。判断标准:
- LUFS 差 <0.5dB 且谱心变化 <100Hz → 无效改动,回滚。
- 主观标签消失或降级(如 `very muddy` → `slight low-end build`) → 保留。
- 一次只改一个参数。改 3 个就定位不到哪一刀有效。

## Bus 处理默认起点(不是终点)
用户没有 mix bus 处理时,先塞这一串,每步渲染留档:
先 `list_tracks` 找到 mix bus 轨(常叫 "Mix Bus"/"Bus");REAPER 的 master 总线本身工具不可寻址,真要挂 master 需 `run_lua`(GetMasterTrack)或让用户手动。

1. `add_track_fx(track_index=<mix bus 轨>, fx_name="ReaEQ")` — high-pass 30Hz(切掉次声,人耳听不到只吃动态余量),shelf 10kHz +1dB("空气感")。
2. `add_track_fx(track_index=<mix bus 轨>, fx_name="ReaComp")` — ratio 2:1、threshold -18、attack 30ms、release 100ms、gain +2 —— 目标 1-2dB gain reduction 做胶水,超过 3dB 就是过压,回滚。
3. `add_track_fx(track_index=<mix bus 轨>, fx_name="LoudMax")` 或 `ReaLimit` — ceiling -1.0 dBTP,threshold 每次降 1dB 复测 integrated LUFS,直到 -14 ±0.5 停手,超过就爆。

每步用 `render_to_wav(out_path="master_bus_comp_2to1_thr-18.wav")` 显式命名,方便 A/B 对比。

## Kontakt / 采样器音色的限制
如果诊断说"某乐器音色本身就闷/刺",告诉用户:**Kontakt / Omnisphere 等重采样器的具体音色库必须在插件窗口内由用户手动加载**——NI 设计如此,MCP 只能 add_track_fx 挂上宿主,选不了具体 patch。 请你在 Kontakt 面板里换一个亮一点的 patch(例:Grandeur → Alicia's Keys),我这边继续跑测量。

## Anti-patterns
- **一次给 5 个 EQ 建议然后不复测**:改完用户不知道哪一刀有效。永远"一刀→测→下一刀"。
- **只信主观、不信 LUFS**:耳朵疲劳后 3dB 差异都听不出,`measure_loudness` 不会骗人。
- **只信 LUFS、不信主观**:-14 LUFS 达标但 Gemini 报 `1:20 harsh 3kHz`,照修不误。
- **工程目录里堆 render**:`out_path=None` 自动落 %TEMP%,让 harness 清理,不要手动挑目录。
- **master bus 上做 >3dB gain reduction**:70% 的"响度不够"是 Kick/Bass stem 冲突,不是 bus 压得不够狠。先回 stem 层解决。
- **说"调 EQ 让 Bass 更清晰"**:必须写 `Bass 200Hz bell -3dB Q=1.4, 80Hz shelf +2dB`。没数字等于没说。
- **用户没投诉就主动上 limiter**:demo 阶段留 6dB headroom,limiter 是 mastering 最后一步,不是 mix 阶段的补丁。
