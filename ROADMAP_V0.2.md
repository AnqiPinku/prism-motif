# Prism Motif v0.2 路线图

> 状态：当前唯一执行计划  
> 建立日期：2026-07-10  
> 当前公开版本：v0.1.0  
> 当前候选版本：v0.1.1-security  
> 下一发布：v0.1.1-security → v0.2.0

## 1. 目标

把 Prism Motif 从“可演示、可安装的 AI 音乐 Agent MVP”推进为：

- 本地控制面有明确安全边界；
- 关键行为可自动验证；
- Skill 与真实工具语义一致；
- 作曲、编曲、混音建议不过度承诺；
- 代码可以继续维护；
- 安装包、许可证和产品说明可信。

v0.2 的产品定位固定为：

> 面向 REAPER 的本地优先音乐制作 Copilot。它把自然语言转成可编辑的 MIDI、轨道、结构与混音操作，并用确定性音频测量验证结果。

## 2. 本周期不做

在 v0.2.0 发布前冻结以下扩张：

- 不增加第四种工作模式；
- 不做多 Agent、Reflexion 或规划器；
- 不做向量记忆；
- 不做 Stem Separation；
- 不扩展其他 DAW；
- 不做 Skill 市场、云同步或账户系统；
- 不做 macOS/Linux；
- 不继续增加泛化系统工具；
- 不用更多 Prompt 掩盖工具或评测缺口。

保留且必须做稳的主路径：

1. 作曲 / 编曲 / 混音三模式；
2. REAPER 控制；
3. 确定性音频分析；
4. 可选 Gemini 主观听感；
5. 项目、线程与上下文管理；
6. Windows MSI。

## 3. 发布序列

```text
Phase 0  文档与基线
  ↓
Phase 1  v0.1.1-security
  ↓
Phase 2  自动化验证与 CI
  ↓
Phase 3  工具语义、音乐知识与 Agent Eval
  ↓
Phase 4  前端 / Gateway 结构重构
  ↓
Phase 5  v0.2.0 发布可信度
```

| 阶段 | 目标 | 发布门 |
|---|---|---|
| 0 | 统一文档、保存基线、冻结范围 | 当前事实只有一个来源 |
| 1 | 修复本地 Gateway 与工具权限 | v0.1.1-security |
| 2 | CI、Fake Provider/MCP、端到端测试 | 关键路径离线可复现 |
| 3 | 工具契约、音乐知识、Gold Tasks | Agent 不再自信地做错事 |
| 4 | 测试保护下拆分结构 | 零行为回归 |
| 5 | 元数据、许可证、安装与产品叙事 | v0.2.0 |

---

## Phase 0：文档与基线

### 范围

- [x] 建立本路线图；
- [x] 重写 DESIGN.md、NOTES.md、HANDOFF.md、AGENTS.md；
- [x] 修复主测试的 reaper-mcp 迁移路径；
- [x] 记录 Python / Node / Rust / MCP 基线结果；
- [x] 记录前端构建体积；
- [ ] 记录 Gateway 冷启动、取消与 20 回合稳定性基线；
- [ ] 固定一个可重复的 REAPER 测试工程。

### 基线命令

```powershell
python test_core.py
npm --prefix frontend run lint
npm --prefix frontend run build
C:\Users\XAQ\.cargo\bin\cargo.exe test --locked --manifest-path frontend/src-tauri/Cargo.toml
python A:\Prismcode\mcps\reaper-mcp\server\test_server.py
python A:\Prismcode\mcps\music-perception-mcp\server\test_server.py
```

### 验收

- 旧文档不再描述已经失真的“当前状态”；
- 本文件是唯一当前路线；
- 每条基线命令有明确 PASS / SKIP / FAIL；
- 未开始任何范围外功能。

### 2026-07-10 基线记录

