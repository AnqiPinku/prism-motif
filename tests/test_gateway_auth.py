"""Gateway 会话认证的纯逻辑测试。"""

import unittest
from email.message import Message
from unittest.mock import patch

from gateway import auth


def headers(**values):
    """构造与 BaseHTTPRequestHandler 相同接口的 Header 对象。"""
    out = Message()
    for name, value in values.items():
        out[name.replace("_", "-")] = value
    return out


class GatewayAuthTests(unittest.TestCase):
    def setUp(self):
        self.token_patch = patch.object(auth, "SESSION_TOKEN", "test-session-token")
        self.origin_patch = patch.object(
            auth,
            "ALLOWED_ORIGINS",
            {"http://tauri.localhost", "http://127.0.0.1:8770"},
        )
        self.token_patch.start()
        self.origin_patch.start()

    def tearDown(self):
        self.origin_patch.stop()
        self.token_patch.stop()

    def test_missing_token_is_unauthorized(self):
        self.assertEqual(auth.authorize(headers()), (False, 401, "unauthorized"))

    def test_wrong_token_is_unauthorized(self):
        result = auth.authorize(headers(X_Prism_Session="wrong"))
        self.assertEqual(result, (False, 401, "unauthorized"))

    def test_allowed_origin_and_token_succeed(self):
        result = auth.authorize(headers(
            Origin="http://tauri.localhost",
            X_Prism_Session="test-session-token",
        ))
        self.assertEqual(result, (True, 200, ""))

    def test_disallowed_origin_fails_before_token(self):
        result = auth.authorize(headers(
            Origin="https://evil.example",
            X_Prism_Session="test-session-token",
        ))
        self.assertEqual(result, (False, 403, "origin_not_allowed"))

    def test_same_origin_cookie_can_authenticate_browser_mode(self):
        result = auth.authorize(headers(
            Origin="http://127.0.0.1:8770",
            Cookie="other=x; prism_session=test-session-token",
        ))
        self.assertEqual(result, (True, 200, ""))

    def test_preflight_rejects_unknown_headers(self):
        result = auth.preflight_allowed(headers(
            Origin="http://tauri.localhost",
            Access_Control_Request_Method="POST",
            Access_Control_Request_Headers="Content-Type, X-Evil",
        ))
        self.assertEqual(result, (False, 403, "headers_not_allowed"))

    def test_preflight_accepts_session_header(self):
        result = auth.preflight_allowed(headers(
            Origin="http://tauri.localhost",
            Access_Control_Request_Method="POST",
            Access_Control_Request_Headers="Content-Type, X-Prism-Session",
        ))
        self.assertEqual(result, (True, 204, ""))

    def test_preflight_accepts_upload_filename_header(self):
        result = auth.preflight_allowed(headers(
            Origin="http://tauri.localhost",
            Access_Control_Request_Method="POST",
            Access_Control_Request_Headers="Content-Type, X-Filename, X-Prism-Session",
        ))
        self.assertEqual(result, (True, 204, ""))

    def test_health_payload_identifies_this_product(self):
        with patch.object(auth, "INSTANCE_ID", "instance-123"):
            self.assertEqual(auth.health_payload(), {
                "product": "prism-motif",
                "protocol": 2,
                "instance_id": "instance-123",
                "ready": True,
            })

    def test_tauri_managed_session_never_bootstraps_cookie(self):
        with patch.object(auth, "SESSION_FROM_ENV", True):
            self.assertIsNone(auth.browser_cookie())


if __name__ == "__main__":
    unittest.main()
