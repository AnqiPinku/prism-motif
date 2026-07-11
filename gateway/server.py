"""Prism Motif 本地 Gateway：提供静态文件、认证 JSON API 与 SSE 聊天流。"""
import os
import sys
import json
import time
import uuid
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from urllib.parse import urlparse, parse_qs              # noqa: E402
from core import runner                                  # noqa: E402
from core import paths                                   # noqa: E402
from core import secrets_store                            # noqa: E402
from core.skills import (load_skills, add_skill, delete_skill,  # noqa: E402
                         load_enabled_map, set_enabled)
from core.mcp_client import MCPClient                    # noqa: E402
from core import threads as threads_mod                  # noqa: E402
from gateway import auth as gateway_auth                 # noqa: E402
from gateway.policy import ToolPolicy                    # noqa: E402

WEB = ROOT / "web"                                       # 静态资源随代码走，只读即可
CONFIG = paths.CONFIG_DIR                                # 可写状态：per-user 目录（发布）/ 就地（开发）
DATA = paths.DATA_DIR

CTYPES = {".html": "text/html", ".js": "application/javascript",
          ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml"}

TOOL_POLICY = ToolPolicy.from_file(paths.INSTALL_ROOT / "config" / "tool_policy.json")
# 待确认的权限请求：id -> {"event": Event, "result": bool}
PENDING = {}

# 正在跑的回合：thread_id -> {"cancel": threading.Event(), "finished": threading.Event()}
# 同线程再来一发 → 先 cancel 上一发 + 等它退出，避免两个 run_turn 并发写同一存档。
RUNNING = {}
RUNNING_LOCK = threading.Lock()


class TurnCancelled(Exception):
    """真取消信号：客户端断线或同线程新请求覆盖时，从 emit 里抛出来，
    穿透 reasoner.on_delta / loop 的每一步 on_event，逼停整个回合。"""


def load_json(p, d):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def validate_endpoint(value, allow_empty=False):
    """只允许 HTTPS；本地模型可使用 loopback HTTP。返回 (规范值, 错误)。"""
    value = str(value or "").strip().rstrip("/")
    if not value:
        return ("", "") if allow_empty else ("", "地址不能为空")
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        _ = parsed.port  # 触发非法端口校验
    except ValueError:
        return "", "地址格式无效"
    if parsed.username or parsed.password:
        return "", "地址不能包含用户名或密码"
    if parsed.scheme == "https" and host:
        return value, ""
    if parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}:
        return value, ""
    return "", "只允许 HTTPS；本地模型可使用 localhost/127.0.0.1 的 HTTP"


def endpoint_host(value):
    """提取用于敏感变更比较的规范主机名。"""
    try:
        return (urlparse(str(value or "")).hostname or "").lower()
    except ValueError:
        return ""


_BRIDGE_INSTALLER = None