- `python test_core.py`：全部通过，真实 sibling reaper-mcp 不再 SKIP；
- 产品安全测试：35 项通过；
- `npm run lint`：零警告；
- 前端生产构建：JS 412.21 kB / gzip 124.04 kB，CSS gzip 8.42 kB；
- Rust：3 项测试通过；
- `tauri build --debug --no-bundle`：成功生成 debug app；
- reaper-mcp：25 个工具，Fake Bridge 测试全部通过；
- music-perception-mcp：合成 WAV 测试全部通过；
- staging：认证、Policy 与 tool_policy 已进入包；system-mcp 未进入正式资源。

---

## Phase 1：v0.1.1-security

### 1.1 Gateway 会话身份

- [x] Tauri 每次启动生成高熵 Session Token；
- [x] Tauri 每次启动生成 Instance ID；
- [x] Tauri 选择随机可用本地端口；
- [x] 通过环境变量传入 Gateway：
  - `PRISM_PORT`
  - `PRISM_SESSION_TOKEN`
  - `PRISM_INSTANCE_ID`
- [x] 所有 `/api/*` 请求要求 `X-Prism-Session`；
- [x] `/health` 返回 product、protocol、instance_id、ready；
- [x] Tauri 打开窗口前发送认证健康请求并核对 Instance ID；
- [x] 前端通过 Tauri Command 获取 base URL 与 Token；
- [x] Session 信息只保存在内存，不进入 localStorage、日志或线程文件。

### 1.2 Origin 与 CSP

- [x] 删除所有 `Access-Control-Allow-Origin: *`；
- [x] Release 只允许实际 Tauri Origin；
- [x] Dev Origin 仅能通过 `PRISM_DEV_ORIGINS` 显式加入；
- [x] OPTIONS 同样验证 Origin；
- [x] 只允许 `Content-Type, X-Prism-Session` 请求头；
- [x] 恢复 Tauri CSP；
- [x] 禁止远程脚本、任意 iframe 和任意外部导航；
- [x] `connect-src` 仅覆盖本地 Gateway。

### 1.3 工具风险模型

工具风险分为：

```text
read          只读
write         可逆写操作
destructive   删除、覆盖、批量替换
execute       执行代码或命令
external      打开外部资源或产生外部副作用
record        录音、录屏或捕获输入
```

- [x] 建立独立、受版本控制的工具风险 Policy；
- [x] MCP 工具风险由 Policy 补齐，后续可读取标准 annotations；
- [x] 未声明工具默认按 `write` 处理，且信任模式不能放行未知工具；
- [x] `read` 自动执行；
- [x] `write` 普通模式确认；
- [x] `destructive`、`execute`、`external`、`record` 始终确认；
- [x] 信任模式不能跳过 destructive / execute / external / record；
- [x] `delete_track`、`run_lua`、覆盖渲染、录音进入强制确认；
- [ ] 权限卡展示目标、参数、风险与不可逆性。

### 1.4 信任模式

- [x] 默认关闭；
- [x] 仅当前进程有效；
- [x] 不再持久化到 localStorage；
- [x] MCP 开关或 Provider 设置改变时自动退出；
- [x] UI 始终显示当前信任状态；
- [x] 明确说明信任模式只跳过普通 write。

### 1.5 正式包收口

- [x] 从正式 MSI Resources 移除 system-mcp；
- [x] 从打包版 MCP 配置移除 system；
- [x] 开发仓保留 system-mcp，默认关闭；
- [x] Provider base_url 只接受 HTTPS，localhost/127.0.0.1 允许 HTTP；
- [x] 已存 Key 且目标主机改变时要求再次确认；
- [x] 日志不包含 Key、Authorization、Session Token。

### 1.6 安全测试

