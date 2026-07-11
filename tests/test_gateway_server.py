"""Gateway Handler 的认证、CORS 与健康握手集成测试。"""

import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from gateway import auth
from gateway.server import Handler, validate_endpoint


class GatewayServerSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_token = auth.SESSION_TOKEN
        cls.original_instance = auth.INSTANCE_ID
        cls.original_origins = auth.ALLOWED_ORIGINS
        cls.original_session_from_env = auth.SESSION_FROM_ENV
        auth.SESSION_TOKEN = "integration-session-token"
        auth.INSTANCE_ID = "integration-instance"
        auth.SESSION_FROM_ENV = False
        auth.ALLOWED_ORIGINS = {"http://tauri.localhost"}
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        auth.SESSION_TOKEN = cls.original_token
        auth.INSTANCE_ID = cls.original_instance
        auth.ALLOWED_ORIGINS = cls.original_origins
        auth.SESSION_FROM_ENV = cls.original_session_from_env

    def request(self, method, path, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        payload = response.read()
        out = (response.status, dict(response.getheaders()), payload)
        conn.close()
        return out

    def test_api_rejects_missing_token(self):
        status, response_headers, body = self.request("GET", "/api/state")
        self.assertEqual(status, 401)
        self.assertNotIn("Access-Control-Allow-Origin", response_headers)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_unauthenticated_writes_never_reach_sensitive_routes(self):
        for path in ("/api/settings", "/api/mcp/toggle", "/api/chat"):
            with self.subTest(path=path):
                status, _, body = self.request(
                    "POST",
                    path,
                    {"Content-Type": "application/json"},
                    b"{}",
                )
                self.assertEqual(status, 401)
                self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_api_rejects_disallowed_origin(self):
        status, response_headers, body = self.request("GET", "/api/state", {
            "Origin": "https://evil.example",
            "X-Prism-Session": "integration-session-token",
        })
        self.assertEqual(status, 403)
        self.assertNotIn("Access-Control-Allow-Origin", response_headers)
        self.assertEqual(json.loads(body)["error"]["code"], "origin_not_allowed")

    def test_health_requires_token_and_matches_instance(self):
        status, response_headers, body = self.request("GET", "/health", {
            "Origin": "http://tauri.localhost",
            "X-Prism-Session": "integration-session-token",
        })
        self.assertEqual(status, 200)
        self.assertEqual(response_headers["Access-Control-Allow-Origin"], "http://tauri.localhost")
        self.assertNotEqual(response_headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(json.loads(body), {
            "product": "prism-motif",
            "protocol": 2,
            "instance_id": "integration-instance",
            "ready": True,
        })

    def test_authenticated_state_route_remains_usable(self):
        status, response_headers, body = self.request("GET", "/api/state", {
            "Origin": "http://tauri.localhost",
            "X-Prism-Session": "integration-session-token",
        })
        self.assertEqual(status, 200)
        self.assertEqual(response_headers["Access-Control-Allow-Origin"], "http://tauri.localhost")
        payload = json.loads(body)
        self.assertIn("providers", payload)
        self.assertIn("mcp", payload)

    def test_allowed_preflight_is_narrow(self):
        status, response_headers, _ = self.request("OPTIONS", "/api/chat", {
            "Origin": "http://tauri.localhost",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-Prism-Session",
        })
        self.assertEqual(status, 204)
        self.assertEqual(response_headers["Access-Control-Allow-Origin"], "http://tauri.localhost")
        self.assertEqual(
            response_headers["Access-Control-Allow-Headers"],
            "Content-Type, X-Filename, X-Prism-Session",
        )

    def test_root_sets_http_only_browser_cookie_without_wildcard_cors(self):
        status, response_headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", response_headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", response_headers["Set-Cookie"])
        self.assertNotIn("Access-Control-Allow-Origin", response_headers)

    def test_static_file_traversal_is_rejected(self):
        status, _, body = self.request("GET", "/../config/providers.json")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"], "not found")

    def test_tauri_managed_root_never_discloses_session_cookie(self):
        with patch.object(auth, "SESSION_FROM_ENV", True):
            status, response_headers, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertNotIn("Set-Cookie", response_headers)


class EndpointValidationTests(unittest.TestCase):
    def test_https_endpoint_is_allowed(self):
        self.assertEqual(
            validate_endpoint("https://api.example.com/v1/"),
            ("https://api.example.com/v1", ""),
        )

    def test_loopback_http_is_allowed_for_local_models(self):
        self.assertEqual(
            validate_endpoint("http://127.0.0.1:11434/v1"),
            ("http://127.0.0.1:11434/v1", ""),
        )

    def test_remote_http_is_rejected(self):
        value, error = validate_endpoint("http://api.example.com/v1")
        self.assertEqual(value, "")
        self.assertIn("HTTPS", error)

    def test_credentials_in_url_are_rejected(self):
        value, error = validate_endpoint("https://user:secret@example.com/v1")
        self.assertEqual(value, "")
        self.assertIn("用户名或密码", error)

    def test_keyed_provider_host_change_requires_explicit_confirmation(self):
        handler = object.__new__(Handler)
        with patch("gateway.server.secrets_store.has_secret", return_value=True):
            result = handler._settings_save({
                "provider": "deepseek",
                "base_url": "https://different-provider.example/v1",
                "model": "test-model",
            })
        self.assertEqual(result["ok"], False)
        self.assertEqual(result["code"], "confirm_provider_host_change")


if __name__ == "__main__":
    unittest.main()
