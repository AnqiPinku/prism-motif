"""Gateway Handler 的认证、CORS、健康握手与上传回读集成测试。"""

import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.parse
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
        for path in ("/api/settings", "/api/mcp/toggle", "/api/chat",
                     "/api/chat/cancel"):
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


class GatewayUploadReadbackTests(unittest.TestCase):
    """/api/upload/file 回读通道：认证、上传目录围栏与正常回放。"""

    AUTH = {"Origin": "http://tauri.localhost",
            "X-Prism-Session": "integration-session-token"}

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
        cls.uploads_root = tempfile.mkdtemp(prefix="prism-uploads-test-")
        cls.root_patcher = patch("gateway.server.uploads_root",
                                 return_value=cls.uploads_root)
        cls.root_patcher.start()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        cls.root_patcher.stop()
        shutil.rmtree(cls.uploads_root, ignore_errors=True)
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

    def readback_url(self, path):
        return "/api/upload/file?path=" + urllib.parse.quote(path)

    def make_upload(self, name, data):
        """模拟一次 /api/upload 落盘：根目录下唯一子目录 + 原名文件。"""
        sub = tempfile.mkdtemp(prefix="u", dir=self.uploads_root)
        p = os.path.join(sub, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def test_readback_requires_session_token(self):
        wav = self.make_upload("take.wav", b"RIFFdata")
        status, _, body = self.request("GET", self.readback_url(wav))
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"]["code"], "unauthorized")

    def test_missing_or_empty_path_param_is_bad_request(self):
        for url in ("/api/upload/file", "/api/upload/file?path="):
            with self.subTest(url=url):
                status, _, body = self.request("GET", url, self.AUTH)
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(body)["error"], "bad path")

    def test_paths_outside_root_never_return_200(self):
        # 根目录旁边放一个真实文件，模拟 ..\ 逃逸与绝对路径直取
        fd, outside = tempfile.mkstemp(suffix=".wav",
                                       dir=os.path.dirname(self.uploads_root))
        os.write(fd, b"outside-secret")
        os.close(fd)
        self.addCleanup(os.remove, outside)
        subdir = tempfile.mkdtemp(prefix="u", dir=self.uploads_root)
        candidates = [
            outside,                                            # 根外绝对路径
            os.path.join(self.uploads_root, "..",
                         os.path.basename(outside)),            # ..\ 越界
            self.uploads_root,                                  # 根本身
            subdir,                                             # 根内目录
        ]
        for p in candidates:
            with self.subTest(path=p):
                status, _, body = self.request("GET", self.readback_url(p), self.AUTH)
                self.assertIn(status, (400, 404))
                self.assertNotIn(b"outside-secret", body)

    def test_symlink_escape_is_rejected(self):
        fd, outside = tempfile.mkstemp(suffix=".wav",
                                       dir=os.path.dirname(self.uploads_root))
        os.write(fd, b"outside-secret")
        os.close(fd)
        self.addCleanup(os.remove, outside)
        link = os.path.join(self.uploads_root, "link.wav")
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("当前环境无 symlink 权限")
        self.addCleanup(os.remove, link)
        status, _, body = self.request("GET", self.readback_url(link), self.AUTH)
        self.assertIn(status, (400, 404))
        self.assertNotIn(b"outside-secret", body)

    def test_missing_file_inside_root_is_gone(self):
        p = os.path.join(self.uploads_root, "uDEAD", "cleaned.wav")
        status, _, body = self.request("GET", self.readback_url(p), self.AUTH)
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"], "gone")

    def test_happy_path_streams_exact_wav_bytes(self):
        data = b"RIFF\x24\x00\x00\x00WAVEfmt " + bytes(range(256)) * 4
        wav = self.make_upload("take.wav", data)
        status, headers, body = self.request("GET", self.readback_url(wav), self.AUTH)
        self.assertEqual(status, 200)
        self.assertEqual(body, data)
        self.assertEqual(headers["Content-Type"], "audio/wav")
        self.assertEqual(headers["Content-Length"], str(len(data)))
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cache-Control"], "private, max-age=3600")

    def test_non_wav_falls_back_to_octet_stream(self):
        mp3 = self.make_upload("take.mp3", b"ID3\x03\x00")
        status, headers, body = self.request("GET", self.readback_url(mp3), self.AUTH)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"ID3\x03\x00")
        self.assertEqual(headers["Content-Type"], "application/octet-stream")


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
