"""工具风险策略测试。"""

import unittest
from pathlib import Path

from gateway.policy import ToolPolicy


class ToolPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = ToolPolicy(default="write", tools={
            "status": "read",
            "delete": "destructive",
            "run": "execute",
            "transport": {
                "risk": "write",
                "when": [{"argument": "action", "equals": "record", "risk": "record"}],
            },
            "render": {
                "risk": "write",
                "when": [{"argument": "out_path", "present": True, "risk": "destructive"}],
            },
        })

    def test_unknown_tool_is_not_treated_as_read_only(self):
        self.assertEqual(self.policy.risk_for("new_tool", {}), "write")
        self.assertEqual(
            self.policy.requires_confirmation("new_tool", {}, trust=False),
            (True, "write"),
        )
        self.assertEqual(
            self.policy.requires_confirmation("new_tool", {}, trust=True),
            (True, "write"),
        )

    def test_read_tool_never_prompts(self):
        self.assertEqual(
            self.policy.requires_confirmation("status", {}, trust=False),
            (False, "read"),
        )

    def test_trust_only_skips_normal_writes(self):
        self.assertEqual(
            self.policy.requires_confirmation("transport", {"action": "play"}, trust=True),
            (False, "write"),
        )
        self.assertEqual(
            self.policy.requires_confirmation("delete", {}, trust=True),
            (True, "destructive"),
        )
        self.assertEqual(
            self.policy.requires_confirmation("run", {}, trust=True),
            (True, "execute"),
        )

    def test_conditional_record_is_always_confirmed(self):
        self.assertEqual(
            self.policy.requires_confirmation("transport", {"action": "record"}, trust=True),
            (True, "record"),
        )

    def test_explicit_render_path_is_destructive(self):
        self.assertEqual(self.policy.risk_for("render", {}), "write")
        self.assertEqual(
            self.policy.risk_for("render", {"out_path": "C:/mix.wav"}),
            "destructive",
        )

    def test_prefixed_collision_name_uses_underlying_policy(self):
        self.assertEqual(self.policy.risk_for("reaper__status", {}), "read")

    def test_product_policy_protects_reaper_escape_hatches(self):
        root = Path(__file__).resolve().parent.parent
        policy = ToolPolicy.from_file(root / "config" / "tool_policy.json")
        self.assertEqual(policy.risk_for("reaper_status", {}), "read")
        self.assertEqual(policy.risk_for("delete_track", {"index": 0}), "destructive")
        self.assertEqual(policy.risk_for("run_lua", {"code": "return 1"}), "execute")
        self.assertEqual(
            policy.risk_for("transport", {"action": "record"}),
            "record",
        )
        self.assertEqual(policy.risk_for("listen_subjective", {}), "external")


if __name__ == "__main__":
    unittest.main()
