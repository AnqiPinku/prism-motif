# Prism Motif 安全模型

> 本文描述 v0.1.1-security 的目标。勾选状态以 `ROADMAP_V0.2.md` 为准。

## 1. 受保护资产

- Provider API Key；
- Gemini API Key；
- 用户 REAPER 工程；
- 本机文件与命令执行能力；
- 会话、线程与工作区数据；
- 用户上传的音频；
- REAPER 录音、渲染和覆盖操作。

## 2. 信任边界

可信：

- 当前启动的 Tauri 主进程；
- Tauri 启动并验证过的 Gateway；
- 本次会话内经过认证的 bundled frontend。

默认不可信：

- 普通网页；
- 其他本机进程；
- 未验证的 localhost 监听者；
- Provider 返回内容；
- 模型生成的 Tool Call；
- 新增或未知 MCP Server；
- Skill 文本和外部音频内容。

## 3. 主要威胁

### 本地网页跨源调用

恶意网页可能尝试访问 loopback Gateway，修改 Provider、启用 MCP、发起聊天或回复权限请求。

控制：Session Token、严格 Origin、CSP、随机端口。

### 端口冒充

其他进程可能抢占固定端口，让 Tauri 把错误服务当作 Gateway。

控制：随机端口、Instance ID、认证健康握手。

### Key 外带

攻击者若能修改 Provider base_url，可能诱导应用把 Credential Manager 中的 Key 发送到错误主机。

控制：API 认证、Provider 主机变更确认、协议校验、日志脱敏。

### 模型越权

模型或注入内容可能调用删除、覆盖、录音、Lua 或命令工具。

控制：代码级风险元数据；高风险操作不可由信任模式绕过。

### 打包攻击面

不必要的 system-mcp 会把音乐应用升级为通用本机执行器。

控制：正式包移除 system-mcp；开发版本显式启用。

## 4. API 认证协议

每次启动生成：

```text
PRISM_PORT
PRISM_SESSION_TOKEN
PRISM_INSTANCE_ID
```

所有 `/api/*` 请求携带：

```http
X-Prism-Session: <token>
```

健康响应：

```json
{
  "product": "prism-motif",
  "protocol": 2,
  "instance_id": "...",
  "ready": true
}
```

认证失败使用通用错误，不回显 Token。

### 浏览器开发模式（Vite 5173）

启动 Gateway 与 Vite 前设置同一个 `PRISM_SESSION_TOKEN`。Vite 代理只为开发页自身的请求注入 `X-Prism-Session` 并抹掉同源 Origin；异源 Origin 原样转发，由 Gateway 拒绝。Token 不进浏览器 JS 与 localStorage。Gateway 直开（8770 服务构建产物）走 HttpOnly 同源 Cookie，无需设置环境变量。

## 5. 工具策略

| 风险 | 默认策略 |
|---|---|
| read | 自动执行 |
| write | 请求确认；当前会话信任模式可放行 |
| destructive | 始终确认 |
| execute | 始终确认并展示代码/命令 |
| external | 按目标与副作用确认 |
| record | 始终确认 |

未知工具不得默认为 read。

## 6. 日志规则

不得写入：

- API Key；
- Authorization Header；
- Session Token；
- Credential Manager 返回值；
- 未脱敏的敏感命令参数。

可以写入：

- Turn ID；
- Tool Name；
- Duration；
- Error Code；
- Token 用量；
- 是否取消；
- 不含敏感值的目标摘要。

## 7. 报告问题

公开仓发现安全问题时，不在公开 Issue 中粘贴可直接利用的 Key、命令或用户数据。先通过仓库所有者提供的私下渠道报告；在正式公开 SECURITY Policy 前，可使用 GitHub Security Advisory。
