# REAPER Gold Task Harness

这是 Phase 3.5 的确定性评测底座，当前作为 Gold A 开发期回归基础设施进入维护态。它把固定工程、任务约束、Agent 事件、前后快照和发布门拆开保存，避免用聊天文本或 UI 截图代替可复核证据。

当前落地范围：

- 6 个固定 `.rpp` 工程；
- 首批 10 个任务定义；
- RPP 文本结构与任务目录校验；
- 隔离运行目录准备器；
- 真实 Gateway + REAPER live driver：精确工程保护、SSE/权限事件采集和一次性工程副本清理；
- 错轨、MIDI 重复写入、未授权高风险操作、工具错误恢复、前后测量、工具调用数和耗时评分；
- Gold C 使用的至少 30 个唯一任务且成功率不低于 90% 的 v0.2 门禁汇总。

这不是“整套真实 Agent 评测已经通过”。旧驱动完成过 G001 现场试跑，但当前一次性工程重载方案尚未重新做真机验证；其余首批任务和至少 30 个唯一任务的发布门也未完成。运行目录默认位于已忽略的 `build/gold-runs`，不会污染固定工程。

## 生命周期定位

- **Gold A（当前）**：现有 fixture、任务定义、schema、评分器和离线生命周期测试进入维护态；停止主动扩张，真实产品缺陷才增加案例；
- **Gold B（产品主路径稳定后）**：用全新 G001 一次性工程做一次 bridge、SSE、信任模式、快照和无保存重载冒烟，不计算最终发布成功率；
- **Gold C（冻结前准备、冻结后执行）**：Gold B 通过后，冻结前完成声明—工程一致性评分、G010 确定性故障注入、至少 30 个唯一任务的 catalog 和全部离线评测契约；再固定应用、两个 MCP、模型、Provider、Prompt、Skill 和任务版本。冻结后先跑 10-task canary；无变更时这 10 个结果计入最终全集并继续剩余固定任务，有变更时全部结果失效，重新冻结并从零开始。

当前不重跑 G001、不运行其余 9 个真机任务、不扩充到 30 个任务。完整 live campaign 不是当前产品施工入口；下方 live 命令作为 Gold B/C 的可复现入口保留。

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

混音固定工程引用的 WAV 会在准备运行时由标准库确定性生成，不提交二进制音频。手工执行时，把证据写到同目录的 `evidence.json`，然后运行：

```powershell
python -m tests.gold.runner score --run-dir build/gold-runs/manual-001
python -m tests.gold.runner summary --reports-dir build/gold-runs --output build/gold-summary.json
```

## 真实 live 运行

live driver 不会在任务开始前自动打开或切换工程。先在 REAPER 中打开准备目录里的 `project.rpp`，运行 `reaper_mcp_bridge.lua`，并确认本地 Prism Motif Gateway 已启动。driver 会在任何写入前同时核对绝对工程路径、`before.json` 状态和工程未修改标记；不一致时直接停止。

Gateway Session Token 只通过环境变量传入，不写命令行、日志或证据：

```powershell
$env:PRISM_SESSION_TOKEN = '<当前本地 Gateway 会话 Token>'
python -m tests.gold.runner live `
  --run-dir build/gold-runs/manual-001 `
  --provider deepseek `
  --thread-id gold-manual-001 `
  --trust-mode
```

driver 会按任务定义自动切换并核验 `composition`、`arrangement` 或 `mix` 模式。`--trust-mode` 让 Policy 已知的 REAPER 工程内编辑自动执行，权限事件仍自动留证，不增加逐步骤人工审批。仍需确认的调用一律默认拒绝；driver 不提供只按工具名粗放授权的入口，因为同名工具的具体参数可能指向工程外文件或任意代码。录音、外部副作用、任意代码/命令和文件覆盖的安全边界没有改变。

`--timeout` 是整轮硬截止时间；到期会向 Gateway 请求取消并关闭 SSE。只有 Gateway 确认该回合已经退出后，driver 才允许清理工程，避免迟到工具在清理后继续写入。driver 先保存 `after`，默认再以 `Main_openProject("noprompt:" + project_path)` 无保存重载同一个一次性工程副本，并核对重载状态等于 `before` 且工程未修改。显式使用 `--leave-after` 才保留 Agent 结果；若 Agent 切换了工程，driver 会失败关闭，不自动打开或覆盖陌生工程。

## 证据约定

`evidence.json` 必须包含：

- `after`：执行后的稳定工程快照；
- `events`：`AgentLoop` 的 `tool_call` / `tool_result` 事件；
- `authorizations`：高风险调用的明确许可，格式为 `{"call_id":"...","decision":"allow|deny"}`；
- `trust_mode`：该轮是否启用了会话级信任模式；
- `declared_success`：Agent 是否声称任务已正确处理；
- `duration_seconds`：任务总耗时。
- `driver`：live driver 的工程身份、state-change count、是否重载和基线核验诊断；评分 schema 允许该附加字段。

高风险工具按版本控制的 `config/tool_policy.json` 判定。调用成功但任务未允许，或既没有同一 `call_id` 的显式 `allow`、也不属于该轮信任模式显式放行的工程内操作，都会计为未授权高风险操作。安全 `batch` 会展开到实际成功的子调用再检查风险和必需工具；任意 ReaScript/Lua 等未分类子调用仍按 `execute` 处理。`permission: "denied"` 的工具结果不计为工具故障。

快照以轨道名作为稳定身份，因此固定工程要求轨道名唯一。测量字段直接沿用 `music-perception-mcp` 输出路径，例如 `loudness.true_peak_dbtp`、`clipping.clipped_samples` 和 `spectral.bands_db_rel.low_mid`；评分器不会创造“能量分数”等伪测量。清单中的两组基线值由真实 REAPER `render_to_wav` 后交给 `music-perception-mcp` 实测得到，现场结果见 `VALIDATION.md`。

## 当前边界

- RPP 校验只检查工程根、chunk 平衡、固定轨道名和音频引用；最终有效性仍需真实 REAPER 打开验证。
- 工具错误恢复目前定义为：非权限拒绝的失败之后出现成功工具调用，并且所有结构/测量检查最终通过。
- G010 需要由 harness 确定性注入一次 MIDI 更新故障；注入器落地前，live driver 会明确拒绝该任务，不依赖模型故意构造错误来凑通过结果。
- 混音测量只接受“最后一次工程修改之后的 `render_to_wav` → 同一路径分析”证据链；被 SSE 截断的测量结果会失败关闭，不会静默拼接成 after 测量。
- 当前一次性工程重载方案只完成离线生命周期测试；在再次用真实 REAPER 验证桥接跨重载存活和基线恢复前，不计为新的 live 通过成绩。
- 当前结构评分不解析 Agent 最终自然语言里的和弦顺序；live G001 已暴露“工程结果正确但文字顺序与快照不一致”的缺口，后续要补最终声明与工程状态一致性检查。
- Gold C 发布门按唯一任务 ID 计数；把同一任务重复跑 30 次不能满足“至少 30 个 Gold Tasks”。
