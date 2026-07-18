"""工具契约静态检查（ROADMAP 3.2）：Skill 文档与真实 Tool Schema 对账。

在仓库根目录运行：python tests/check_tool_contracts.py
做四件事，任何一条违规即退出码 1：
1. Skill 里引用的工具名必须真实存在（防止"改了工具、忘了改文档"的语义漂移）；
2. Skill 示例调用的参数名必须在该工具的 inputSchema 里（含签名式的裸参数名）；
3. 两个正式包 MCP 的每个工具都必须在 tool_policy.json 里有显式风险条目
   （不允许静默落到 default）；
4. 策略标为 destructive 的工具，描述必须写明覆盖/删除/撤销语义。

工具真相来源：直接 spawn 兄弟仓的两个 MCP server 取 tools/list（reaper 端
无需 REAPER 运行，感知端重依赖懒加载，均可离线出 schema）。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.mcp_client import MCPClient  # noqa: E402

MCPS = ROOT.parent / "mcps"
SERVERS = [
    MCPS / "reaper-mcp" / "server" / "reaper_mcp_server.py",
    MCPS / "music-perception-mcp" / "server" / "music_perception_server.py",
]

# 反引号里的下划线词并不都是工具——技术名词/环境变量/文件名等在此放行。
# 只放行确认不是工具引用的词；新增前先想想它是不是拼错的工具名。
KNOWN_NON_TOOLS = {
    "pm_onboarded",              # 前端 localStorage 键
    "prism_session",             # 认证 cookie 名
    "open_hat",                  # 音乐术语示例
    "tool_policy",               # 配置文件名
    "low_mid",                   # analyze_audio 返回的频段名（结果字段，非入参）
}

CALL_RE = re.compile(r"([a-z][a-z0-9_]{2,})\(([^()]*)\)")
KWARG_RE = re.compile(r"(\w+)\s*=")
BARE_ARG_RE = re.compile(r"^[a-z][a-z0-9_]*$")
BACKTICK_RE = re.compile(r"`([a-z][a-z0-9_]{2,})`")


def load_real_tools() -> dict:
    tools = {}
    for script in SERVERS:
        if not script.is_file():
            raise SystemExit("required MCP checkout missing: %s" % script)
        client = MCPClient(sys.executable, [str(script)], timeout=20)
        client.start()
        try:
            for spec in client.list_tools():
                tools[spec.name] = spec
        finally:
            client.close()
    return tools


def schema_properties(spec) -> set:
    return set((spec.parameters or {}).get("properties", {}).keys())


def schema_enum_values(spec) -> set:
    """收集 schema 里所有字符串枚举值——技能会以 `toggle_repeat` 这类
    反引号动作值引用它们，属正当引用不是幻觉工具。"""
    values: set = set()

    def walk(node):
        if isinstance(node, dict):
            for v in node.get("enum", []):
                if isinstance(v, str):
                    values.add(v)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(spec.parameters or {})
    return values


def check_skills(tools: dict, problems: list) -> None:
    param_vocabulary = set()
    for spec in tools.values():
        param_vocabulary |= schema_properties(spec)
        param_vocabulary |= schema_enum_values(spec)

    for path in sorted((ROOT / "data" / "skills").rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")

        # 1) 调用式引用：name(...)，校验工具存在 + 参数名对得上
        for match in CALL_RE.finditer(text):
            name, arg_blob = match.group(1), match.group(2)
            if name not in tools:
                # 只有"长得像我们的工具"才追责：含下划线且不在放行清单
                if "_" in name and name not in KNOWN_NON_TOOLS \
                        and name not in param_vocabulary:
                    problems.append("%s: 调用了不存在的工具 %s(...)" % (rel, name))
                continue
            allowed = schema_properties(tools[name])
            for kwarg in KWARG_RE.findall(arg_blob):
                if kwarg not in allowed:
                    problems.append("%s: %s() 的参数 %s 不在 schema 里（可用: %s）"
                                    % (rel, name, kwarg, ", ".join(sorted(allowed))))
            if "=" not in arg_blob:      # 签名式写法：裸参数名逐个对账
                for token in (t.strip() for t in arg_blob.split(",")):
                    if BARE_ARG_RE.match(token) and token not in allowed:
                        problems.append("%s: %s(...) 签名里的参数 %s 不在 schema 里"
                                        % (rel, name, token))

        # 2) 反引号引用：`name` 若像工具但不存在则报
        for token in set(BACKTICK_RE.findall(text)):
            if token in tools or "_" not in token:
                continue
            if token in param_vocabulary or token in KNOWN_NON_TOOLS:
                continue
            problems.append("%s: 引用了不存在的工具 `%s`" % (rel, token))


def policy_risk(entry):
    return entry.get("risk") if isinstance(entry, dict) else entry


def check_policy_coverage(tools: dict, problems: list) -> None:
    policy = json.loads((ROOT / "config" / "tool_policy.json").read_text("utf-8"))
    entries = policy.get("tools", {})
    for name in sorted(tools):
        if name not in entries:
            problems.append("tool_policy.json: 工具 %s 无显式风险条目（会静默落到 default=%s）"
                            % (name, policy.get("default")))

    # destructive 工具的描述必须写明覆盖/删除/撤销语义
    markers = re.compile(r"undo|delete|replace|overwrite|destructive|remove", re.IGNORECASE)
    for name, entry in entries.items():
        risks = {policy_risk(entry)}
        if isinstance(entry, dict):
            risks |= {w.get("risk") for w in entry.get("when", [])}
        if "destructive" in risks and name in tools:
            if not markers.search(tools[name].description or ""):
                problems.append("%s: destructive 工具的描述未写明覆盖/删除/撤销语义" % name)


def main() -> int:
    tools = load_real_tools()
    print("已发现真实工具 %d 个（reaper + perception）" % len(tools))
    problems: list = []
    check_skills(tools, problems)
    check_policy_coverage(tools, problems)
    if problems:
        print("工具契约检查失败，共 %d 条：" % len(problems))
        for item in problems:
            print("  ✗ %s" % item)
        return 1
    print("工具契约检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
