"""MCP 工具风险策略：未知工具默认需要确认。"""

from __future__ import annotations

import json
from pathlib import Path


VALID_RISKS = {"read", "write", "destructive", "execute", "external", "record"}
HIGH_RISKS = {"destructive", "execute", "external", "record"}
_RISK_PRIORITY = {
    "read": 0,
    "write": 1,
    "destructive": 2,
    "execute": 3,
    "external": 4,
    "record": 5,
}


class ToolPolicy:
    """从受版本控制的 JSON 配置解析工具风险。"""

    def __init__(self, default="write", tools=None):
        self.default = default if default in VALID_RISKS else "write"
        self.tools = tools or {}

    @classmethod
    def from_file(cls, path):
        """读取策略文件；读取失败时安全回落为 unknown=write。"""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        return cls(data.get("default", "write"), data.get("tools") or {})

    def _entry(self, name):
        entry = self.tools.get(name)
        if entry is None and "__" in name:
            entry = self.tools.get(name.split("__", 1)[1])
        return entry

    def is_known(self, name):
        """只有被策略显式覆盖的工具才允许信任模式自动放行。"""
        return self._entry(name) is not None

    @staticmethod
    def _batch_arguments(func, raw_args):
        """Translate positional bridge calls back to policy argument names."""
        if func == "transport":
            return {"action": raw_args[0] if raw_args else None}
        if func in ("render_project", "render_to_wav"):
            return {"out_path": raw_args[0] if raw_args else None}
        return {}

    def _batch_calls(self, entry, arguments):
        """Return policy-visible batch calls, or None for an unsafe shape/function."""
        config = entry.get("batch")
        if not isinstance(config, dict):
            return None
        allowed = config.get("project_functions")
        aliases = config.get("aliases") or {}
        calls = (arguments or {}).get("calls")
        if not isinstance(allowed, list) or not isinstance(aliases, dict) or not isinstance(calls, list):
            return None

        visible = []
        for call in calls:
            if not isinstance(call, dict):
                return None
            func = call.get("func")
            raw_args = call.get("args", [])
            if not isinstance(func, str) or func not in allowed or not isinstance(raw_args, list):
                return None
            name = aliases.get(func, func)
            if not isinstance(name, str) or not self.is_known(name):
                return None
            high_level_args = call.get("arguments")
            if high_level_args is None and len(raw_args) == 1 and isinstance(raw_args[0], dict):
                high_level_args = raw_args[0]
            if high_level_args is not None and not isinstance(high_level_args, dict):
                return None
            policy_args = (
                high_level_args
                if isinstance(high_level_args, dict)
                else self._batch_arguments(func, raw_args)
            )
            visible.append((name, policy_args))
        return visible

    def _batch_risk(self, entry, arguments):
        calls = self._batch_calls(entry, arguments)
        if calls is None:
            # Unknown bridge functions are arbitrary ReaScript calls, so a
            # malformed or unclassified batch must fail closed as execute.
            return "execute"
        risks = [self.risk_for(name, args) for name, args in calls]
        return max(risks, key=_RISK_PRIORITY.get) if risks else "read"

    def batch_calls(self, name, arguments=None):
        """Expose classified batch subcalls for audit and deterministic evals."""
        entry = self._entry(name)
        if not isinstance(entry, dict) or "batch" not in entry:
            return None
        return self._batch_calls(entry, arguments)

    def risk_for(self, name, arguments=None):
        """按工具名与条件规则返回风险等级。"""
        entry = self._entry(name)
        if isinstance(entry, str):
            return entry if entry in VALID_RISKS else self.default
        if not isinstance(entry, dict):
            return self.default
        if "batch" in entry:
            return self._batch_risk(entry, arguments)
        risk = entry.get("risk", self.default)
        args = arguments or {}
        for rule in entry.get("when") or []:
            key = rule.get("argument")
            if not key:
                continue
            matches = False
            if "equals" in rule:
                matches = args.get(key) == rule.get("equals")
            elif "present" in rule:
                present = key in args and args.get(key) not in (None, "")
                matches = present == bool(rule.get("present"))
            if matches:
                risk = rule.get("risk", risk)
                break
        return risk if risk in VALID_RISKS else self.default

    def trust_allows(self, name, arguments=None):
        """Whether trust mode may execute this known, project-scoped action."""
        entry = self._entry(name)
        if isinstance(entry, dict) and "batch" in entry:
            calls = self._batch_calls(entry, arguments)
            return calls is not None and all(
                self.risk_for(call_name, call_args) == "read"
                or self.trust_allows(call_name, call_args)
                for call_name, call_args in calls
            )
        if entry is None:
            return False
        risk = self.risk_for(name, arguments)
        if risk == "write":
            return True
        return (
            isinstance(entry, dict)
            and entry.get("trust") is True
            and risk == "destructive"
        )

    def requires_confirmation(self, name, arguments=None, trust=False):
        """read 自动执行；trust 放行已知的工程内写入与显式可信删除。"""
        risk = self.risk_for(name, arguments)
        if risk == "read":
            return False, risk
        if trust and self.trust_allows(name, arguments):
            return False, risk
        return True, risk
