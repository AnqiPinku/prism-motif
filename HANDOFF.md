# Prism Motif 当前交接

> 更新：2026-07-19。完整计划见 `ROADMAP_V0.2.md`。

## 当前状态

- 当前公开版本：v0.1.0；
- 仓库候选版本：v0.1.1-security；当前施工目标：完成 Phase 3 Eval，再进入 v0.2.0 结构与发布收口；
- 功能扩张已冻结；
- Phase 1 安全代码、Gateway Session、动态端口、认证健康握手、严格 Origin/CSP、工具风险 Policy、会话级信任模式和正式包收口已合入 `main`；路线图仍有权限卡信息展示一项 UI 待办；
- Phase 2 已完成：当前 Python 80 项、前端 11 项、Rust 3 项、真实 MCP 集成、工具契约、仓库卫生和 20+ 回合 Soak 门禁均通过；
- Phase 3.1 MIDI 原子编辑已完成并经真实 REAPER 20/20 验收；Phase 3.2 的 32 工具契约门禁、Phase 3.3 的 BS.1770 三时间尺度响度已完成；
- Phase 3.4 已完成第一轮 10 Skill 可信度审计与残留复核，清理伪统计、跨平台 -14 LUFS 概括、未定义能量阈值和 MPC→REAPER Swing 精确换算；尚待真实制作人复核，并由 3.5 Gold Task 提供 A/B/测量证据；
- 真实 WebView 烟雾测试、日志扫描和正常关闭后的进程树验收已通过；
- v0.1.1 MSI 已构建；管理安装、v0.1.0 → v0.1.1 真实升级、安装目录启动和卸载均通过，32 个非日志用户文件哈希保持不变；
- v0.1.1-security 批次经 8 路对抗审查后修复三处（chatReducer 未知事件白屏、CORS 漏 X-Filename、Vite dev 认证断裂）并已提交，含真发消息的 WebView E2E 验证；
- Windows CI 于 2026-07-11 首绿：`ci.yml` 在干净 runner 复现全套验证；当时的 `msi-smoke.yml` 完整安装链通过。该证据属于 v0.1.1-security 基线，Phase 5 发布候选必须用当前主线重新验证；
- 三仓均已推送（两个 MCP 仓先变基到洗净历史再推，fast-forward）；
- 当前 Git 分支：`main`，与 `origin/main` 对齐；
- reaper-mcp 存在用户原有的未跟踪 `TOOL_COVERAGE.md`，不得覆盖或删除。

## 先读

1. `ROADMAP_V0.2.md`
2. `DESIGN.md`
3. `SECURITY.md`
4. `AGENTS.md`

## 当前施工顺序

1. 建立 Phase 3.5 Gold Task Harness，固定 `empty.rpp`、`chord-loop.rpp`、`arrangement-flat.rpp`、`mix-clipping.rpp`、`mix-muddy.rpp`、`melody-offkey.rpp`；
2. 先跑出 10 个可重复任务，再扩展到至少 30 个，并记录错误轨修改、重复 MIDI、未授权破坏、工具恢复、前后测量与撤销性；
3. 用 Gold Task 的渲染、测量和 A/B 结果关闭 Phase 3.4 最后一项，并安排真实制作人复核关键 Skill；
4. Eval 门通过后才开始 Phase 4；Phase 5 重新做当前主线的 GUI、MSI、升级与干净机验证。

## 必跑验证

```powershell
python test_core.py
python -m unittest discover -s tests -v
python tests\soak_test.py
python tests\check_repo_hygiene.py
python tests\check_tool_contracts.py
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
