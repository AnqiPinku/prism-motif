---
name: eq-fundamentals
disclosure: lazy
mode: mix
tags: [eq, mixing, muddy, harsh, sibilance, kick-bass, reaper, frequency]
description: Trigger this skill when the user is mixing and describes a symptom that maps to a frequency problem: 浑浊/糊/mud/muddy、刺耳/harsh/毛刺、齿音/sibilance/嘶嘶、Kick 和 Bass 打架/低频糊、闷/dull、薄/thin、鼻音/boxy、脆/brittle。Also triggers on "EQ 怎么调"、"该切哪一段"、"高通设多少"、"ReaEQ 参数"、Bass/Vocal/Kick/Guitar EQ 请求,以及 "扫频怎么找问题点"、"Q 值设多少"。给出精确 Hz、dB、Q 值,用于 ReaEQ 或任何参数化 EQ,不用 "适当衰减" 之类模糊语言。不用于总线/母带 EQ 或整体混音哲学(改用 master-bus skill)。
---

# EQ Fundamentals — 按症状开方,不猜

## When to use
你听到一个具体问题(浑、刺、齿、Kick 撞 Bass、闷、薄)想立刻在 REAPER 里动手改。默认工具 ReaEQ(REAPER 免费自带的参数化 EQ),所有频点、增益、Q 值我都写死;你套上去 A/B 一遍就知道对不对。**先做减法(cut),再做加法(boost)** —— 同一段频率如果衰减别的能解决,就别 boost 主体,信噪比更干净。

## 名词速览(先看一眼,后文都在用)

- **Bell(钟形)** — 中间尖两边斜的对称曲线,只影响中心频率上下一小段,用于精修某个 Hz。
- **Shelf(搁架)** — 从某频率起一路抬/降到底,像门槛,用于整体加空气感或去低频。
- **HPF/LPF(高通/低通)** — HPF 砍掉某 Hz 以下,LPF 砍掉以上。斜率单位 dB/oct = 每一个八度衰减多少 dB,12 dB/oct 是常用默认。
- **Q 值** — bell 的宽窄。Q 越大越窄(手术刀),Q 越小越宽(棉签)。Q=1.4 是通用,Q=4-6 是齿音这种要精准打击。
- **oct(octave,八度)** — 频率翻倍算一个八度,ReaEQ 的 Bandwidth 用 oct 单位,不用 Q,要换算。
- **LUFS** — 响度单位,行业标准,取代峰值 dB 判断 "听感响多少"。

## 五个症状对应的手术刀参数

| 症状(你听到的) | 频段 | 动作 | 典型参数 |
|---|---|---|---|
| 浑浊/糊/像隔了层布 | 200–500 Hz | Bell cut | -3 到 -6 dB, Q=1.4,扫频定点 |
| 刺耳/毛刺/尖 | 2–5 kHz | Bell cut | -2 到 -4 dB, Q=2.0 |
| 齿音 s/sh(人声) | 5–9 kHz | Bell cut 或 De-esser | -4 到 -8 dB, Q=4–6;或用 ReaXComp 侧链压 |
| Kick 和 Bass 打架 | 60–150 Hz | 互补切 | 见下节 |
| 闷/沉/没空气 | 10–16 kHz | High shelf boost | +2 到 +3 dB,从 10 kHz 起 |

**De-esser** = 专门压齿音的动态处理,只在 s/sh 触发时衰减 5-9 kHz。**侧链(sidechain)** = 让一个信号触发另一个通道的压缩/衰减。REAPER 里 ReaXComp 多段压缩器可以当 de-esser 用:5-9 kHz 段设 threshold -20 dB、ratio 4:1、attack 1 ms。

**扫频找问题点(sweep-and-destroy)** — 新建一个 bell,增益拉到 +8 dB、Q=6,慢慢横着扫频率轴,最难听/最凸出的那个 Hz 就是元凶,记下这个数,然后把增益翻负号变成 cut(比如 +8 dB 变 -4 dB)。这不是玄学,是标准工作流。

## Kick vs Bass 冲突 — 60/100 Hz 互补法

两个默认互斥方案,选一个,不要都干:

