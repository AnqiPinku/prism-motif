"""上下文压缩（领域无关）：让"发给模型的那份"保持精简，磁盘线程仍存全本。

Phase 1：**工具结果消隐**——把"最近 K 个用户回合之前"的超长工具输出换成占位符
（保留 tool_call 痕迹与对应 id），不花 LLM 调用。通过 CompactingReasoner 在每次
decide 前对消息做一次性投影：AgentLoop 持有的消息列表保持全本（照常存盘），模型只看到消隐版。
同时按 on_event 上报上下文占用（prompt token / 窗口），供前端"上下文占用环"。
（Phase 2 的摘要压实将在此基础上加。）
"""
from .contracts import Message
from .reasoner import Reasoner


def _chars(content):
    return len(content) if isinstance(content, str) else 0


def recent_cut(messages, keep_recent_turns):
    """返回下标 i，使 messages[i:] 覆盖"最近 keep_recent_turns 个用户回合"；用户回合不足则返回 0。"""
    user_seen = 0
    for i in range(len(messages) - 1, -1, -1):
        if getattr(messages[i], "role", None) == "user":
            user_seen += 1
            if user_seen >= keep_recent_turns:
                return i
    return 0


def elide_tool_results(messages, keep_recent_turns=4, elide_over_chars=2000):
    """把"最近 keep_recent_turns 个用户回合之前"的超长工具输出换成占位符。
    返回 (新消息列表, 省略条数)。保留 role/tool_call_id 与"调用过"的事实，只省略冗长输出本身。
    不修改入参（返回新列表）。短对话（用户回合不足 K）原样返回。"""
    recent_start = recent_cut(messages, keep_recent_turns)
    out, elided = [], 0
    for i, m in enumerate(messages):
        if (i < recent_start and getattr(m, "role", None) == "tool"
                and _chars(m.content) > elide_over_chars):
            out.append(Message(role="tool", tool_call_id=m.tool_call_id,
                               content="[工具输出已省略 · 原 %d 字符]" % len(m.content)))
            elided += 1
        else:
            out.append(m)
    return out, elided


def estimate_tokens(messages):
    """无 API usage 可用时的兜底粗估：按字符数估 token（中英混合取中和系数 2.5 字/token）。"""
    chars = sum(_chars(getattr(m, "content", "")) for m in messages)
    return int(chars / 2.5)


# Phase 2：摘要压实——一次 LLM 调用把较早历史压成"保留关键信息"的摘要。
SUMMARY_SYSTEM = (
    "你是对话压缩器。把【较早的对话】压成简洁摘要，**必须保留**：关键决定、已确认的事实、"
    "未完成的任务、用户偏好与约束、重要的工具结果结论。丢弃寒暄与冗余细节。"
    "若给了【已有摘要】，把新内容并入它、产出更新后的完整摘要。只输出摘要正文，不要解释、不要客套。")


def _render_for_summary(messages):
    """把消息渲染成纯文本喂给摘要器（工具调用只留一句标记，避免把巨量参数也塞进去）。"""
    role_cn = {"user": "用户", "assistant": "助手", "tool": "工具", "system": "系统"}
    lines = []
    for m in messages:
        role = role_cn.get(getattr(m, "role", ""), getattr(m, "role", ""))
        c = m.content if isinstance(m.content, str) else ""
        if not c and getattr(m, "tool_calls", None):
            c = "[调用工具：%s]" % "、".join(tc.name for tc in m.tool_calls)
        if c:
            lines.append("%s：%s" % (role, c))
    return "\n".join(lines)


def summarize_messages(reasoner, prev_summary, old_messages, on_event=None):
    """把 old_messages（可叠加 prev_summary）压成一条摘要文本。一次 LLM 调用、不带工具。
    失败/空则沿用 prev_summary，绝不抛出（压缩不该拖垮主流程）。"""
    notify = on_event or (lambda e: None)
    notify({"type": "compaction", "kind": "summarize", "content": "正在摘要较早的对话…"})
    parts = []
    if prev_summary:
        parts.append("【已有摘要】\n" + prev_summary)
    parts.append("【较早的对话】\n" + _render_for_summary(old_messages))
    parts.append("请输出更新后的摘要。")
    msgs = [Message(role="system", content=SUMMARY_SYSTEM),
            Message(role="user", content="\n\n".join(parts))]
    try:
        decision = reasoner.decide(msgs, [])
        text = decision.text if (decision and decision.kind == "final") else ""
    except Exception:  # noqa: BLE001
        text = ""
    return text or prev_summary or ""


class CompactingReasoner(Reasoner):
    """包在真 Reasoner 外的"压缩透镜"：每次 decide 前把消息投影成精简版发给内层模型，
    并按 on_event 上报上下文占用（供前端圆环）。本身就是个 Reasoner，对 AgentLoop 透明；
    AgentLoop 持有的全本消息不受影响，照常由上层存盘。"""

    def __init__(self, inner, window_tokens=128000, compact_at=0.6,
                 keep_recent_turns=4, elide=True, elide_over_chars=2000, on_event=None):
        self.inner = inner
        self.window_tokens = window_tokens
        self.compact_at = compact_at
        self.keep_recent_turns = keep_recent_turns
        self.elide = elide
        self.elide_over_chars = elide_over_chars
        self.on_event = on_event or (lambda e: None)

    def decide(self, messages, tools, on_delta=None):
        sent = messages
        if self.elide:
            sent, n = elide_tool_results(messages, self.keep_recent_turns, self.elide_over_chars)
            if n:
                self.on_event({"type": "compaction", "kind": "elide", "count": n,
                               "content": "已省略 %d 段陈旧工具输出" % n})
        decision = self.inner.decide(sent, tools, on_delta=on_delta)
        self._report(sent)
        return decision

    def _report(self, sent):
        """上报上下文占用：优先用内层模型的真实 prompt_tokens（API usage），否则兜底估算。"""
        pt = getattr(self.inner, "last_prompt_tokens", None)
        if pt is None:
            pt = estimate_tokens(sent)
        win = self.window_tokens or 0
        pct = round(pt / win, 4) if win else 0
        self.on_event({"type": "context", "prompt_tokens": pt, "window": win, "pct": pct})

    @property
    def last_prompt_tokens(self):
        """透传内层模型最近的 prompt token 数（供存档/按线程显示圆环）。"""
        return getattr(self.inner, "last_prompt_tokens", None)
