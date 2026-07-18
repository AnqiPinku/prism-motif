---
name: mastering-basics
disclosure: lazy
mode: mix
tags: [mastering, LUFS, loudness, true-peak, limiter, streaming, spotify, dynamic-range]
description: 当你混完一首歌准备上传 Spotify/Apple Music/YouTube/SoundCloud 前的最后一步——把整体响度推到平台标准、真峰值不炸、动态范围保住。触发词:mastering、母带、响度、LUFS、真峰值、-14 LUFS、-9 LUFS、限制器、maximizer、平台响度、streaming loudness、normalization、发布前处理、上传前处理、我的歌上传后比别人小声、Spotify 播放像盖了层棉被、preview 太小声。也用于诊断响度问题、判断"这混音能不能上母带",给出各平台 LUFS/True Peak/LRA 数字目标和母带链的具体插件顺序与参数。不用于混音阶段的 EQ/压缩(那是 mixing),也不用于商业级 stem mastering 交付(那需要专门工程师)。
---

# Mastering Basics — 平台响度与动态的取舍

## When to use

当你混完一首歌,拿去 Spotify/Apple Music/YouTube/SoundCloud 发布前的最后一步——把整体响度推到平台标准、真峰值不炸、动态范围(LRA)保住。触发词:mastering、母带、响度、LUFS、真峰值、-14 LUFS、-9 LUFS、限制器、maximizer、平台响度、normalization、streaming loudness、送母带、preview 时太小声、发布前处理。也用于:诊断"为什么我的歌上传后比别人小声"、"为什么 Spotify 播放我的歌像盖了层棉被"。不用于:混音阶段的 EQ/压缩(那是 mixing),也不用于 stem mastering(把混音分组交给专门母带工程师的商业流程)。

## 先给一个默认动作(30 秒内开工)

假设你的目标是 Spotify + Apple Music(占流媒体 80%),先把混音 bus 渲染为 wav(24bit,采样率保持工程原生)拿去测:

```
render_to_wav(全曲区间) → measure_loudness(path) → 看 integrated LUFS 和 true_peak
```

**目标**(按平台):

| 平台 | Integrated LUFS | True Peak | LRA |
|---|---|---|---|
| Spotify / Apple Music / Tidal | **-14 LUFS** | ≤ **-1.0 dBTP** | 6–9 LU |
| YouTube / Amazon Music | -14 LUFS | ≤ -1.0 dBTP | 6–9 LU |
| EDM / club / Beatport | **-8 到 -6 LUFS** | ≤ -1.0 dBTP | 3–5 LU |
| 古典 / jazz / 电影配乐 | **-18 到 -16 LUFS** | ≤ -1.0 dBTP | 10–20 LU |
| SoundCloud / TikTok / 无 normalization | -9 到 -7 LUFS | ≤ -1.0 dBTP | 4–6 LU |

术语先扫一遍(第一次遇到就记住):
- **LUFS** — Loudness Units Full Scale,人耳感知的平均响度。integrated = 全曲一个数,人听到的"这歌多响"。
- **True Peak (dBTP)** — 采样点之间重建后的最高峰值,超 0 dBTP 在 mp3/aac 编码时会失真。留 -1.0 dBTP 是给编码器的安全余量。
- **LRA (Loudness Range)** — 全曲响度动态范围,单位 LU。LRA 太小(<3)= 一堵墙,听着累;太大(>15)= 副歌上不去,流媒体自动降的时候还更小声。
- **Normalization** — Spotify 把所有歌拉到 -14 LUFS 播放,你母带做到 -8 反而会被降 6dB,听着更死。
- **Headroom** — 峰值离 0 dBFS 的余量,数字越负余量越大,给下一级插件留发挥空间。
- **GR (Gain Reduction)** — 压缩器/限制器的"压了多少 dB"表针读数,GR = 3dB 表示这一刻把信号压低了 3dB。
- **Bell / High Shelf / High Pass** — EQ 曲线类型。bell 是钟形,只影响中心频段;high shelf 从某频率起整体抬高或降低;high pass 是低频往下逐步砍掉。

## 母带链的最小配置(Master bus,4 个插件,顺序不能反)

在 REAPER Master track 上用 `add_track_fx` 从上到下加(用 `list_installed_fx` 先确认名字):

1. **Utility / Gain**(用 JS: Volume/Pan 或 ReaJS) — 调整输入电平,让下一环节最响处 peak ≈ **-6 dBFS**。留 headroom 给后面吃。
2. **Master EQ**(用 ReaEQ) — 只做两件事,超过说明混音没做好,回混音阶段:
   - **High pass 20–30Hz**(去次低频轰隆,不然限制器抽风)
   - 若整体 muddy → 200–400Hz 用 **bell 减 1–2dB, Q=1**
   - 若不够 air → 12–16kHz 用 **high shelf 加 1–2dB**
   - **动 EQ 不超过 ±2dB 硬上限**
