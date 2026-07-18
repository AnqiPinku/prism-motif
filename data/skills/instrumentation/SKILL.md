---
name: instrumentation
disclosure: lazy
mode: arrangement
tags: [instrumentation, arrangement, track-budget, frequency-mapping, reasynth, kontakt, genre-template, panning]
description: 当用户需要决定"这首歌放几轨、每轨用什么乐器、频率上谁占哪一段"时触发。典型场景:demo 有旋律和和弦但听起来单薄想加乐器、频率打架不知道谁让路、只有 ReaSynth/ReaSynDr 没音色库、第一次搭编曲不知道轨道预算、切换风格(Pop/Lo-fi/EDM/Cinematic/Rock)要改配器骨架、pan 和立体声宽度分配、如何用 list_installed_fx(instruments_only=True) 挑音源。触发词:配器、乐器、几轨、频率打架、糊、单薄、加什么乐器、pad、bass、lead、Kontakt、ReaSynth、pan、立体声、编曲骨架、轨道数、sidechain、swing。
---

# Instrumentation — 配器与频率分工

## When to use
当用户需要决定"这首歌放几轨、每轨用什么乐器、频率上谁占哪一段"时用这个 skill。典型触发:demo 有旋律和和弦但听起来单薄、想加乐器又怕糊、频率打架不知道谁让路、只有 ReaSynth/ReaSynDr 没音色库、第一次搭编曲不知道轨道预算、切换风格要改骨架。默认动作:先按下面的 6 轨骨架搭起来,不合适 30 秒再改。

## 术语一次说清(后面直接用)

