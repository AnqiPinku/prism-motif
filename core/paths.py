"""运行时路径解析：把"代码/模板在哪"(INSTALL_ROOT) 与 "可写状态在哪"(DATA_ROOT) 分开。

目标：同一套代码既能在源码树里原地跑(开发)，又能装进只读目录、把 config/data 写到
per-user 目录(发布)。桌面壳/启动器负责用环境变量告诉后端可写目录在哪。

- INSTALL_ROOT : music-agent 仓根 —— 随 app 分发的代码 + web/ + 配置模板 + 内置技能。只读。
- PRISM_HOME   : 四个仓的公共父目录(默认 A:/Prismcode)。用于展开 mcp_servers.json 里的
                 "${PRISM_HOME}/.../server.py" 令牌，替掉硬编码盘符路径。启动器可用环境变量覆盖。
- DATA_ROOT    : 可写状态根。优先 PRISM_DATA_DIR；冻结(sys.frozen)时用 per-user OS 目录；
                 否则(源码运行)就地用 INSTALL_ROOT —— 开发行为完全不变。
- CONFIG_DIR / DATA_DIR = DATA_ROOT/config、DATA_ROOT/data。
"""
import os
import sys
import shutil
from pathlib import Path

INSTALL_ROOT = Path(__file__).resolve().parents[1]        # .../music-agent

# 四仓公共父目录：展开 ${PRISM_HOME} 用。写回 os.environ 供 expandvars + 子进程继承。
PRISM_HOME = Path(os.environ.get("PRISM_HOME") or str(INSTALL_ROOT.parent)).resolve()
os.environ["PRISM_HOME"] = str(PRISM_HOME)


def _user_data_root():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(base) / "PrismMusicAgent"
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "share")
    return Path(base) / "prism-music-agent"


def _resolve_data_root():
    override = os.environ.get("PRISM_DATA_DIR")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):                     # 打包冻结 → per-user 可写目录
        return _user_data_root()
    return INSTALL_ROOT                                   # 源码运行 → 就地，开发行为不变


DATA_ROOT = _resolve_data_root()
CONFIG_DIR = DATA_ROOT / "config"
DATA_DIR = DATA_ROOT / "data"


def ensure_seeded():
    """首启把随 app 分发的配置模板 + 内置技能拷进可写目录。
    源码就地运行(DATA_ROOT == INSTALL_ROOT)时是 no-op —— 绝不动开发树。
    只读/权限异常吞掉不 crash 启动；缺文件由各读取点按默认值兜底。"""
    if DATA_ROOT == INSTALL_ROOT:
        return
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        src_cfg = INSTALL_ROOT / "config"
        if src_cfg.is_dir():          # 逐文件补种：更新时新增的模板也补上，且不覆盖用户已改的
            for f in src_cfg.iterdir():
                if f.is_file() and not (CONFIG_DIR / f.name).exists():
                    shutil.copy2(f, CONFIG_DIR / f.name)
        src_skills = INSTALL_ROOT / "data" / "skills"
        dst_skills = DATA_DIR / "skills"
        if src_skills.is_dir() and not dst_skills.exists():
            shutil.copytree(src_skills, dst_skills)
    except OSError:
        pass


def expand(value):
    """展开路径里的 ${PRISM_HOME}（mcp_servers.json 的 server 路径令牌）。
    expandvars 为主，手动替换兜底跨平台差异。非字符串原样返回。"""
    if not isinstance(value, str):
        return value
    return os.path.expandvars(value).replace("${PRISM_HOME}", str(PRISM_HOME))
