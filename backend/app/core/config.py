"""Pydantic Settings module reading environment configuration variables."""

# Non-secret placeholders allow import-time validation and unit tests when .env is absent.
# env_file is resolved to an ABSOLUTE path anchored at this file's directory so that scripts
# running from any working directory (e.g. repo root) always load backend/.env correctly.

from functools import lru_cache
from pathlib import Path
from typing import Self
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path to backend/.env, resolved relative to this file — CWD-independent
_ENV_FILE: Path = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    # Application Info
    PROJECT_TITLE: str = "WorkMate AI API"
    PROJECT_VERSION: str = "1.0.0"
    APP_ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # Snowflake persistence and source-stage connection settings
    SNOWFLAKE_ACCOUNT: str = "your_snowflake_account_placeholder"
    SNOWFLAKE_USER: str = "your_snowflake_user_placeholder"
    SNOWFLAKE_PASSWORD: str = "your_snowflake_password_placeholder"
    SNOWFLAKE_WAREHOUSE: str = "COMPUTE_WH"
    SNOWFLAKE_DATABASE: str = "WORKMATE_AI"
    SNOWFLAKE_SCHEMA: str = "KNOWLEDGE_STUDIO"
    SNOWFLAKE_ROLE: str = ""  # Optional: Snowflake role to activate on connection (e.g. SYSADMIN)
    SNOWFLAKE_POOL_SIZE: int = 4
    SNOWFLAKE_POOL_ACQUIRE_TIMEOUT_SECONDS: float = 5.0
    SNOWFLAKE_STAGE_NAME: str = "RAW_OWD_STAGE"
    OWD_CLI_USER_ID: str = "usr_admin001"

    # Copilot retrieval and generation. Production defaults to published only.
    COPILOT_RETRIEVAL_LIMIT: int = 5
    COPILOT_ALLOWED_KNOWLEDGE_STATUSES: str = "published"
    COPILOT_MIN_CONFIDENCE_THRESHOLD: float = 0.70
    COPILOT_HISTORY_LIMIT: int = 6

    # Free/self-hosted Ollama runtime. Snowflake is candidate storage only.
    LOCAL_AI_ENABLED: bool = True
    LOCAL_AI_BASE_URL: str = "http://ollama:11434"
    LOCAL_CHAT_MODEL: str = "qwen2.5:3b"
    LOCAL_TRANSLATION_MODEL: str = "translategemma:4b"
    LOCAL_EMBEDDING_MODEL: str = "nomic-embed-text"
    LOCAL_AI_TIMEOUT_SECONDS: float = 8.0
    LOCAL_AI_CANDIDATE_LIMIT: int = 100
    LOCAL_AI_INDEX_MAX_CANDIDATES: int = 5000
    LOCAL_AI_MIN_SIMILARITY: float = 0.35

    # Self-hosted multilingual voice pipeline.
    VOICE_ENABLED: bool = True
    VOICE_SUPPORTED_LANGUAGES: str = "en,hi,kn,ta,te,ml"
    VOICE_MAX_AUDIO_BYTES: int = 25 * 1024 * 1024
    VOICE_AUDIO_DIR: str = "/app/data/voice/audio"
    VOICE_AUDIO_TTL_SECONDS: int = 3600
    WHISPER_MODEL: str = "large-v3"
    WHISPER_FALLBACK_MODEL: str = "medium"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_DOWNLOAD_ROOT: str = "/app/data/voice/whisper"
    WHISPER_LARGE_MIN_MEMORY_GB: float = 6.0
    WHISPER_TRANSCRIPTION_TIMEOUT_SECONDS: float = 300.0
    PIPER_VOICE_DIR: str = "/app/data/voice/piper"
    PIPER_USE_CUDA: bool = False
    PIPER_VOICE_MAP: str = (
        '{"en":"en_US-lessac-medium.onnx",'
        '"hi":"hi_IN-pratham-medium.onnx"}'
    )
    TRANSLATION_TIMEOUT_SECONDS: float = 180.0
    TRANSLATION_KEEP_ALIVE: str = "0"
    VOICE_MODEL_REUSE_MIN_MEMORY_GB: float = 8.0

    # Auth & Security Credentials
    JWT_SECRET: str = "replace_with_at_least_32_random_characters"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # Internal Webhook & Service Security
    INTERNAL_WEBHOOK_SECRET: str = "replace_with_a_random_webhook_secret"

    # Orchestration Settings
    N8N_BASE_URL: str = "http://localhost:5678"
    N8N_WEBHOOK_BASE_URL: str = "http://localhost:5678"
    N8N_NOTIFICATIONS_ENABLED: bool = False

    @model_validator(mode="after")
    def validate_runtime_security(self) -> Self:
        if "*" in {origin.strip() for origin in self.FRONTEND_ORIGIN.split(",")}:
            raise ValueError("FRONTEND_ORIGIN must contain explicit origins when credentials are enabled")
        if self.APP_ENV.strip().lower() in {"prod", "production"}:
            protected_values = {
                "SNOWFLAKE_ACCOUNT": self.SNOWFLAKE_ACCOUNT,
                "SNOWFLAKE_USER": self.SNOWFLAKE_USER,
                "SNOWFLAKE_PASSWORD": self.SNOWFLAKE_PASSWORD,
                "JWT_SECRET": self.JWT_SECRET,
                "INTERNAL_WEBHOOK_SECRET": self.INTERNAL_WEBHOOK_SECRET,
            }
            markers = ("your_", "replace_with_", "placeholder")
            invalid = [
                name
                for name, value in protected_values.items()
                if not value or any(marker in value.casefold() for marker in markers)
            ]
            if invalid:
                raise ValueError(
                    "Production configuration contains missing or placeholder secrets: "
                    + ", ".join(invalid)
                )
        return self

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Returns a singleton, cached instance of application settings."""
    return Settings()


# Cached settings instance export
settings = get_settings()
