"""Verify that runtime logs do not disclose credential-shaped values."""

from __future__ import annotations

import http.client
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class SensitiveLogTests(unittest.TestCase):
    def test_gateway_logs_exclude_tokens_authorization_and_api_keys(self):
        markers = {
            "session": "session-secret-DO-NOT-LOG-5f9a6c",
            "wrong_session": "wrong-session-DO-NOT-LOG-12ec",
            "authorization": "authorization-secret-DO-NOT-LOG-84be",
            "api_key": "api-key-secret-DO-NOT-LOG-bf20",
        }
        port = free_loopback_port()

        with tempfile.TemporaryDirectory(prefix="prism-log-scan-") as temp_dir:
            env = os.environ.copy()
            env.update(
                {
                    "PRISM_PORT": str(port),
                    "PRISM_SESSION_TOKEN": markers["session"],
                    "PRISM_INSTANCE_ID": "log-scan-instance",
                    "PRISM_HOME": str(ROOT),
                    "PRISM_DATA_DIR": str(Path(temp_dir) / "data"),
                    "LOCALAPPDATA": temp_dir,
                    "DEEPSEEK_API_KEY": markers["api_key"],
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUNBUFFERED": "1",
                }
            )
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
                [sys.executable, "-u", "gateway/server.py"],
                cwd=ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=flags,
            )
            try:
                deadline = time.time() + 20
                while time.time() < deadline:
                    try:
                        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                        connection.request(
                            "GET",
                            "/health",
                            headers={
                                "Origin": "http://tauri.localhost",
                                "X-Prism-Session": markers["session"],
                                "Authorization": f"Bearer {markers['authorization']}",
                            },
                        )
                        response = connection.getresponse()
                        response.read()
                        connection.close()
                        if response.status == 200:
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    self.fail("Gateway did not become ready for the log scan")

                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request(
                    "GET",
                    "/api/state",
                    headers={"X-Prism-Session": markers["wrong_session"]},
                )
                response = connection.getresponse()
                response.read()
                connection.close()
                self.assertEqual(response.status, 401)
            finally:
                process.terminate()
                try:
                    output, _ = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    output, _ = process.communicate(timeout=5)

            logged_text = output
            for path in Path(temp_dir).rglob("*"):
                if path.is_file():
                    logged_text += path.read_text(encoding="utf-8", errors="replace")

            for label, marker in markers.items():
                with self.subTest(secret_type=label):
                    self.assertNotIn(marker, logged_text)


if __name__ == "__main__":
    unittest.main()
