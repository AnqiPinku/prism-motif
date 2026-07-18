# Gold Task Harness 验证记录

日期：2026-07-19

## 已验证

目录与离线合约：

```text
python -m tests.gold.runner verify
=> tasks: 10, fixtures: 6

python -m unittest tests.test_gold_eval -v
=> 10/10 passed
```

同轮仓库门禁结果：Python 90/90、前端 11/11、Rust 3/3、25 回合 Soak、仓库卫生、32 个真实工具契约和两个 sibling MCP 自测均通过；前端生产构建为 413.42 kB（gzip 124.56 kB）。

真实 REAPER 验证前先通过 `reaper_status` 确认当前实例为 `(unsaved)`、0 轨、停止状态。随后用 `reaper_call(Main_openProject)` 依次打开运行器准备的工程：

| fixture | 实际轨道 | MIDI 音符 |
|---|---|---:|
| `empty.rpp` | 无 | — |
| `chord-loop.rpp` | Chords | 13 |
| `arrangement-flat.rpp` | Drums, Bass, Pad | — |
| `mix-clipping.rpp` | Mix Bus | — |
| `mix-muddy.rpp` | Mix Bus | — |
| `melody-offkey.rpp` | Lead | 8 |

六个工程均成功打开且 `reaper_status` 的轨道结构与清单一致；两个 MIDI 工程通过真实 `get_midi_notes` 逐项比较 pitch、起点、长度、力度和 channel，均与 manifest 精确一致。验证后重新打开 `empty.rpp`，REAPER 回到空工程。

两个混音工程还经过真实 `render_to_wav(source="master")` → `music-perception-mcp.analyze_audio` 闭环：

| fixture | 渲染时长 | true peak | clipped samples | low-mid rel. | high-mid rel. |
|---|---:|---:|---:|---:|---:|
| `mix-clipping.rpp` | 4.0 s | 0.04 dBTP | 98,880 | -0.1 dB | -29.7 dB |
| `mix-muddy.rpp` | 4.0 s | -1.50 dBTP | 0 | -0.0 dB | -21.0 dB |

任务清单中的初始测量字段采用上述真实渲染结果。`low-mid rel.` 是 MCP 定义的 250–500 Hz 能量占总频谱能量的相对 dB，不是主观“浑浊分数”。

## 尚未验证

- 尚未接通自动驱动来运行真实 Prism Motif Agent；
- 10 个任务目前是可评分定义，不是 10 份真实 Agent 成绩；
- 尚未扩到 30 个唯一任务，因此 v0.2 Eval 门仍未通过；
- 尚未形成处理后渲染、响度匹配 A/B 和制作人复核结果；
- RPP 在线验证属于本机证据，CI 仍只运行离线目录、结构和评分合约测试。
