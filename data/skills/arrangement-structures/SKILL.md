---
name: arrangement-structures
disclosure: lazy
mode: arrangement
tags: [arrangement, song-form, structure, markers, template, pop, edm, lofi]
description: 当用户要"搭骨架/定曲式/排段落/加 marker/写 arrangement/song form/section layout",或说"这段该多少小节""副歌前要不要 build-up""桥段放哪""ambient 怎么铺"时触发。也适用于用户已有 loop 但不知道怎么扩成 3 分钟完整曲、或成品听起来"平"没有起伏的情况。覆盖 pop verse-chorus、lo-fi 循环体、EDM buildup-drop、ambient 长弧线、ballad 抒情结构五类模板,给出精确的小节数、能量曲线、marker 命名规范、每段进出乐器清单,并说明何时可以偏离模板。Triggers: 曲式、结构、段落、arrangement、song form、section、marker、buildup、drop、bridge、outro、hook、intro。
---

# Arrangement Structures — 5 个成品曲式模板

## When to use
当你已经有一段 loop、一个动机、或一组和弦,但不知道怎么把它扩成一首 2–4 分钟的完整曲子——这个 skill 直接给模板。不要问"你想要什么风格",按用户提到的类型词(pop / lo-fi / EDM / ambient / ballad)套下面对应模板,用 `add_marker` 一次性把段落标签打进 REAPER 时间线,再谈局部改动。默认 BPM 已给,不合适用户 30 秒会告诉你改。

## 通用能量曲线原则(名词先释义)
**能量规划分数(energy plan score)** — 下表的 [0, 1] 数值只是 **creative_default** 编曲草图,不是工具输出、心理声学量或可跨歌曲比较的测量值。0 表示近乎静音/只剩尾音,0.25 表示 1–2 个稀疏层,0.5 表示核心节奏与和声已在,0.75 表示大部分主层进入,1.0 表示本曲计划中的峰值。它只用于检查同一首歌的段落曲线是否有起伏;实际结果必须用发声层数、片段 integrated LUFS、频谱分布和 A/B 试听分别验证。

**hook** — 最容易被记住的那一段(通常是 chorus 的主旋律或 drop),要求听众第一次听就能哼。

**creative_default**:pop/EDM 可先把第一个 hook 放在 **0:30–0:45**；ballad 可以铺垫更长,ambient 可以没有 hook,参考曲或用户意图优先。不要把能量规划分数的差值解释成听觉阈值。骨架搭完后,分别渲染 verse 与 chorus,比较片段 integrated LUFS、活跃层数和频谱,再做响度匹配 A/B；约 3 dB 的段落响度差只能作为 **heuristic** 起点,不是“进段感成立”的硬门槛。

## Template 1 — Pop verse-chorus(默认 3:20,90 BPM,4/4)
段落与 marker(用 `add_marker` 打在这些拍位,name 就用 `Marker name` 列的字符串):

| 段落 | 小节数 | 起始小节 | Marker name | 能量 | 进/出的乐器 |
|---|---|---|---|---|---|
| Intro | 4 | 1 | `INTRO` | 0.2 | 进:pad+piano |
| Verse 1 | 8 | 5 | `V1` | 0.35 | 进:vocal+kick(4-on-floor 或 half-time) |
| Pre-chorus | 4 | 13 | `PRE1` | 0.55 | 进:snare、bass 上行 |
| Chorus 1 | 8 | 17 | `CHORUS1` | 0.85 | 全员进,和声 3 度+5 度叠 vocal |
| Verse 2 | 8 | 25 | `V2` | 0.4 | 出:和声、pad;留 kick+bass+vocal |
| Pre-chorus 2 | 4 | 33 | `PRE2` | 0.6 | 同 PRE1 但加 riser |
| Chorus 2 | 8 | 37 | `CHORUS2` | 0.9 | 全员+adlib 和声 |
| Bridge | 8 | 45 | `BRIDGE` | 0.5 | 出:鼓;进:变调或 IV-V-vi-iii 新和弦 |
| Final Chorus | 8 | 53 | `CHORUS3` | 1.0 | 升半音 or 双倍鼓(2 层 kick 错开 8 分) |
| Outro | 4 | 61 | `OUTRO` | 0.25 | 只剩 piano+vocal 尾音 |

