---
name: tension-design
disclosure: lazy
mode: arrangement
tags: [arrangement, dynamics, buildup, drop, energy-curve, automation, negative-space, velocity]
description: 编曲能量曲线设计:控制歌曲从头到尾的张力起伏、加减轨、力度阶梯、build-up 与 drop 前留白。触发词:"编曲太平"、"没有起伏"、"副歌不够炸"、"drop 无力"、"build-up 怎么写"、"drop 前一秒怎么处理"、"哪里该减轨"、"密度太满"、"能量曲线"、"tension arc"、"dynamic contrast"、"arrangement feels flat"、"chorus doesn't hit"、"密度阶梯"、"负空间"。当用户已有基本编曲(和弦/主旋律/鼓/bass)但整首歌听感"从头到尾一样满"或"副歌爆发无力"时使用。不用于混音层的压缩/EQ 音色处理(那是 mix 领域),这里管的是段与段之间的轨道数、力度、响度差、以及 build-up/drop 的结构。
---

# Tension Design — 编曲能量曲线

## When to use

用户有一段编曲(主歌+副歌+鼓+bass)但反馈"太平"、"副歌不炸"、"从头满到尾"、"drop 没冲击力"时触发。核心工作是重新分配能量:哪里该空、哪里该满、每一段比前一段涨多少 dB / 多几层轨。默认动作:先用 `measure_loudness` 分段测出当前每段短时 LUFS,再对照下面的能量表打差值,然后按密度阶梯砍轨或加轨,30 秒内可回滚。

## 第一步:先量当前的能量曲线(不猜)

**tension→release — 张力→释放**:副歌的"炸"不来自副歌本身多响,而来自副歌前那段有多空。人耳判定"一样满"的阈值是 3dB 短时 LUFS 差以内。

打开项目,用 `set_time_selection` 圈出每段,`measure_loudness` 逐段测短时 LUFS(不要测整首 integrated):

| 段落 | 目标短时 LUFS(相对副歌 0 参考) | 常见错误 |
|------|-------------------------------|---------|
| Intro | -6 到 -9 LUFS | 只低 1-2dB 等于没 intro |
| Verse 1 | -4 到 -6 LUFS | 和副歌一样满 |
| Pre-chorus | -2 到 -4 LUFS | 直接顶到副歌 |
| Chorus | 0 LUFS(基准) | — |
| Bridge/Breakdown | -5 到 -8 LUFS | 只减 1dB 观众听不出 |
| Final Chorus | 0 到 +0.5 LUFS | 和第一遍完全一样 |

Verse 与 Chorus 差值 <3dB 就必须动手。目标 4-6dB。

## 第二步:密度阶梯(density staircase)— 同时响的轨道数

**density staircase — 密度阶梯**:每段同时发声的轨道数量按段递进,大脑对"多一层"极敏感,对"响一点"迟钝。数轨道比推 fader 有效。

默认配置:

- **Intro**(4-8 小节):2-3 轨(Pad + 主旋律动机,**无鼓无 bass**)
- **Verse 1**:4-5 轨(加 Kick+Snare、Bass、一个和声乐器)
- **Pre-chorus**:6-7 轨(hi-hat 从 1/8 变 1/16、加一层 pad 高八度、Snare 加 reverb tail)
- **Chorus**:9-12 轨(加 Lead、加 double 人声、加 Shaker、Bass 叠一层 sub 低八度)
- **Verse 2**:5-6 轨,**换乐器组合**,不要照抄 V1(比如换成 pluck 代替 piano)
- **Bridge**:3-4 轨,**至少持续 8 小节**(砍鼓 or 砍 bass,只留一个;短于 4 小节耳朵 reset 不了)
- **Final Chorus**:12-14 轨,比第一次副歌**多 2-3 轨**(ad-lib 人声、tambourine、strings pad 高八度)

在 REAPER 里用 `add_marker` 打上每段起点,标记名写成 "V1_5tracks"、"Ch1_10tracks" 这种,一眼看到密度。

## 第三步:build-up 的 8 拍配方(pre-chorus → chorus 那一秒)

副歌前最后 2 小节(4/4 8 拍),按拍分层加东西:

