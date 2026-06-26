# Prism Core — 架构设计文档（v0.3 定稿）

> 一束白光经棱镜分成多色：一个核心，分出音乐 / 桌宠 / 玩具等多种用途。
>
> **已锁定**：Python · 纯手写 · 零依赖（仅标准库）· 默认大脑 DeepSeek · 配置用 JSON · 磁盘文件夹将命名为 `prism-core/`。

---

## 1. 一句话本质

Prism Core = **一个大脑可换的 agent 内核**。你通过"挑上下文 + 挑能力 + 挑大脑"来组装一个 agent。
所有东西只分两类：**它知道什么（上下文）**、**它能做什么（能力）**。

---

## 2. 两种基本东西（地基）

```
上下文 Context（模型"知道"的，纯文本，进提示）
  · 技能（用户自建的上下文模块；人格 = 其中"常驻"的一类）
  · 回忆出来的记忆（从库里捞的文本）
  · 对话历史

能力 Capability（模型"能做"的，可调用的函数）
  · MCP 工具
      - 动作型：set_tempo / add_track / click（产生效果）
      - 取数型：memory_search / read_file / screenshot（取回上下文）
```

- **人格 = 技能**：都是上下文模块，只差 `disclosure: full(常驻) | lazy(按需)`。人格 = `full` 的技能，可多选、可层叠。
- **技能由用户自建**：我们不预置任何技能/分类；用户随时新增，并用自定义 `tags` 分类。
- **MCP = 能力**：不是上下文（只有工具清单那点名字+描述进提示）。取数型工具的产出会变成上下文。
- **记忆**：`库（硬盘）` → `门（注入 或 取数型工具）` → `上下文`。库可插拔。

---

## 3. 核心循环（ReAct，大脑无关、用途无关）

```
想 reasoner.decide → 做 调MCP工具 → 看 结果回灌 → 重复，直到最终回答
                                  └─ M2 加：听/自我批评 钩子
                                  └─ 危险动作：先过 permission 钩子（用户确认）
```

---

## 4. 四个可插拔槽（同一招：接口 + 多实现 + 配置选）

| 槽 | 接口 | 换它 = |
|---|---|---|
| 大脑 | `Reasoner.decide()` | 改 `config/providers.json` 的 base_url → DeepSeek/Qwen/本地/OpenAI/Claude |
| 记忆 | `Memory.recall/remember()` | 改 `config/memory.json` 的 backend → json/sqlite/向量 |
| 能力 | MCP 协议 | 改 `config/mcp_servers.json` 或 UI 开关 → reaper/memory/system/pet… |
| 上下文 | markdown + frontmatter | 在 UI 勾选启用哪些技能（含常驻人格） |

中间的 `core/` 永远不动。

---

## 5. 分层（界面 → 底层）

```
web/  前端（纯 HTML/CSS/JS，白底蓝点缀）
      线程记录 | 对话 | 底部：+ / 麦克风 / 模型选择 / 发送
      右栏：MCP 能力开关 · 技能库（用户自建分类 + 常驻/按需 + 新建）
   │ HTTP + SSE
   ▼
gateway/  本地服务（Python 标准库 http.server）：给前端提供接口 + 流式推回 agent 输出
   │
   ▼
core/  AgentLoop(ReAct)
        ├─ Reasoner ──urllib──► 任意 LLM（DeepSeek 默认）
        ├─ ToolHub ──MCP(subprocess+json)──► reaper-mcp / memory / system / pet-mcp …
        ├─ Context 装配（常驻技能 + 命中的按需技能 + 记忆 + 历史 → 系统提示）
        ├─ Memory（接口 + 后端）──► 记忆库
        └─ Threads（线程记录）──► 对话存档
```

全程零依赖：`urllib` / `subprocess` / `json` / `sqlite3` / `http.server`。

---

## 6. 目录结构

```
prism-core/
├── core/
│   ├── contracts.py     # Message / ToolSpec / ToolCall / ToolResult / Decision
│   ├── reasoner.py      # Reasoner 抽象基类
│   │   reasoners/openai_compat.py   # urllib 打 OpenAI 兼容（换大脑）
│   ├── mcp_client.py    # 手写 MCP stdio 客户端
│   ├── tools.py         # ToolHub：连多个 MCP，聚合工具，路由调用
│   ├── skills.py        # 技能库：读/增/删 用户技能，按 disclosure 处理
│   ├── context.py       # 装配系统提示（常驻技能 + 命中按需技能 + 记忆 + 历史）
│   ├── memory.py        # Memory 接口 + 实现 + 工厂（插拔）
│   ├── loop.py          # ReAct 循环 + permission 钩子 + (M2)感知钩子
│   ├── threads.py       # 线程记录：存/取对话
│   └── runner.py        # 装配 + 跑一个会话
├── config/              # 旋钮（用户拧的）
│   ├── providers.json   # 大脑清单（default: deepseek）
│   ├── mcp_servers.json # 所有 MCP 服务器
│   ├── memory.json      # 记忆后端选择
│   └── settings.json    # 全局（max_steps / timeout）
├── data/                # 用户数据（可随时增删）
│   ├── skills/          # 用户技能，每个 .md（frontmatter: name/disclosure/tags）
│   ├── threads/         # 对话存档
│   └── memory/          # 记忆库
├── gateway/             # 本地服务（http + SSE）
├── web/                 # 前端
├── run.py               # 入口（命令行：python run.py "做段 lo-fi"）
├── DESIGN.md  ·  AGENTS.md  ·  README.md   # 无 requirements.txt（零依赖）
```