**首个 hook 在 0:43**(90 BPM 下 chorus1 起点第 17 小节 ≈ 43 秒),踩点。

## Template 2 — Lo-fi 循环体(默认 2:40,72 BPM,4/4)
**Lo-fi** — 低保真美学,用 vinyl noise、tape wow/flutter、Rhodes 电钢制造"下午三点昏昏欲睡"的氛围;不靠戏剧对比,靠"元素慢慢进、慢慢出"制造弧线。8 小节为一"页"。

- 页 A(bar 1–8) `LOOP_A` — 只有 drum(hihat 以 MPC 风格 55% 为目标 feel；在 REAPER 里按网格与 A/B 匹配,不直接复制数值)+ Rhodes 主和弦,能量 0.4
- 页 B(bar 9–16) `LOOP_B_BASS` — 加 bass(sub + 低频泛音,高通 45Hz),能量 0.55
- 页 C(bar 17–24) `LOOP_C_MELODY` — 加主旋律 lead(saxophone 或 Rhodes 独奏,音量 -6 dB 相对 loop A),能量 0.7
- 页 D(bar 25–32) `LOOP_D_FULL` — 全员+vinyl noise 抬 2 dB,能量 0.8
- 页 E(bar 33–40) `LOOP_E_STRIP` — 只留 Rhodes+bass,能量 0.5
- 页 F(bar 41–48) `OUTRO` — 只剩 Rhodes+vinyl,4 小节线性淡出至 -60 dB,能量 0.2

**Sidechain** — 用 kick 触发 Rhodes bus 的压缩器,让 kick 一响 Rhodes 就短暂让路,制造"泵"感。用 `add_track_fx` 加 ReaComp 到 Rhodes bus:ratio 4:1,attack 5 ms,release 120 ms,threshold 调到使 kick 峰值处压出约 3 dB 减益(**GR = gain reduction,压缩表针读数**;threshold 是你设的门限,GR 是压缩器输出结果 —— 慢慢降 threshold 直到 GR 表读到 -3 dB 就停)。

## Template 3 — EDM buildup-drop(默认 3:30,128 BPM,4/4)
**Drop** — buildup 张力累积到顶点后的"爆发段",低音+鼓全员炸进。必须落在整 8 拍强拍(第 1 拍)。**Buildup** 末尾一小节留 1/2 拍全静音(gap),让 drop 更炸。

| 段落 | 小节数 | Marker name | 关键动作 |
|---|---|---|---|
| Intro | 16 | `INTRO` | 只有 pad + filter sweep(cutoff 从 200Hz 扫到 8kHz) |
| Breakdown 1 | 16 | `BREAK1` | 加主旋律,不加 kick |
| Buildup 1 | 8 | `BUILD1` | snare roll 从 1/4 → 1/32,riser 音量 +6 dB,末尾 1/2 拍全静音 |
| Drop 1 | 16 | `DROP1` | 全员炸,短时 LUFS -6 |
| Breakdown 2 | 8 | `BREAK2` | 剥回 pad+vocal chop |
| Buildup 2 | 8 | `BUILD2` | 同 build1 但 riser 上升 2 个八度 |
| Drop 2 | 16 | `DROP2` | 变奏:和弦升半音 or 换鼓 pattern |
| Outro | 8 | `OUTRO` | filter 关闭(cutoff 从 8kHz 扫回 200Hz),pad 独留 |

用 `render_to_wav` 渲染 DROP1 8 拍 → `measure_loudness` 检查短时 LUFS(前提:master 链已推到成品响度;粗排阶段绝对值不作数,改看与 BREAK1 的相对差),不到 -7 dB 就说明没炸出来,回去查 kick+bass 的层是否叠够。

## Template 4 — Ambient 长弧线(默认 5:00,自由拍)
**Ambient** — 无明确节奏、无 hook,靠频谱和空间缓变制造氛围;不数小节,数"分钟标记"。

