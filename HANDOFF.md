# Prism Motif 当前交接

> 更新：2026-07-19。完整计划见 `ROADMAP_V0.2.md`。

## 当前状态

- 当前公开版本：v0.1.0；
- 仓库候选版本：v0.1.1-security；当前施工目标：完成 Phase 3 Eval，再进入 v0.2.0 结构与发布收口；
- 功能扩张已冻结；
- Phase 1 安全代码、Gateway Session、动态端口、认证健康握手、严格 Origin/CSP、工具风险 Policy、会话级信任模式和正式包收口已合入 `main`；路线图仍有“只在强制确认的高风险操作上补全权限卡信息”一项 UI 待办，它不是逐步骤人工审计；
- Phase 2 已完成；本轮非实时回归为 Python 125/125（Gold 结构评分 19/19、live driver 生命周期 22/22），真实 MCP 集成、32 工具契约和仓库卫生通过。前端 11 项、Rust 3 项与 25 回合 Soak 沿用最近完整基线，本轮未因 REAPER live 清理重复运行；
- Phase 3.1 MIDI 原子编辑已完成并经真实 REAPER 20/20 验收；Phase 3.2 的 32 工具契约门禁、Phase 3.3 的 BS.1770 三时间尺度响度已完成；
- Phase 3.4 已完成第一轮 10 Skill 可信度审计与残留复核，清理伪统计、跨平台 -14 LUFS 概括、未定义能量阈值和 MPC→REAPER Swing 精确换算；尚待真实制作人复核，并由 3.5 Gold Task 提供 A/B/测量证据；
- Phase 3.5 已建立 6 个固定工程、首批 10 个唯一任务定义、隔离准备器、评分器、live driver 与 30-task 发布门汇总；6 个工程已在真实 REAPER 打开验证，两个混音工程已跑通渲染→确定性测量。G001 历史失败轮保留为回归证据：对象式批参数曾造成额外 `Track 1`，未伪记通过；后续现场试跑证明 composition 与信任模式下已知工程内编辑可保持零权限请求，但旧试跑不再算当前严格评分的通过成绩。driver 现改为核对一次性工程/before、采集 SSE、保存 after，再无保存重载同一副本并验证基线；该方案尚未重新做真机验收。实际和弦顺序与 Agent 最终文字的一致性仍待加入硬评分；
- 真实 WebView 烟雾测试、日志扫描和正常关闭后的进程树验收已通过；
- v0.1.1 MSI 已构建；管理安装、v0.1.0 → v0.1.1 真实升级、安装目录启动和卸载均通过，32 个非日志用户文件哈希保持不变；
- v0.1.1-security 批次经 8 路对抗审查后修复三处（chatReducer 未知事件白屏、CORS 漏 X-Filename、Vite dev 认证断裂）并已提交，含真发消息的 WebView E2E 验证；
- Windows CI 于 2026-07-11 首绿：`ci.yml` 在干净 runner 复现全套验证；当时的 `msi-smoke.yml` 完整安装链通过。该证据属于 v0.1.1-security 基线，Phase 5 发布候选必须用当前主线重新验证；
- 三仓均已推送（两个 MCP 仓先变基到洗净历史再推，fast-forward）；
- 当前 Git 分支：`main`；本地有尚未推送的阶段提交，不再声称与 `origin/main` 对齐；
- reaper-mcp 存在用户原有的未跟踪 `TOOL_COVERAGE.md`，不得覆盖或删除。

## 先读

1. `ROADMAP_V0.2.md`
2. `DESIGN.md`
3. `SECURITY.md`
4. `AGENTS.md`

## 当前施工顺序

1. 下一次真机施工先重启 REAPER 桥接以载入 beat-origin 修复，用全新的 G001 一次性工程验证无保存重载与基线恢复；不要复用旧 `build/gold-runs` 工程；
2. 为 live driver 增加最终自然语言声明与工程快照一致性证据；`composition-workflow` 已要求写后 `get_midi_notes` 读回，但评分层仍需落地；
3. 用固化 driver 运行其余首批任务，形成 10 个真实、可重复基线；信任模式下已知工程内编辑预期零人工确认，权限事件只自动记录；
4. 将任务扩展到至少 30 个唯一任务并执行 v0.2 Eval 门；
5. 用 Gold Task 的渲染、测量和 A/B 结果关闭 Phase 3.4 最后一项，并安排真实制作人复核关键 Skill；
6. Eval 门通过后才开始 Phase 4；Phase 5 重新做当前主线的 GUI、MSI、升级与干净机验证。

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

- 不新增模式、MCP 或音乐功能；
- 不依赖 Prompt 保护危险操作；
- 不把 Token、Key 写入日志、配置或 localStorage；
- 安全协议变更必须带测试；
- 不对 App.tsx 做无测试的一次性重写；
- 不修改用户已有的未跟踪文件。
