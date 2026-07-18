# Prism Motif 当前交接

> 更新：2026-07-10。完整计划见 `ROADMAP_V0.2.md`。

## 当前状态

- 当前公开版本：v0.1.0；
- 当前目标：v0.1.1-security；
- 功能扩张已冻结；
- Gateway Session、动态端口、认证健康握手、严格 Origin/CSP、工具风险 Policy、会话级信任模式和正式包收口已完成首版；
- 产品安全测试 36 项、Rust 测试 3 项、前端 lint/build、Tauri debug build 与两个 MCP 自测均通过；
- 真实 WebView 烟雾测试、日志扫描和正常关闭后的进程树验收已通过；
- v0.1.1 MSI 已构建；管理安装、v0.1.0 → v0.1.1 真实升级、安装目录启动和卸载均通过，32 个非日志用户文件哈希保持不变；
- v0.1.1-security 批次经 8 路对抗审查后修复三处（chatReducer 未知事件白屏、CORS 漏 X-Filename、Vite dev 认证断裂）并已提交，含真发消息的 WebView E2E 验证；
- Windows CI 已首绿（2026-07-11）：`ci.yml` 在干净 runner 复现全套验证；`msi-smoke.yml` 完整安装链通过——冻结 sidecar、NuGet 3.10.11 重建内置 CPython、MSI 构建、静默安装、启动确认 Gateway 子进程、收口零残留、静默卸载（注意：安装的主程序是 `app.exe`，productName 只用于目录/快捷方式名，v0.2 Phase 5 再改 mainBinaryName）；
- 三仓均已推送（两个 MCP 仓先变基到洗净历史再推，fast-forward）；
- 当前 Git 分支：`agent/v0-2-hardening`；
- reaper-mcp 存在用户原有的未跟踪 `TOOL_COVERAGE.md`，不得覆盖或删除。

## 先读

1. `ROADMAP_V0.2.md`
2. `DESIGN.md`
3. `SECURITY.md`
4. `AGENTS.md`

## 当前施工顺序

1. 决定 `agent/v0-2-hardening` 合回 `main` 的时机（合并后 `MSI Smoke` 可直接 workflow_dispatch）；Phase 2 已完成（CI + MSI Smoke + Soak 全绿）；
2. 按 `ROADMAP_V0.2.md` 进入 Phase 3（工具语义、音乐知识与 Agent Eval）。

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
powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_tauri_smoke.ps1
python A:\Prismcode\mcps\reaper-mcp\server\test_server.py
python A:\Prismcode\mcps\music-perception-mcp\server\test_server.py
```

## 约束

- 不新增模式、MCP 或音乐功能；
- 不依赖 Prompt 保护危险操作；
- 不把 Token、Key 写入日志、配置或 localStorage；
- 安全协议变更必须带测试；
- 不对 App.tsx 做无测试的一次性重写；
- 不修改用户已有的未跟踪文件。
