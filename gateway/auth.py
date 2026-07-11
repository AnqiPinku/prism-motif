"""Gateway 会话认证、Origin 校验与安全响应头。"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from http.cookies import SimpleCookie
from urllib.parse import urlparse


PRODUCT = "prism-motif"
PROTOCOL_VERSION = 2
SESSION_HEADER = "X-Prism-Session"
SESSION_COOKIE = "prism_session"
# x-filename 是 /api/upload 的文件名头（见 server._upload），预检必须放行否则 Tauri 跨源上传直接 403
ALLOWED_REQUEST_HEADERS = {"content-type", "x-filename", SESSION_HEADER.lower()}


SESSION_FROM_ENV = bool(os.environ.get("PRISM_SESSION_TOKEN"))


def _session_token() -> str:
    """读取壳传入的 Token；浏览器开发模式缺省时生成进程级 Token。"""
    return os.environ.get("PRISM_SESSION_TOKEN") or secrets.token_urlsafe(32)


SESSION_TOKEN = _session_token()
INSTANCE_ID = os.environ.get("PRISM_INSTANCE_ID") or secrets.token_hex(16)


def _port() -> int:
    """读取当前 Gateway 端口。"""
    try:
        return int(os.environ.get("PRISM_PORT", "8770"))
    except ValueError:
        return 8770


def _configured_origins() -> set[str]:
    """构造允许的 Tauri、同源浏览器与显式开发 Origin。"""
    port = _port()
    origins = {
        "tauri://localhost",
        "http://tauri.localhost",
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
    }
    raw = os.environ.get("PRISM_DEV_ORIGINS", "")
    origins.update(x.strip().rstrip("/") for x in raw.split(",") if x.strip())
    return origins


ALLOWED_ORIGINS = _configured_origins()


def _cookie_token(raw: str | None) -> str:
    """从浏览器同源开发会话 Cookie 中读取 Token。"""
    if not raw:
        return ""
    try:
        cookie = SimpleCookie()
        cookie.load(raw)
        item = cookie.get(SESSION_COOKIE)
        return item.value if item else ""
    except Exception:  # malformed Cookie 视为未认证
        return ""


def request_token(headers) -> str:
    """优先读取认证 Header，回退到 HttpOnly 同源 Cookie。"""
    return (headers.get(SESSION_HEADER) or _cookie_token(headers.get("Cookie"))).strip()


def token_matches(candidate: str) -> bool:
    """常量时间比较会话 Token。"""
    if not candidate:
        return False
    return hmac.compare_digest(candidate, SESSION_TOKEN)


def origin_allowed(origin: str | None) -> bool:
    """无 Origin 的本机非浏览器请求仍需 Token；浏览器只允许白名单。"""
    if not origin:
        return True
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if not parsed.scheme or not parsed.hostname:
        return False
    normalized = origin.rstrip("/")
    return normalized in ALLOWED_ORIGINS


def authorize(headers) -> tuple[bool, int, str]:
    """校验 Origin 与 Token，返回 (ok, status, error_code)。"""
    if not origin_allowed(headers.get("Origin")):
        return False, 403, "origin_not_allowed"
    if not token_matches(request_token(headers)):
        return False, 401, "unauthorized"
    return True, 200, ""


def preflight_allowed(headers) -> tuple[bool, int, str]:
    """校验 CORS 预检的 Origin、方法与请求头。"""
    origin = headers.get("Origin")
    if not origin or not origin_allowed(origin):
        return False, 403, "origin_not_allowed"
    method = (headers.get("Access-Control-Request-Method") or "").upper()
    if method not in {"GET", "POST", "OPTIONS"}:
        return False, 405, "method_not_allowed"
    requested = {
        x.strip().lower()
        for x in (headers.get("Access-Control-Request-Headers") or "").split(",")
        if x.strip()
    }
    if not requested.issubset(ALLOWED_REQUEST_HEADERS):
        return False, 403, "headers_not_allowed"
    return True, 204, ""


def cors_origin(headers) -> str | None:
    """返回可安全回显的 Origin；未知 Origin 不写 CORS 头。"""
    origin = headers.get("Origin")
    return origin.rstrip("/") if origin and origin_allowed(origin) else None


def browser_cookie() -> str | None:
    """只给手工浏览器开发模式设置 Cookie；Tauri 正式会话绝不下发 Token。"""
    if SESSION_FROM_ENV:
        return None
    return f"{SESSION_COOKIE}={SESSION_TOKEN}; HttpOnly; SameSite=Strict; Path=/"


def health_payload() -> dict:
    """构造供 Tauri 验证身份的健康响应。"""
    return {
        "product": PRODUCT,
        "protocol": PROTOCOL_VERSION,
        "instance_id": INSTANCE_ID,
        "ready": True,
    }


def token_fingerprint() -> str:
    """仅供诊断对比的不可逆短指纹；不得记录原 Token。"""
    return hashlib.sha256(SESSION_TOKEN.encode("utf-8")).hexdigest()[:12]
