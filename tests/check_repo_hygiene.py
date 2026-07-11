"""仓库卫生门禁：密钥、私有绝对路径、大文件 / 音频、打包配置与发布元数据一致性。

在仓库根目录运行：python tests/check_repo_hygiene.py
只检查 git 跟踪的文件；违规逐条打印，存在任何一条即以退出码 1 失败。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Windows GBK 控制台打印中文/符号会崩，切 utf-8（与 stage_pkg.py 一致）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
SELF = "tests/check_repo_hygiene.py"

# 有意保留的例外（防新增泄漏，不追溯已知且无害的旧例）：
# - core/paths.py 的 docstring 描述本机默认目录布局；
# - lib.rs 的 dev 回退路径只在 bundled resources 缺失（cargo run 开发态）时使用，
#   打包版永远命中 resources/python 分支。
PRIVATE_PATH_ALLOWLIST = {
    "core/paths.py",
    "frontend/src-tauri/src/lib.rs",
}

SECRET_PATTERNS = [
    ("openai-style key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("google api key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("github token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("slack token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
PRIVATE_PATH = re.compile(r"[A-Za-z]:[\\/](?:Users|Prismcode|Python310|科广)")
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".aif", ".aiff", ".ogg", ".m4a"}
BINARY_EXTENSIONS = {".png", ".ico", ".icns", ".jpg", ".jpeg", ".gif", ".woff", ".woff2"}
MAX_FILE_BYTES = 2_000_000
REPOSITORY_URL = "https://github.com/AnqiPinku/prism-motif"


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True,
    )
    return [x for x in out.stdout.decode("utf-8").split("\0") if x]


def check_files(problems: list[str]) -> None:
    for rel in tracked_files():
        path = ROOT / rel
        if not path.is_file():
            continue
        size = path.stat().st_size
        suffix = path.suffix.lower()
        if suffix in AUDIO_EXTENSIONS:
            problems.append(f"{rel}: 音频文件不得进仓（{size:,} 字节）")
            continue
        if size > MAX_FILE_BYTES:
            problems.append(f"{rel}: 超过 {MAX_FILE_BYTES:,} 字节上限（{size:,} 字节）")
        if suffix in BINARY_EXTENSIONS or rel == SELF:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in SECRET_PATTERNS:
            found = pattern.search(text)
            if found:
                problems.append(f"{rel}: 疑似密钥（{label}）: {found.group()[:16]}…")
        if suffix != ".md" and rel not in PRIVATE_PATH_ALLOWLIST:
            found = PRIVATE_PATH.search(text)
            if found:
                problems.append(f"{rel}: 私有绝对路径: {found.group()}")


def check_packaged_config(problems: list[str]) -> None:
    packaged = json.loads((ROOT / "config" / "mcp_servers.packaged.json").read_text("utf-8"))
    names = {server.get("name", "") for server in packaged.get("servers", [])}
    if any("system" in name for name in names):
        problems.append(f"config/mcp_servers.packaged.json: 正式包配置含 system MCP: {sorted(names)}")
    tauri_text = (ROOT / "frontend" / "src-tauri" / "tauri.conf.json").read_text("utf-8")
    if "system-mcp" in tauri_text:
        problems.append("tauri.conf.json: 打包 resources 引用了 system-mcp")


def check_metadata(problems: list[str]) -> None:
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text("utf-8"))
    tauri = json.loads((ROOT / "frontend" / "src-tauri" / "tauri.conf.json").read_text("utf-8"))
    cargo_text = (ROOT / "frontend" / "src-tauri" / "Cargo.toml").read_text("utf-8")

    versions = {
        "frontend/package.json": pkg.get("version"),
        "tauri.conf.json": tauri.get("version"),
    }
    cargo_version = re.search(r'^version\s*=\s*"([^"]+)"', cargo_text, re.MULTILINE)
    versions["Cargo.toml"] = cargo_version.group(1) if cargo_version else None
    if len(set(versions.values())) != 1:
        problems.append(f"版本号不一致: {versions}")

    license_path = ROOT / "LICENSE"
    if not license_path.is_file() or "MIT" not in license_path.read_text("utf-8")[:200]:
        problems.append("LICENSE 缺失或不是 MIT")
    if not re.search(r'^license\s*=\s*"MIT"', cargo_text, re.MULTILINE):
        problems.append("Cargo.toml: license 不是 MIT")
    repository = re.search(r'^repository\s*=\s*"([^"]*)"', cargo_text, re.MULTILINE)
    if not repository or repository.group(1) != REPOSITORY_URL:
        problems.append(
            f"Cargo.toml: repository 应为 {REPOSITORY_URL}，"
            f"当前 {repository.group(1) if repository else '(缺失)'}"
        )


def main() -> int:
    problems: list[str] = []
    check_files(problems)
    check_packaged_config(problems)
    check_metadata(problems)
    if problems:
        print(f"仓库卫生检查失败，共 {len(problems)} 条：")
        for item in problems:
            print(f"  ✗ {item}")
        return 1
    print("仓库卫生检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
