"""从环境变量读取配置。密钥只存在于本机环境，不写进代码。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = ROOT / "data" / "agent.db"


@dataclass(frozen=True)
class Settings:
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    database_path: str
    xianyu_browser_user_data: str
    wechat_id: str

    @property
    def deepseek_enabled(self) -> bool:
        return bool(self.deepseek_api_key)


def load_dotenv(path: Path | None = None) -> None:
    """读取项目根目录的 .env。已存在的环境变量优先，避免覆盖本机真实配置。"""
    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_settings() -> Settings:
    database_path = os.environ.get("DATABASE_PATH", "").strip()
    return Settings(
        deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY", "").strip(),
        deepseek_base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
        or "https://api.deepseek.com",
        deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat",
        database_path=database_path or str(DEFAULT_DATABASE_PATH),
        xianyu_browser_user_data=os.environ.get("XIANYU_BROWSER_USER_DATA", "").strip(),
        wechat_id=os.environ.get("WECHAT_ID", "").strip(),
    )


def build_generator():
    """有密钥时使用 DeepSeek，否则使用可离线测试的模板生成器。"""
    from app.llm.deepseek import DeepSeekReplyGenerator
    from app.llm.template import TemplateReplyGenerator

    settings = load_settings()
    if not settings.deepseek_enabled:
        return TemplateReplyGenerator()
    return DeepSeekReplyGenerator(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        wechat_id=settings.wechat_id,
    )
