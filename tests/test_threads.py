"""Thread persistence, metadata, serialization, and concurrency tests."""

import json
import tempfile
import threading
import unittest
from pathlib import Path

from core.contracts import Message, ToolCall
from core import threads


class ThreadPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = self.temp.name

    def tearDown(self):
        self.temp.cleanup()

    def test_save_load_list_and_deserialize_round_trip(self):
        messages = [
            Message("user", "写一段 loop\n[音频文件: C:/private.wav]"),
            Message("assistant", None, tool_calls=[ToolCall("c1", "echo", {"value": 7})]),
            Message("tool", "ok", tool_call_id="c1"),
        ]
        threads.save_thread(self.directory, "thread-1", {"workspace": "project"}, messages)
        saved = threads.load_thread(self.directory, "thread-1")
        self.assertEqual(saved["title"], "写一段 loop")
        self.assertEqual(threads.list_threads(self.directory)[0]["workspace"], "project")
        restored = threads.deserialize(saved["messages"])
        self.assertEqual(restored[1].tool_calls[0].arguments, {"value": 7})
        self.assertEqual(restored[2].tool_call_id, "c1")

    def test_rename_archive_and_retag_preserve_mtime(self):
        threads.save_thread(
            self.directory, "thread-1", {"workspace": "old"}, [Message("user", "hello")]
        )
        original = threads.load_thread(self.directory, "thread-1")["mtime"]
        self.assertTrue(threads.rename_thread(self.directory, "thread-1", "custom"))
        self.assertTrue(threads.set_archived(self.directory, "thread-1", True))
        self.assertEqual(threads.retag_workspace(self.directory, "old", "new"), 1)
        saved = threads.load_thread(self.directory, "thread-1")
        self.assertEqual(saved["mtime"], original)
        self.assertEqual(saved["title"], "custom")
        self.assertTrue(saved["archived"])
        self.assertEqual(saved["config"]["workspace"], "new")

    def test_concurrent_save_and_retag_never_corrupt_json(self):
        threads.save_thread(
            self.directory, "thread-1", {"workspace": "old"}, [Message("user", "start")]
        )
        errors = []

        def save_many():
            try:
                for index in range(50):
                    threads.save_thread(
                        self.directory,
                        "thread-1",
                        {"workspace": "old"},
                        [Message("user", "turn-%d" % index)],
                    )
            except Exception as exc:  # pragma: no cover - asserted through errors
                errors.append(exc)

        def retag_many():
            try:
                for _ in range(50):
                    threads.retag_workspace(self.directory, "old", "new")
            except Exception as exc:  # pragma: no cover - asserted through errors
                errors.append(exc)

        workers = [threading.Thread(target=save_many), threading.Thread(target=retag_many)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)
        self.assertFalse(errors)
        path = Path(self.directory) / "thread-1.json"
        self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)
        self.assertFalse((Path(str(path) + ".tmp")).exists())


if __name__ == "__main__":
    unittest.main()
