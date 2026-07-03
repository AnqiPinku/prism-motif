# AGENTS.md — Prism Core 施工规范（给开发 agent 读）

Prism Core 是一个**干净的原型/种子**：多个领域 agent 都从它**起步**，起步之后该改核心就改核心，不必保持不变。下面这些"约定"是为了让**种子**保持干净、一致、好合并上游——**开发核心（prism-core 本身）时尽量守住；分叉出去的领域 agent 可以按需打破，自负合并成本**。先读本文件，再读 `DESIGN.md`。

> 仓库模型：`prism-core` = 干净种子。开领域 agent = `git clone` 它当起点（把 prism-core 设为 `upstream`），自由加技能/config/harness、也可改核心；想要核心后来的改进就偶尔 `git merge upstream`。详见 HANDOFF。

---

## 0. 种子原则（开发核心时守，分叉可酌情打破）

1. **语言 Python ≥ 3.10。零依赖**：只用标准库（`urllib`/`subprocess`/`json`/`sqlite3`/`http.server`/`dataclasses`/`pathlib`/`argparse`）。**禁止 pip 安装任何包**，禁止 `requirements.txt`。
2. **配置用 JSON**（不用 YAML）。技能文件用 markdown + 极简 frontmatter（见 §3）。
3. **没有 "domain/场景" 概念**。用途 = 挂哪些 MCP + 开哪些技能。
4. **不要预置任何技能或分类**。`data/skills/` 起步为空。
5. 命名小写下划线；面向用户的字符串用中文。每个公开函数写一行 docstring。
6. 错误不要静默吞掉：工具失败→返回 `ToolResult(is_error=True, content=错误文字)`，让循环把错误回灌给模型。
7. **只实现分配给你的文件**，import 其它模块时**只依赖本文件 §2 的契约签名**，不要假设其内部实现。

---

## 1. 模块依赖图（决定可并行性）

```
contracts.py (T1, 地基, 必须先冻结)
   ├─ reasoner.py + reasoners/openai_compat.py (T2)   ──┐
   ├─ mcp_client.py (T3) ──► tools.py (T4)             │
   ├─ skills.py + context.py (T5)                      ├─► runner.py + run.py (T8, 集成)
   ├─ memory.py (T6)                                   │
   └─ loop.py (T7)                                   ──┘
config/*.json (T0, 随时可写)
```
冻结 T1 后，**T2 / T3 / T5 / T6 / T7 可并行**；T4 依赖 T3；T8 最后集成。

---

## 2. 核心数据模型 / 约定（改前想清楚；分叉的领域 agent 可打破，自负合并成本）

### 2.1 `core/contracts.py`（T1 实现，全员依赖）
用 `@dataclass`：

```python
@dataclass
class Message:
    role: str                 # "system" | "user" | "assistant" | "tool"
    content: object           # str；或 list（多模态块，M1 只用 str）
    tool_call_id: str = None  # role=="tool" 时填，对应 ToolCall.id

@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict          # JSON Schema（object）

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class ToolResult:
    id: str
    content: object           # str（或多模态块）
    is_error: bool = False

@dataclass
class Decision:
    kind: str                 # "final" | "tools"
    text: str = None          # kind=="final" 时
    tool_calls: list = None   # kind=="tools" 时，list[ToolCall]
```

### 2.2 `core/reasoner.py`（T2）
```python
class Reasoner(ABC):
    @abstractmethod
    def decide(self, messages: list[Message], tools: list[ToolSpec]) -> Decision: ...
```
`reasoners/openai_compat.py`：
```python
class OpenAICompatReasoner(Reasoner):
    def __init__(self, base_url: str, model: str, api_key: str, timeout: int = 120): ...
```
- 用 `urllib.request` POST `base_url.rstrip('/') + "/chat/completions"`，头 `Authorization: Bearer {api_key}`、`Content-Type: application/json`。
- 请求体：`{"model", "messages":[...], "tools":[{"type":"function","function":{name,description,parameters}}...] }`（仅当 tools 非空时带 tools）。`messages` 需把我们的 `Message` 转成 OpenAI 格式（tool 角色用 `{"role":"tool","tool_call_id":...,"content":...}`；assistant 的工具调用用 `tool_calls`）。
- 解析 `choices[0].message`：有 `tool_calls` → `Decision(kind="tools", tool_calls=[ToolCall(id, name, json.loads(arguments))...])`；否则 → `Decision(kind="final", text=content)`。
- **验收**：给一个 mock HTTP（或真 DeepSeek）能返回 Decision；工具调用能正确解析。

### 2.3 `core/mcp_client.py`（T3）
说 MCP stdio JSON-RPC（与 `reaper-mcp` 服务端对称）。
```python
class MCPClient:
    def __init__(self, command: str, args: list[str], env: dict = None): ...
    def start(self) -> None: ...                      # 起子进程 + initialize 握手 + initialized 通知
    def list_tools(self) -> list[ToolSpec]: ...       # 发 tools/list
    def call_tool(self, name: str, arguments: dict) -> ToolResult: ...  # 发 tools/call
    def close(self) -> None: ...
```
- 传输：每条 JSON-RPC 消息一行（newline-delimited），写 `proc.stdin`、读 `proc.stdout`。
- 握手：发 `initialize`(protocolVersion/clientInfo) → 收结果 → 发 `notifications/initialized`。
- `call_tool` 返回的 MCP content（文本块）拼成 `ToolResult.content`；MCP 报错 → `is_error=True`。
- **验收**：能连上 `A:/Prismcode/mcps/reaper-mcp/server/reaper_mcp_server.py`，`list_tools()` 拿到 ~20 个工具，`call_tool("reaper_status",{})` 有返回。

