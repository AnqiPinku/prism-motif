"""Prism Core 本地 Gateway：用标准库 http.server 提供前端静态文件 + JSON 接口 + SSE 聊天流。
启动：python gateway/server.py  然后浏览器开 http://127.0.0.1:8770"""
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

WEB = ROOT / "web"                                       # 静态资源随代码走，只读即可
CONFIG = paths.CONFIG_DIR                                # 可写状态：per-user 目录（发布）/ 就地（开发）
DATA = paths.DATA_DIR

CTYPES = {".html": "text/html", ".js": "application/javascript",
          ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml"}

# 需要用户确认的危险工具（写/删/执行）
DANGEROUS = {"run_command", "write_file", "edit_file", "move_path", "delete_path"}
# 待确认的权限请求：id -> {"event": Event, "result": bool}
PENDING = {}


def load_json(p, d):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # ---------- GET ----------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", ""):
            return self._serve("index.html")
        if path == "/api/state":
            return self._json(self._state())
        if path == "/api/workspaces":
            return self._json({"current": runner.current_workspace(),
                               "names": runner.list_workspaces()})
        if path == "/api/settings":
            return self._json(self._settings_get())
        if path == "/api/mcp/tools":
            q = parse_qs(urlparse(self.path).query)
            return self._json(self._mcp_tools((q.get("name") or [""])[0]))
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
        if path == "/api/threads/delete":
            threads_mod.delete_thread(str(DATA / "threads"), body.get("id", ""))
            return self._json({"ok": True})
        if path == "/api/threads/rename":
            threads_mod.rename_thread(str(DATA / "threads"), body.get("id", ""), body.get("title", ""))
            return self._json({"ok": True})
        if path == "/api/permission":
            entry = PENDING.get(body.get("id"))
            if entry:
                entry["result"] = bool(body.get("allow"))
                entry["event"].set()
            return self._json({"ok": True})
        if path in ("/api/workspace/switch", "/api/workspace/create"):
            return self._json(self._ws_set(body.get("name")))
        if path == "/api/workspace/rename":
            return self._json(self._ws_call(runner.rename_workspace,
                                            body.get("old"), body.get("new")))
        if path == "/api/workspace/delete":
            return self._json(self._ws_call(runner.delete_workspace, body.get("name")))
        return self._json({"error": "not found"}, 404)

    # ---------- helpers ----------
    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            return {}

    def _send(self, code, data, ctype):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _serve(self, rel):
        target = (WEB / rel).resolve()
        if not str(target).startswith(str(WEB.resolve())) or not target.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = CTYPES.get(target.suffix, "application/octet-stream")
        if ctype.startswith(("text/", "application/javascript", "application/json")):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def _state(self):
        prov = load_json(CONFIG / "providers.json", {"default": "deepseek", "providers": {}})
        mcp = load_json(CONFIG / "mcp_servers.json", {"servers": []})
        en = load_enabled_map(str(DATA / "skills"))
        skills = [{"name": s.name, "disclosure": s.disclosure, "tags": s.tags,
                   "enabled": en.get(s.name, True)}
                  for s in load_skills(str(DATA / "skills"))]
        fb = (load_json(CONFIG / "settings.json", {}).get("context") or {}).get("window_tokens", 128000)
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
                          "names": runner.list_workspaces()},
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
        if body.get("default"):
            prov["default"] = body["default"]
        name = body.get("provider")
        providers = prov.get("providers", {})
        if name and name in providers:
            if "base_url" in body:
                providers[name]["base_url"] = body["base_url"]
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
            g = body.get("gemini") or {}
            updates = {}
            if "base_url" in g:
                updates["GEMINI_BASE_URL"] = g["base_url"]
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

    def _ws_set(self, name):
        try:
            cur = runner.set_workspace(name)
            return {"ok": True, "current": cur, "names": runner.list_workspaces()}
        except Exception as e:  # noqa: BLE001 含非法名(ValueError)与写盘/建目录失败(OSError)
            return {"error": str(e)}

    def _ws_call(self, fn, *args):
        try:
            fn(*args)
            return {"ok": True, "current": runner.current_workspace(),
                    "names": runner.list_workspaces()}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def _chat(self, body):
        goal = body.get("goal", "")
        provider = body.get("provider") or None
        thread_id = body.get("thread_id") or None
        bypass = bool(body.get("bypass"))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(e):
            try:
                self.wfile.write(("data: " + json.dumps(e, ensure_ascii=False) + "\n\n").encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, OSError):
                pass

        def permission(call):
            # 安全工具直接放行；危险工具在“绕过”关闭时弹确认并阻塞等待用户决定
            if bypass or call.name not in DANGEROUS:
                return True
            pid = uuid.uuid4().hex[:12]
            ev = threading.Event()
            PENDING[pid] = {"event": ev, "result": False}
            emit({"type": "permission_request", "id": pid,
                  "name": call.name, "arguments": call.arguments})
            ev.wait(timeout=300)
            return PENDING.pop(pid, {}).get("result", False)

        tid = thread_id or time.strftime("%Y%m%d-%H%M%S")
        emit({"type": "thread", "id": tid})
        try:
            runner.run_turn(goal, provider=provider, on_event=emit,
                            thread_id=tid, permission=permission)
        except Exception as e:  # noqa: BLE001
            emit({"type": "error", "message": str(e)})
        emit({"type": "done"})


def main():
    port = int(os.environ.get("PRISM_PORT", "8770"))
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        print("启动失败：端口 %d 被占用（可能已有一个 Prism Core 在运行）。" % port)
        print("换个端口再启动：先 set PRISM_PORT=8771，再 python gateway/server.py")
        print("（原始错误：%s）" % e)
        return
    print("Prism Core 前端已启动：http://127.0.0.1:%d  (Ctrl+C 退出)" % port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()