- [x] 无 Token 请求返回 401；
- [x] 错误 Token 返回 401；
- [x] 非允许 Origin 返回 403；
- [x] 正确 Origin + Token 成功；
- [x] 未认证请求不能修改 Provider；
- [x] 未认证请求不能启用 MCP；
- [x] 未认证请求不能发起聊天；
- [x] 健康握手拒绝错误 Instance ID；
- [x] delete_track 无确认被拒绝；
- [x] run_lua 无确认被拒绝；
- [x] 信任模式不能跳过 destructive；
- [x] 正式包配置与 Resources 不包含 system-mcp；
- [x] 日志扫描不命中敏感值；
- [x] 关闭窗口后 Gateway 与 MCP 子进程退出。

### v0.1.1-security 发布门

以下条件缺一不可：

- API 全部有 Session Token；
- 不再存在通配 CORS；
- 不再固定依赖 8770；
- 健康检查验证 Instance ID；
- 正式包不含 system-mcp；
- REAPER 高风险工具受代码级权限保护；
- CSP 已恢复；
- 安全测试全过；
- 干净 Windows 安装烟雾测试通过。

Phase 1 不夹带新音乐功能和大规模 UI 重构。

---

## Phase 2：自动化验证与 CI

### 2.1 Python 测试布局

目标结构：

```text
tests/
  test_loop.py
  test_reasoner.py
  test_mcp_client.py
  test_compaction.py
  test_threads.py
  test_gateway_auth.py
  test_gateway_settings.py
  test_gateway_chat.py
  test_permissions.py
  fixtures/
    fake_provider.py
    fake_mcp_server.py
```

- [ ] 保持运行时零依赖；测试优先使用 unittest；
- [ ] Fake Provider 覆盖流式、重试、断流、空响应、工具调用；
- [ ] Fake MCP 覆盖握手、超时、退出、错误、超长结果与风险元数据；
- [ ] Gateway 测试不依赖真实 API Key；
- [ ] 主仓执行真正 MCP 集成测试，不再静默 SKIP。

### 2.2 前端事件状态机

- [ ] 从 App.tsx 抽出纯 `reduceChatEvent`；
- [ ] 覆盖全部 ChatEvent；
- [ ] 覆盖 EOF 无 done、重复事件、迟到事件、取消后事件；
- [ ] SSE 网络层与 UI 状态层分离；
- [ ] 前端零 Lint 警告。

### 2.3 CI

- [x] Python 3.10 核心 / Gateway / Staging 测试；
- [x] Node `npm ci`、lint、build；
- [x] Windows Rust test、release check；
- [x] 禁止密钥、私有绝对路径和大音频文件；
- [x] 检查正式配置无 system-mcp；
- [x] 检查版本号、许可证和仓库地址一致。

已落地：`.github/workflows/ci.yml`（push/PR，2026-07-11 首绿）+ `tests/check_repo_hygiene.py`。

### 2.4 稳定性

- [ ] 连续 20 回合聊天；
- [ ] 中途取消 5 次；
- [ ] Provider 失败 5 次；
- [ ] MCP 超时 3 次；
- [ ] 无遗留进程；
- [ ] 无损坏线程；
- [ ] SSE 连接回落；
- [ ] 内存不持续线性增长。

### 验收

- CI 全绿；
- Rust 有实际测试，不再是 0 tests；
- 关键验证不需真实 Key；
- 20 回合 Soak Test 通过。

---

## Phase 3：工具语义、音乐知识与 Agent Eval

### 3.1 MIDI 原子修改

- [ ] 新增 `update_midi_note`；
- [ ] 新增 `delete_midi_notes`；
- [ ] 新增 `replace_midi_notes`；
- [ ] 替换操作进入 REAPER Undo Block；
- [ ] Pitch Correction 不再调用只追加的 add_midi_notes 做替换；
- [ ] 写操作返回 before/after 摘要；
- [ ] 验证无重复音符、错轨和属性污染。

### 3.2 工具契约

- [ ] 静态检查 Skill 中的工具名；
- [ ] 验证参数名、单位、索引与追加/替换语义；
- [ ] Skill 示例必须通过当前 Tool Schema；
- [ ] 写操作标明可撤销性与覆盖风险。

