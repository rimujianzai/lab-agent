from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # 后端项目的根路径（backend/）
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    # 该字段的值由环境变量 / .env 提供，不在代码里写死
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL: str
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8"
    )

    # 允许跨域访问的前端地址，多个用英文逗号分隔。
    # 前端（Vite）默认跑在 5173，这里默认把它放行，避免浏览器报 CORS 错误。
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        # .env 里出现与本类无关的键时直接忽略，不要让程序启动失败
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


# 字段是必填的，但取值来自 .env；类型检查器看不到这一步，
# 会误报 "缺少参数 DATABASE_URL"，故忽略 call-arg 这一类告警
try:
    settings = Settings()  # type: ignore[call-arg]
except ValidationError as exc:
    # 把 pydantic 那串又长又难懂的报错，换成一句人能看懂的话
    raise RuntimeError(
        f"配置读取失败：请确认 {ENV_FILE} 存在，并且里面有 DATABASE_URL，例如：\n"
        "DATABASE_URL=mysql+pymysql://root:你的密码@127.0.0.1:3306/lab_agent"
    ) from exc

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".zip",
}
