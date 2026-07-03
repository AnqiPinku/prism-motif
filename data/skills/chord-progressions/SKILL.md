---
name: chord-progressions
disclosure: lazy
mode: composition
tags: [chords, progression, harmony, composition, borrowed, substitution, voicing, midi]
description: 当用户要写和弦进行、卡在"下一段和弦怎么走"、想要某种情绪(明亮/忧郁/紧张/温暖/悬浮/电影感)对应的进行、想给现有旋律配和弦、想把"太普通的 I-V-vi-IV"换个说法、或问 borrow/secondary dominant/tritone sub/Neapolitan/模态互换/turnaround 这类替代手法时触发。触发词:和弦进行、chord progression、配和弦、走向、卡农进、4536251、借用和弦、副属、离调、tritone sub、Neapolitan、模态互换、模态借用、voicing、转位、bassline、走低音。用于 composition 阶段决定骨架,不管配器和混音。默认直接给具体调、罗马数字、和弦符号、MIDI 音高数组,可以直接喂 reaper-mcp 的 add_midi_notes。
---

# Chord Progressions — 情绪对味的和弦骨架库

## When to use

用户要写新段落的和弦骨架、给旋律配和弦、或想把老套的进行改出新意。默认输出:**调 + 罗马数字 + 具体和弦符号 + MIDI 音高数组**,可以直接调 `add_midi_notes` 落到 REAPER 的 MIDI item。先给一个默认进行动手,再解释为什么它有那个情绪;用户 30 秒内否掉再换。不问"你想要什么感觉",直接先给 F 大调 vi-IV-I-V 4 小节,不合适再改。

## 术语一次说清

- **罗马数字**:大写=大三和弦(I IV V),小写=小三和弦(ii iii vi),° = 减和弦。写在调内,I 在 C 调=C,在 F 调=F。
- **MIDI 音高约定**:本文档 middle C = MIDI 60 = C4(General MIDI 规范,REAPER 默认)。C3=48,C5=72。喂 `add_midi_notes` 时 pitch 参数就是这个数。
- **borrow(借用和弦 / 模态互换)**:从同主音小调借一个和弦进大调。C 大调借 iv=Fm、bVI=Ab、bVII=Bb。加一层"忧郁的阴影"。
- **secondary dominant(副属)**:临时把某个和弦当"新主",给它接一个属七。写作 V/x。C 调里 V/vi = E7 → Am。制造 tension→resolve(紧张→释放,属七不稳定,回到目标和弦有"到家了"的感觉)。
- **tritone sub(三全音替代)**:把 V7 换成低半音的 V7(G7 → Db7),bass 半音下行到 I,jazz/neo-soul 常用。
- **Neapolitan(那不勒斯)**:小调里 bII 的大三和弦(Am 调里的 Bb),一次性戏剧色彩,通常接 V。
- **turnaround**:段落末尾把和声"绕"回段首的短过渡进行,jazz 里最典型的是 iii-vi-ii-V-I。
- **voicing**:同一个和弦的音怎么摆。close(密集,一个八度内)vs open(开放,音分散);转位=不用根音在最低。
- **add9 / maj7 / dom7**:add9=三和弦上叠根音上方九度(C add9 加 D);maj7=三和弦加大七度(C 加 B);dom7=大三和弦加小七度(C 加 Bb),属七功能必须用它。

## 情绪 × 进行 速查表

| 情绪 | 进行(C 调罗马) | C 调和弦 | 用在哪 | 关键音 |
|---|---|---|---|---|
| 明亮直白 | I-V-vi-IV | C-G-Am-F | pop 副歌、动画片头 | 4 小节循环 |
| 忧郁温柔 | vi-IV-I-V | Am-F-C-G | 抒情 verse、city pop | 起在 vi |
| 悬而未决 | I-iii-vi-IV | C-Em-Am-F | ambient、lofi | iii 让 I→vi 不那么直 |
| 卡农进(循环下行 bass)| I-V/vi-vi-iii-IV-I/iii-ii-V | C-E7-Am-Em-F-C/E-Dm-G | 卡农、婚礼、日系 | bass 顺阶下行 8 度 |
| 电影感张力 | i-bVI-bIII-bVII | Am-F-C-G(小调)| Hans Zimmer、trailer | 起在 i(小调)|
| 蓝调忧郁 | I-iv-I-V | C-Fm-C-G | soul、R&B verse | iv 是模态互换 |
| Jazz turnaround | iii-vi-ii-V-I | Em7-Am7-Dm7-G7-Cmaj7 | jazz 段落收尾 | 全 7 和弦化 |
| 冷峻电子 | i-bVII-bVI-bVII | Am-G-F-G | synthwave、dark pop | 全在白键 |
| 神秘悬浮 | Imaj7-IVmaj7 循环 | Cmaj7-Fmaj7 | neo-soul、lofi 主题 | 两个和弦足够 |
| Andalusian(西班牙感)| i-bVII-bVI-V | Am-G-F-E | flamenco、metal | E 是大三,亮 |
| Neapolitan 收束 | i-bII-V-i | Am-Bb-E-Am | 戏剧、古典 | Bb 一次性用 |