- **frequency masking(频率遮蔽)**:两个乐器占同一段频率时,响的那个会把弱的盖住,耳朵听不到细节。
- **track budget(轨道预算)**:一首歌能同时响的音色数上限。Pop/Rock 8–16 轨够;Cinematic 30+;Lo-fi 4–6。轨越多越难混。
- **HPF (High-Pass Filter, 高通滤波)**:砍掉某频率以下的所有低频。"HPF 80Hz" = 80Hz 以下全砍。
- **sidechain(侧链压缩)**:让 A 轨触发压缩器,把 B 轨在 A 响的瞬间压低几 dB。EDM 常用:kick 一响,pad 就短暂让位,律动更 pump。
- **swing / shuffle(摇摆量)**:把偶数位 16 分音符往后推。MPC 风格比例通常以 50% 表示平直；REAPER 的 Swing amount 以 0 表示平直,官方 API 暴露 -1..1 的独立量程。两者分母不同,不能把数值直接复制或声称存在官方精确换算。来源:[REAPER GetSetProjectGrid API](https://www.reaper.fm/sdk/reascript/reascripthelp.html#GetSetProjectGrid)。
- **bus 分组**:多个轨道汇总到一条 bus 轨统一处理(如 4 层 strings 汇到 Strings bus 再加 EQ/reverb)。
- **Cutoff / Resonance**:合成器低通截止频率 / 截止点的峰凸出量。Cutoff 800Hz = 只让 800Hz 以下过;Resonance 高了会"嗡"。
- **ADSR(Attack/Decay/Sustain/Release)**:音头快慢 / 衰减到持续的时间 / 持续音量 / 松开后余音时间。单位 ms 或 0–1。
- **Portamento(滑音)**:两个音之间以指定 ms 数滑过去而不是硬切。
- **DI+cab**:Bass/Guitar 直插信号 + cabinet impulse response 模拟音箱。REAPER 用 ReaVerbate 或 ReaCabinet 类插件加载 IR 文件。

## 默认 6 轨骨架(先搭,再谈风格)

不管什么风格,先按这个骨架开轨。工程一开就跑 `list_installed_fx(instruments_only=True)` 看手上有什么音源。

| 轨 | 角色 | 频率主战场 | 立体声位置 (pan) | 默认音源 |
|---|---|---|---|---|
| 1 Kick | 律动地基 | 40–100Hz 基波 + 2–5kHz 敲击 | Center (0) | ReaSynDr / Kontakt 鼓库 |
| 2 Bass | 低频旋律 | 60–250Hz | Center (0) | ReaSynth 方波+低通 / Kontakt bass |
| 3 Chords/Pad | 和声垫 | 200Hz–4kHz | Wide (L/R 各 60%) | ReaSynth 三振荡叠 / Kontakt keys |
| 4 Lead/Vocal | 主旋律 | 500Hz–5kHz | Center (0) | 采样 vocal / Kontakt lead |
| 5 Snare/Clap | 反拍 backbeat | 150–250Hz 体+3–8kHz 空气 | Center (0) | ReaSynDr snare |
| 6 Hat/Perc | 高频律动 | 8–16kHz | 微 L 或 R (±20%) | ReaSynDr hihat |

(**backbeat**:4/4 拍里 2、4 拍的强反拍,snare/clap 站的位置。)

## 按风格改骨架(30 秒替换表)

风格切换只改"多加什么"和"删什么",6 轨骨架不动。

- **Pop**:+ Vocal double(主 vocal 录两遍,复制轨 pan L30/R30)、+ Piano 高八度 layer(和 pad 同和弦、高一个八度)。
- **Lo-fi Hip-hop**:删 Pad → 换 Rhodes 电钢;Hat 以 MPC 风格 58% 作为目标 feel 时,在 REAPER 启用 Swing 后从轻到中等量开始,看偶数位 16 分音符的位置并 A/B 调到相同律动。不要输入 0.58,也不要把推导值写成跨软件精确等价；全体加一条 bus,ReaEQ 12kHz 以上 lowpass 砍 -12dB/oct 制造"闷"感。
- **EDM/House**:+ sidechain pad(Track FX 加 ReaComp,Detector input 指向 kick 送来的信号,Threshold 触发时压 6dB, Release 200ms)、+ Riser 8 小节爬升音效。Bass 拆两轨:sub sine(ReaSynth Sine, HPF 关, LPF 80Hz)+ mid bass(80–250Hz)。
- **Cinematic/Orchestra**:Strings 分 4 层(Bass/Cello/Viola/Violin, pan L60/L20/R20/R60),Brass 单独一轨占 200Hz–2kHz。轨数放到 20+,靠 bus 分组管理(Strings bus / Brass bus / Perc bus 各一条)。
- **Rock**:+ Rhythm guitar L/R 各一轨 double(pan L80/R80,不同 take 录音自然错开)、+ Lead guitar center。Bass 用 DI+cab 模拟。

## 频率分工(不打架的核心)

一句话原则:**一段频率一个主角**。80Hz 是 kick 的,你就让 bass HPF 80Hz;300Hz 是 vocal 温暖度,pad 就在 300Hz 挖 3dB(ReaEQ 加一个 bell,Freq 300, Gain -3, Q=1.5)。

分工示例(Pop 六轨,直接照抄到 ReaEQ):
- 20–60Hz:留给 kick 基波,其他全部 HPF 砍掉(斜率 -18dB/oct)。
- 60–120Hz:kick+bass 共享;bass 加 sidechain,kick 触发时压 3dB。
- 120–500Hz:pad + guitar 主战场;vocal 在 200Hz 挖 -3dB(Q=1)让位。
- 500Hz–2kHz:vocal + lead 主战场;pad 在 1kHz 挖 -2dB(Q=1.5)。
- 2–8kHz:vocal 齿音 + snare 敲击 + guitar 咬人段。
- 8–16kHz:hat + cymbal + vocal 空气。

## FX 选择:只有 ReaSynth / ReaSynDr 怎么办

Kontakt / 第三方音色库需要用户在 Kontakt 界面手动加载具体 patch(NI 设计如此,agent 只能 `add_track_fx("Kontakt")`,不能自动选音色 — 明确告诉用户"你打开 Kontakt 窗口选 Session Strings 的 Legato patch")。

只有 stock 插件时的救急方案(用 `add_track_fx` 加 ReaSynth/ReaSynDr,`get_fx_params` 看参数名,`set_fx_param` 按下面填数字):
- **Bass 音色**:ReaSynth → Wave=Square, Cutoff=800Hz, Resonance=0.2, Attack=5ms, Decay=200ms, Sustain=0.7, Release=100ms。
- **Pad 音色**:ReaSynth 三个 oscillator 全开 → Wave=Sawtooth, Detune 分别 -7/0/+7 cent, Attack=800ms, Release=1500ms(慢起慢落 = 垫感)。
- **Lead 音色**:ReaSynth → Wave=Sawtooth, Cutoff=3kHz, Portamento=30ms(音间滑 30 毫秒)。
- **Kick/Snare**:ReaSynDr 直接用默认 patch,不够狠加 ReaEQ:Kick 60Hz +4dB(bell, Q=1.5),Snare 200Hz +3dB(bell, Q=1)。

流程:`list_installed_fx(instruments_only=True)` → 挑一个 → `add_track_fx` → `get_fx_params` 看参数 → `set_fx_param` 按上表填 → `set_time_selection` 圈 4 小节 → `render_to_wav` 试听。

## 加/减轨的决策清单

每次想加一轨,先自答三个问题(不用问用户,自己判断):
1. **它占的频率段现在空吗?** 不空就先决定谁让位(在原轨用 ReaEQ 挖 -3dB)。
2. **它占的节奏位空吗?** 全员都在正拍,新轨走反拍 / off-beat(16 分的第 2、4、6、8 位)。
3. **它的立体声位空吗?** center 挤了就 pan ±40 以上。

三个都答"是"就加。有一个答"不是",要么删,要么改音色/pan/节奏错开。

## Anti-patterns

- **一次开 20 轨才开始混**:先 6 轨骨架完成到能循环听 4 小节,再加装饰。轨多不等于满,等于糊(frequency masking 叠满)。
- **Bass 不 HPF**:20–60Hz 全留给 kick,bass 默认 HPF 80Hz(-18dB/oct),否则低频抢功率、母带一压全塌。例外:EDM 拆出的 sub 层就是设计来占 40–80Hz 的(kick 靠 sidechain 让位),那一层不 HPF。
- **Pad 塞满整个频谱**:Pad 只负责 200Hz–4kHz 的和声垫,低于 200Hz HPF,高于 4kHz LPF,不然 vocal 站不出来。
- **"再加一个 lead 会更丰富"**:同一段频率 + 同一节奏位再加一轨 = frequency masking,听感更糊不是更满。
- **假装能自动加载 Kontakt patch**:agent 只能 `add_track_fx("Kontakt")`,具体 patch 用户手动选。明说,不要糊弄。
- **所有轨都 pan center**:立体声宽度靠 pan 分工,不是靠 reverb。Chord/Guitar/Perc 至少 pan ±40,否则听起来是一团 mono。