### 3.3 音频术语

- [ ] 区分 Integrated / Short-term / Momentary LUFS；
- [ ] Skill 不再把片段 Integrated 误称 Short-term；
- [ ] 增加真正的时间序列响度工具，或收缩现有表述；
- [ ] 平台响度写成参考和策略，不写成唯一母带目标。

### 3.4 Skill 可信度

知识分为：

```text
standard          标准或可测量定义
heuristic         有适用条件的经验
creative_default  为快速开始提供的创作默认
```

- [ ] 删除无来源的伪精确阈值；
- [ ] 强数字规则写明风格、条件和误差；
- [ ] 重要 Skill 经过真实制作人复核；
- [ ] A/B 与测量用于验证重要建议。

### 3.5 Gold Task Eval

固定工程至少覆盖：

```text
empty.rpp
chord-loop.rpp
arrangement-flat.rpp
mix-clipping.rpp
mix-muddy.rpp
melody-offkey.rpp
```

指标：

- Task Success Rate；
- Wrong-Track Modification Rate；
- Duplicate MIDI Rate；
- Unauthorized Destructive Action Rate；
- Tool Error Recovery Rate；
- Before/After Measurement Validity；
- Undoability；
- 平均工具调用数和完成时间。

### v0.2 Eval 门

- 至少 30 个 Gold Tasks；
- 总成功率 ≥ 90%；
- 未授权破坏性操作 = 0；
- 错轨修改 = 0；
- MIDI 重复写入 = 0；
- 工具失败后仍声称成功 = 0。

---

## Phase 4：结构重构

### 4.1 前端

目标边界：

```text
frontend/src/
  app/
  api/
  chat/
  workspace/
  reaper/
  settings/
  shared/
```

- [ ] 先抽纯函数；
- [ ] 再抽 Chat Event Reducer；
- [ ] 再抽只读展示组件；
- [ ] 再抽 Workspace / REAPER Hooks；
- [ ] 最后缩小根 App；
- [ ] 不进行一次性重写；
- [ ] 长消息使用 content-visibility 或虚拟化；
- [ ] 历史消息和工具使用稳定 ID。

### 4.2 Gateway

目标边界：

```text
gateway/
  server.py
  auth.py
  routes.py
  chat_stream.py
  settings_service.py
  workspace_service.py
  reaper_service.py
```

- [ ] 所有 API 经过统一 Auth；
- [ ] 路由、业务、存储和 SSE 分离；
- [ ] 统一结构化错误模型；
- [ ] 日志结构化且默认脱敏。

### 验收

- App.tsx 只负责高层组合；
- Gateway Auth 只有一个入口；
- 零 Lint 警告；
- 构建体积相对基线增长不超过 15%，除非有记录；
- 截图、Gold Tasks 和 Soak Test 无回归。

---

## Phase 5：v0.2.0 发布可信度

### 5.1 元数据

- [ ] package.json、Cargo.toml、tauri.conf、serverInfo 统一 0.2.0；
- [ ] Cargo description / authors / license / repository 正确；
- [ ] Git Tag、MSI 文件名、Release Notes 一致。

### 5.2 许可证

- [ ] prism-motif MIT；
- [ ] reaper-mcp MIT；
- [ ] music-perception-mcp 补 LICENSE；
- [ ] 增加 THIRD_PARTY_NOTICES.md；
- [ ] 逐项列出 bundled 组件与许可证义务。

### 5.3 产品表述

统一使用“本地优先”：

> REAPER 操作、工程文件、确定性音频分析和会话存档在本机完成；文本模型可选择本地或云端，Gemini 主观听感是可选云能力。

- [ ] 删除“100% on your machine”歧义；
- [ ] README 展示真实工程修改与前后测量；
- [ ] 明确当前限制；
- [ ] 增加 Security、Data Flow、Testing、Eval 章节。

