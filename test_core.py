"""Compatibility entry point for the complete offline unittest suite.

Use ``python -m unittest discover -s tests -v`` for direct test-runner flags.
This wrapper remains so existing contributor and packaging commands keep working.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> int:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
