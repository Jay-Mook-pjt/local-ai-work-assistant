"""Application settings loaded from environment variables / project-root .env."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> project root is two levels above backend/
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # APP_ENV_FILE selects the profile: .env (development) or e.g. .env.offline (closed network)
        env_file=PROJECT_ROOT / os.environ.get("APP_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    database_url: str = "sqlite:///database/meeting.db"
    storage_dir: Path = Path("storage")
    # Local model folders (see app/services/model_store.py); preferred over the HF cache.
    models_dir: Path = Path("models")
    log_dir: Path = Path("logs")
    log_level: str = "INFO"

    max_upload_mb: int = Field(default=500, gt=0)
    allowed_audio_extensions: str = "mp3,wav,m4a,mp4"

    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen3:14b"
    llm_temperature: float = 0.1
    llm_num_ctx: int = 16384
    llm_timeout_seconds: int = 900
    llm_keep_alive: str = "2m"
    # Never send meeting text to Ollama cloud models (":cloud"/"-cloud", remote_host).
    llm_allow_cloud: bool = False
    # Free the LLM's memory when a job finishes (next job starts with STT, not a resident LLM).
    llm_unload_after_job: bool = True
    # Transcript characters per LLM analysis chunk (Korean ~1.5 chars/token).
    llm_chunk_chars: int = Field(default=6000, ge=1000)

    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"
    worker_poll_seconds: float = Field(default=2.0, gt=0)

    stt_model: str = "mlx-community/whisper-large-v3-turbo"
    stt_language: str = "ko"
    # Long audio is transcribed in windows of this length, overlapping by stt_overlap_seconds.
    stt_chunk_seconds: int = Field(default=600, ge=60)
    stt_overlap_seconds: int = Field(default=10, ge=0, le=60)

    # Speaker diarization (pyannote.audio). The model is downloaded once with
    # `python -m app.services.diarization_service download` and then used offline.
    diarization_enabled: bool = False
    diarization_model: str = "pyannote/speaker-diarization-community-1"
    diarization_device: str = "auto"  # auto | mps | cpu
    hf_keychain_service: str = "local-ai-work-assistant-hf"
    hf_keychain_account: str = "huggingface"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str = ""
    smtp_password: str = Field(default="", repr=False)
    # Alternative to SMTP_PASSWORD: read it from the macOS Keychain
    # (security add-generic-password -s <service> -a <SMTP_USERNAME> -w).
    smtp_keychain_service: str = ""
    smtp_from: str = ""
    smtp_from_name: str = "AI 회의록 비서"
    smtp_timeout_seconds: int = 30
    email_max_recipients: int = 50

    @field_validator("storage_dir", "log_dir", "models_dir")
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
