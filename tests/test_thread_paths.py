"""线程存储路径必须留在受管目录。"""

import tempfile
import unittest

from core import threads


class ThreadPathTests(unittest.TestCase):
    def test_normal_thread_id_is_allowed(self):
        with tempfile.TemporaryDirectory() as root:
            path = threads._thread_path(root, "20260710-123456")
            self.assertTrue(path.endswith("20260710-123456.json"))

    def test_directory_traversal_is_rejected(self):
        for value in ("../secrets", "..\\secrets", "C:secret", "a/b", ".."):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    threads._safe_thread_id(value)

    def test_invalid_delete_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(threads.delete_thread(root, "../outside"))


if __name__ == "__main__":
    unittest.main()
