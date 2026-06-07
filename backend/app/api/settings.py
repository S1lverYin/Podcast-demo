from pathlib import Path

from fastapi import APIRouter

from app.config import get_settings
from app.schemas import DiarizationSettingsRead, DiarizationSettingsUpdate, ParagraphSettingsRead, ParagraphSettingsUpdate, TranslationSettingsRead, TranslationSettingsUpdate


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




def _translation_settings_read() -> TranslationSettingsRead:
    settings = get_settings()
    provider = settings.translation_api_provider.lower().strip()
    if provider not in {"openai", "anthropic"}:
        provider = "openai"
    return TranslationSettingsRead(
        translation_api_provider=provider,
        translation_api_base_url=settings.translation_api_base_url,
        translation_api_model=settings.translation_api_model,
        translation_api_key_configured=bool(settings.translation_api_key),
        translation_contextual=settings.translation_contextual,
    )


@router.get("/translation", response_model=TranslationSettingsRead)
def get_translation_settings() -> TranslationSettingsRead:
    return _translation_settings_read()


@router.put("/translation", response_model=TranslationSettingsRead)
def update_translation_settings(payload: TranslationSettingsUpdate) -> TranslationSettingsRead:
    values: dict[str, str] = {}
    if payload.translation_api_provider is not None:
        values["TRANSLATION_API_PROVIDER"] = payload.translation_api_provider
    if payload.translation_api_base_url is not None:
        values["TRANSLATION_API_BASE_URL"] = payload.translation_api_base_url.strip()
    if payload.translation_api_model is not None:
        values["TRANSLATION_API_MODEL"] = payload.translation_api_model.strip()
    if payload.translation_contextual is not None:
        values["TRANSLATION_CONTEXTUAL"] = "true" if payload.translation_contextual else "false"
    if payload.clear_translation_api_key:
        values["TRANSLATION_API_KEY"] = ""
    elif payload.translation_api_key and payload.translation_api_key.strip():
        values["TRANSLATION_API_KEY"] = payload.translation_api_key.strip()
    if values:
        _write_env_values(values)
    return _translation_settings_read()


def _diarization_settings_read() -> DiarizationSettingsRead:
    settings = get_settings()
    provider = settings.diarization_api_provider.lower().strip()
    if provider not in {"openai", "anthropic"}:
        provider = "openai"
    return DiarizationSettingsRead(
        diarization_api_provider=provider,
        diarization_api_base_url=settings.diarization_api_base_url,
        diarization_api_model=settings.diarization_api_model,
        diarization_api_key_configured=bool(settings.diarization_api_key),
    )


@router.get("/diarization", response_model=DiarizationSettingsRead)
def get_diarization_settings() -> DiarizationSettingsRead:
    """Return diarization settings without exposing secrets."""
    return _diarization_settings_read()


@router.put("/diarization", response_model=DiarizationSettingsRead)
def update_diarization_settings(payload: DiarizationSettingsUpdate) -> DiarizationSettingsRead:
    """Persist diarization settings to the local .env file."""
    values: dict[str, str] = {}
    if payload.diarization_api_provider is not None:
        values["DIARIZATION_API_PROVIDER"] = payload.diarization_api_provider
    if payload.diarization_api_base_url is not None:
        values["DIARIZATION_API_BASE_URL"] = payload.diarization_api_base_url.strip()
    if payload.diarization_api_model is not None:
        values["DIARIZATION_API_MODEL"] = payload.diarization_api_model.strip()
    if payload.clear_diarization_api_key:
        values["DIARIZATION_API_KEY"] = ""
    elif payload.diarization_api_key and payload.diarization_api_key.strip():
        values["DIARIZATION_API_KEY"] = payload.diarization_api_key.strip()
    if values:
        _write_env_values(values)
    return _diarization_settings_read()


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
