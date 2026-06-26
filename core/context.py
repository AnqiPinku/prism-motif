"""装配系统提示：base → 常驻技能（full，整段）→ 按需技能（lazy）清单 → 相关记忆。"""


def build_system_prompt(enabled_skills, memories, base=""):
    """把启用的技能与召回的记忆拼成系统提示字符串。"""
    parts = []
    if base:
        parts.append(base.strip())

    full = [s for s in enabled_skills if s.disclosure == "full"]
    lazy = [s for s in enabled_skills if s.disclosure != "full"]

    for s in full:
        if s.body.strip():
            parts.append(s.body.strip())

    if lazy:
        lines = ["可用技能（需要时我会参考其要点）："]
        for s in lazy:
            first = (s.body.strip().splitlines() or [""])[0]
            lines.append("- %s：%s" % (s.name, first))
        parts.append("\n".join(lines))

    if memories:
        parts.append("相关记忆：\n" + "\n".join("- %s" % m for m in memories))

    return "\n\n".join(p for p in parts if p)
