# Prism Motif 施工约束

## 1. 文档优先级

1. `ROADMAP_V0.2.md`：当前唯一任务计划；
2. `SECURITY.md`：安全边界；
3. `DESIGN.md`：当前架构；
4. `HANDOFF.md`：当前短交接；
5. `NOTES.md`：稳定决策。

README 面向用户，不作为内部任务清单。

## 2. 当前范围

v0.1.1-security 的安全代码、CI、MSI 与升级/卸载验证已完成并合入 `main`；当前公开版本仍为 v0.1.0。现在按 `ROADMAP_V0.2.md` 收口 Phase 3：

1. 完成 3.4 的真实制作人复核与 A/B/测量证据；
2. 接通 3.5 Gold Task 的真实 Agent 运行驱动，用现有 6 个固定工程和 10 个任务定义跑出基线，再扩到至少 30 个唯一任务；
3. 通过 Eval 门后再进入 Phase 4 结构重构；
4. 最后执行 Phase 5 的元数据、许可证、文档和干净机发布验证。

在 Phase 3 Eval 门完成前：

- 不增加模式、MCP 或新的音乐功能；
- 不扩其他 DAW；
- 不做大规模 UI/Gateway 重写；
- 不引入与当前验证闭环无关的依赖。

## 3. 代码边界

- `core/`：模型、循环、MCP、Skills、Memory、Threads；领域无关部分尽量保持标准库实现。
- `gateway/`：本地 API、SSE、认证和产品服务。
- `frontend/src/`：React UI；网络会话层与组件状态分开。
- `frontend/src-tauri/`：桌面壳、运行时会话和子进程生命周期。
- `data/skills/`：音乐知识；不是安全边界。
- `mcps/`：独立能力仓；修改时分别检查 Git 状态。

## 4. Skill 知识规则

- 强数字与强结论必须标明为 `standard`、`heuristic` 或 `creative_default`；
- `standard` 附官方或标准来源，`heuristic` 写清风格/素材/测量前提，`creative_default` 必须允许用户或参考曲覆盖；
- 不把不同平台的播放行为合并成一个 LUFS 标准；平台规则在发布前按最新官方文档复核；
- 内部规划分数必须明确写成不可跨歌曲比较、非工具输出，不得伪装成听觉阈值；
- 跨软件参数没有官方映射或实机验证时，不得写成精确等价；
- A/B 必须先做合理的响度匹配；工具没有返回的指标不得声称已经测得。

## 5. 安全规则

- 所有 `/api/*` 必须统一认证；
- 不允许通配 CORS；
- 未知工具默认不是只读；
- destructive / execute / record 不可被信任模式绕过；
- Key、Authorization、Session Token 不得进入日志或提交；
- 正式包不包含 system-mcp；
- Provider 主机变化必须被视为敏感配置变更。

## 6. 文件与 Git

- 保留用户未提交改动；
- 不删除或覆盖不属于当前任务的未跟踪文件；
- 不使用 destructive Git 命令；
- 编辑文件使用补丁；
- 配置模板不得包含真实 Key；
- 构建产物、音频和本地状态不得提交。

## 7. Python

- 支持 Python 3.10+；
- 公共函数写简短 docstring；
- 错误必须可观察，不静默吞掉关键安全失败；
- 运行时核心优先标准库；
- 测试可使用标准库 unittest；
- Windows 路径与 UTF-8 必须覆盖。

## 8. React

- 不把新的安全会话状态塞进巨型 App.tsx；
- API Session 单独成模块；
- 避免重复全局监听和重复请求；
- 独立请求并行启动；
- 高频流事件先合并再更新 React；
- 新状态机优先纯 Reducer + 测试；
- 保持 TypeScript 严格，不新增无必要 any。

## 9. Rust / Tauri

- Tauri 拥有 Gateway Session；
- 端口、Token、Instance ID 每次启动生成；
- 打开主窗口前验证 Gateway 身份；
- 关闭窗口必须清理整个子进程树；
- Release 不使用仓库绝对路径；
- 安全相关纯逻辑必须有 Rust 测试。

## 10. 必跑验证

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

安全协议变更还必须运行对应 Gateway Auth 测试。桌面壳、打包或发布链变更还必须运行 `tests\run_tauri_smoke.ps1`；Phase 5 发布候选必须重新跑 clean-host MSI Smoke，不能沿用 2026-07-11 的历史产物作为当前版本证据。
