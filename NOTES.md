# Prism Motif 工程决策记录

> 当前路线见 `ROADMAP_V0.2.md`；当前架构见 `DESIGN.md`。本文只保留仍然有效的决策，不承担任务排期。

## 当前成立的决策

1. 产品聚焦 REAPER，不在 v0.2 前扩展其他 DAW。
2. 文本 LLM 是决策层；REAPER MCP 是动作层；音乐感知 MCP 是取数层。
3. 确定性 DSP 与主观模型听感分开呈现。
4. REAPER 输出必须保持可编辑、可检查、可撤销。
5. Prism Core 保持领域无关；音乐知识放在 Skills，DAW 逻辑放在 MCP。
6. 上下文压缩只改变模型投影，线程磁盘全本保留。
7. 密钥存系统凭据管理器，不写普通配置文件。
8. 正式包使用 bundled Python 与 perception sidecar。
9. 安全策略由代码执行，不能依赖 Skill 提示词。
10. v0.2 前冻结新增模式和大型能力。
11. 信任模式是会话级工作流开关：已知的 REAPER 工程内编辑与显式标记的可撤销删除/替换自动执行；录音、外部调用、任意代码/命令和显式文件覆盖/删除仍确认。安全 `batch` 必须展开到子调用判定。

## 已验证能力

- Python ReAct 核心、上下文、压缩、重试与 MCP 超时有离线测试；
- reaper-mcp Fake Bridge 测试通过并发现 25 个工具；
- music-perception 合成 WAV 测试覆盖响度、真峰值、调性、频段和削波；
- React 生产构建成功；
- Tauri/Rust 有 3 项安全相关测试，debug app 完整构建成功；
- Gateway/Auth/Policy/路径安全与日志脱敏产品测试 36 项通过；
- 真实 Tauri WebView 烟雾测试覆盖设置、信任模式、状态请求与两个正式包 MCP；正常关闭后 Tauri、Gateway、MCP 残留均为 0；
- v0.1.0 MSI 构建链存在；
- 真实 REAPER 工程操作和渲染—分析闭环曾完成真机验证。

## 当前最高风险

1. 安全首版仍需 Windows-latest 干净主机验证；
2. 前端事件状态机尚未抽出测试；
3. Skill 中存在工具语义不一致和过度精确表述；
4. App.tsx 与 Gateway Handler 已形成结构债务；
5. 发布元数据、许可证和“离线”表述需要校正。

## 开发问题记录

### 2026-07-10：真实 WebView 自动化首次接入失败

- 现象：只设置 `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` 时，Tauri debug app 没有开放预期的 CDP 端口，Playwright 无法连接；这次运行不计入烟雾测试结果。
- 清理问题：测试脚本超时后强制结束宿主进程，绕过了窗口 `Destroyed` 事件，留下一个 bundled Gateway 子进程；已按可执行路径核对并清理，不能据此判断正常关闭路径是否泄漏。
- 修正：debug 构建只在显式提供 `PRISM_WEBVIEW_BROWSER_ARGS` 时把参数传给主 WebView；release 构建不读取该测试入口。
- 结果：`tests/run_tauri_smoke.ps1` 已固化页面与进程树验收；脚本调用 reaper、music-perception 两个正式包 MCP 后通过页面关闭按钮退出，确认 Tauri、Gateway、MCP 残留均为 0。

### 2026-07-10：开发依赖在线安装超时

- 现象：`rustup component add rustfmt` 与 `npm install --save-dev playwright-core` 均在本机网络环境超时；已终止对应残留安装进程，未留下 package.json/package-lock 变更。
- 处理：Rust 代码由编译和 3 项测试验证；WebView 自动化使用本机已有的 Python Playwright，并在 `requirements-dev.txt` 中固定版本，避免下载浏览器内核。

### 2026-07-10：WiX 获取超时与 MSI 验收

- 现象：Tauri release app 编译成功，但自动下载 40 MB WiX 3.14.1 时发生全局超时；单连接 GitHub/NuGet 下载也无法在默认时限完成。
- 处理：使用 WiX 官方维护者发布的 NuGet 3.14.1 包做 HTTP Range 并行下载；合并后的长度、MD5 与 NuGet 响应提供的 SHA-512 全部一致，`candle.exe` 报告版本 3.14.1.8722。
- 结果：生成 `Prism Motif_0.1.1_x64_en-US.msi`，大小 154,925,705 字节，SHA-256 为 `FAAE9789625BE6B08458B4BF810FA2EE459F7376B2018266F289F803CA55EA79`；当前未签名，签名仍是 v0.2 正式发布门。
- 安装验收：管理安装得到 4,676 个文件；正式配置只含 reaper 与 music-perception，不含 system-mcp、密钥、线程、记忆或临时数据。
- 升级验收：v0.1.0 与 v0.1.1 UpgradeCode 相同；本机完成 v0.1.0 安装、v0.1.1 原位升级、安装目录启动和 v0.1.1 卸载。卸载后产品状态为未安装，32 个非日志用户文件的合并 SHA-256 前后均为 `D29E5CC74421CFB665F818CFF0EFE7D7C730AC46D3728505B2713B20674D74C8`。

### 2026-07-10：原生窗口消息不等价于产品关闭按钮

- 现象：对隐藏的 release 窗口发送 `WM_CLOSE` 或 `SC_CLOSE` 没有触发 Tauri 页面关闭路径；强制结束宿主后会绕过 `Destroyed` 清理事件。
- 结论：这不是正常产品交互的验收方式。正常关闭已经由真实 WebView 自动化点击产品关闭按钮验证，Tauri、Gateway 与 MCP 残留均为 0；release 安装烟雾测试只用原生窗口句柄确认启动，失败清理由 `taskkill /T` 显式收口。

### 2026-07-10：Windows Installer 后台事务晚于客户端返回

- 现象：无界面 `msiexec` 客户端很快返回，后台 `/V` 服务仍继续处理 bundled 文件；卸载在 5 分钟轮询边界后数秒才完成。
- 处理：安装验证必须等待 Installer 服务空闲并读取最终产品状态与日志，不能在客户端返回后立即判断。最终升级与卸载日志均返回 0。

## 验证命令

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

## 文档职责

- `README.md`：面向用户；
- `ROADMAP_V0.2.md`：唯一当前执行计划；
- `DESIGN.md`：当前架构；
- `SECURITY.md`：威胁与安全协议；
- `AGENTS.md`：施工约束；
- `HANDOFF.md`：当前短交接。
