"""命令行入口：python run.py "目标" [--provider 名字]"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.runner import run_once  # noqa: E402


def _fmt(args):
    try:
        s = json.dumps(args, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        s = str(args)
    return s if len(s) <= 80 else s[:80] + "…"


def on_event(e):
    t = e.get("type")
    if t == "tool_call":
        print("  → 调用 %s(%s)" % (e["name"], _fmt(e.get("arguments"))), flush=True)
    elif t == "tool_result":
        mark = "✗" if e.get("is_error") else "✓"
        text = (e.get("content") or "").strip().replace("\n", " ")
        if len(text) > 120:
            text = text[:120] + "…"
        print("  %s %s" % (mark, text), flush=True)
    elif t == "final":
        print("\n" + (e.get("text") or ""), flush=True)


def main():
    ap = argparse.ArgumentParser(description="Prism Core")
    ap.add_argument("goal", help="给 agent 的目标（自然语言）")
    ap.add_argument("--provider", default=None, help="覆盖默认大脑（见 config/providers.json）")
    args = ap.parse_args()
    try:
        run_once(args.goal, provider=args.provider, on_event=on_event)
    except Exception as e:  # noqa: BLE001
        print("出错: %s" % e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
