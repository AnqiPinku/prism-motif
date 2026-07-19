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
- [x] `execute`、`external`、`record` 始终确认；普通模式下 `destructive` 也确认；
- [x] 信任模式只放行 Policy 已知的 REAPER 工程内写入，以及显式标记的可撤销删除/替换；
- [x] `batch` 展开到子调用判定；任意 ReaScript/Lua、覆盖渲染、录音仍进入强制确认；
- [ ] 权限卡展示目标、参数、风险与不可逆性。

### 1.4 信任模式

- [x] 默认关闭；
- [x] 仅当前进程有效；
- [x] 不再持久化到 localStorage；
- [x] MCP 开关或 Provider 设置改变时自动退出；
- [x] UI 始终显示当前信任状态；
- [x] 明确说明信任模式让 REAPER 工程内编辑自动执行，录音、文件与代码操作仍确认。

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
- [x] 普通模式下 delete_track 无确认被拒绝；信任模式可放行显式标记的工程内删除；
- [x] run_lua 无确认被拒绝；
- [x] 信任模式不能跳过任意代码、录音、外部调用和文件副作用；
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

- [x] 保持运行时零依赖；测试优先使用 unittest；
- [x] Fake Provider 覆盖流式、重试、断流、空响应、工具调用；
- [x] Fake MCP 覆盖握手、超时、退出、错误、超长结果与风险元数据；
- [x] Gateway 测试不依赖真实 API Key；
- [x] 主仓执行真正 MCP 集成测试，不再静默 SKIP。

### 2.2 前端事件状态机

- [x] 从 App.tsx 抽出纯 `reduceChatEvent`；
- [x] 覆盖全部 ChatEvent；
- [x] 覆盖 EOF 无 done、重复事件、迟到事件、取消后事件；
- [x] SSE 网络层与 UI 状态层分离；
- [x] 前端零 Lint 警告。

### 2.3 CI

- [x] Python 3.10 核心 / Gateway / Staging 测试；
- [x] Node `npm ci`、lint、build；
- [x] Windows Rust test、release check；
- [x] 禁止密钥、私有绝对路径和大音频文件；
- [x] 检查正式配置无 system-mcp；
- [x] 检查版本号、许可证和仓库地址一致。

已落地：`.github/workflows/ci.yml`（push/PR，2026-07-11 首绿）+ `tests/check_repo_hygiene.py`。

### 2.4 稳定性

- [x] 连续 20 回合聊天；
- [x] 中途取消 5 次；
- [x] Provider 失败 5 次；
- [x] MCP 超时 3 次；
- [x] 无遗留进程；
- [x] 无损坏线程；
- [x] SSE 连接回落；
- [x] 内存不持续线性增长。

已落地：`tests/soak_test.py`（真实 Gateway 进程 + Fake Provider/MCP 全离线，另含
1 次同线程抢占；每操作后校验 /api/state 秒回、线程档案可解析、TCP 不累积；
2026-07-12 本机 20.8s 全过，进 CI 为独立步骤）。

### 验收

- CI 全绿；
- Rust 有实际测试，不再是 0 tests；
- 关键验证不需真实 Key；
- 20 回合 Soak Test 通过。

（以上四条 2026-07-12 全部达成，Phase 2 完成。）

---

## Phase 3：工具语义、音乐知识与 Agent Eval

### 3.1 MIDI 原子修改

- [x] 新增 `update_midi_note`；
- [x] 新增 `delete_midi_notes`；
- [x] 新增 `replace_midi_notes`；
- [x] 替换操作进入 REAPER Undo Block（三个写操作均单 undo 块，pcall 保证出错也配对关闭）；
- [x] Pitch Correction 不再调用只追加的 add_midi_notes 做替换（composition-workflow、
      tension-design 同类误导表述一并清除）；
- [x] 写操作返回 before/after 摘要；
- [x] 验证无重复音符、错轨和属性污染（2026-07-12 真机 REAPER 验收 20/20：写音/逐音改/
      删除/替换/muted 保真/坏参数攻击零数据丢失/小数索引攻击无误删/单步 undo 精确回退/
      清理零残留。真机另抓到并修复一个离线测不出的坑：Undo_Begin/EndBlock2 对纯 MIDI
      修改不生成撤销点，须用 Undo_OnStateChange_Item——一步 undo 曾连带撤掉整条轨）。

Phase 3.1 完成。离线证据：13 项 server 自测 + 19 项内嵌 Lua 运行时行为仿真。

### 3.2 工具契约

- [x] 静态检查 Skill 中的工具名；
- [x] 验证参数名、单位、索引与追加/替换语义；
- [x] Skill 示例必须通过当前 Tool Schema；
- [x] 写操作标明可撤销性与覆盖风险（MIDI 工具的 undo/追加/替换语义见 3.1；
      渲染工具补 OVERWRITE 警示；destructive 描述义务由检查器持续门禁）。

