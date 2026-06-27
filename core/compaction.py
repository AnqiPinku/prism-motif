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


def elide_tool_results(messages, keep_recent_turns=4, elide_over_chars=2000):
    """把"最近 keep_recent_turns 个用户回合之前"的超长工具输出换成占位符。
    返回 (新消息列表, 省略条数)。保留 role/tool_call_id 与"调用过"的事实，只省略冗长输出本身。
    不修改入参（返回新列表）。短对话（用户回合不足 K）原样返回。"""
    user_seen = 0
    recent_start = 0
    for i in range(len(messages) - 1, -1, -1):
        if getattr(messages[i], "role", None) == "user":
            user_seen += 1
            if user_seen >= keep_recent_turns:
                recent_start = i
                break
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


class CompactingReasoner(Reasoner):
    """包在真 Reasoner 外的"压缩透镜"：每次 decide 前把消息投影成精简版发给内层模型，
    并按 on_event 上报上下文占用（供前端圆环）。本身就是个 Reasoner，对 AgentLoop 透明；
    AgentLoop 持有的全本消息不受影响，照常由上层存盘。"""

    def __init__(self, inner, window_tokens=65536, compact_at=0.8,
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
