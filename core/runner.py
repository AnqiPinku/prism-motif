"""装配 + 跑一个会话：读配置 → 造模型/工具/记忆/技能 → AgentLoop → 存线程。"""
import os
import json
import time
import shutil
from pathlib import Path

from .contracts import Message
from .reasoners.openai_compat import OpenAICompatReasoner
from .tools import ToolHub
from .skills import enabled_skills
from .context import build_system_prompt
from .memory import build_memory
from .loop import AgentLoop
from .compaction import CompactingReasoner, estimate_tokens
from . import threads as threads_mod

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"

# 中性最小底座：不预设身份/领域，干净。身份交给用户启用的人格技能。
# 可在 config/settings.json 的 "base_prompt" 覆盖，设为 "" 则完全无底座。
# 默认无底座：身份与行为完全交给用户启用的人格技能。
# 想要一个全局底座，在 config/settings.json 的 "base_prompt" 填内容即可。
DEFAULT_BASE_PROMPT = ""


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _settings():
    return _load_json(CONFIG / "settings.json", {"max_steps": 64, "request_timeout_s": 120})


def build_reasoner(provider=None):
    """按 providers.json 造模型，返回 (reasoner, provider_name)。"""
    cfg = _load_json(CONFIG / "providers.json", {"default": "deepseek", "providers": {}})
    name = provider or cfg.get("default")
    p = cfg.get("providers", {}).get(name)
    if not p:
        raise RuntimeError("未找到 provider: %s（检查 config/providers.json）" % name)
    if p.get("type") == "mock":
        from .reasoners.mock import MockReasoner
        return MockReasoner(), name
    # key 解析优先级：UI 存的 secrets.json → 环境变量
    secrets = _load_json(CONFIG / "secrets.json", {})
    api_key = secrets.get(name) or os.environ.get(p.get("api_key_env", ""), "")
    reasoner = OpenAICompatReasoner(
        p["base_url"], p["model"], api_key,
        timeout=_settings().get("request_timeout_s", 120))
    return reasoner, name


def _provider_window(provider_name):
    """取该模型的上下文预算 window_tokens（providers.json 每模型一个）；未配则用 settings 兜底。"""
    cfg = _load_json(CONFIG / "providers.json", {"default": "deepseek", "providers": {}})
    p = (cfg.get("providers", {}) or {}).get(provider_name or cfg.get("default")) or {}
    fallback = (_settings().get("context") or {}).get("window_tokens", 128000)
    return p.get("window_tokens") or fallback


def _memory_base_dir():
    """记忆库根目录（工作区子目录的父级），来自 memory.json，默认 data/memory。"""
    cfg = _load_json(CONFIG / "memory.json",
                     {"backend": "json", "options": {"dir": "data/memory"}})
    d = (cfg.get("options") or {}).get("dir", "data/memory")
    return d if os.path.isabs(d) else str(ROOT / d)


def _build_memory(workspace="default"):
    """按当前工作区造记忆后端：记忆落在 data/memory/<workspace>/，按领域隔离、互不污染。"""
    cfg = _load_json(CONFIG / "memory.json",
                     {"backend": "json", "options": {"dir": "data/memory"}})
    opts = cfg.setdefault("options", {})
    opts["dir"] = os.path.join(_memory_base_dir(), workspace or "default")
    return build_memory(cfg)


