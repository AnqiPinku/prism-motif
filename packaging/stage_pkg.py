"""P5b step 1: 打包前净化 + 分级 stage 目录。

把要发布的干净副本组装到 build/pkg/,并写一份 MANIFEST 让人肉眼可见:
什么进了、什么没进。运行:python packaging/stage_pkg.py

净化策略:
- **进 exe(会分发)**:
  - gateway/、core/ 代码(不含 __pycache__)
  - web/ 前端构建产物
  - config/ 三份模板(设过默认值/清空临时字段)
  - data/skills/ 内置 10 个 skill 目录(不含 _enabled.json)
- **不进 exe(用户私人数据)**:
  - data/threads/、data/memory/、data/tmp/(历史对话/记忆/缓存)
  - numba-cache/(perception JIT 缓存,首启动重建)
  - config/secrets.json(所有 API key 都在 Windows keyring)
  - _enabled.json 等运行时状态

**API keys 在 Windows Credential Manager,是操作系统级别的,和 exe 完全分离**——绝对不会被打包。
"""
import json
import os
import shutil
import sys
from pathlib import Path

# stdout 在 Windows GBK 控制台里遇到勾号会崩,先切 utf-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent          # prism-motif/
STAGE = ROOT / "build" / "pkg"


def clean_stage():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)


def copy_tree_no_pyc(src, dst):
    """拷贝目录树,跳过 __pycache__ / .pyc / 常见构建/缓存副产物。"""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".pytest_cache", ".mypy_cache",
        "node_modules", ".git", ".DS_Store",
    ))


def stage_code():
    """gateway + core 代码原样(去 __pycache__)。"""
    copy_tree_no_pyc(ROOT / "gateway", STAGE / "gateway")
    copy_tree_no_pyc(ROOT / "core", STAGE / "core")


def stage_web():
    """前端构建产物(需要先跑 npm run build)。"""
    if (ROOT / "web" / "index.html").is_file():
        copy_tree_no_pyc(ROOT / "web", STAGE / "web")
    else:
        print("⚠ 前端未构建 —— 请先在 frontend/ 里跑 npm run build",
              file=sys.stderr)


def stage_config():
    """三份 config,净化后拷贝。"""
    dst_cfg = STAGE / "config"
    dst_cfg.mkdir()

    # settings.json 里净化"当前状态"字段,保留模板性字段
    settings = _load(ROOT / "config" / "settings.json")
    settings["workspace"] = "default"                  # 用户第一次跑是 default
    settings.pop("archived_workspaces", None)           # 你的归档项目名不带走
    # base_prompt / max_steps / retry / context / tool_timeout_s 全都保留(产品默认值)
    _dump(dst_cfg / "settings.json", settings)

    # modes.json 里 current 重置成 "" (默认无 mode)
    modes = _load(ROOT / "config" / "modes.json")
    modes["current"] = ""
    _dump(dst_cfg / "modes.json", modes)

    # mcp_servers 用打包版:perception 指向冻结 exe,reaper/system 用 python → bundled CPython
    pkg_mcp = ROOT / "config" / "mcp_servers.packaged.json"
    if pkg_mcp.exists():
        shutil.copy2(pkg_mcp, dst_cfg / "mcp_servers.json")
    else:
        shutil.copy2(ROOT / "config" / "mcp_servers.json", dst_cfg / "mcp_servers.json")

    # 其余 config/*.json(providers.json 等)按原样拷 —— 内容不需要净化,拿不到 key 名就没
    # 意义。用通用循环兜底:未来新加的模板文件默认也进包,不用再改这个函数。黑名单排除已
    # 由上面处理过的 3 份 + 绝不进包的 secrets.json + 打包临时件。
    handled = {"settings.json", "modes.json", "mcp_servers.json",
               "mcp_servers.packaged.json", "secrets.json"}
    for f in (ROOT / "config").iterdir():
        if f.is_file() and f.suffix == ".json" and f.name not in handled:
            shutil.copy2(f, dst_cfg / f.name)

    # 绝不带 secrets.json —— 所有 key 都在 Windows keyring
    if (ROOT / "config" / "secrets.json").exists():
        print("⚠ 检测到 config/secrets.json —— 已跳过不打包(所有 API key 在 keyring)",
              file=sys.stderr)

    # 断言:providers.json 必须进 stage;没这份文件 UI 会渲染成空胶囊、发消息也炸。
    # 让漏配置在 stage 阶段就失败,别拖到装完 MSI 启动才发现。
    staged_providers = dst_cfg / "providers.json"
    if not staged_providers.is_file():
        raise RuntimeError(
            f"stage 后 {staged_providers} 不存在。源 config/providers.json 缺失?"
            "  没这份 gateway 三条读路径都会静默回落到空 providers,UI 无胶囊、发消息炸。"
        )


def stage_mcps():
    """把 3 个 MCP 仓的**代码部分**拷到 build/mcps/,踢掉 .git/README/构建产物。
    tauri.conf.json 里 resources 指向这里,避免把 .git 打进安装包。"""
    dst_root = ROOT / "build" / "mcps"
    if dst_root.exists():
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True)
    mcps_root = ROOT.parent / "mcps"
    # reaper-mcp: 只要 server/ bridge/ installer/
    for sub in ("server", "bridge", "installer"):
        src = mcps_root / "reaper-mcp" / sub
        if src.is_dir():
            copy_tree_no_pyc(src, dst_root / "reaper-mcp" / sub)
    # system-mcp: 单文件 server.py 就够
    src = mcps_root / "system-mcp"
    if src.is_dir():
        (dst_root / "system-mcp").mkdir()
        for f in src.iterdir():
            if f.is_file() and f.suffix == ".py":
                shutil.copy2(f, dst_root / "system-mcp" / f.name)
    # music-perception 用冻结产物,不 stage 源码


def stage_skills():
    """data/skills/ 的所有 skill 目录(不含 _enabled.json)。"""
    src = ROOT / "data" / "skills"
    dst = STAGE / "data" / "skills"
    dst.mkdir(parents=True)
    for entry in sorted(src.iterdir()):
        if entry.is_dir():
            copy_tree_no_pyc(entry, dst / entry.name)
    # 明确不带 _enabled.json —— 那是用户的当前勾选状态,应由 mode 切换在运行时管理


def write_manifest():
    """遍历 STAGE 输出清单,统计大小。"""
    lines = ["# Prism Motif 打包清单(build/pkg/ 内容)",
             "# 生成: python packaging/stage_pkg.py",
             "# 这些文件将进入 exe;其余(threads/memory/keys/...)绝不进入。", ""]
    total = 0
    for path in sorted(STAGE.rglob("*")):
        if path.is_file():
            size = path.stat().st_size
            total += size
            rel = path.relative_to(STAGE).as_posix()
            lines.append(f"  {size:>10,}  {rel}")
    lines.append("")
    lines.append(f"# 总计 {total:,} 字节 ({total/1024/1024:.1f} MB)")
    (STAGE / "MANIFEST.txt").write_text("\n".join(lines), encoding="utf-8")
    return total


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _dump(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    print(f"stage → {STAGE}")
    clean_stage()
    stage_code()
    stage_web()
    stage_config()
    stage_skills()
    stage_mcps()
    total = write_manifest()
    print(f"✓ 完成:{total/1024/1024:.1f} MB, MANIFEST 在 {STAGE / 'MANIFEST.txt'}")


if __name__ == "__main__":
    main()
