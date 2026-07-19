# Prism Motif 当前交接

> 更新：2026-07-19。完整计划见 `ROADMAP_V0.2.md`。

## 当前状态

- 当前公开版本：v0.1.0；
- 仓库候选版本：v0.1.1-security；当前施工目标：执行 Phase 4.0 产品完整性盘点，先补全并稳定 v0.2 既定用户主路径；
- 模式、MCP、其他 DAW 和范围外大型能力继续冻结；允许补全已有作曲、编曲、混音主路径必需的产品状态、错误处理与恢复能力；
- Phase 1 安全代码、Gateway Session、动态端口、认证健康握手、严格 Origin/CSP、工具风险 Policy、会话级信任模式和正式包收口已合入 `main`；路线图仍有“只在强制确认的高风险操作上补全权限卡信息”一项 UI 待办，它不是逐步骤人工审计；
- Phase 2 已完成；本轮非实时回归为 Python 125/125（Gold 结构评分 19/19、live driver 生命周期 22/22），真实 MCP 集成、32 工具契约和仓库卫生通过。前端 11 项、Rust 3 项与 25 回合 Soak 沿用最近完整基线，本轮未因 REAPER live 清理重复运行；
- Phase 3.1 MIDI 原子编辑已完成并经真实 REAPER 20/20 验收；Phase 3.2 的 32 工具契约门禁、Phase 3.3 的 BS.1770 三时间尺度响度已完成；
- Phase 3.4 已完成第一轮 10 Skill 可信度审计与残留复核，清理伪统计、跨平台 -14 LUFS 概括、未定义能量阈值和 MPC→REAPER Swing 精确换算；尚待真实制作人复核与针对性的响度匹配 A/B/测量证据，不必等待完整 Gold campaign；
- Phase 3.5 的 Gold A 已建立 6 个固定工程、首批 10 个唯一任务定义、隔离准备器、评分器、live driver 与发布门汇总，当前进入开发期维护态。6 个工程已在真实 REAPER 打开验证，两个混音工程已跑通渲染→确定性测量。G001 历史失败轮保留为回归证据：对象式批参数曾造成额外 `Track 1`，未伪记通过；后续现场试跑证明 composition 与信任模式下已知工程内编辑可保持零权限请求，但旧试跑不再算当前严格评分的通过成绩。driver 现改为核对一次性工程/before、采集 SSE、保存 after，再无保存重载同一副本并验证基线；该方案尚未重新做真机验收。Gold B 最小 G001 冒烟推迟到产品主路径稳定后，Gold C 的 10/30-task 最终信任门推迟到发布候选冻结后；
- 真实 WebView 烟雾测试、日志扫描和正常关闭后的进程树验收已通过；
- v0.1.1 MSI 已构建；管理安装、v0.1.0 → v0.1.1 真实升级、安装目录启动和卸载均通过，32 个非日志用户文件哈希保持不变；
- v0.1.1-security 批次经 8 路对抗审查后修复三处（chatReducer 未知事件白屏、CORS 漏 X-Filename、Vite dev 认证断裂）并已提交，含真发消息的 WebView E2E 验证；
- Windows CI 于 2026-07-11 首绿：`ci.yml` 在干净 runner 复现全套验证；当时的 `msi-smoke.yml` 完整安装链通过。该证据属于 v0.1.1-security 基线，Phase 5 发布候选必须用当前主线重新验证；
- 三仓均已推送（两个 MCP 仓先变基到洗净历史再推，fast-forward）；
- 当前 Git 分支：`main`；2026-07-19 已将本地阶段提交全部推送，四仓（prism-core、prism-motif、reaper-mcp、music-perception-mcp）均与各自 `origin/main` 对齐，prism-core 已建立私有 GitHub 远程；
- reaper-mcp 存在用户原有的未跟踪 `TOOL_COVERAGE.md`，不得覆盖或删除。

## 先读

1. `ROADMAP_V0.2.md`
2. `DESIGN.md`
3. `SECURITY.md`
4. `AGENTS.md`

## 当前施工顺序

1. 做 Phase 4.0 产品完整性盘点：从普通用户的安装/启动、Provider 与 REAPER/Bridge 连接、三模式任务、执行反馈、结果核验、失败恢复、线程保存和退出逐步检查，形成有界的 v0.2 缺口清单；
2. 为作曲、编曲、混音各确定一个必须成立的纵向主路径，只补阻断这些路径的既有范围缺口；
3. 在 Gold A 离线回归与 Soak 保护下完成必要的前端 / Gateway 结构收口；真实缺陷才新增 Gold 回归案例，不为数量扩任务；
4. 主路径稳定后执行一次 Gold B：重启桥接载入 beat-origin 修复，用全新 G001 一次性工程验证 bridge、SSE、信任模式、快照与无保存重载；不要复用旧 `build/gold-runs`；
5. Gold B 通过后执行 Gold C Prep：在发布候选冻结前完成最终声明—工程快照一致性评分、G010 确定性故障注入、至少 30 个唯一任务的固定 catalog、离线评测契约验证、制作人复核与响度匹配 A/B；
6. 冻结发布候选、模型、Provider、Prompt、Skill、工具和任务 catalog 版本后，执行 Gold C 的 10-task canary；无变更则计入最终结果并继续剩余固定任务，有变更则重新冻结并从零开始；
7. Gold C 达标后继续 Phase 5.2–5.5 的 GUI、MSI、升级、许可证、元数据和干净机验证。

当前不运行 G001，不运行其余 9 个真机任务，不扩充到 30 个任务；Gold C 是 v0.2 发布门，不是 Phase 4 的前置门。

## 必跑验证

```powershell
python test_core.py
python -m unittest discover -s tests -v
python tests\soak_test.py
python tests\check_repo_hygiene.py
python tests\check_tool_contracts.py
python -m tests.gold.runner verify
npm --prefix frontend run lint
npm --prefix frontend run test
npm --prefix frontend run build
C:\Users\XAQ\.cargo\bin\cargo.exe test --locked --manifest-path frontend/src-tauri/Cargo.toml
python A:\Prismcode\mcps\reaper-mcp\server\test_server.py
python A:\Prismcode\mcps\music-perception-mcp\server\test_server.py
```

桌面壳、打包或发布链变更另跑 `powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_tauri_smoke.ps1`；Phase 5 发布候选必须重新跑 clean-host MSI Smoke。

## 约束

- 不新增模式、MCP、其他 DAW 或范围外大型能力；允许补全既有三模式主路径；
- 不依赖 Prompt 保护危险操作；
- 不把 Token、Key 写入日志、配置或 localStorage；
- 安全协议变更必须带测试；
- 不对 App.tsx 做无测试的一次性重写；
- 不修改用户已有的未跟踪文件。
