# Prism Motif 当前架构

> 本文只描述当前产品架构与边界。执行路线见 `ROADMAP_V0.2.md`。

## 1. 产品定义

Prism Motif 是面向 REAPER 的本地优先音乐制作 Copilot。用户通过自然语言提出目标，Agent 读取工程、调用 MCP 工具执行可编辑操作，并在需要时渲染音频做确定性测量或可选主观听感分析。

它不替代 REAPER，不以一次生成不可编辑成品为目标。

## 2. 分层

```text
React UI
  │ HTTP + SSE
  ▼
Python Gateway
  │
  ▼
Runner / AgentLoop
  ├─ OpenAI-compatible text reasoner
  ├─ mode prompt + enabled skills + memory + thread history
  └─ ToolHub
       ├─ reaper-mcp ── Lua bridge ── REAPER
       └─ music-perception-mcp ── DSP / optional Gemini

Tauri shell
  ├─ starts and supervises Gateway
  ├─ owns the per-launch API session
  ├─ opens the native WebView
  └─ kills the child-process tree on exit
```

## 3. 核心边界

### 文本模型

- 负责理解意图、选择工具、解释结果；
- 可使用本地或云端 OpenAI-compatible Provider；
- 不直接拥有 REAPER 或文件权限。

### Skills

- Markdown + frontmatter；
- `full` 内容常驻，`lazy` 内容按当前加载策略注入；
- 三种 Mode 选择对应 Skills；
- Skill 是建议与流程，不是安全边界。

### MCP

- 能力边界；
- reaper-mcp 执行 DAW 操作；
- music-perception-mcp 读取音频事实或可选主观判断；
- 工具风险必须由代码级 Policy 控制，不能依赖 Prompt。

### Threads 与 Memory

- Threads 保存完整对话与工具轨迹；
- 上下文压缩只影响发送给模型的投影，不删除磁盘全本；
- Workspace 是 Memory 命名空间与线程组织方式；
- 当前 Memory 仍是轻量实现，不是 v0.2 的扩张重点。

## 4. 音乐感知

两层必须分开：

1. 确定性 DSP / MIR：LUFS、True Peak、BPM、Key、频段、Clipping；
2. 可选主观模型：Mood、Muddy、Harsh、Sibilant 等。

确定性数值用于可重复比较；主观模型输出必须标明非确定性，不得伪装成测量标准。

## 5. 安全边界

目标状态：

- Gateway 只绑定 loopback；
- 每次启动使用随机端口、Session Token 与 Instance ID；
- Tauri 验证 Gateway 身份后才打开 UI；
- 前端通过 Tauri 获取运行时 API Session；
- Origin、Token、CSP 三层同时限制；
- 工具按 read/write/destructive/execute/external/record 分类；
- destructive、execute、record 始终确认；
- 正式包不包含 system-mcp。

具体威胁与控制见 `SECURITY.md`。

## 6. 数据与密钥

- 安装资源只读；
- 用户配置、线程、日志写入 per-user data root；
- API Key 存 Windows Credential Manager；
- Session Token 只在当前进程内存与子进程环境中存在；
- 正式日志不得写入 Key、Authorization 或 Session Token；
- 音频上传写入受管临时目录并限制大小与保留数量。

## 7. 打包

- React 构建物由 Tauri 打包；
- Gateway 使用 bundled CPython；
- reaper-mcp 使用 bundled Python；
- music-perception 使用冻结 sidecar；
- REAPER 由用户单独安装；
- Tauri 负责 Gateway 生命周期和错误展示。

## 8. 不进入核心的东西

- 领域编排、Reflexion、多 Agent；
- 具体音乐知识；
- DAW 专用逻辑；
- UI 状态；
- 实时音频渲染循环。

这些分别属于产品 Harness、Skills、MCP 或前端。