- `0:00` `START` — 只有 sub pad(60–200 Hz),LUFS -30
- `1:00` `LAYER_MID` — 加中频 pad(300–1200 Hz),LUFS 抬到 -24
- `2:30` `PEAK` — 加高频 shimmer(reverb wet 60%),LUFS -20(整曲峰值)
- `3:30` `RECEDE` — 关中频层,回到 sub+shimmer,LUFS -25
- `4:30` `FADE` — 30 秒线性淡出至 -60 dB

不放 kick,不放明确旋律 hook——听众要"泡"进去,不是听故事。

## Template 5 — Ballad 抒情(默认 3:50,68 BPM,4/4)
比 pop 慢、动态范围更大。声乐/主奏永远在最前(Vocal bus 比 backing bus 高 6 dB),伴奏永远退让。

- Intro 8 小节 `INTRO` — piano 独奏,能量 0.25
- Verse 1 16 小节 `V1` — 加 vocal + 弦乐 pad(音量 -18 dB 相对 vocal),能量 0.4
- Chorus 1 12 小节 `CHORUS1` — 加 bass + 鼓 brush,能量 0.7
- Verse 2 16 小节 `V2` — 保留鼓,能量 0.5
- Chorus 2 12 小节 `CHORUS2` — 加弦乐 legato,能量 0.85
- Bridge 8 小节 `BRIDGE` — 掉到只剩 piano+vocal,能量 0.3(反差)
- Final Chorus 16 小节 `CHORUS3` — 全弦乐+和声,能量 1.0
- Outro 8 小节 `OUTRO` — piano 独奏尾,能量 0.2

## 何时可以偏离模板
- **参考曲比模板短 30% 以上** → 按参考曲比例压缩每段小节数,优先砍 Verse2 和 Bridge,不要保留全部段落。
- **用户要"treatment/remix/interlude"** → 只用模板的 30–60 秒片段,不做完整结构。
- **用户明确说"实验/atonal/drone"** → 抛掉 verse-chorus 逻辑,只用 ambient 弧线思路。
- **参考曲 hook 出现在 0:15 之前** → intro 砍到 2 小节以内,直接进 chorus。

## 一次搭好骨架的流程
1. 认风格 → 选模板 → 用 `add_marker` 按上表 `Marker name` 全部打上(一次 8–10 次调用)。
2. 用 `set_time_selection` 选中第一个 chorus 的起止拍,`render_to_wav` 渲染 → 让用户先听 hook 是否成立。hook 不行,后面全不行。
3. 骨架确认后再谈音色、混音、变奏。骨架错的话音色调再好都平。
4. Kontakt 需要具体音色时明说:"**Kontakt / Omnisphere 等重采样器的具体音色库必须在插件窗口内由用户手动加载**——NI 设计如此,MCP 只能 add_track_fx 挂上宿主,选不了具体 patch。
"

## Anti-patterns
- **每段都 8 小节均匀切**——听众会睡着;pre-chorus 4 小节、bridge 变长或变短制造不对称才有推进感。
- **hook 出现在 1 分钟之后**——流媒体听众切歌毫不留情;pop/EDM 的首个记忆点必须 ≤ 0:45(ballad/ambient 按各自模板走)。
- **Bridge 加更多元素**——反了。Bridge 应该"减"元素(去鼓 or 去 bass),给最终 chorus 让路,能量曲线要有一次下沉。
- **不打 marker 就开始编曲**——没有可视时间轴,后面加减段落对不齐,鼓型也会飘;永远先 `add_marker` 后 `add_midi_notes`。
- **EDM drop 不留 gap**——buildup 末尾直接接 drop 会糊,至少留 1/2 拍全静音。
- **Ambient 硬套 verse-chorus 命名**——ambient 没有段落切分,只有频谱缓变,别标 `V1/CHORUS`,标 `LAYER_MID/PEAK/RECEDE`。
- **骨架没渲染就开始调音色**——搭完 marker 后分别渲染 verse 与 chorus,检查活跃层数、片段 integrated LUFS 和频谱,再做响度匹配 A/B。不要用能量规划分数或单一 3 dB 阈值代替听感判断。