- **拍 1-8**:Snare roll,1/8 → 1/16 → 1/32 每 2 拍细分翻倍(用 `add_midi_notes` 直接写)
- **拍 1-8**:白噪声 riser 一条独立轨,音量 envelope 从 -30dB 线性推到 -12dB(REAPER track volume envelope 手画)
- **拍 1-8**:一层 FX/riser 层做 pitch rise +0 → +12 semitones 线性 up(**只对 riser/FX 层,不要对和声乐器做,否则整首走调**)
- **拍 5-8**:所有和声乐器改成短促断奏(音符时值砍成 1/16 staccato)
- **拍 7 反拍到拍 8 结束**:**全部乐器静音 200ms**,只留 reverb tail
- **副歌第 1 拍(downbeat)**:Kick + Crash + Bass + 全和声同时进,MIDI velocity=127

**negative space — 负空间/留白**:drop 前 100-300ms 的绝对静音,大脑用这 200ms 校准听觉基准,副歌一进来的对比度直接翻倍,等于免费 3dB 冲击力。90% 的"drop 无力"是漏了这 200ms。

## 第四步:velocity 力度阶梯(MIDI 层面)

用 `get_midi_notes` 读出鼓 MIDI 力度,直接改数字,不要说"稍微加强":

- **Verse 底鼓 Kick**:velocity 90-100
- **Chorus 底鼓 Kick**:velocity 115-125(**不要 127**,留 headroom 给 fill/过门)
- **Fill/过门/副歌 downbeat**:velocity 127
- **Hi-hat 主歌**:velocity 60-75(闭镲不要太亮)
- **Hi-hat 副歌**:velocity 85-100,同时换开镲(open hat)
- **Snare 主歌**:velocity 85-95
- **Snare 副歌**:velocity 110-120

重写现有鼓 MIDI 力度用 `replace_midi_notes`(读出→改 velocity→整体替换,一个 undo 步;`add_midi_notes` 是追加,会把整套鼓叠成双份);只调几个音就 `update_midi_note` 逐音改。无论哪种,每一层的力度都必须明确落到具体数字。

## 第五步:自动化 — 三条最省事的 envelope

在 REAPER 里给这三个参数画自动化,能撑起 60% 的动态感:

1. **主 bus 音量**:Verse -3dB,Pre-chorus -1dB,Chorus 0dB(是靠 arrangement level 拉差,不是靠 mix compressor 事后追)
2. **Reverb send 量**:Verse 25%(远),Bridge 40-50%(飘),Chorus 15%(**punch — 冲击感,近而干才有拳头感**,只加短 plate 0.8-1.5s + pre-delay 20-40ms,不做大 hall)
3. **低通 cutoff(ReaEQ Band 1 类型 Low Pass,slope 24dB/oct)**:Intro cutoff 从 800Hz 每 4 小节升 400Hz,到 Verse 1 开到 20kHz(全开)— 这是最经典"从远处走近"的滤波扫频效果。**注意是 Low Pass 不是 High Pass**,砍高频才等于"远"。

## Anti-patterns

- **每段都满**:12 轨从头响到尾,大脑 30 秒后自动降低敏感度,副歌等于没炸。至少留 1 段密度 ≤4 轨。
- **build-up 只加音量不加密度**:光靠 riser 推 volume,没有 snare roll 细分翻倍、没有 hi-hat 加密,冲击力打对折。
- **副歌用大 hall reverb**:副歌要 punch,大 hall(2s+)让它糊。副歌只用短 plate 0.8-1.5s、pre-delay 20-40ms;长 reverb 留给 verse 和 bridge。
- **减轨只减 1-2 小节**:bridge 想做空却只砍 2 拍就回,耳朵还没 reset 就又满了。最少 4 小节,最好 8 小节。
- **Final chorus 和第一遍一样**:观众第二次听副歌已经"知道了",必须加 2-3 轨新元素(ad-lib、strings 高八度、tambourine)否则感觉在倒带。
- **忘了 negative space**:副歌 downbeat 前那 100-300ms 静音是免费的 3dB 冲击力,漏掉就是浪费。
- **对和声乐器做 pitch rise**:build-up 的 +12 semitone 扫频只能加在 riser/FX 层,加到 pad/piano 上就是整首走调不是编曲手法。