## 默认动作:F 大调 vi-IV-I-V,4 小节,每和弦 1 小节

和弦:**Dm - Bb - F - C**。close voicing,写成 MIDI(middle C = 60 = C4):

- Dm: `[62, 65, 69]` = D4 F4 A4
- Bb: `[58, 62, 65]` = Bb3 D4 F4
- F:  `[57, 60, 65]` = A3 C4 F4
- C:  `[60, 64, 67]` = C4 E4 G4

调 `add_midi_notes`:每和弦占 1 整小节(4/4 = 4 拍),start=0/1/2/3 小节起,length=1 小节,velocity=80。

**Bass 单独一轨走根音**,音区 F2–F3 一带(听得见 bass 又不闷)。MIDI:

- Dm 小节 → D3 = `38`
- Bb 小节 → Bb2 = `34`
- F 小节  → F2  = `29`(太低就用 F3=41)
- C 小节  → C3  = `36`

**为什么 vi 开头**:vi 是相对小调,主音在暗色一侧,4 小节末尾停在 V(C)带出"下一句"的悬念,天然循环。

## 3 种改造:同一进行不同味道

不喜欢?30 秒改一次:

1. **加副属推进** — 在 F(I)前一拍插 V/IV = C7,变成 `Dm | Bb-C7 | F | C`。C7 MIDI `[60, 64, 67, 70]` = C4 E4 G4 Bb4。Bb→A 半音进 F 的 A,推动感立刻出。
2. **借用 iv 换 IV** — 把 Bb 换成 Bbm(F 调的 iv 借用)。Bbm MIDI `[58, 61, 65]` = Bb3 Db4 F4。Db 是特征音,忧郁度 +50%。用在 verse 最后一句效果最好。
3. **末尾 tritone sub** — 把最后的 C(V)换成 F#7(bII7)。bass 走 F#→F,neo-soul 感立刻出。F#7 MIDI `[54, 58, 61, 64]` = F#3 Bb3(=A#3) C#4 E4;bass F#2 = `30`。

## Voicing 具体指令

- **左手 bass 单音在 F2–F3(MIDI 29–41)**,右手三/四音和弦放在 C4–C5(MIDI 60–72)之间不打架。
- **转位规则:让每个和弦的最低音走小二度或大二度(顺阶),不跳四五度**。默认动作里 Dm→Bb 右手最低音 D4→Bb3 走大三度,已经很平顺;若要更紧,把 Bb 用第一转位 Bb/D:`[62, 65, 70]` = D4 F4 Bb4,最低音 D4 保持不动。
- **Add9 / maj7 上色**:任何 I 或 IV 可以直接加 9(Cmaj 上加 D5=74)或 maj7(Cmaj 上加 B4=71),lofi/neo-soul 立刻到位。V 不加 maj7(会毁掉属功能),要属功能就加 b7:C7 = `[60, 64, 67, 70]`。

## Anti-patterns

- **只给"I-V-vi-IV"不给调、不给 MIDI**。用户还得自己查 C 大调 vi 是什么。永远写出具体和弦名 + MIDI 音高数组。
- **MIDI 音高不写清 middle C = 多少**。C3 还是 C4 是 General MIDI 和 Yamaha 标准的差异,不声明会差一个八度。本 skill 统一 middle C = MIDI 60 = C4。
- **每个和弦都塞满 7 音**。verse 应该留白,7/9/13 全上是 jazz 语汇,pop verse 用会显得油腻。先三和弦,副歌才铺 7。
- **Bass 音区选错**。低于 MIDI 28(≈E1)在多数听音环境放不出来,高于 MIDI 48(C3)会跟人声打架。稳妥区间 MIDI 29–41。
- **忽略 bassline 的顺滑度**。和弦符号对但 bass 上蹿下跳,听起来就散。转位规则一定要执行。
- **借用和弦当调味料乱撒**。iv、bVII、Neapolitan 有效是因为它们在特定位置(通常在回 I 之前)提供一次色彩转折。每 4 小节最多一个借用,多了变味。
- **副属和弦不解决**。V/vi = E7 后面必须接 Am,不接就是悬空的怪音,不是"高级"。