**方案 A(推荐,现代流行/摇滚)** —— Kick 占低,Bass 占中低:
- Kick: 60 Hz bell +3 dB, Q=1.5;250 Hz bell -3 dB, Q=1.2(去 "纸箱共振")
- Bass: 60 Hz bell -3 dB, Q=1.5(让位给 Kick);100 Hz bell +2 dB, Q=1.2

**方案 B(hip-hop / 808 低音)** —— Bass 占低,Kick 占中:
- Kick: 60 Hz bell -3 dB, Q=1.5;3 kHz bell +3 dB, Q=1.5(打点感,click)
- Bass: 60 Hz bell +2 dB, Q=1.2

**A/B 判断**:solo(单独听)Kick+Bass 两轨,先用 measure_loudness 确认两轨响度差 <0.5 LUFS,单独听 30 秒,能分清两个乐器谁在哪就对了;糊成一坨就换方案。

## 高通/低通 —— 每轨都要问一遍

**HPF 默认值,直接抄**(所有 12 dB/oct 斜率):
- Vocal 主唱: 80 Hz
- 电吉他/木吉他: 100 Hz
- Piano/Keys: 60 Hz
- Overhead 鼓组顶麦: 200 Hz(去 kick 溢出)
- Hi-hat/踩镲: 300 Hz
- Kick / Bass / Sub: **不加 HPF**

**LPF** 只有两种情况用:模拟老磁带感(15 kHz 起,6 dB/oct),或者背景音轨挤空间给主音让路(12 kHz 起,12 dB/oct)。主音轨不要滥用 LPF —— 你砍掉的是 "存在感" 和 "空气感"。

## ReaEQ 具体操作(REAPER)

1. `add_track_fx` 参数 `"ReaEQ"`
2. 默认 4 段:HP shelf(点 Type 下拉改成 High-pass)、Low bell、Mid bell、High shelf
3. 每段右上角 **Type** 下拉换类型;**Frequency / Gain / Bandwidth (Q)** 三个数字**手输**,不要拖鼠标估
4. **Bandwidth(oct) 换算 Q**:1.0 oct ≈ Q=1.4;0.5 oct ≈ Q=2.9;2.0 oct ≈ Q=0.7;0.3 oct ≈ Q≈4.8(齿音级)
5. 用 `get_fx_params` / `set_fx_param` 可以脚本化改参数;`list_fx_presets` 看有没有现成起点

## 用 listen_subjective 交叉验证(耳朵疲劳时必做)

改完 EQ,3 步命令流:
1. `set_time_selection` 框选 20 秒关键段(副歌 + 前奏一半)
2. `render_to_wav`(不填 out_path 就自动落 %TEMP%/prism-renders)
3. `measure_loudness` 对比 EQ 前后 LUFS,**必须** <0.5 LUFS 差再判断(响=好听幻觉)
4. `listen_subjective` 喂这段 wav,prompt 写 "muddy? harsh? sibilant? 时间戳标记",Gemini 会回带秒数的主观描述,机器不累。

## 关于 Kontakt 音色

如果混的是 Kontakt 的采样乐器,**音色必须用户手动在 Kontakt UI 里加载**(NI 的设计,MCP 无法自动切库)。EQ 参数一样适用,但预设起点要按 Kontakt 里那个音色的原始频响调整。

## Anti-patterns

- **每段都 boost、不 cut** —— 结果整轨 +12 dB,推子推爆还是浑。铁律:先扫频 cut,不够再 boost。
- **Q 值一律 1.0** —— 齿音要 Q=4-6 的窄手术刀,空气感要 Q<1 的宽带。一个 Q 打天下就是没在 EQ。
- **HPF 全推到 200 Hz 图省事** —— Bass 和 Kick HPF 就等于砍了自己饭碗,别加。
- **不 solo 听、不 bypass A/B** —— bypass 开关是 EQ 最重要的按钮,每改一段都要点两下确认真的变好。
- **闷了就狂 boost 10 kHz** —— 先检查是不是 200–500 Hz 太满**遮住了**高频,cut 中低往往比 boost 高频更透。
- **A/B 时响度没匹配** —— 大声总是显得更好听。前后 `measure_loudness` 差 <0.5 LUFS 再下结论。
- **在耳机疲劳后期改 EQ** —— 听了 2 小时就走 `render_to_wav` + `listen_subjective`,让 Gemini 当第二双耳朵。