3. **Bus Compressor**(用 ReaComp,SSL-style 参数) — 粘合各轨:
   - Ratio **2:1**、Attack **30ms**、Release **auto** 或 **100ms**、Threshold 让 **GR 表 1–2dB 抖动**、Makeup 补回损失的电平
   - 目的是"胶水",不是压电平。GR 平均超过 3dB 就是过头,回步骤 2 减低输入电平
4. **Limiter / Maximizer**(用自带 JS: `LOSER/masterLimiter` 或免费 **Youlean Loudness Meter + TDR Limiter 6 GE**) — 定终响度:
   - **Ceiling = -1.0 dBTP**(必须支持 true peak 检测)
   - Threshold 每次下推 0.5dB,直到 `measure_loudness` 显示 integrated ≈ 目标 LUFS
   - GR 平均 **≤ 3–4dB**,瞬间峰值到 6dB 可接受。GR 常挂 **8dB+** 就是在毁动态,回混音

## 用工具闭环(别信耳朵,靠数字)

每次改完限制器 threshold,跑一遍这个循环:

```
1. render_to_wav(master 段, 含 head/tail 各 500ms 静音, out_path 可省略自动落 %TEMP%)
2. measure_loudness(path) → integrated LUFS / true_peak / LRA
3. 差多少 dB,回限制器 threshold 推等量(差 -2dB 就 threshold 再降 2dB)
4. 若 LRA < 6 且是流行/摇滚 → threshold 上抬 1dB 松开,不然 Spotify normalize 后声音死
5. 若 true_peak > -1.0 → ceiling 降到 -1.2,或换支持 true peak 的限制器
6. listen_subjective(path) → 听 muddy/harsh/pumping;若报告 "pumping at 1:23"(限制器泵浦感,音量呼吸式起伏),回步骤 3 减 1dB 增益
7. add_marker 在 REAPER 工程标 "MASTER v1 -14LUFS -1.0dBTP" 便于回溯
```

## 什么时候说"这混音不能上母带"(打回混音阶段)

母带只能加最后 1–3 dB 的响度感,救不了混音本身的问题。出现下面任一,别硬推,回 arrangement/mixing:

- `measure_loudness` 前测 peak 已经 **-0.5 dBFS** 但 integrated 只有 **-18 LUFS** → 有一两下失控峰值,回混音找哪个 kick/snare 没压好
- 打到目标 LUFS 时 Bus Comp + Limiter 合计 **GR 平均 > 6dB** → 混音本身动态没控好,回去压单轨
- `listen_subjective` 报告 muddy 在 200–400Hz → 回混音削那个频段,别在母带 EQ 上砍 4dB 硬救
- **LRA < 3** 且母带还没上限制器 → 混音已经过压,母带无救,回混音松单轨压缩

## 平台上传前的最终 checklist

- [ ] Wav **24bit**,采样率保持工程原生(48k 就 48k,别转 44.1)
- [ ] Integrated LUFS 在目标 **±0.5 LU** 内
- [ ] True peak **≤ -1.0 dBTP**(`measure_loudness` 确认)
- [ ] LRA 在平台推荐范围(见上表)
- [ ] 曲首曲尾各留 **100–500ms** 静音,防止播放器切歌爆音
- [ ] 手机外放 + 耳机 + 车载三处 A/B 同风格商业发行版
- [ ] `add_marker` 在工程标 "MASTER v1 -14LUFS -1.0dBTP" 便于回溯

## Anti-patterns

- **追响度战争**:把流行歌推到 -6 LUFS 交 Spotify,平台降 8dB 播放,动态被你毁了却没多响一分。**流媒体时代 -14 就够,别硬推**。
- **在母带 EQ 上砍 4dB+ 救混音**:母带 EQ 是修饰,不是修复。muddy 回混音减 bass/kick 200Hz 那一档,别在 master 上砍。
- **限制器 GR 长期挂 8dB+**:泵浦感、失真、动态死。GR 平均超 4dB 就是在告诉你"混音送来时太小声或太失控",回混音而非硬压。
- **不用 true-peak-aware 的限制器**:普通 sample peak 显示 -0.1 也会在 mp3/aac 编码后 clipping。用支持 true peak 检测的限制器,ceiling 设 -1.0 dBTP。
- **只听 monitor 不看数字**:总控音量 -20dB 和 0dB 感觉的响度不同(Fletcher-Munson 曲线,低音量时低频听感更弱)。用 `measure_loudness` 看数字,别信耳朵在不同音量下的判断。
- **给不同平台各做一版母带**:除非专门做 EDM club master,一版 -14 LUFS 母带能通吃所有主流流媒体(Spotify/Apple/YouTube/Tidal 都是 -14)。别过度加工。
- **在母带上试图加 reverb/stereo widener**:那是混音阶段的活。母带只做 EQ 微调 + bus comp 粘合 + limiter 定响度,加空间感等于告诉自己"我混得不对"。
