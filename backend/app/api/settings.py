from pathlib import Path

from fastapi import APIRouter

from app.config import get_settings
from app.schemas import ParagraphSettingsRead, ParagraphSettingsUpdate


router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = PROJECT_ROOT / ".env"


def _bool_env(value: bool) -> str:
    return "true" if value else "false"


def _write_env_values(values: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen: set[str] = set()
    updated_lines: list[str] = []

    for line in lines:
        key = line.split("=", 1)[0] if "=" in line and not line.lstrip().startswith("#") else None
        if key and key in values:
            updated_lines.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            updated_lines.append(line)

    if updated_lines and updated_lines[-1] != "":
        updated_lines.append("")
    for key, value in values.items():
        if key not in seen:
            updated_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")
    ENV_PATH.chmod(0o600)
    get_settings.cache_clear()


def _settings_read() -> ParagraphSettingsRead:
    settings = get_settings()
    mode = settings.paragraphing_mode.lower().strip()
    if mode not in {"rules", "llm"}:
        mode = "rules"
    correction_mode = settings.transcript_correction_mode.lower().strip()
    if correction_mode not in {"off", "rules", "llm"}:
        correction_mode = "rules"
    provider = settings.paragraphing_api_provider.lower().strip()
    if provider not in {"openai", "anthropic"}:
        provider = "openai"
    return ParagraphSettingsRead(
        paragraphing_mode=mode,
        transcript_correction_mode=correction_mode,
        transcript_correction_batch_size=settings.transcript_correction_batch_size,
        whisper_initial_prompt=settings.whisper_initial_prompt,
        paragraphing_api_provider=provider,
        paragraphing_api_base_url=settings.paragraphing_api_base_url,
        paragraphing_api_model=settings.paragraphing_api_model,
        paragraphing_api_key_configured=bool(settings.paragraphing_api_key),
        paragraphing_api_max_sentences=settings.paragraphing_api_max_sentences,
        paragraphing_split_on_speaker=settings.paragraphing_split_on_speaker,
    )


@router.get("/paragraphing", response_model=ParagraphSettingsRead)
def get_paragraphing_settings() -> ParagraphSettingsRead:
    """Return paragraphing settings without exposing secrets."""
    return _settings_read()


@router.put("/paragraphing", response_model=ParagraphSettingsRead)
def update_paragraphing_settings(payload: ParagraphSettingsUpdate) -> ParagraphSettingsRead:
    """Persist paragraphing settings to the local .env file."""
    values: dict[str, str] = {}
    if payload.paragraphing_mode is not None:
        values["PARAGRAPHING_MODE"] = payload.paragraphing_mode
    if payload.transcript_correction_mode is not None:
        values["TRANSCRIPT_CORRECTION_MODE"] = payload.transcript_correction_mode
    if payload.transcript_correction_batch_size is not None:
        values["TRANSCRIPT_CORRECTION_BATCH_SIZE"] = str(payload.transcript_correction_batch_size)
    if payload.whisper_initial_prompt is not None:
        values["WHISPER_INITIAL_PROMPT"] = payload.whisper_initial_prompt.strip()
    if payload.paragraphing_api_provider is not None:
        values["PARAGRAPHING_API_PROVIDER"] = payload.paragraphing_api_provider
    if payload.paragraphing_api_base_url is not None:
        values["PARAGRAPHING_API_BASE_URL"] = payload.paragraphing_api_base_url.strip()
    if payload.paragraphing_api_model is not None:
        values["PARAGRAPHING_API_MODEL"] = payload.paragraphing_api_model.strip()
    if payload.paragraphing_api_max_sentences is not None:
        values["PARAGRAPHING_API_MAX_SENTENCES"] = str(payload.paragraphing_api_max_sentences)
    if payload.paragraphing_split_on_speaker is not None:
        values["PARAGRAPHING_SPLIT_ON_SPEAKER"] = _bool_env(payload.paragraphing_split_on_speaker)
    if payload.clear_paragraphing_api_key:
        values["PARAGRAPHING_API_KEY"] = ""
    elif payload.paragraphing_api_key and payload.paragraphing_api_key.strip():
        values["PARAGRAPHING_API_KEY"] = payload.paragraphing_api_key.strip()

    if values:
        _write_env_values(values)
    return _settings_read()
