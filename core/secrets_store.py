"""密钥存储：包一层 `keyring`（Windows 凭据管理器 / macOS Keychain / Linux SecretService）。

设计：
- service 固定 'prism-motif'；每个密钥一个 username（如 'GEMINI_API_KEY' 或 provider 名）。
- get 只查钥匙链，缺失/后端不可用返回 None —— precedence（env vs 钥匙链）由调用方决定，这里不碰环境变量。
- 只有 gateway/kernel 进程用它；perception sidecar 仍只读 os.environ（密钥由 mcp_client 在 spawn 时注入）。
- keyring 懒加载：没装/后端不可用也不 crash 启动（读返回 None，写把异常上抛让 UI 报"保存失败"）。
"""
import os

SERVICE = "prism-motif"


def _kr():
    import keyring          # 懒加载：缺依赖时只影响真正用密钥的路径
    return keyring


def get_secret(name):
    """从钥匙链取密钥；缺失或后端不可用返回 None。不回退环境变量。"""
    try:
        return _kr().get_password(SERVICE, name) or None
    except Exception:        # noqa: BLE001 后端不可用/未装 → 优雅降级为"没有"
        return None


def set_secret(name, value):
    """写入钥匙链。异常上抛，让调用方（设置接口）能报"保存失败"。"""
    _kr().set_password(SERVICE, name, value)


def delete_secret(name):
    try:
        _kr().delete_password(SERVICE, name)
    except Exception:        # noqa: BLE001 不存在/后端不可用都当已删
        pass


def has_secret(name):
    return bool(get_secret(name))


def env_only(name):
    """密钥只在环境变量里、钥匙链里没有 —— 用于提示用户从旧 setx 迁移到钥匙链。"""
    return bool(os.environ.get(name)) and not has_secret(name)
