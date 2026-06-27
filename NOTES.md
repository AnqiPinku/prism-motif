# Prism Core — 设计讨论 & 调研笔记

> HANDOFF.md = "做到哪 / 下一步做什么"（路线图）；DESIGN.md = 架构定稿；AGENTS.md = 冻结契约。
> 本文件 = "为什么这么决定 + 调研留档"，HANDOFF 不该被这些细节撑大。

---

## 1. 当前内核状态（2026-06-27）

干净的领域无关内核：**ReAct 循环 + 四个可插拔槽（模型 / 记忆 / 能力(MCP) / 上下文(技能)） + 权限闸 + 线程 + 工作区**。零依赖。
- Reflexion 曾完整实现又**整体撤出核心**（见 §2）。
- 工作区 = 长期记忆命名空间（只管记忆隔离，**当前无写入路径**，记忆为只读槽）。
- UI 术语 "大脑" 已全改为 "模型"。

## 2. 决策：Reflexion 属 harness 层，不进核心

- Reflexion 是**对循环的编排策略**（跑→评→再跑），不属于四个槽里的任何一个，和"规划/多 agent"同类。**编排策略是搭具体（领域）agent 时才决定的，属 harness/应用层。**
- "用评判器感知" 本就是内核自带原语：**客观感知 = 取数型 MCP 工具，判官 = 一次 reasoner 调用**，无需内核内置 Reflexion 机器。
- 做音乐**领域 agent**时，在上层用内核（reasoner 当判官、MCP 工具当客观感知、memory 当反思记忆）**组合** Reflexion。

参考：曾设计的可插拔评判器 = judge / tool / composite(grounded|ensemble)；grounded = 客观工具先量→判官读数字给有据可依的批评（"语言+感知器一起"）。

## 3. 决策：Reflexion vs Self-Refine（认知留档）

- **Self-Refine** = 同一产物 + 自我反馈 + 原地反复改（无外部信号）。
- **Reflexion** = 多次尝试 + （常客观的）评判信号 + 把失败写成教训存进记忆 + 下次带着教训重来。
- 音乐场景的"最佳形态" = Self-Refine 的原地迭代 + Reflexion 的客观评判（+ 判官分离 + 反思记忆）——但这是**领域 agent** 的事。

## 4. 调研：好的"长期记忆教训"要满足四要素（将来做领域反思时用）

1. **可迁移**（通用规则，非一次性事实）2. **会被召回**（未来任务捞得出）3. **真改变行为** 4. **可验证**（记住它到底有没有帮上）。
- 参考架构各偷一招：Reflexion（反思重灌下一次）· Generative Agents（检索=相关×重要×新近 + 定期合成洞见）· Voyager（成功→可复用 skill）· ExpeL（留有用丢没用）· MemGPT/Letta（分层自管记忆）。
- **关键洞见**：一条值得长期留的教训本质就是一个 lazy **技能(skill)**——可复用 Prism 已有原语（教训→晋升技能），别另搭平行管线。
- 验证(④)依赖**客观标尺** = 未来的 audio-mcp。

## 5. 调研：上下文压缩（SOTA，已按"零依赖内核可用"过滤）

业界共识：不压 token 本身，而是**压实对话历史**，找"最小高信号 token 集合"。

| 技术 | 说明 | 适用 |
|---|---|---|
| 摘要压实 compaction | 近窗口上限时一次 LLM 调用把旧历史压成"决定/事实/未决任务"摘要 | ✅ 主力 |
| 工具结果消隐 observation masking | 旧大块工具输出换占位符、留调用痕迹（JetBrains：省一半成本不掉点） | ✅✅ 最划算，无 LLM 调用，先做 |
| 滑窗 + 摘要 | 系统提示 + 最近 K 轮原文 + 更早摘要 | ✅ 标准结构 |
| 自适应触发 Self-Compact | 按信息密度提前触发，不固定阈值 | 🔶 进阶 |
| 分层外置 MemGPT/Letta | 旧history page 到外部库按需检索 | 🔶 = 记忆 MCP，外置不进核心 |
| LLMLingua 提示压缩 | 小模型按 token 重要性压到 1/20 | ❌ 破零依赖，将来可做 MCP |

Anthropic 告诫：压缩是**不可逆丢弃**，有风险 → 对策"磁盘留全本、只压发给模型那份"。

