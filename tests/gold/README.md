# REAPER Gold Task Harness

这是 Phase 3.5 的确定性评测底座。它把固定工程、任务约束、Agent 事件、前后快照和发布门拆开保存，避免用聊天文本或 UI 截图代替可复核证据。

当前落地范围：

- 6 个固定 `.rpp` 工程；
- 首批 10 个任务定义；
- RPP 文本结构与任务目录校验；
- 隔离运行目录准备器；
- 错轨、MIDI 重复写入、未授权高风险操作、工具错误恢复、前后测量、工具调用数和耗时评分；
- 至少 30 个唯一任务且成功率不低于 90% 的 v0.2 门禁汇总。

这不是“真实 Agent 评测已经通过”。当前代码能准备工程并评分证据；真实 REAPER 驱动、实际 Agent 执行和 30 个唯一任务结果仍需后续接入。运行目录默认位于已忽略的 `build/gold-runs`，不会污染固定工程。

## 命令

在仓库根目录运行：

```powershell
python -m tests.gold.runner verify
python -m tests.gold.runner list
python -m tests.gold.runner prepare --task G003-chord-fsharp-to-f --run-id manual-001
```

`prepare` 会创建：

```text
build/gold-runs/manual-001/
  project.rpp
  task.json
  before.json
  evidence.template.json
```

混音固定工程引用的 WAV 会在准备运行时由标准库确定性生成，不提交二进制音频。把执行后的证据写到同目录的 `evidence.json`，然后运行：

```powershell
python -m tests.gold.runner score --run-dir build/gold-runs/manual-001
python -m tests.gold.runner summary --reports-dir build/gold-runs --output build/gold-summary.json
```

## 证据约定

`evidence.json` 必须包含：

- `after`：执行后的稳定工程快照；
- `events`：`AgentLoop` 的 `tool_call` / `tool_result` 事件；
- `authorizations`：高风险调用的明确许可，格式为 `{"call_id":"...","decision":"allow|deny"}`；
- `declared_success`：Agent 是否声称任务已正确处理；
- `duration_seconds`：任务总耗时。

高风险工具按版本控制的 `config/tool_policy.json` 判定。调用成功但任务未允许，或证据中没有同一 `call_id` 的显式 `allow`，都会计为未授权高风险操作。`permission: "denied"` 的工具结果不计为工具故障。

快照以轨道名作为稳定身份，因此固定工程要求轨道名唯一。测量字段直接沿用 `music-perception-mcp` 输出路径，例如 `loudness.true_peak_dbtp`、`clipping.clipped_samples` 和 `spectral.bands_db_rel.low_mid`；评分器不会创造“能量分数”等伪测量。清单中的两组基线值由真实 REAPER `render_to_wav` 后交给 `music-perception-mcp` 实测得到，现场结果见 `VALIDATION.md`。

## 当前边界

- RPP 校验只检查工程根、chunk 平衡、固定轨道名和音频引用；最终有效性仍需真实 REAPER 打开验证。
- 工具错误恢复目前定义为：非权限拒绝的失败之后出现成功工具调用，并且所有结构/测量检查最终通过。
- 发布门按唯一任务 ID 计数；把同一任务重复跑 30 次不能满足“至少 30 个 Gold Tasks”。
