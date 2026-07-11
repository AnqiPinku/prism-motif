"""Gateway provider settings remain validated and secret-free on disk."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gateway import server
from gateway.server import Handler


class GatewaySettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Path(self.temp.name)
        (self.config / "providers.json").write_text(json.dumps({
            "default": "deepseek",
            "providers": {
                "deepseek": {
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat",
                    "api_key_env": "DEEPSEEK_API_KEY",
                }
            },
        }), encoding="utf-8")
        (self.config / "mcp_servers.json").write_text(json.dumps({
            "servers": [{
                "name": "music-perception",
                "env": {
                    "GEMINI_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai",
                    "GEMINI_MODEL": "gemini-test",
                },
            }],
        }), encoding="utf-8")
        (self.config / "settings.json").write_text("{}", encoding="utf-8")
        self.config_patch = patch.object(server, "CONFIG", self.config)
        self.config_patch.start()
        self.handler = object.__new__(Handler)

    def tearDown(self):
        self.config_patch.stop()
        self.temp.cleanup()

    def test_settings_get_only_exposes_key_presence(self):
        with patch("gateway.server.secrets_store.has_secret", return_value=True), \
             patch("gateway.server.secrets_store.env_only", return_value=False):
            settings = self.handler._settings_get()
        self.assertTrue(settings["providers"]["deepseek"]["has_key"])
        self.assertNotIn("api_key", settings["providers"]["deepseek"])

    def test_remote_http_provider_is_rejected_without_writing(self):
        before = (self.config / "providers.json").read_text(encoding="utf-8")
        result = self.handler._settings_save({
            "provider": "deepseek",
            "base_url": "http://remote.example/v1",
            "model": "test",
        })
        self.assertFalse(result["ok"])
        self.assertIn("HTTPS", result["error"])
        self.assertEqual((self.config / "providers.json").read_text(encoding="utf-8"), before)

    def test_keyed_host_change_requires_confirmation(self):
        with patch("gateway.server.secrets_store.has_secret", return_value=True):
            result = self.handler._settings_save({
                "provider": "deepseek",
                "base_url": "https://different.example/v1",
                "model": "test",
            })
        self.assertEqual(result["code"], "confirm_provider_host_change")

    def test_confirmed_save_puts_key_in_secret_store_not_json(self):
        with patch("gateway.server.secrets_store.has_secret", return_value=True), \
             patch("gateway.server.secrets_store.set_secret") as set_secret:
            result = self.handler._settings_save({
                "provider": "deepseek",
                "base_url": "https://different.example/v1",
                "model": "test-model",
                "api_key": "secret-value",
                "confirm_host_change": True,
            })
        self.assertTrue(result["ok"])
        set_secret.assert_called_once_with("deepseek", "secret-value")
        on_disk = (self.config / "providers.json").read_text(encoding="utf-8")
        self.assertNotIn("secret-value", on_disk)
        self.assertEqual(json.loads(on_disk)["providers"]["deepseek"]["model"], "test-model")


if __name__ == "__main__":
    unittest.main()
