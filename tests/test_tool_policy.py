"""工具风险策略测试。"""

import unittest
from pathlib import Path

from gateway.policy import ToolPolicy


class ToolPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = ToolPolicy(default="write", tools={
            "status": "read",
            "delete": "destructive",
            "project_delete": {"risk": "destructive", "trust": True},
            "run": "execute",
            "transport": {
                "risk": "write",
                "when": [{"argument": "action", "equals": "record", "risk": "record"}],
            },
            "render": {
                "risk": "write",
                "when": [{"argument": "out_path", "present": True, "risk": "destructive"}],
            },
            "batch": {
                "risk": "execute",
                "batch": {
                    "project_functions": ["status", "transport", "project_delete"],
                    "aliases": {},
                },
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

    def test_trust_skips_known_writes_and_explicit_project_deletes(self):
        self.assertEqual(
            self.policy.requires_confirmation("transport", {"action": "play"}, trust=True),
            (False, "write"),
        )
        self.assertEqual(
            self.policy.requires_confirmation("delete", {}, trust=True),
            (True, "destructive"),
        )
        self.assertEqual(
            self.policy.requires_confirmation("project_delete", {}, trust=True),
            (False, "destructive"),
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

    def test_batch_inspects_every_project_call(self):
        safe = {
            "calls": [
                {"func": "status", "args": []},
                {"func": "transport", "args": ["play"]},
                {"func": "project_delete", "args": [0]},
            ]
        }
        self.assertEqual(self.policy.risk_for("batch", safe), "destructive")
        self.assertEqual(
            self.policy.requires_confirmation("batch", safe, trust=True),
            (False, "destructive"),
        )

    def test_batch_fails_closed_for_recording_or_escape_hatches(self):
        record = {"calls": [{"func": "transport", "args": ["record"]}]}
        object_record = {"calls": [{"func": "transport", "arguments": {"action": "record"}}]}
        legacy_object_record = {"calls": [{"func": "transport", "args": [{"action": "record"}]}]}
        arbitrary = {"calls": [{"func": "Main_OnCommand", "args": [40042, 0]}]}
        malformed = {"calls": [{"func": "status", "args": "not-a-list"}]}
        self.assertEqual(
            self.policy.requires_confirmation("batch", record, trust=True),
            (True, "record"),
        )
        self.assertEqual(
            self.policy.requires_confirmation("batch", object_record, trust=True),
            (True, "record"),
        )
        self.assertEqual(
            self.policy.requires_confirmation("batch", legacy_object_record, trust=True),
            (True, "record"),
        )
        self.assertEqual(
            self.policy.requires_confirmation("batch", arbitrary, trust=True),
            (True, "execute"),
        )
        self.assertEqual(self.policy.risk_for("batch", malformed), "execute")

    def test_product_policy_protects_reaper_escape_hatches(self):
        root = Path(__file__).resolve().parent.parent
        policy = ToolPolicy.from_file(root / "config" / "tool_policy.json")
        self.assertEqual(policy.risk_for("reaper_status", {}), "read")
        self.assertEqual(policy.risk_for("delete_track", {"index": 0}), "destructive")
        self.assertEqual(policy.risk_for("run_lua", {"code": "return 1"}), "execute")
        # MIDI 原子修改（Phase 3.1）：逐音改=write；删除与整体替换=destructive。
        # 显式标记的工程内、可撤销删除可由信任模式放行。
        self.assertEqual(policy.risk_for("update_midi_note", {"note_index": 1}), "write")
        self.assertEqual(policy.risk_for("delete_midi_notes", {"note_indices": [1]}),
                         "destructive")
        self.assertEqual(policy.risk_for("replace_midi_notes", {"notes": []}),
                         "destructive")
        self.assertEqual(
            policy.risk_for("transport", {"action": "record"}),
            "record",
        )
        self.assertEqual(policy.risk_for("listen_subjective", {}), "external")
        self.assertEqual(
            policy.requires_confirmation("delete_track", {"index": 0}, trust=True),
            (False, "destructive"),
        )

        safe_batch = {
            "calls": [
                {"func": "set_tempo", "arguments": {"bpm": 95}},
                {"func": "set_time_signature", "args": [4, 4]},
                {"func": "add_track", "args": [{"name": "Chords"}]},
            ]
        }
        self.assertEqual(policy.risk_for("batch", safe_batch), "write")
        self.assertEqual(
            policy.requires_confirmation("batch", safe_batch, trust=True),
            (False, "write"),
        )

        destructive_batch = {"calls": [{"func": "delete_track", "args": [0]}]}
        self.assertEqual(policy.risk_for("batch", destructive_batch), "destructive")
        self.assertEqual(
            policy.requires_confirmation("batch", destructive_batch, trust=True),
            (False, "destructive"),
        )

        for calls, expected_risk in (
            ([{"func": "transport", "args": ["record"]}], "record"),
            ([{"func": "render_to_wav", "args": ["C:/mix.wav"]}], "destructive"),
            ([{"func": "run_lua", "code": "return 1"}], "execute"),
            ([{"func": "Main_OnCommand", "args": [40042, 0]}], "execute"),
        ):
            self.assertEqual(
                policy.requires_confirmation("batch", {"calls": calls}, trust=True),
                (True, expected_risk),
            )


if __name__ == "__main__":
    unittest.main()
