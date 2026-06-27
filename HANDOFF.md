# Prism Core — 交接文档（给下一个 agent）

> 你接手的是一个**已能跑通**的本地 agent 系统。先读本文件，再读 `DESIGN.md`（架构 v0.3）和 `AGENTS.md`（冻结的接口契约 + 施工规范）。**严守第 4 节的不变量。**

---

## 1. 这是什么

**Prism Core** = 一个**领域无关、零依赖、大脑可换**的 Python agent 内核 + 本地 Web 界面。
通过挂不同的 **MCP server** 获得能力（控音乐 / 操作电脑…），通过**技能**赋予人格与玩法。
当前用 **DeepSeek** 当大脑，已接两个 MCP：**reaper-mcp**（控 REAPER 做音乐）、**system-mcp**（操作电脑文件/命令）。

## 2. 三个仓库位置（同在 `A:\科广\`，注意路径含中文，已处理好）

| 路径 | 是什么 | 依赖 |
|---|---|---|
| `A:\科广\prism-core\` | agent 内核 + gateway + web 前端 | **零依赖**（仅标准库） |
| `A:\科广\reaper-mcp\` | REAPER 的 MCP server（Lua 桥 + Python server，20 工具） | **零依赖** |
| `A:\科广\system-mcp\` | 电脑操作 MCP server（11 工具） | **零依赖** |

## 3. 已完成（M1 内核 + 完整前端 + 电脑操作能力，均已实测）

**core/**（`A:\科广\prism-core\core\`）
- `contracts.py` 数据模型；`reasoner.py` 大脑接口 + `reasoners/openai_compat.py`（urllib 打 OpenAI 兼容，**支持流式**）+ `reasoners/mock.py`（免 key 测试用）
- `mcp_client.py` 手写 MCP stdio 客户端；`tools.py` ToolHub（连多 MCP、聚合、路由）
- `skills.py` 技能库（增删/启用状态，存 `data/skills/_enabled.json`）；`context.py` 拼系统提示
- `memory.py` Memory 接口 + JsonMemory + 工厂；`loop.py` **ReAct 循环**（流式 + 权限钩子）
- `threads.py` 线程存/读/列/重命名/删除/还原；`runner.py` `run_turn`（**多轮记忆** + 权限 + 选大脑）

**gateway/server.py**：`http.server` + SSE。接口：`/api/state`、`/api/chat`(SSE 流式、线程连续、权限闸)、`/api/settings`(GET/POST 改 key/base_url/模型/默认)、`/api/skills`(add/delete/toggle)、`/api/mcp`(tools/add/delete/toggle)、`/api/threads`(load/delete/rename)、`/api/permission`。

**web/**：`index.html` + `app.js`。功能：流式对话、线程(新建/重命名/删除/续聊)、底部模型选择、MCP 面板(开关/工具数/添加/删除)、技能面板(按用户分类分组/开关/新建)、设置弹窗(配 key)、**危险操作权限确认卡**、**绕过确认**开关、**停止生成**。白底蓝点缀。

**config/**：`providers.json`(默认 deepseek，另有 qwen/openai/local/mock)、`mcp_servers.json`(reaper+system)、`memory.json`、`settings.json`(`base_prompt` 现为 `""`=无底座)、`secrets.json`(deepseek key，**已 gitignore**)。

**system-mcp 11 工具**：只读=list_dir/read_text_file/search_files/grep_files/find_audio_plugins/make_dir；**危险(执行前弹确认)**=run_command/write_file/edit_file/move_path/delete_path。

**已验证**：`test_core.py` 全过；真 DeepSeek 端到端（工具调用、流式、多轮记忆、危险操作权限闸）全部 OK。

## 4. 不变量（务必遵守，违反就背离了整套设计）

1. **`core/`、`reaper-mcp`、`system-mcp` 保持零依赖**（仅标准库）。**只有未来的 `audio-mcp` 允许用 numpy/scipy**（DSP），且依赖只在那个 server 里。
2. **`core/` 永远领域无关**——不许出现音乐/REAPER 专属代码。能力→MCP；人格/玩法→技能；可调参数→config。
3. **两类东西**：上下文(技能=markdown，full常驻/lazy按需，用户自定义 tags；人格=full 技能；记忆；历史) vs 能力(MCP 工具：动作型 / 取数型)。
4. **四个可换插槽**：大脑(Reasoner 接口/providers.json)、记忆(Memory 接口/memory.json)、能力(MCP/mcp_servers.json)、上下文(技能)。
5. **实时(动画/语音/口型)不走 MCP**——本地引擎跑，MCP 只发高层命令。
6. 改接口签名前先看 `AGENTS.md` 的冻结契约，别擅自改。

## 5. 未完成 / 下一步任务（按优先级）

### ⛔ M2 Reflexion：曾实现，已从核心移除（2026-06-27 定）
**经过**：先把"通用受控反思循环 + 可插拔评判器（judge/tool/composite）+ 三态持久化 + UI 面板"完整做出来并通过对抗校验；随后和用户复盘**架构定位**，决定**整体撤出核心**，回到干净内核。
**为什么撤**：Reflexion 是**对循环的一种编排策略**（跑一轮→评→再跑），不属于四个可插拔槽（大脑/记忆/能力/上下文）里的任何一个，和"规划""多 agent"同类——**编排策略是搭某个具体（领域）agent 时才决定的，属于 harness/应用层，不该焊进领域无关的内核**。而且"用评判器感知"本就是内核自带原语：**客观感知＝取数型 MCP 工具，判官＝一次 reasoner 调用**，无需内核内置 Reflexion 机器。
**已撤干净**：删 `core/reflection.py`、runner 的反思接线、settings 的 `reflection` 段、`/api/reflection`、`/api/memory/remember`、前端反思面板与事件、反思测试；还原 `loop.py`（去掉 exhausted 标志）。保留 `core/memory.py` 的召回修复（真 bug 修复，与反思无关）。`test_core.py` 全过。

### ✅ 工作区（已保留）= 长期记忆命名空间
- **工作区只管记忆隔离**（不打包技能/MCP/大脑；线程仍全局）。记忆落 `data/memory/<workspace>/`；切工作区＝换 `recall` 读取的命名空间。**注意：当前没有"写入记忆"的路径**（反思的保存按钮随反思一并撤了），记忆暂为"只读槽、待未来工具/领域 agent 填"。
- `core/runner.py`：`current/list/set/rename/delete_workspace` + `_safe_ws`（挡 `/ \ : .. .` 与 Windows 盘符穿越）；rename 撞名拒绝、不静默切 current。
- `gateway/server.py`：`/api/workspaces`、`/api/workspace/{switch,create,rename,delete}`，`/api/state` 带 workspace。
- `web/`：左栏顶部工作区块（下拉切换 / 新建 / 重命名 / 删除）。

### ✅ 上下文压缩 Phase 1 + 占用环（已完成；方案见 NOTES.md §5）
- **token 追踪**：`OpenAICompatReasoner` 读 `usage.prompt_tokens`（流式加 `stream_options`）存 `last_prompt_tokens`。
- **工具结果消隐**（无 LLM）：`core/compaction.py` 的 `elide_tool_results` 把旧超长工具输出换占位符、留 `tool_call` 痕迹。
- **压缩透镜** `CompactingReasoner`：包在模型外，每次 decide 前投影成消隐版发给模型、上报占用；**AgentLoop 持有全本、照常存盘**。
- **占用环**（纯 SVG，底部输入栏，hover 显已用/预算 K/M）：切线程按线程显示、新对话归零。
- **预算按模型**：`providers.json` 每模型 `window_tokens`（⚙ 滑轨可调，8K–1M 档）；`compact_at` 0.6。

### ▶ 进行中：上下文压缩 Phase 2（摘要压实）
接近预算时**一次 LLM 调用**把"最近 K 回合之前"的旧历史增量压成摘要（保留决定/事实/未决/偏好），折进 system 发给模型；**磁盘仍存全本**（摘要+upto 存 thread config，不丢历史）。之后：自适应触发 / 记忆 MCP。

### 成熟度待办（"成熟≠加功能"；详见 NOTES.md §6）
健壮性：①上下文压缩(上面) ②重试/退避+工具超时 ③服务端真取消+token/步数预算。
可观测：④结构化 trace 持久化 + token 计量。
更干净：⑤权限闸去硬编码（危险性来自工具元数据/config，核心不再认识具体工具名）⑥记忆写入走"记忆 MCP"而非核心代码。
立地基：⑦核心作为"库"的清晰 API（run_turn/Session + 文档）。

### 之后：audio-mcp + 在领域层组合 Reflexion
做音乐**领域 agent**时，在 harness 层用本内核（reasoner 当判官、MCP 工具当客观感知、memory 当反思记忆）**组合** Reflexion；建 `audio-mcp` 的 `analyze_mix`（渲染 REAPER 工程→LUFS/频段平衡/掩蔽）当客观信号。内核保持干净，不回收这套机器。

### 可选体验
- 服务端真·取消（现在"停止"只是前端中断，服务端那轮仍在后台跑完）。
- MCP 面板"添加 MCP"已支持；可加每条 MCP 的工具列表展开。

## 6. 怎么跑 / 怎么验证

```bash
cd A:\科广\prism-core
python gateway/server.py          # 启动，浏览器开 http://127.0.0.1:8770（窗口别关）
python test_core.py               # 离线自测（不需 REAPER/不需 key）
```
- DeepSeek key 已在 `config/secrets.json`，也可在界面 ⚙ 改。用 **mock** 大脑可零依赖测 UI。
- 真控 REAPER：打开 REAPER → Actions 里 Run `A:\科广\reaper-mcp\bridge\reaper_mcp_bridge.lua`（见 "ready"）。

## 7. 已知坑
- **端口 8770 同一时刻只能一个 gateway**；旧进程没退会"端口占用"（现在有明确提示，或 `set PRISM_PORT=8771` 换端口）。
- Windows 控制台中文显示乱码是 GBK 代码页问题（不影响功能，`chcp 65001` 可修）。
- reaper 工具需 REAPER 开着 + 桥在跑，否则超时报错（UI 显示 ✗）。
- 权限闸只拦 system-mcp 的危险工具；reaper 工具直接执行。
- `data/skills/` 起步为空，技能由用户在界面创建；`data/threads/`、`data/memory/`、`config/secrets.json` 已 gitignore。

## 8. 必读参考
- `DESIGN.md`：架构定稿（v0.3），两类东西 / 四插槽 / 分层 / 路线图。
- `AGENTS.md`：冻结的数据契约 + 模块依赖图 + 逐文件验收。
- `NOTES.md`：设计取舍（为什么这么定）+ 调研留档（Reflexion 属 harness、记忆教训四要素、上下文压缩 SOTA + 实现规划）。
