"""MCP 工具风险策略：未知工具默认需要确认。"""

from __future__ import annotations

import json
from pathlib import Path


VALID_RISKS = {"read", "write", "destructive", "execute", "external", "record"}
ALWAYS_CONFIRM = {"destructive", "execute", "external", "record"}


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

    def risk_for(self, name, arguments=None):
        """按工具名与条件规则返回风险等级。"""
        entry = self._entry(name)
        if isinstance(entry, str):
            return entry if entry in VALID_RISKS else self.default
        if not isinstance(entry, dict):
            return self.default
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

    def requires_confirmation(self, name, arguments=None, trust=False):
        """read 自动执行；trust 只跳过普通 write。"""
        risk = self.risk_for(name, arguments)
        if risk == "read":
            return False, risk
        if risk == "write" and trust and self.is_known(name):
            return False, risk
        return True, risk
