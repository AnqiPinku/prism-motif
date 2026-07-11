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
- 下一步先用 Windows-latest CI 补齐干净主机证据，再进入 Phase 2 的测试拆分与稳定性门禁；
- 当前 Git 分支：`agent/v0-2-hardening`；
- prism-motif 工作区在开工前干净；
- reaper-mcp 存在用户原有的未跟踪 `TOOL_COVERAGE.md`，不得覆盖或删除。

## 先读

1. `ROADMAP_V0.2.md`
2. `DESIGN.md`
3. `SECURITY.md`
4. `AGENTS.md`

## 当前施工顺序

1. 增加 Windows CI，在干净 runner 复跑 Python、Node、Rust、Staging 与 MSI 安装烟雾测试；
2. 完成 Phase 2 的 Fake Provider/MCP 与前端事件 reducer；
3. 完成 20 回合 Soak Test；
4. 按 `ROADMAP_V0.2.md` 继续 Phase 3–5。

## 必跑验证

```powershell
python test_core.py
python -m unittest discover -s tests -v
npm --prefix frontend run lint
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