### 5.4 干净机验证

- [ ] 无 Python / Node / Rust；
- [ ] 安装路径含空格；
- [ ] Windows 用户名含中文；
- [ ] REAPER 普通版与便携版；
- [ ] 无 Key 仍能进入界面；
- [ ] 本地模型与云模型；
- [ ] Bridge 安装与重载；
- [ ] 关闭后无遗留进程；
- [ ] 卸载不删用户工程；
- [ ] v0.1.1 → v0.2.0 保留配置与线程。

发布物：

```text
Prism-Motif-0.2.0-x64.msi
SHA256SUMS.txt
THIRD_PARTY_NOTICES.md
RELEASE_NOTES.md
```

### v0.2.0 发布门

- 安全测试全过；
- CI 全绿；
- Gold Tasks 达标；
- 无未授权破坏性操作；
- 前端零 Lint 警告；
- Rust 有实际测试；
- 20 回合 Soak Test 通过；
- MSI 干净机通过；
- 版本、许可证、仓库地址一致；
- 正式包不含 system-mcp；
- 日志敏感信息检查通过。

---

## 4. 建议提交序列

```text
docs: establish the v0.2 roadmap and replace stale project notes
test: fix the sibling MCP integration path
test: add gateway auth and fake-provider harness
feat(security): add per-session gateway authentication
feat(shell): allocate a dynamic port and verify gateway identity
fix(security): restrict origins and restore CSP
feat(policy): add MCP tool risk metadata
fix(policy): protect destructive REAPER tools
chore(pkg): remove system-mcp from release resources
test(ci): add Windows CI and repository hygiene checks
release: v0.1.1-security

feat(reaper): add atomic MIDI update/delete/replace tools
fix(skills): align pitch correction with mutation semantics
feat(perception): distinguish integrated and short-term loudness
docs(skills): classify standards, heuristics and creative defaults
test(evals): add REAPER gold-task harness
refactor(chat): extract the event reducer and chat state machine
refactor(ui): split workspace and archive components
refactor(gateway): centralize auth and route services
docs: add security, data-flow and testing documentation
chore(release): normalize package metadata and licenses
release: v0.2.0
```

每个提交必须：

- 独立可构建；
- 测试全过；
- 不夹带无关格式化；
- 安全协议变更必须带测试；
- 不同时进行大规模行为变更与 UI 重写。

## 5. 当前施工入口

首批任务状态：

1. [x] 修正 test_core.py 的 sibling MCP 路径；
2. [x] 建立 Gateway 会话认证测试；
3. [x] 实现 Session Token、Origin 校验与健康握手；
4. [x] 实现 Tauri 动态端口和运行时 API 会话；
5. [x] 移除通配 CORS；
6. [x] 收紧 CSP；
7. [x] 从正式包移除 system-mcp；
8. [x] 建立工具风险 Policy 与会话级信任模式；
9. [x] 增加 Provider URL 校验与跨主机二次确认；
10. [x] 修复静态文件和线程 ID 路径穿越边界；
11. [x] 在真实 Tauri WebView 中做认证/CSP UI 烟雾测试；
12. [x] 增加日志敏感信息扫描与子进程退出自动测试；
13. [x] 构建 v0.1.1 MSI，并以管理安装验证完整文件树与禁入项；
14. [x] 在无已安装版本的本机完成 v0.1.0 安装 → v0.1.1 升级 → 启动 → 卸载，确认用户数据不变；
15. [x] 在 Windows-latest 干净主机复跑安装烟雾测试（2026-07-11，`msi-smoke.yml`：冻结 sidecar → 重建内置 CPython → MSI 构建 → 静默安装 → 安装树校验 → 启动确认 Gateway 子进程 → 收口零残留 → 静默卸载，全链路通过，MSI 与安装日志见 run artifact）。

未完成 Phase 1 发布门之前，不开始 Phase 2–5 的功能性工作。