# ---------------- 工作区（= 长期记忆命名空间，领域无关） ----------------
def _save_settings(s):
    (CONFIG / "settings.json").write_text(
        json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_ws(name):
    """校验工作区名：单段、无路径分隔符/盘符/相对段，防目录穿越（含 Windows 的 C: 盘符相对路径）。"""
    name = (name or "").strip()
    bad = ("/", "\\", ":", "..")
    if not name or name in (".", "..") or any(b in name for b in bad) or os.sep in name:
        raise ValueError("非法工作区名")
    return name


def current_workspace():
    """当前工作区名（settings.json 的 workspace，默认 default）。"""
    return _settings().get("workspace", "default")


def list_workspaces():
    """列出所有工作区（data/memory 下的子目录 + default + 当前），排序返回。"""
    names = {"default", current_workspace()}
    try:
        base = _memory_base_dir()
        for n in os.listdir(base):
            if os.path.isdir(os.path.join(base, n)):
                names.add(n)
    except OSError:
        pass
    return sorted(names)


def set_workspace(name):
    """切换/新建工作区：写入 settings.workspace 并确保其记忆目录存在。返回工作区名。"""
    name = _safe_ws(name)
    s = _settings()
    s["workspace"] = name
    _save_settings(s)
    os.makedirs(os.path.join(_memory_base_dir(), name), exist_ok=True)
    return name


def rename_workspace(old, new):
    """重命名工作区（移动其记忆目录）；目标名已存在则拒绝（不覆盖、不切换、不产生孤儿）。
    仅在移动成功后，若改的是当前工作区才同步切换——避免静默把 current 指到异域数据集。"""
    old, new = _safe_ws(old), _safe_ws(new)
    if old == new:
        return new
    base = _memory_base_dir()
    src, dst = os.path.join(base, old), os.path.join(base, new)
    if os.path.exists(dst):
        raise ValueError("目标工作区已存在：%s" % new)
    if os.path.isdir(src):
        os.rename(src, dst)
    if current_workspace() == old:
        set_workspace(new)
    return new


def delete_workspace(name):
    """删除工作区及其记忆目录；不允许删 default 或当前工作区（请先切换）。"""
    name = _safe_ws(name)
    if name == "default":
        raise ValueError("不能删除 default 工作区")
    if name == current_workspace():
        raise ValueError("不能删除当前工作区，请先切换到其它工作区")
    p = os.path.join(_memory_base_dir(), name)
    if os.path.isdir(p):
        shutil.rmtree(p)
    return True


def run_turn(goal, provider=None, on_event=None, thread_id=None, permission=None):
    """在一个会话线程内跑一轮：载入该线程的历史 → 追加本轮 → 跑循环 → 存回同一线程。
    返回 (thread_id, final)。同一对话多轮共用一个 thread_id，能记住上下文。"""
    reasoner, provider_name = build_reasoner(provider)

    mcp_cfg = _load_json(CONFIG / "mcp_servers.json", {"servers": []})
    enabled = [s for s in mcp_cfg.get("servers", []) if s.get("enabled", True)]
    toolhub = ToolHub(enabled)
    toolhub.start()

    try:
        settings = _settings()
        workspace = settings.get("workspace", "default")

        # 上下文压缩"透镜"：发给模型的消息做工具结果消隐 + 上报占用，磁盘仍存全本（领域无关）。
        ctx = settings.get("context") or {}
        if ctx.get("enabled"):
            reasoner = CompactingReasoner(
                reasoner,
                window_tokens=_provider_window(provider_name),
                compact_at=ctx.get("compact_at", 0.8),
                keep_recent_turns=ctx.get("keep_recent_turns", 4),
                elide=ctx.get("elide_tool_results", True),
                elide_over_chars=ctx.get("elide_over_chars", 2000),
                on_event=on_event)

        skills = enabled_skills(str(DATA / "skills"))   # 只注入勾选启用的技能
        memory = _build_memory(workspace)
        memories = memory.recall(goal)
        base = settings.get("base_prompt", DEFAULT_BASE_PROMPT)
        system_prompt = build_system_prompt(skills, memories, base=base)

        prior = []
        if thread_id:
            try:
                data = threads_mod.load_thread(str(DATA / "threads"), thread_id)
                prior = threads_mod.deserialize(data.get("messages", []))
            except (OSError, ValueError):
                prior = []
        else:
            thread_id = time.strftime("%Y%m%d-%H%M%S")

        # 系统提示每轮重建；为空则根本不插入 system 消息（纯净，无底座）
        head = [Message(role="system", content=system_prompt)] if system_prompt else []
        messages = head + prior + [Message(role="user", content=goal)]

        loop = AgentLoop(reasoner, toolhub,
                         max_steps=settings.get("max_steps", 64),
                         on_event=on_event, permission=permission)
        final = loop.run(messages)

        # 存档时去掉开头的 system（如果有）
        convo = messages[1:] if (messages and messages[0].role == "system") else messages
        thread_cfg = {"provider": provider_name}
        pt = getattr(reasoner, "last_prompt_tokens", None)
        if pt is not None:                 # 记录本轮真实占用，供切线程时按线程显示圆环
            thread_cfg["context"] = {"prompt_tokens": pt, "window": _provider_window(provider_name)}
        threads_mod.save_thread(str(DATA / "threads"), thread_id, thread_cfg, convo)
        return thread_id, final
    finally:
        toolhub.close()


def run_once(goal, provider=None, on_event=None, thread_id=None):
    """命令行用：跑一轮并返回最终回答（丢弃 thread_id）。"""
    return run_turn(goal, provider=provider, on_event=on_event, thread_id=thread_id)[1]


def thread_context(data):
    """计算一条线程的上下文占用（供切线程时更新圆环）：优先用存档的真实 prompt_tokens，
    否则按消息粗估。返回 {prompt_tokens, window, pct}。"""
    cfg = data.get("config") or {}
    saved = cfg.get("context") or {}
    win = saved.get("window") or _provider_window(cfg.get("provider"))
    pt = saved.get("prompt_tokens")
    if pt is None:
        pt = estimate_tokens(threads_mod.deserialize(data.get("messages", [])))
    return {"prompt_tokens": pt, "window": win, "pct": round(pt / win, 4) if win else 0}