### 2.4 `core/tools.py`（T4，依赖 T3）
```python
class ToolHub:
    def __init__(self, servers: list[dict]): ...   # servers 来自 mcp_servers.json 中 enabled 的项
    def start(self) -> None: ...                     # 启动所有 MCPClient
    def specs(self) -> list[ToolSpec]: ...           # 聚合所有工具
    def execute(self, call: ToolCall) -> ToolResult: ...  # 按 name 路由到对应 client
    def close(self) -> None: ...
```
- 维护 `name -> MCPClient` 映射。名字冲突时用 `"{server}__{tool}"` 前缀消歧（specs 与 execute 要一致）。

### 2.5 `core/skills.py` + `core/context.py`（T5）
技能数据结构：
```python
@dataclass
class Skill:
    name: str
    disclosure: str   # "full" | "lazy"
    tags: list
    body: str
    path: str
```
`skills.py`：
```python
def load_skills(skills_dir: str) -> list[Skill]: ...   # 读 data/skills/*.md，解析 frontmatter（见 §3）
def add_skill(skills_dir, name, body, disclosure, tags) -> Skill: ...
def delete_skill(skills_dir, name) -> None: ...
```
`context.py`：
```python
def build_system_prompt(enabled_skills: list[Skill], memories: list[str], base: str = "") -> str: ...
```
- 顺序：base → 所有 `disclosure=="full"` 的技能 body（整段）→ 所有 `lazy` 技能的「name + 首行描述」清单（告诉模型有这些可用）→ 相关记忆。
- **验收**：给定若干 Skill + memories，产出拼好的系统提示字符串，顺序正确。

### 2.6 `core/memory.py`（T6）
```python
class Memory(ABC):
    @abstractmethod
    def remember(self, item: dict) -> None: ...
    @abstractmethod
    def recall(self, query: str, k: int = 5) -> list: ...   # 返回 list[str]
    def reflect(self) -> None: ...                            # 默认 pass

class JsonMemory(Memory): ...     # data/memory/*.json；recall 做关键词匹配
def build_memory(cfg: dict) -> Memory: ...   # 按 cfg["backend"] 造对应实现
```
- M1 只需 `JsonMemory`，空库时 `recall` 返回 `[]`。

### 2.7 `core/loop.py`（T7）
```python
class AgentLoop:
    def __init__(self, reasoner: Reasoner, toolhub: ToolHub,
                 max_steps: int = 64, on_event=None, permission=None): ...
    def run(self, messages: list[Message]) -> str: ...   # 返回最终回答文本
```
- 循环：`decide` → `final` 则返回 text；`tools` 则对每个 ToolCall：
  - 若 `permission` 提供且该工具需确认 → 调 `permission(call)`，False 则跳过并回灌"用户拒绝"。
  - `toolhub.execute(call)` → 把 assistant(tool_calls) 与 tool 结果 append 进 messages。
- 每步通过 `on_event(event: dict)` 发出（`{"type":"tool_call"/"tool_result"/"final", ...}`），M1 命令行可打印。
- 防护：到 `max_steps` 仍未 final 则返回兜底文字。
- **验收**：配合 mock reasoner + mock toolhub，能跑完一个"调一次工具再 final"的回合。

### 2.8 `core/threads.py`（T8 附带）
```python
def save_thread(threads_dir, thread_id, config: dict, messages: list[Message]) -> None: ...
def load_thread(threads_dir, thread_id) -> dict: ...
def list_threads(threads_dir) -> list[dict]: ...   # [{id,title,updated_at}]
```
存为 `data/threads/<id>.json`。

### 2.9 `core/runner.py` + `run.py`（T8，集成）
```python
def run_once(goal: str, provider: str = None, thread_id: str = None) -> str: ...
```
- 读 `config/*.json` → 选 provider 造 Reasoner → 取 enabled MCP 造 ToolHub → load_skills + build memory + build_system_prompt → AgentLoop.run([system, user(goal)]) → 存 thread → 返回。
- `run.py`：`python run.py "做段 lo-fi" [--provider qwen]`，把 on_event 打印到终端。

---

## 3. 技能 frontmatter（极简，手解析，零依赖）
```
---
name: 资深制作人
disclosure: full
tags: [人设, 音乐]
---
正文 markdown……
```
解析规则：首尾两行 `---` 之间逐行 `key: value`；`tags` 形如 `[a, b]` 按逗号拆分去空格。正文 = 第二个 `---` 之后的全部。

## 4. 配置样例（T0 写）
`config/providers.json`
```json
{ "default": "deepseek",
  "providers": {
    "deepseek": {"base_url":"https://api.deepseek.com","model":"deepseek-chat","api_key_env":"DEEPSEEK_API_KEY"}
  } }
```
`config/mcp_servers.json`
```json
{ "servers": [
  {"name":"reaper","enabled":true,"command":"python","args":["A:/Prismcode/mcps/reaper-mcp/server/reaper_mcp_server.py"]}
] }
```
`config/memory.json` → `{"backend":"json","options":{"dir":"data/memory"}}`
`config/settings.json` → `{"max_steps":64,"request_timeout_s":120}`

## 5. M1 验收（整体）
1. REAPER 开着 + reaper-mcp 桥运行。
2. 设 `DEEPSEEK_API_KEY` 环境变量。
3. `python run.py "把工程速度设为 124，并新建一条叫 Drums 的轨道"`。
4. 预期：终端打印工具调用轨迹（set_tempo / add_track 等），REAPER 里真的生效，最后输出中文总结。
5. 换 `--provider`（第二个大脑）重跑，行为一致 → 证明换大脑。

## 6. 不做（M1 范围外，别顺手加）
gateway / web 前端（M4）、analyze_mix 感知闭环（M2）、向量记忆（L2）、computer-use（按需）。M1 只交付命令行能跑通的 `core/`。
