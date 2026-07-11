"""Main-repository integration with the two real sibling MCP servers."""

import sys
import unittest
from pathlib import Path

from core.mcp_client import MCPClient


ROOT = Path(__file__).resolve().parents[1]
MCPS = ROOT.parent / "mcps"


class RealMcpIntegrationTests(unittest.TestCase):
    def list_real_tools(self, script):
        self.assertTrue(script.is_file(), "required MCP checkout missing: %s" % script)
        client = MCPClient(sys.executable, [str(script)], timeout=15)
        client.start()
        try:
            return [tool.name for tool in client.list_tools()]
        finally:
            client.close()

    def test_reaper_mcp_is_really_discoverable(self):
        names = self.list_real_tools(MCPS / "reaper-mcp" / "server" / "reaper_mcp_server.py")
        self.assertGreaterEqual(len(names), 20)
        self.assertIn("reaper_status", names)
        self.assertIn("render_to_wav", names)

    def test_music_perception_mcp_is_really_discoverable(self):
        names = self.list_real_tools(
            MCPS / "music-perception-mcp" / "server" / "music_perception_server.py"
        )
        self.assertEqual(len(names), 4)
        self.assertIn("analyze_audio", names)
        self.assertIn("transcribe_melody", names)


if __name__ == "__main__":
    unittest.main()
