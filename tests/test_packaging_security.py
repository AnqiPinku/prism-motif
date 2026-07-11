"""正式包不得重新带入通用系统执行服务。"""

import json
import unittest
from pathlib import Path


class PackagingSecurityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent

    def test_packaged_mcp_config_only_contains_music_services(self):
        cfg = json.loads(
            (self.root / "config" / "mcp_servers.packaged.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            [server["name"] for server in cfg["servers"]],
            ["reaper", "music-perception"],
        )

    def test_tauri_resources_do_not_bundle_system_mcp(self):
        cfg = json.loads(
            (self.root / "frontend" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
        )
        resources = cfg["bundle"]["resources"]
        self.assertFalse(any("system-mcp" in key or "system-mcp" in value
                             for key, value in resources.items()))


if __name__ == "__main__":
    unittest.main()