已落地：`tests/check_tool_contracts.py`（spawn 两个真实 MCP server 取 schema 对账
Skill 引用；进 CI）。首跑即抓 14 条真实漂移：6 个技能里的错误参数名
（wav→path、focus→question、start_beat→start_beats、fxidx→fx_index、
param_index→param、start/end→start_beats/end_beats）、幻觉工具引用
（set_eq_band）、以及 add_track_fx 无法寻址 master 总线的过度承诺——全部修正。

### 3.3 音频术语

- [x] 区分 Integrated / Short-term / Momentary LUFS；
- [x] Skill 不再把片段 Integrated 误称 Short-term（工具描述与 mastering-basics
      均明示"片段测得的是该片段的 integrated"）；
- [x] 增加真正的时间序列响度工具（扩展 measure_loudness：short_term_max /
      momentary_max / short_term_series 逐秒曲线，K 加权一次三尺度共享，
      合成 burst 测试验证 6-9s 响段可精确定位）；
- [x] 平台响度写成参考和策略（mastering-basics 重写：归一化参考线 ≠ 交付目标，
      交付区间按风格审美选；checklist 的 ±0.5 LU 硬指标改为策略区间；
      pumping 诊断改为主观听感 + short_term_series 曲线交叉验证）。

### 3.4 Skill 可信度

知识分为：

```text
standard          标准或可测量定义
heuristic         有适用条件的经验
creative_default  为快速开始提供的创作默认
```

- [x] 删除无来源的伪精确阈值（2026-07-19 第一轮审计 10 个技能：清除编造统计
      「70%/90%/100%/占 80%/60% 的动态感」、假心理声学换算「免费 3dB」、
      误用行规「两乐器间 <0.5 LUFS」；修正事实错误：hook 时点算术 0:34→0:43、
      四分音符拍值、跳进定义、步数计数；第二轮修正跨平台 -14 LUFS 概括、
      未定义的能量阈值和未经官方确认的 MPC→REAPER Swing 精确换算）；
- [x] 强数字规则写明风格、条件和误差（hook 时窗限定 pop/EDM 并给 ballad/ambient
      出口；段落 LUFS 阈值补「master 推到成品响度」前提；de-esser threshold 改为
      「起调值 + 触发判据」；vibrato 批量删除补吉他/口琴例外 + 删前 A/B；
      限制器在链上时增益映射非 1:1）；
- [ ] 重要 Skill 经过真实制作人复核（人工门：需真实制作人参与，待用户安排）；
- [ ] A/B 与测量用于验证重要建议（依赖 3.5 Gold Task 的渲染-测量闭环落地）。

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

- [x] 建立上述 6 个固定工程模板；混音素材在隔离运行目录确定性生成，不提交二进制音频；
- [x] 6 个工程经真实 REAPER 逐个打开验证，轨道结构一致，两个 MIDI 工程分别读出 13 / 8 个音符；
- [x] 建立首批 10 个唯一任务、证据 schema、隔离运行准备器、结构/测量评分器和发布门汇总；
- [x] `mix-clipping` / `mix-muddy` 经真实 REAPER 渲染，再由 `music-perception-mcp` 完成基线测量；
- [x] 完成 G001 的普通模式与信任模式现场试跑：信任模式下 12 次工具调用、2 个安全 `batch` 为零权限请求；该轮因对象式批参数造成额外轨道而失败，未伪记为通过；
- [x] reaper-mcp 对已知工具的对象式批参数增加规范化，避免 Lua 把对象强制转换成错误轨名；离线 MCP 自测已覆盖；
- [ ] 接入真实 Prism Motif Agent 运行驱动，自动采集前后快照、事件、许可和耗时证据；
- [ ] 跑完首批 10 个真实任务并形成基线，再扩到至少 30 个唯一任务。

指标：

- Task Success Rate；
- Wrong-Track Modification Rate；
- Duplicate MIDI Rate；
- Unauthorized Destructive Action Rate；
- Tool Error Recovery Rate；
- Before/After Measurement Validity；
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

Phase 1 首批任务状态（历史，已完成并合入 `main`）：

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

当前施工入口：

1. [ ] 安排真实制作人复核关键 Skill；
2. [x] 建立 3.5 的 6 个固定 REAPER 工程、首批 10 个任务定义与离线 Gold Task Harness；
3. [ ] REAPER 重新运行桥接后复跑 G001；随后固化真实 Agent 运行驱动，先跑出这 10 个任务的可重复基线，再扩到至少 30 个唯一任务并达到 v0.2 Eval 门；
4. [ ] 用渲染、测量和响度匹配 A/B 关闭 3.4 最后一项；
5. [ ] Eval 门通过后进入 Phase 4，随后执行 Phase 5 当前主线的完整发布验证。

在 Phase 3 Eval 门完成前，不新增模式、MCP、其他 DAW 或新的音乐功能，也不开始大规模 UI/Gateway 重写。