def bridge_installer():
    """懒加载 reaper-mcp 的 install_bridge.py（兄弟仓，经 ${PRISM_HOME} 定位）。"""
    global _BRIDGE_INSTALLER
    if _BRIDGE_INSTALLER is None:
        import importlib.util
        # 优先新位置 mcps/reaper-mcp/，回退旧位置（兼容尚未搬家的部署）
        candidates = [
            os.path.join(str(paths.PRISM_HOME), "mcps", "reaper-mcp", "installer", "install_bridge.py"),
            os.path.join(str(paths.PRISM_HOME), "reaper-mcp", "installer", "install_bridge.py"),
        ]
        p = next((c for c in candidates if os.path.isfile(c)), None)
        if not p:
            return None
        spec = importlib.util.spec_from_file_location("reaper_bridge_installer", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _BRIDGE_INSTALLER = mod
    return _BRIDGE_INSTALLER


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # ---------- GET ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health" or path.startswith("/api/"):
            if not self._authorize_api():
                return
        if path == "/health":
            return self._json(gateway_auth.health_payload())
        if path in ("/", ""):
            return self._serve("index.html")
        if path == "/api/state":
            return self._json(self._state())
        if path == "/api/workspaces":
            return self._json({"current": runner.current_workspace(),
                               "names": runner.list_workspaces(),
                               "archived": runner.archived_workspaces()})
        if path == "/api/settings":
            return self._json(self._settings_get())
        if path == "/api/mcp/tools":
            q = parse_qs(urlparse(self.path).query)
            return self._json(self._mcp_tools((q.get("name") or [""])[0]))
        if path == "/api/reaper/status":
            return self._json(self._reaper_status())
        if path.startswith("/api/threads/"):
            tid = path[len("/api/threads/"):]
            try:
                data = threads_mod.load_thread(str(DATA / "threads"), tid)
                data["context"] = runner.thread_context(data)   # 该线程的上下文占用（圆环用）
                return self._json(data)
            except (OSError, ValueError) as e:
                return self._json({"error": str(e)}, 404)
        return self._serve(path.lstrip("/"))

    # ---------- POST ----------
    def do_POST(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/") and not self._authorize_api():
            return
        if path == "/api/upload":           # 原始字节流，须在 JSON 解析之前拦截
            return self._upload()
        body = self._read_body()
        if path == "/api/chat":
            return self._chat(body)
        if path == "/api/skills":
            sk = add_skill(str(DATA / "skills"), body.get("name", "技能"),
                           body.get("body", ""), body.get("disclosure", "lazy"),
                           body.get("tags") or [])
            return self._json({"ok": True, "name": sk.name})
        if path == "/api/skills/delete":
            delete_skill(str(DATA / "skills"), body.get("name", ""))
            return self._json({"ok": True})
        if path == "/api/skills/toggle":
            set_enabled(str(DATA / "skills"), body.get("name", ""), body.get("enabled"))
            return self._json({"ok": True})
        if path == "/api/mcp/toggle":
            return self._json(self._toggle_mcp(body.get("name"), body.get("enabled")))
        if path == "/api/mcp/add":
            return self._json(self._mcp_add(body))
        if path == "/api/mcp/delete":
            return self._json(self._mcp_delete(body.get("name")))
        if path == "/api/settings":
            return self._json(self._settings_save(body))
        if path == "/api/reaper/install-bridge":
            return self._json(self._reaper_install(body.get("resource_path")))
        if path == "/api/mode/switch":
            # 切换三模块工作流:改 config/modes.json 的 current 字段;下一回合 runner 会拾起来。
            # mode="" (空串) 是默认模式 —— 不叠加任何 mode 的 base_prompt,只启用 general skill。
            m = str(body.get("mode") or "").strip()
            cfg = load_json(CONFIG / "modes.json", {})
            if m and m not in (cfg.get("modes") or {}):
                return self._json({"error": "unknown mode: " + m}, 400)
            cfg["current"] = m
            (CONFIG / "modes.json").write_text(
                json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            # 自动切换 skill enable 状态:mode-specific skill 按目标 mode 开关,
            # general skill 保留用户手动选择(避免覆盖 reaper-producer 之类的常驻人设)
            self._sync_skills_to_mode(m, cfg)
            return self._json({"ok": True, "current": m})
        if path == "/api/open":
            # 系统浏览器打开一个 URL（onboarding 里的下载链接等）。
            # 只允许 hostname 白名单 —— 防被越狱的 agent / 注入的页面拿去打开任意 URL。
            import webbrowser
            import urllib.parse as _urp
            u = str(body.get("url") or "")
            try:
                pr = _urp.urlparse(u)
            except ValueError:
                return self._json({"error": "invalid url"}, 400)
            hosts = {"www.reaper.fm", "reaper.fm"}
            if pr.scheme != "https" or pr.hostname not in hosts:
                return self._json({"error": "url not allowed"}, 400)
            webbrowser.open(u)
            return self._json({"ok": True})
        if path == "/api/threads/delete":
            threads_mod.delete_thread(str(DATA / "threads"), body.get("id", ""))
            return self._json({"ok": True})
        if path == "/api/threads/rename":
            threads_mod.rename_thread(str(DATA / "threads"), body.get("id", ""), body.get("title", ""))
            return self._json({"ok": True})
        if path == "/api/threads/archive":
            threads_mod.set_archived(str(DATA / "threads"), body.get("id", ""),
                                     body.get("archived", True))
            return self._json({"ok": True})
        if path == "/api/permission":
            entry = PENDING.get(body.get("id"))
            if entry:
                entry["result"] = bool(body.get("allow"))
                entry["event"].set()
            return self._json({"ok": True})
        if path in ("/api/workspace/switch", "/api/workspace/create"):
            return self._json(self._ws_set(body.get("name")))
        if path == "/api/workspace/archive":
            return self._json(self._ws_call(runner.set_workspace_archived,
                                            body.get("name"),
                                            body.get("archived", True)))
        if path == "/api/workspace/rename":
            out = self._ws_call(runner.rename_workspace,
                                body.get("old"), body.get("new"))
            if "error" not in out:      # 线程归属跟着项目改名走
                threads_mod.retag_workspace(str(DATA / "threads"),
                                            body.get("old"), body.get("new"))
            return self._json(out)
        if path == "/api/workspace/delete":
            out = self._ws_call(runner.delete_workspace, body.get("name"))
            if "error" not in out:      # 被删项目的线程回落到「对话」（default）
                threads_mod.retag_workspace(str(DATA / "threads"),
                                            body.get("name"), "default")
            return self._json(out)
        return self._json({"error": "not found"}, 404)

    def _upload(self):
        """聊天里附音频：收原始字节流存进受管临时目录，返回本机路径给 agent 用。
        文件名走 X-Filename（URL 编码）；目录只留最近 20 个文件，不会积累。"""
        import glob
        import re
        import tempfile
        import urllib.parse
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= 200 * 1024 * 1024:
            return self._json({"error": "文件为空或超过 200MB"}, 400)
        raw = urllib.parse.unquote(self.headers.get("X-Filename") or "audio.wav")
        name = re.sub(r"[^\w.\-一-鿿]+", "_", os.path.basename(raw))[-80:] or "audio.wav"
        updir = os.path.join(tempfile.gettempdir(), "prism-uploads")
        os.makedirs(updir, exist_ok=True)
        # 每次上传一个唯一子目录，文件保留原名（显示干净）；只留最近 20 次
        import shutil
        old = sorted(glob.glob(os.path.join(updir, "*")), key=os.path.getmtime)
        for p in old[:-19]:
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            except OSError:
                pass
        dest = os.path.join(tempfile.mkdtemp(prefix="u", dir=updir), name)
        with open(dest, "wb") as f:
            remaining = length
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                f.write(chunk)
                remaining -= len(chunk)
        return self._json({"path": dest})

    # ---------- helpers ----------
    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            return {}

    def _security_headers(self):
        """发送所有响应共用的安全头和精确 Origin CORS。"""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "object-src 'none'; base-uri 'none'; form-action 'none'",
        )
        origin = gateway_auth.cors_origin(self.headers)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _authorize_api(self):
        """统一保护所有 API 与健康接口。"""
        ok, status, code = gateway_auth.authorize(self.headers)
        if ok:
            return True
        self._json({"error": {"code": code, "message": "Gateway 请求未获授权"}}, status)
        return False

    def _send(self, code, data, ctype, extra_headers=None):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        """只为白名单 Origin 放行所需的 CORS 预检。"""
        ok, status, code = gateway_auth.preflight_allowed(self.headers)
        if not ok:
            return self._json({"error": {"code": code, "message": "CORS 预检被拒绝"}}, status)
        self.send_response(204)
        self._security_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Filename, X-Prism-Session")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _serve(self, rel):
        target = (WEB / rel).resolve()
        try:
            target.relative_to(WEB.resolve())
        except ValueError:
            return self._json({"error": "not found"}, 404)
        if not target.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = CTYPES.get(target.suffix, "application/octet-stream")
        if ctype.startswith(("text/", "application/javascript", "application/json")):
            ctype += "; charset=utf-8"
        cookie = gateway_auth.browser_cookie() if target.name == "index.html" else None
        extra = {"Set-Cookie": cookie} if cookie else None
        self._send(200, target.read_bytes(), ctype, extra_headers=extra)

    def _state(self):
        prov = load_json(CONFIG / "providers.json", {"default": "deepseek", "providers": {}})
        mcp = load_json(CONFIG / "mcp_servers.json", {"servers": []})
        en = load_enabled_map(str(DATA / "skills"))
        skills = [{"name": s.name, "disclosure": s.disclosure, "tags": s.tags,
                   "mode": getattr(s, "mode", "general"),
                   "enabled": en.get(s.name, True)}
                  for s in load_skills(str(DATA / "skills"))]
        fb = (load_json(CONFIG / "settings.json", {}).get("context") or {}).get("window_tokens", 128000)
        # 三模块工作流：给前端 current + labels/icons/accents，供 mode selector 渲染
        modes = load_json(CONFIG / "modes.json", {})
        return {
            "providers": {"default": prov.get("default"),
                          "names": list(prov.get("providers", {}).keys()),
                          "windows": {n: (p.get("window_tokens") or fb)
                                      for n, p in prov.get("providers", {}).items()}},
            "mcp": [{"name": s["name"], "enabled": s.get("enabled", True)}
                    for s in mcp.get("servers", [])],
            "skills": skills,
            "threads": threads_mod.list_threads(str(DATA / "threads")),
            "workspace": {"current": runner.current_workspace(),
                          "names": runner.list_workspaces(),
                          "archived": runner.archived_workspaces()},
            "mode": {
                "current": modes.get("current") or "",
                "list": [{"id": k, "label": v.get("label") or k,
                          "icon": v.get("icon"), "accent": v.get("accent")}
                         for k, v in (modes.get("modes") or {}).items()],
            },
        }

    def _toggle_mcp(self, name, enabled):
        cfg = load_json(CONFIG / "mcp_servers.json", {"servers": []})
        for s in cfg.get("servers", []):
            if s["name"] == name:
                s["enabled"] = bool(enabled)
        (CONFIG / "mcp_servers.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}

    def _mcp_tools(self, name):
        cfg = load_json(CONFIG / "mcp_servers.json", {"servers": []})
        srv = next((s for s in cfg.get("servers", []) if s["name"] == name), None)
        if not srv:
            return {"error": "未找到 MCP: %s" % name}
        client = MCPClient(srv["command"], srv.get("args", []), srv.get("env"))
        try:
            client.start()
            tools = client.list_tools()
            return {"count": len(tools),
                    "tools": [{"name": t.name, "description": t.description} for t in tools]}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
        finally:
            client.close()

    def _mcp_add(self, body):
        name = (body.get("name") or "").strip()
        if not name:
            return {"error": "名称不能为空"}
        cfg = load_json(CONFIG / "mcp_servers.json", {"servers": []})
        if any(s["name"] == name for s in cfg.get("servers", [])):
            return {"error": "已存在同名 MCP"}
        args = body.get("args")
        if isinstance(args, str):
            args = [a.strip() for a in args.replace("\r", "").split("\n") if a.strip()]
        cfg.setdefault("servers", []).append({
            "name": name, "enabled": True,
            "command": (body.get("command") or "python").strip(),
            "args": args or [],
        })
        (CONFIG / "mcp_servers.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}

    def _mcp_delete(self, name):
        cfg = load_json(CONFIG / "mcp_servers.json", {"servers": []})
        cfg["servers"] = [s for s in cfg.get("servers", []) if s["name"] != name]
        (CONFIG / "mcp_servers.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}

    def _settings_get(self):
        prov = load_json(CONFIG / "providers.json", {"default": "deepseek", "providers": {}})
        secrets = load_json(CONFIG / "secrets.json", {})
        out = {"default": prov.get("default"), "providers": {}}
        for name, p in prov.get("providers", {}).items():
            env_set = bool(p.get("api_key_env") and os.environ.get(p.get("api_key_env")))
            # has_key 覆盖钥匙链 + 旧 secrets.json + 环境变量；绝不回传 key 本身
            out["providers"][name] = {
                "base_url": p.get("base_url", ""),
                "model": p.get("model", ""),
                "type": p.get("type", ""),
                "window_tokens": p.get("window_tokens", ""),
                "has_key": secrets_store.has_secret(name) or bool(secrets.get(name)) or env_set,
            }
        # Gemini / 感知（音频分析）：非密钥的 base_url/model 存 mcp_servers.json 的 perception env
        mcp = load_json(CONFIG / "mcp_servers.json", {"servers": []})
        perc = next((s for s in mcp.get("servers", []) if s.get("name") == "music-perception"), {})
        penv = perc.get("env", {}) or {}
        out["gemini"] = {
            "base_url": penv.get("GEMINI_BASE_URL", ""),
            "model": penv.get("GEMINI_MODEL", ""),
            "has_key": secrets_store.has_secret("GEMINI_API_KEY") or bool(os.environ.get("GEMINI_API_KEY")),
            "env_only": secrets_store.env_only("GEMINI_API_KEY"),   # 提示从旧 setx 迁移
        }
        return out

    def _update_perception_env(self, updates):
        """把非密钥的 GEMINI_BASE_URL/GEMINI_MODEL 写进 mcp_servers.json 的 perception env。"""
        cfg = load_json(CONFIG / "mcp_servers.json", {"servers": []})
        for s in cfg.get("servers", []):
            if s.get("name") == "music-perception":
                s.setdefault("env", {}).update(updates)
        (CONFIG / "mcp_servers.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    def _settings_save(self, body):
        prov = load_json(CONFIG / "providers.json", {"default": "deepseek", "providers": {}})
        name = body.get("provider")
        providers = prov.get("providers", {})
        g = body.get("gemini") or {}

        provider_url = None
        if name and name in providers and "base_url" in body:
            provider_url, error = validate_endpoint(body.get("base_url"), allow_empty=False)
            if error:
                return {"ok": False, "code": "invalid_provider_url", "error": error}
        gemini_url = None
        if "base_url" in g:
            gemini_url, error = validate_endpoint(g.get("base_url"), allow_empty=True)
            if error:
                return {"ok": False, "code": "invalid_gemini_url", "error": error}

        legacy_secrets = load_json(CONFIG / "secrets.json", {})
        if provider_url is not None and name in providers:
            old_url = providers[name].get("base_url", "")
            old_host, new_host = endpoint_host(old_url), endpoint_host(provider_url)
            has_key = (secrets_store.has_secret(name) or bool(legacy_secrets.get(name))
                       or bool(os.environ.get(providers[name].get("api_key_env", ""))))
            if old_host and new_host != old_host and has_key and not body.get("confirm_host_change"):
                return {"ok": False, "code": "confirm_provider_host_change",
                        "error": "模型服务主机将从 %s 改为 %s；确认后才会保存。" % (old_host, new_host),
                        "from_host": old_host, "to_host": new_host}

        mcp_cfg = load_json(CONFIG / "mcp_servers.json", {"servers": []})
        perc = next((s for s in mcp_cfg.get("servers", [])
                     if s.get("name") == "music-perception"), {})
        old_gemini_url = (perc.get("env") or {}).get("GEMINI_BASE_URL", "")
        if gemini_url is not None:
            old_host, new_host = endpoint_host(old_gemini_url), endpoint_host(gemini_url)
            has_key = (secrets_store.has_secret("GEMINI_API_KEY")
                       or bool(os.environ.get("GEMINI_API_KEY")))
            if old_host and new_host != old_host and has_key and not body.get("confirm_host_change"):
                return {"ok": False, "code": "confirm_gemini_host_change",
                        "error": "音频模型主机将从 %s 改为 %s；确认后才会保存。" % (old_host, new_host),
                        "from_host": old_host, "to_host": new_host}

        if body.get("default"):
            prov["default"] = body["default"]
        if name and name in providers:
            if provider_url is not None:
                providers[name]["base_url"] = provider_url
            if "model" in body:
                providers[name]["model"] = body["model"]
            if body.get("window_tokens"):
                try:
                    providers[name]["window_tokens"] = max(1000, int(body["window_tokens"]))
                except (TypeError, ValueError):
                    pass
        (CONFIG / "providers.json").write_text(
            json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
        # 密钥一律进系统钥匙链，绝不落 secrets.json（明文）
        try:
            if name and body.get("api_key"):
                secrets_store.set_secret(name, body["api_key"])
            updates = {}
            if gemini_url is not None:
                updates["GEMINI_BASE_URL"] = gemini_url
            if "model" in g:
                updates["GEMINI_MODEL"] = g["model"]
            if updates:
                self._update_perception_env(updates)
            if g.get("import_env"):          # 从旧 setx 环境变量一键导入钥匙链
                v = os.environ.get("GEMINI_API_KEY")
                if v:
                    secrets_store.set_secret("GEMINI_API_KEY", v)
            elif g.get("api_key"):
                secrets_store.set_secret("GEMINI_API_KEY", g["api_key"])
        except Exception as e:  # noqa: BLE001 钥匙链后端不可用/写失败 → 明确报错，不 500
            return {"ok": False, "error": "密钥保存失败：%s" % e}
        return {"ok": True}

    def _reaper_status(self):
        ib = bridge_installer()
        if not ib:
            return {"error": "找不到 reaper-mcp 安装器（检查安装完整性）"}
        try:
            return ib.status()
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def _sync_skills_to_mode(self, mode_id, cfg):
        """切模式时同步 skill enable 状态:mode-specific 的按目标 mode 自动开关,
        general 的保持用户手动选择(避免覆盖常驻人设)。"""
        mode_def = (cfg.get("modes") or {}).get(mode_id, {}) if mode_id else {}
        allowed = set(mode_def.get("skill_modes") or [])
        skills_dir = str(DATA / "skills")
        for s in load_skills(skills_dir):
            sk_mode = getattr(s, "mode", "general")
            if sk_mode == "general":
                continue                       # general 尊重用户手动选择
            set_enabled(skills_dir, s.name, sk_mode in allowed)

    def _reaper_install(self, resource_path):
        ib = bridge_installer()
        if not ib:
            return {"ok": False, "error": "找不到 reaper-mcp 安装器（检查安装完整性）"}
        try:
            return ib.install(resource_path or None)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def _ws_set(self, name):
        try:
            cur = runner.set_workspace(name)
            return {"ok": True, "current": cur, "names": runner.list_workspaces(),
                    "archived": runner.archived_workspaces()}
        except Exception as e:  # noqa: BLE001 含非法名(ValueError)与写盘/建目录失败(OSError)
            return {"error": str(e)}

    def _ws_call(self, fn, *args):
        try:
            fn(*args)
            return {"ok": True, "current": runner.current_workspace(),
                    "names": runner.list_workspaces(),
                    "archived": runner.archived_workspaces()}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def _chat(self, body):
        goal = body.get("goal", "")
        provider = body.get("provider") or None
        thread_id = body.get("thread_id") or None
        bypass = bool(body.get("bypass"))
        started = time.time()
        # SSE 头：HTTP/1.0(stdlib 默认) + close_delimited；不要发 keep-alive，否则 socket
        # 永远不关 → 客户端读不到 EOF、streamChat 的 finally 不执行、每轮泄一条连接。
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self._security_headers()
        self.end_headers()
        self.close_connection = True   # 保险：do_POST 返回后 stdlib 立刻关 socket

        tid = thread_id or time.strftime("%Y%m%d-%H%M%S")

        # —— 同线程闸：若 tid 已有回合在跑，先请它退出，再接手。
        cancel = threading.Event()      # 我们这一发的取消信号
        finished = threading.Event()    # 我们这一发的完成信号
        with RUNNING_LOCK:
            prev = RUNNING.get(tid)
            RUNNING[tid] = {"cancel": cancel, "finished": finished}
        if prev:
            prev["cancel"].set()
            prev["finished"].wait(timeout=30)   # 上一发把 toolhub.close() 走完再进

        seq = 0
        closed = False
        write_lock = threading.Lock()
        last_emit = {"type": "open", "at": started}
        # delta 合帧：50ms 窗口内的 delta 累积成一个大 delta 事件，避免每 token 一帧 →
        # 前端 React 重渲染 + ReactMarkdown 逐帧解析 → 长回答卡顿。
        delta_buf = {"text": "", "step": None, "since": 0.0}
        DELTA_WINDOW_MS = 50
        # 超长 tool_result 截断阈值：只发前 2KB 给前端；全文本已在 threads 存档里，
        # 需要看全文的话 UI 从 /api/threads/:id 拉。省带宽 + 前端 state 不吃满。
        MAX_TOOL_RESULT_BYTES = 2048

        def _write_frame(payload):
            nonlocal seq
            seq += 1
            payload["seq"] = seq
            now_ms = int(time.time() * 1000)
            payload["ts"] = now_ms
            payload["elapsed_ms"] = int((time.time() - started) * 1000)
            event_name = str(payload.get("type") or "event").replace("\n", "_")
            frame = "id: %d\nevent: %s\ndata: %s\n\n" % (
                seq, event_name, json.dumps(payload, ensure_ascii=False))
            self.wfile.write(frame.encode("utf-8"))
            self.wfile.flush()

        def _flush_delta_locked():
            """在 write_lock 内调用：把 buffer 里累积的 delta 拍平发一个大帧。"""
            if not delta_buf["text"]:
                return
            _write_frame({"type": "delta", "text": delta_buf["text"],
                          "step": delta_buf["step"], "coalesced": True})
            last_emit["type"] = "delta"; last_emit["at"] = time.time()
            delta_buf["text"] = ""; delta_buf["step"] = None; delta_buf["since"] = 0.0

        def emit(e, record=True):
            nonlocal seq, closed
            if record and (closed or cancel.is_set()):
                raise TurnCancelled()
            now = time.time()
            payload = dict(e or {})
            payload.setdefault("type", "event")
            etype = payload.get("type")
            # 截超长 tool_result：全文在存档，SSE 帧和前端 state 都不必扛
            if etype == "tool_result":
                c = payload.get("content") or ""
                if len(c) > MAX_TOOL_RESULT_BYTES:
                    payload["content"] = c[:MAX_TOOL_RESULT_BYTES]
                    payload["truncated"] = True
                    payload["original_chars"] = len(c)
            try:
                with write_lock:
                    if closed:
                        return
                    # delta 累积：只有满窗（≥50ms）才 flush，其他类型事件到来时也强制 flush 保序
                    if etype == "delta":
                        if delta_buf["since"] == 0.0:
                            delta_buf["since"] = now
                            delta_buf["step"] = payload.get("step")
                        delta_buf["text"] += payload.get("text") or ""
                        if (now - delta_buf["since"]) * 1000 >= DELTA_WINDOW_MS:
                            _flush_delta_locked()
                        return
                    # 非 delta：先把 buffer 里的 delta 吐出去（保持事件顺序），再发本事件
                    _flush_delta_locked()
                    _write_frame(payload)
                    if record:
                        last_emit["type"] = etype
                        last_emit["at"] = now
            except (BrokenPipeError, OSError, ValueError):
                closed = True

        def force_flush_deltas():
            """回合结束前调用：把最后一小段还没到 50ms 的 delta 吐掉。"""
            try:
                with write_lock:
                    if not closed:
                        _flush_delta_locked()
            except (BrokenPipeError, OSError, ValueError):
                pass

        def heartbeat():
            # record=False 的 heartbeat 不会抛 TurnCancelled，只把心跳丢给对端；
            # 一旦 closed=True，就跟着退出，绝不写已关闭的 socket。
            while not closed and not cancel.is_set():
                for _ in range(50):                     # 分片睡，取消响应更快
                    if closed or cancel.is_set():
                        return
                    time.sleep(0.1)
                idle_ms = int((time.time() - last_emit["at"]) * 1000)
                try:
                    emit({"type": "heartbeat", "idle_ms": idle_ms,
                          "last_event": last_emit["type"]}, record=False)
                except TurnCancelled:
                    return

        hb = threading.Thread(target=heartbeat, daemon=True)
        hb.start()
        try:
            emit({"type": "sse_open", "phase": "connected", "message": "SSE 已连接"})
        except TurnCancelled:
            pass

        def permission(call):
            needs_confirmation, risk = TOOL_POLICY.requires_confirmation(
                call.name, call.arguments, trust=bypass)
            if not needs_confirmation:
                return True
            if closed or cancel.is_set():        # 断线后不再发 permission_request
                return False
            pid = uuid.uuid4().hex[:12]
            ev = threading.Event()
            PENDING[pid] = {"event": ev, "result": False}
            try:
                emit({"type": "permission_request", "id": pid,
                      "name": call.name, "arguments": call.arguments,
                      "risk": risk})
            except TurnCancelled:
                PENDING.pop(pid, None); raise
            outcome = "timeout"                   # 300s 都没点 → 认作 timeout
            for _ in range(300):                  # 每秒查一次断线/取消，别死等
                if ev.wait(1):
                    entry = PENDING.pop(pid, {})
                    outcome = "allow" if entry.get("result", False) else "deny"
                    break
                if closed or cancel.is_set():
                    PENDING.pop(pid, None)
                    outcome = "disconnected"
                    break
            else:
                PENDING.pop(pid, None)
            # 发个 permission_result 让前端锁死卡片状态（超时/断线后不再让用户点击）
            try:
                emit({"type": "permission_result", "id": pid, "outcome": outcome},
                     record=False)
            except TurnCancelled:
                pass
            return outcome == "allow"

        emit({"type": "thread", "id": tid})
        cancelled_by_client = False
        try:
            runner.run_turn(goal, provider=provider, on_event=emit,
                            thread_id=tid, permission=permission)
        except TurnCancelled:
            cancelled_by_client = True
        except Exception as e:  # noqa: BLE001
            try: emit({"type": "error", "message": str(e)})
            except TurnCancelled: pass
        force_flush_deltas()   # 把窗未满的尾巴吐掉，别让最后几个 token 卡住
        # 未发过 done 就没成功；断线时对端读不到也无所谓，但顺路发一发。
        try:
            emit({"type": "done", "cancelled": cancelled_by_client}, record=False)
        except TurnCancelled:
            pass
        closed = True
        finished.set()
        with RUNNING_LOCK:
            if RUNNING.get(tid, {}).get("finished") is finished:
                RUNNING.pop(tid, None)


def _write_startup_error(msg):
    """Tauri 壳会在 wait_port 超时后读这个文件展示给用户,避免 45s 静默空窗。"""
    try:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "PrismMotif", "logs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "startup_error.txt"), "w", encoding="utf-8") as f:
            f.write(msg)
    except OSError:
        pass


def main():
    port = int(os.environ.get("PRISM_PORT", "8770"))
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        msg = ("启动失败：本轮分配的本地端口 %d 被占用。\n"
               "可能有其它进程在启动竞态中抢占了该端口；重新启动 Prism Motif 会分配新端口。\n\n"
               "原始错误:%s" % (port, e))
        print(msg)
        _write_startup_error(msg)
        return
    print("Prism Motif Gateway 已启动：http://127.0.0.1:%d  (Ctrl+C 退出)" % port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()
