# Gold Task Harness 验证记录

日期：2026-07-19

## 已验证

目录与离线合约：

```text
python -m tests.gold.runner verify
=> tasks: 10, fixtures: 6

python -m unittest tests.test_gold_eval -v
=> 19/19 passed

python -m unittest tests.test_gold_live_driver -v
=> 22/22 passed

python -m unittest discover -s tests -v
=> 125/125 passed
```

本轮移除整轮撤销评分并改为一次性工程重载后，只执行非实时验证：Python 125/125、仓库卫生、32 个真实工具契约、Gold 目录 10 任务/6 工程和 reaper-mcp 14/14 均通过。按用户要求没有启动或控制 REAPER，也没有把当前重载方案记成真机通过；前端、Rust、Soak 与完整发布门沿用最近基线，未在本轮重复运行。

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

## G001 真实 Agent 试跑

同日用真实 Prism Motif Gateway、DeepSeek Provider、REAPER 和桥接脚本对 `G001-empty-create-chords` 做了多轮现场试跑：

1. 普通模式（`bypass=false`）：Agent 读取空工程后调用 `batch` 设置速度、拍号并加轨；旧策略把整个 `batch` 固定归为 `execute`，自动驱动按审计场景拒绝，工程保持 120 BPM、0 轨，Agent未声明完成。该轮没有未授权动作，也没有 false-success，但任务失败。
2. 修正策略后的信任模式（`bypass=true`）：12 次工具调用含 2 个安全 `batch`，权限请求为 0，证明工程内编辑不再逐步要求人工许可。最终工程为 100 BPM，含 `Track 1` 与 `Chords` 两轨，`Chords` 有 12 个音符；模型却声称只有一轨并完成任务。评分器据实记录 wrong-track modification = 1、false-success = 1、unauthorized high-risk = 0，任务失败。

第二轮暴露的原因不是权限策略，而是模型把批处理位置参数写成了对象；Lua 将对象强制转换后先创建了默认 `Track 1`。reaper-mcp 随后增加已知工具对象参数规范化，并用 Fake Bridge 自测覆盖 `add_track` / `set_tempo` 两种对象写法。

桥接重启并恢复隔离空工程后，又完成两次历史试跑：

3. composition 模式、信任模式的手工驱动复跑：7 次工具调用、0 次权限请求；第一次 `create_midi_item` 约 10 秒超时，Agent 先重新读取状态再重试成功。最终只修改 `Chords`，有 4 小节、12 个 MIDI 音符，证明工程内编辑无需逐步骤人工许可。
4. 仓库内旧 live driver 真实复跑：5 次工具调用、0 次权限请求、14.959 秒；输出为 C 大调 `Am-F-C-G` 循环，并促使 G001 的 C 大三和弦规则从固定 MIDI `60/64/67` 改成八度无关的 pitch class `0/4/7`。这两轮使用的旧清理机制已退役，不计为当前严格 G001 或当前 live driver 的通过成绩。

第四轮同时发现一个尚未进入硬评分的新问题：实际 MIDI 为 `Am-F-C-G`，Agent 最终文字却报告 `C-G-Am-F`。工程任务本身满足“4 小节 C 大调和弦循环”，但最终描述与快照不一致。`composition-workflow` 已增加写后 `get_midi_notes` 读回规则；仍需在 live driver/评分层补独立的一致性证据，不能把当前结构通过写成“所有语义声明均已验证”。

## 尚未验证

以下项目仍是发布前必须完成的事实缺口，但按 2026-07-19 更新后的路线图分配到 Gold B、Gold C Prep 和冻结后执行，不是当前施工入口：产品主路径稳定后只做一次 Gold B G001 生命周期冒烟；Gold B 通过后，声明一致性、G010 注入、30-task catalog 与离线契约在候选冻结前完成；冻结后再执行 Gold C 的完整真机矩阵与发布门。

- 当前 live driver 已改为一次性工程副本与无保存重载，但尚未重新做真机生命周期验证；其余 9 个首批任务仍主要是可评分定义，不是 9 份通过的真实 Agent 成绩；
- 最终自然语言声明与工程快照的一致性尚未进入硬评分；
- 尚未扩到 30 个唯一任务，因此 v0.2 Eval 门仍未通过；
- 尚未形成处理后渲染、响度匹配 A/B 和制作人复核结果；
- RPP 在线验证属于本机证据，CI 仍只运行离线目录、结构和评分合约测试。
