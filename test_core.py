"""离线自测：用 mock 大脑 + mock 工具验证循环/契约/技能/记忆；
再用真 reaper-mcp 验证 MCP 客户端连通（list_tools 不需要 REAPER 打开）。
运行：python test_core.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.contracts import Message, ToolSpec, ToolCall, ToolResult, Decision
from core.loop import AgentLoop
from core.skills import _parse, add_skill, load_skills, delete_skill
from core.context import build_system_prompt
from core.memory import JsonMemory
from core.tools import ToolHub

failures = []


def check(label, cond):
    print(("  PASS" if cond else "  FAIL"), label)
    if not cond:
        failures.append(label)


# A. 循环（mock 大脑 + mock 工具）
class MockReasoner:
    def __init__(self):
        self.calls = 0

    def decide(self, messages, tools, on_delta=None):
        self.calls += 1
        if self.calls == 1:
            return Decision(kind="tools",
                            tool_calls=[ToolCall(id="1", name="echo", arguments={"x": 7})])
        return Decision(kind="final", text="完成")


class MockToolHub:
    def specs(self):
        return [ToolSpec(name="echo", description="", parameters={"type": "object", "properties": {}})]

    def execute(self, call):
        return ToolResult(id=call.id, content="echoed")

    def close(self):
        pass


print("A. ReAct 循环")
events = []
out = AgentLoop(MockReasoner(), MockToolHub(),
                on_event=lambda e: events.append(e)).run([Message(role="user", content="hi")])
check("循环返回最终文本", out == "完成")
check("触发了工具调用", any(e["type"] == "tool_call" and e["name"] == "echo" for e in events))
check("回灌了工具结果", any(e["type"] == "tool_result" for e in events))

print("B. 技能 / 上下文 / 记忆")
sk = _parse("---\nname: 制作人\ndisclosure: full\ntags: [人设, 音乐]\n---\n你是制作人。", "x.md")
check("frontmatter name", sk.name == "制作人")
check("frontmatter disclosure", sk.disclosure == "full")
check("frontmatter tags", sk.tags == ["人设", "音乐"])
check("frontmatter body", sk.body == "你是制作人。")

lazy = _parse("---\nname: 理论\ndisclosure: lazy\ntags: []\n---\n写和弦优先 ii-V-I。", "y.md")
sp = build_system_prompt([sk, lazy], ["用户爱 75bpm"], base="BASE")
check("系统提示含 base", "BASE" in sp)
check("含常驻技能正文", "你是制作人。" in sp)
check("含按需技能清单", "理论" in sp and "可用技能" in sp)
check("含相关记忆", "用户爱 75bpm" in sp)

mem = JsonMemory(tempfile.mkdtemp())
check("空库 recall 为空", mem.recall("x") == [])
mem.remember("用户喜欢 lo-fi 75bpm")
mem.remember("用户讨厌过亮的高频")
check("recall 命中关键词", any("lo-fi" in t for t in mem.recall("lo-fi")))

sd = tempfile.mkdtemp()
add_skill(sd, "测试技能", "正文", disclosure="lazy", tags=["t1"])
loaded = load_skills(sd)
check("add+load 技能", len(loaded) == 1 and loaded[0].name == "测试技能")
check("delete 技能", delete_skill(sd, "测试技能") and load_skills(sd) == [])

# 记忆隔离（memory.recall 修复）：没命中关键词即返回 []，不兜底塞最近 k 条
miso = JsonMemory(tempfile.mkdtemp())
miso.remember("只谈绘画：构图与色彩")
check("无关查询不命中即返回空(记忆隔离)", miso.recall("音乐 混音 LUFS") == [])

print("C. MCP 客户端连通（真 reaper-mcp，不需 REAPER 打开）")
server = "A:/科广/reaper-mcp/server/reaper_mcp_server.py"
if os.path.exists(server):
    hub = ToolHub([{"name": "reaper", "command": sys.executable, "args": [server]}])
    try:
        hub.start()
        specs = hub.specs()
        names = {s.name for s in specs}
        check("连上 MCP 并发现工具(>=10)", len(specs) >= 10)
        check("含 reaper_status 工具", "reaper_status" in names)
    finally:
        hub.close()
else:
    print("  SKIP reaper-mcp 不存在")

print()
if failures:
    print("%d 项失败: %s" % (len(failures), failures))
    sys.exit(1)
print("全部通过。")
