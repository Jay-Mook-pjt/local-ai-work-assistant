"""Application settings loaded from environment variables / project-root .env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> project root is two levels above backend/
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    database_url: str = "sqlite:///database/meeting.db"
    storage_dir: Path = Path("storage")
    log_dir: Path = Path("logs")
    log_level: str = "INFO"

    max_upload_mb: int = Field(default=500, gt=0)
    allowed_audio_extensions: str = "mp3,wav,m4a,mp4"

    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen3:14b"
    llm_temperature: float = 0.1
    llm_num_ctx: int = 8192
    llm_timeout_seconds: int = 600

    stt_model: str = "mlx-community/whisper-large-v3-turbo"
    stt_language: str = "ko"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str = ""
    smtp_password: str = Field(default="", repr=False)
    smtp_from: str = ""

    @field_validator("storage_dir", "log_dir")
    @classmethod
    def _resolve_dir(cls, v: Path) -> Path:
        return v if v.is_absolute() else (PROJECT_ROOT / v).resolve()

    @property
    def resolved_database_url(self) -> str:
        """Resolve a relative sqlite path against the project root."""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            path = Path(self.database_url[len(prefix):])
            if not path.is_absolute():
                path = (PROJECT_ROOT / path).resolve()
            return f"{prefix}{path}"
        return self.database_url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_extension_set(self) -> set[str]:
        return {e.strip().lower().lstrip(".") for e in self.allowed_audio_extensions.split(",") if e.strip()}

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


@lru_cache
def get_settings() -> Settings:
    return Settings()