### 实现规划（核心健壮性，领域无关，正当进核心）
- **token 量**：不引 tokenizer，直接读 API 返回 `usage.prompt_tokens` 当真值；`OpenAICompatReasoner` 存 `last_prompt_tokens`（加属性，不改契约）。也是 UI 圆环的数据源。流式需 `stream_options:{include_usage:true}` 取末尾 usage chunk（DeepSeek/OpenAI 支持；极少数严格服务端可能不认该字段 → 无 usage 时回退 `estimate_tokens` 粗估，不崩）。
- **两段式**（`core/compaction.py`）：① 工具结果消隐（无 LLM）② 还超预算→摘要压实（一次 LLM 调用，结构化提示保留决定/事实/未决/偏好）。永远保留 系统提示 + 最近 K 轮原文 + 摘要。
- **触发**：`run_turn` 回合前 `last_prompt_tokens > compact_at × window` 就先压实（pre-turn）。
- **不可逆对策**：磁盘线程存全本，压实只作用于"发给模型那份"。
- **config**（settings.json，默认开=安全网）：`"context": {"enabled":true,"window_tokens":65536,"compact_at":0.8,"keep_recent_turns":4,"elide_tool_results":true,"elide_over_chars":2000,"summarize":true}`。
- **UI**：压实发 `{"type":"compaction"}`；每轮发 `{"type":"context",prompt_tokens,window,pct}` → 前端**上下文占用环**（绿→琥珀→红，到阈值自动压实后回落，topbar 右上，纯 SVG）。
- **分期**：✅ Phase 1（消隐+token追踪+圆环+按线程占用）已完成 → ▶ Phase 2（摘要压实，进行中）→ 自适应/记忆 MCP 留后。
- **预算 = 按模型配（已定）**：CC 默认用模型真实窗口、让用户调小；但 Prism 连任意端点、拿不到可信真实窗口（硬编码会过期，65536 就是教训）。所以 `window_tokens` 当"**质量预算**"，每模型一个（providers.json，⚙ 滑轨 8K–1M 档），默认 128K；圆环分母=预算，`compact_at` 0.6（CC 社区"50-70%提前压"）。这比拿 1M 硬上限当分母有用（否则圈永远贴 0%）。
- **Phase 2 设计（增量摘要 + 全本存盘）**：接近 `compact_at×预算` 时，把 `prior[upto:recent_cut]`（最近 K 回合之前、上次摘要之后的新内容）连同已有摘要一次 LLM 压成新摘要；摘要折进 system 发给模型，最近 K 回合原文照发。摘要 `{text,upto}` 存进 thread config，**磁盘线程仍存全本**（prior 全量 + 本轮新消息），不丢历史、不每轮重复摘要。

来源：Anthropic「Effective context engineering for AI agents」/ Claude Cookbook（memory/compaction/tool clearing）/ JetBrains「Efficient context management」/ Morph「Compaction vs Summarization」/ microsoft/LLMLingua / Letta「Memory Blocks」。

## 6. 成熟度待办（"成熟 ≠ 加功能"；内核只需 健壮 + 可观测 + 好搭）

健壮性：✅① **上下文压缩**（Phase1+2 完成，见 §5）✅② **重试/退避 + 工具超时**（完成，见 §7）③ 服务端真取消 + token/步数预算。
可观测：④ 结构化 trace 持久化 + token 计量。
更干净：⑤ 权限闸去硬编码（危险性来自工具元数据/config，核心不再认识具体工具名）⑥ 记忆写入走"记忆 MCP"而非核心代码。
立地基：⑦ 把核心作为"库"的清晰 API（run_turn / Session 类 + 文档），因为编排都在 harness 层组合。
别加：编排（反思/规划/多agent）→harness；领域逻辑→不进核心；具体能力→MCP。

## 7. 可靠性：重试/退避 + 工具超时（已完成）

- **LLM 重试/退避**（`openai_compat.py` 的 `_open`）：只对**瞬时错误**重试（429/408/409/5xx + URLError/Timeout/OSError），4xx（400/401 等）立即抛不重试；指数退避 `base×2^(n-1)` + 抖动；`max_attempts`/`base_delay_s` 来自 `settings.retry`。**流式只重试"建连"那步**——一旦开始读流/吐字就不再重试，避免重复吐字。`on_retry` 回调 → 前端 `retry` 事件（琥珀 ⟳）。
- **MCP 工具超时**（`mcp_client.py`）：原来 `_rpc` 阻塞 `readline()` 会无限挂（Windows 管道无法 select）。改成**后台读线程把 stdout 逐行塞队列 + `_rpc` 用 deadline + `queue.get(timeout=)` 等响应**；超时则抛 → `call_tool` 兜成 `is_error` ToolResult，循环把错误回灌给模型、不挂死。进程退出塞 "" 哨兵。超时后迟到的响应留队列里，下次 `_rpc` 靠 id 不匹配跳过。`tool_timeout_s`（默认 60）经 `ToolHub(tool_timeout=)` 传入。
- 契约：`OpenAICompatReasoner/MCPClient/ToolHub.__init__` 只加**带默认值的可选参数**，向后兼容；`Reasoner.decide` 未动。零依赖（time/random/queue/threading/urllib 皆 stdlib）。
