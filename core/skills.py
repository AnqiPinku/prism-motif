"""技能库：读/增/删 用户技能（data/skills/*.md）。人格 = disclosure==full 的技能。
frontmatter 极简、手解析、零依赖。"""
import os
import json
from dataclasses import dataclass


@dataclass
class Skill:
    name: str
    disclosure: str        # "full" | "lazy"
    tags: list
    body: str
    path: str
    mode: str = "general"  # "composition" | "arrangement" | "mix" | "general" — 三模块工作流按此过滤


def _parse(text, path):
    name = os.path.splitext(os.path.basename(path))[0]
    disclosure = "lazy"
    tags = []
    mode = "general"
    body = text.strip()
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        meta, i = [], 1
        while i < len(lines) and lines[i].strip() != "---":
            meta.append(lines[i])
            i += 1
        body = "\n".join(lines[i + 1:]).strip()
        for ml in meta:
            if ":" not in ml:
                continue
            k, v = ml.split(":", 1)
            k, v = k.strip(), v.strip()
            if k == "name":
                name = v or name
            elif k == "disclosure":
                disclosure = v or "lazy"
            elif k == "tags":
                v = v.strip().lstrip("[").rstrip("]")
                tags = [x.strip() for x in v.split(",") if x.strip()]
            elif k == "mode":
                mode = v or "general"
    return Skill(name=name, disclosure=disclosure, tags=tags, body=body, path=path, mode=mode)


def load_skills(skills_dir):
    """读取目录下的技能。两种形态：
      · 扁平：data/skills/<name>.md
      · 文件夹：data/skills/<name>/SKILL.md（可带 references/ scripts/ 等附件）
    目录不存在则返回空列表。"""
    out = []
    if not os.path.isdir(skills_dir):
        return out
    for fn in sorted(os.listdir(skills_dir)):
        p = os.path.join(skills_dir, fn)
        if fn.endswith(".md") and os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                out.append(_parse(f.read(), p))
        elif os.path.isdir(p):
            skill_md = os.path.join(p, "SKILL.md")
            if os.path.isfile(skill_md):
                with open(skill_md, "r", encoding="utf-8") as f:
                    out.append(_parse(f.read(), skill_md))
    return out


def add_skill(skills_dir, name, body, disclosure="lazy", tags=None):
    """新增一个技能文件。"""
    os.makedirs(skills_dir, exist_ok=True)
    tags = tags or []
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or "skill"
    path = os.path.join(skills_dir, safe + ".md")
    text = "---\nname: %s\ndisclosure: %s\ntags: [%s]\n---\n%s\n" % (
        name, disclosure, ", ".join(tags), body)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return _parse(text, path)


def delete_skill(skills_dir, name):
    """按技能 name 删除对应文件。"""
    for sk in load_skills(skills_dir):
        if sk.name == name:
            os.remove(sk.path)
            return True
    return False


# ---- 启用状态（哪些技能当前生效，存 data/skills/_enabled.json）----
def _enabled_path(skills_dir):
    return os.path.join(skills_dir, "_enabled.json")


def load_enabled_map(skills_dir):
    """返回 {技能名: bool}；未记录的技能默认视为启用。"""
    try:
        with open(_enabled_path(skills_dir), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def set_enabled(skills_dir, name, enabled):
    """设置某技能是否启用。"""
    os.makedirs(skills_dir, exist_ok=True)
    m = load_enabled_map(skills_dir)
    m[name] = bool(enabled)
    with open(_enabled_path(skills_dir), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)


def enabled_skills(skills_dir):
    """只返回当前启用的技能（默认启用）。"""
    m = load_enabled_map(skills_dir)
    return [s for s in load_skills(skills_dir) if m.get(s.name, True)]
