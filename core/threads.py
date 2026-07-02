"""线程记录：把一次对话存成 json，可列出 / 读取 / 还原。"""
import os
import json
import time

from .contracts import Message, ToolCall


def _serialize(messages):
    out = []
    for m in messages:
        d = {"role": m.role, "content": m.content}
        if m.tool_call_id:
            d["tool_call_id"] = m.tool_call_id
        if m.tool_calls:
            d["tool_calls"] = [{"id": c.id, "name": c.name, "arguments": c.arguments}
                               for c in m.tool_calls]
        out.append(d)
    return out


def save_thread(threads_dir, thread_id, config, messages):
    """保存一条对话线程。已有的自定义标题和归档状态会被保留。"""
    os.makedirs(threads_dir, exist_ok=True)
    path = os.path.join(threads_dir, thread_id + ".json")
    title, archived = "", False
    if os.path.exists(path):                      # 保留已有标题（含用户重命名的）+ 归档状态
        try:
            with open(path, "r", encoding="utf-8") as f:
                old = json.load(f)
            title = old.get("title", "") or ""
            archived = bool(old.get("archived"))
        except (OSError, ValueError):
            title = ""
    if not title:
        for m in messages:
            if m.role == "user" and isinstance(m.content, str):
                # 附件行（[音频文件: 路径]）不进标题，只取用户真正说的话
                lines = [ln for ln in m.content.splitlines()
                         if ln.strip() and not ln.startswith("[音频文件:")]
                text = " ".join(lines).strip()
                if text:
                    title = text[:30]
                    break
        if not title:
            title = "音频对话"
    data = {"id": thread_id, "title": title, "archived": archived,
            "mtime": int(time.time()),
            "config": config, "messages": _serialize(messages)}
    # 原子写：僵尸回合和当前回合并发写时不会互相截断，读端不会读到半截 JSON
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _stable_mtime(path, data):
    try:
        return int(data.get("mtime") or os.path.getmtime(path))
    except (OSError, TypeError, ValueError):
        return int(time.time())


def _write_metadata(path, data, mtime):
    data["mtime"] = int(mtime)
    try:
        atime = os.path.getatime(path)
    except OSError:
        atime = time.time()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        os.utime(path, (atime, int(mtime)))
    except OSError:
        pass


def rename_thread(threads_dir, thread_id, title):
    """给线程设置自定义标题。"""
    path = os.path.join(threads_dir, thread_id + ".json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return False
    mtime = _stable_mtime(path, d)
    d["title"] = title
    _write_metadata(path, d, mtime)
    return True


def retag_workspace(threads_dir, old, new):
    """工作区改名/删除时同步线程归属（config.workspace），避免侧栏出现孤儿线程。"""
    if not os.path.isdir(threads_dir) or old == new:
        return 0
    n = 0
    for fn in os.listdir(threads_dir):
        if not fn.endswith(".json"):
            continue
        p = os.path.join(threads_dir, fn)
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            cfg = d.get("config") or {}
            if (cfg.get("workspace") or "default") == old:
                mtime = _stable_mtime(p, d)
                cfg["workspace"] = new
                d["config"] = cfg
                _write_metadata(p, d, mtime)
                n += 1
        except (OSError, ValueError):
            pass
    return n


def set_archived(threads_dir, thread_id, archived):
    """归档/取消归档一条线程（收进侧栏底部的折叠区，不删数据）。"""
    path = os.path.join(threads_dir, thread_id + ".json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return False
    mtime = _stable_mtime(path, d)
    d["archived"] = bool(archived)
    _write_metadata(path, d, mtime)
    return True


def delete_thread(threads_dir, thread_id):
    """删除一条线程。"""
    try:
        os.remove(os.path.join(threads_dir, thread_id + ".json"))
        return True
    except OSError:
        return False


def load_thread(threads_dir, thread_id):
    with open(os.path.join(threads_dir, thread_id + ".json"), "r", encoding="utf-8") as f:
        return json.load(f)


def deserialize(dicts):
    """把存档里的消息 dict 还原成 Message 列表（含 tool_calls）。"""
    out = []
    for d in dicts or []:
        tcs = None
        if d.get("tool_calls"):
            tcs = [ToolCall(id=c.get("id"), name=c.get("name"),
                            arguments=c.get("arguments") or {}) for c in d["tool_calls"]]
        out.append(Message(role=d.get("role"), content=d.get("content"),
                           tool_call_id=d.get("tool_call_id"), tool_calls=tcs))
    return out


def list_threads(threads_dir):
    out = []
    if not os.path.isdir(threads_dir):
        return out
    for fn in sorted(os.listdir(threads_dir)):
        if fn.endswith(".json"):
            p = os.path.join(threads_dir, fn)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                out.append({
                    "id": d.get("id"), "title": d.get("title", ""),
                    "archived": bool(d.get("archived")),
                    "workspace": (d.get("config") or {}).get("workspace") or "default",
                    "mtime": _stable_mtime(p, d),   # 侧栏相对时间用：最后一次对话内容更新时间
                })
            except (OSError, ValueError):
                pass
    return out
