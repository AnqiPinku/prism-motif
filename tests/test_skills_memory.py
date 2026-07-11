"""Skill parsing, context disclosure, and memory isolation tests."""

import tempfile
import unittest

from core.context import build_system_prompt
from core.memory import JsonMemory
from core.skills import _parse, add_skill, delete_skill, load_skills


class SkillsAndMemoryTests(unittest.TestCase):
    def test_frontmatter_and_disclosure(self):
        full = _parse(
            "---\nname: 制作人\ndisclosure: full\ntags: [人设, 音乐]\n---\n你是制作人。",
            "full.md",
        )
        lazy = _parse(
            "---\nname: 理论\ndisclosure: lazy\ntags: []\n---\n写和弦优先 ii-V-I。",
            "lazy.md",
        )
        prompt = build_system_prompt([full, lazy], ["用户爱 75bpm"], base="BASE")
        self.assertEqual(full.tags, ["人设", "音乐"])
        self.assertIn("你是制作人。", prompt)
        self.assertIn("理论", prompt)
        self.assertIn("用户爱 75bpm", prompt)

    def test_add_load_and_delete_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            add_skill(directory, "测试技能", "正文", disclosure="lazy", tags=["t1"])
            loaded = load_skills(directory)
            self.assertEqual(loaded[0].name, "测试技能")
            self.assertTrue(delete_skill(directory, "测试技能"))
            self.assertEqual(load_skills(directory), [])

    def test_unrelated_memory_never_falls_back_to_recent_items(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = JsonMemory(directory)
            self.assertEqual(memory.recall("x"), [])
            memory.remember("用户喜欢 lo-fi 75bpm")
            memory.remember("只谈绘画：构图与色彩")
            self.assertTrue(any("lo-fi" in item for item in memory.recall("lo-fi")))
            self.assertEqual(memory.recall("混音 LUFS"), [])


if __name__ == "__main__":
    unittest.main()
