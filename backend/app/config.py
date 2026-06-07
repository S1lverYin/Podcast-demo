from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "VoiceScribe WebUI"
    database_url: str = "sqlite:///./storage/voicescribe.sqlite3"
    redis_url: str = "redis://redis:6379/0"
    storage_dir: str = "./storage"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    hf_token: str | None = Field(default=None, alias="HF_TOKEN")
    whisper_model_size: str = Field(default="large-v3", alias="WHISPER_MODEL_SIZE")
    whisper_device: str = Field(default="auto", alias="WHISPER_DEVICE")
    whisper_compute_type: str = Field(default="auto", alias="WHISPER_COMPUTE_TYPE")
    whisper_initial_prompt: str | None = Field(default=None, alias="WHISPER_INITIAL_PROMPT")
    transcript_correction_mode: str = Field(default="rules", alias="TRANSCRIPT_CORRECTION_MODE")
    transcript_correction_batch_size: int = Field(default=30, alias="TRANSCRIPT_CORRECTION_BATCH_SIZE")
    translation_mode: str = Field(default="off", alias="TRANSLATION_MODE")
    translation_target_language: str = Field(default="zh", alias="TRANSLATION_TARGET_LANGUAGE")
    translation_local_model: str = Field(default="Helsinki-NLP/opus-mt-en-zh", alias="TRANSLATION_LOCAL_MODEL")
    translation_api_base_url: str = Field(default="https://api.openai.com/v1", alias="TRANSLATION_API_BASE_URL")
    translation_api_key: str | None = Field(default=None, alias="TRANSLATION_API_KEY")
    translation_api_model: str | None = Field(default=None, alias="TRANSLATION_API_MODEL")
    translation_batch_size: int = Field(default=16, alias="TRANSLATION_BATCH_SIZE")
    paragraphing_mode: str = Field(default="rules", alias="PARAGRAPHING_MODE")
    paragraphing_api_provider: str = Field(default="openai", alias="PARAGRAPHING_API_PROVIDER")
    paragraphing_api_base_url: str = Field(default="https://api.openai.com/v1", alias="PARAGRAPHING_API_BASE_URL")
    paragraphing_api_key: str | None = Field(default=None, alias="PARAGRAPHING_API_KEY")
    paragraphing_api_model: str | None = Field(default=None, alias="PARAGRAPHING_API_MODEL")
    paragraphing_api_max_sentences: int = Field(default=220, alias="PARAGRAPHING_API_MAX_SENTENCES")
    paragraphing_split_on_speaker: bool = Field(default=True, alias="PARAGRAPHING_SPLIT_ON_SPEAKER")
    max_upload_mb: int = Field(default=2048, alias="MAX_UPLOAD_MB")
    podcast_subscription_csv: str = Field(default="./app/data/subscriptions.csv", alias="PODCAST_SUBSCRIPTION_CSV")
    run_tasks_inline: bool = Field(default=False, alias="RUN_TASKS_INLINE")

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_dir).resolve()

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