---

## 7. 数据约定

### 技能文件（`data/skills/<name>.md`）
```
---
name: 资深制作人
disclosure: full        # full=常驻整段注入 / lazy=按需(平时只给描述,命中才读全文)
tags: [人设]            # 用户自定义分类,可多个
---
你是一位资深音乐制作人……
```

### 记忆三件套
- `core/memory.py` = 代码（接口 + 实现 + 工厂）
- `config/memory.json` = 选哪个后端（如 `{"backend":"sqlite","options":{"path":"data/memory/prism.db"}}`）
- `data/memory/…` = 真正存的数据

---

## 8. 电脑操控（Codex/CC 那种）

- 本质也是工具：**终端/文件型**（system-mcp：run_command/read/write/edit）+ **图形界面型**（computer-use：screenshot 取数 + click/type 动作）。
- 默认不挂；要就在 `mcp_servers.json` 里加一个 MCP，UI 勾上即得。
- **MCP 为主**：LLM 驱动的离散动作，MCP 开销被 LLM 思考时间淹没，可忽略。
- **必要时内置"快通道"**：高频/大负载/实时（连续截屏、实时流）不走 MCP，做成内置/本地。截屏走"存文件返回路径"避免大 base64 挤管道。
- **危险动作必须过 permission 钩子**（写操作/shell/点击 执行前要用户确认）。

---

## 9. 实时（桌宠的动画/语音/口型）

不走 MCP、不走核心循环。MCP 只发一句高层命令（`speak("…", expression="happy")`），**本地引擎自己连续渲染 + 从音频实时算口型**。EventBus 属于桌宠领域的身体运行时，不在 core。

---

## 10. 路线图

| 里程碑 | 内容 | 产出 |
|---|---|---|
| **M1 骨架** | core 全套 + 命令行跑通 | "一句话 → 操作 REAPER"；换两个大脑各跑一次 |
| **M2 感知闭环** | reaper-mcp 加 `analyze_mix` + loop 感知钩子 | before/after 对比 |
| **M3 第二用途** | system-mcp 或 pet-mcp | 验证核心通用 |
| **M4 前端 + 打磨** | gateway + web + 线程/记忆/技能 UI | 可展示成品 |

> 注：前端在 M4。M1~M3 先用命令行把核心打扎实（先有内核可显示，前端才有意义）。

---

## 11. 决策记录（全部已定）
- [x] Python · 零依赖 · 手写 · JSON 配置 · DeepSeek 默认
- [x] 去掉 "domain/场景"：用途 = MCP + 技能的组合
- [x] 人格 = 技能（disclosure: full）；技能用户自建 + 自定义分类
- [x] 记忆：接口 + 后端 + 数据 三件套，可插拔分级（L0 json → L1 sqlite/文件 → L2 向量）
- [x] 线程记录（会话持久化）
- [x] 模型选择放底部输入区右下角；UI 白底蓝点缀
- [x] 电脑操控 = 可选 MCP + permission 钩子 + 必要时内置快通道
- [x] 默认与定制哲学：合理默认 + 可选定制（opt-in）+ 定制只在可插拔槽、核心不脏（详见 §12）

---

## 12. 默认与定制哲学（合理默认，可选定制，定制自愿）

贯穿所有功能的准绳——任何新功能都照此设计：

- **合理默认**：每个旋钮都有能用的默认值，用户什么都不配也能开箱即用（如大脑默认 DeepSeek、记忆默认 `default` 工作区、无底座 base_prompt）。
- **可选定制（opt-in）**：定制是自愿的——不碰就是默认，碰了才生效。用户拥有"要不要深入定制"的选择权，系统从不强迫配置。
- **三档递进控制**（以大脑为例）：零配置默认（providers.json 的 default）→ 选预设（界面底部切 provider）→ 深度自定义（改 base_url/model/key、加新 provider）。
- **定制只在可插拔槽发生**：大脑 / 记忆 / 能力(MCP) / 上下文(技能)。核心永远纯净、领域无关、不被定制内容污染。
- **谁说了算 = 配置，不是代码**：工厂（`build_reasoner` / `build_memory` 等）只照 config 机械执行、自身无主见；"规章"由默认 / 用户写。**编排策略**（反思/Reflexion、规划、多 agent）不属于这四个槽——它是"用内核搭某个具体 agent 时"才决定的，属于 harness/应用层，不焊进内核。

一句话：**开箱即用，深度可定制，定制自愿，核心不脏。**
