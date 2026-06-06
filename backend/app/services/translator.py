import json
import logging
import os
import re
from functools import lru_cache
from typing import TypeVar

import httpx

from app.config import get_settings
from app.schemas import TranscriptSegment


logger = logging.getLogger(__name__)
T = TypeVar("T")

LANGUAGE_NAMES = {
    "zh": "Simplified Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}


def _chunks(items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _target_name(target_language: str) -> str:
    return LANGUAGE_NAMES.get(target_language, target_language)


def split_text_for_translation(text: str, max_chars: int = 450) -> list[str]:
    """Split long transcript text into sentence-aware chunks for local translation."""
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    sentences = re.split(r"(?<=[.!?。？！])\s+", normalized)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for index in range(0, len(sentence), max_chars):
                chunks.append(sentence[index : index + max_chars])
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _api_translate(texts: list[str], source_language: str | None, target_language: str) -> list[str]:
    """Translate segment texts through an OpenAI-compatible chat completions API."""
    settings = get_settings()
    if not settings.translation_api_key:
        raise RuntimeError("TRANSLATION_API_KEY is required when TRANSLATION_MODE=api")
    if not settings.translation_api_model:
        raise RuntimeError("TRANSLATION_API_MODEL is required when TRANSLATION_MODE=api")

    payload_items = [{"id": index, "text": text} for index, text in enumerate(texts)]
    system_prompt = (
        "You are a careful transcript translator. Translate each item into "
        f"{_target_name(target_language)}. Preserve technical terms, names, numbers, and meaning. "
        "Return only JSON in this shape: [{\"id\": 0, \"translation\": \"...\"}]."
    )
    user_prompt = {
        "source_language": source_language or "auto",
        "target_language": target_language,
        "items": payload_items,
    }

    endpoint = settings.translation_api_base_url.rstrip("/") + "/chat/completions"
    response = httpx.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {settings.translation_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.translation_api_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    data = json.loads(content)
    translations = {int(item["id"]): str(item["translation"]) for item in data}
    return [translations.get(index, "") for index in range(len(texts))]


@lru_cache(maxsize=2)
def _local_pipeline(model_name: str):
    """Load and cache a local Hugging Face translation pipeline."""
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        from transformers import pipeline
    except ImportError as exc:  # pragma: no cover - optional local translation dependency
        raise RuntimeError(
            "Local translation requires transformers. Install backend requirements again."
        ) from exc

    logger.info("Loading local translation model '%s'", model_name)
    return pipeline("translation", model=model_name)


def _local_translate(texts: list[str], target_language: str) -> list[str]:
    """Translate segment texts locally with Hugging Face transformers."""
    settings = get_settings()
    translator = _local_pipeline(settings.translation_local_model)
    outputs = translator(texts)
    return [str(item["translation_text"]) for item in outputs]


def translate_texts(
    texts: list[str],
    source_language: str | None,
    target_language: str | None = None,
) -> list[str]:
    """Translate plain text items using the configured translation backend."""
    settings = get_settings()
    mode = settings.translation_mode.lower().strip()
    if mode in {"", "off", "none", "disabled"}:
        raise RuntimeError("Translation is disabled. Set TRANSLATION_MODE=local or api.")

    target = target_language or settings.translation_target_language
    batch_size = max(1, settings.translation_batch_size)
    translated: list[str] = []
    for batch in _chunks(texts, batch_size):
        if mode == "api":
            translated.extend(_api_translate(batch, source_language, target))
        elif mode == "local":
            translated.extend(_local_translate(batch, target))
        else:
            raise RuntimeError("TRANSLATION_MODE must be one of: off, local, api")
    return translated


def translate_text(
    text: str,
    source_language: str | None,
    target_language: str | None = None,
) -> str:
    """Translate one text block, splitting long paragraphs before translation."""
    chunks = split_text_for_translation(text)
    if not chunks:
        return ""
    return " ".join(translate_texts(chunks, source_language, target_language)).strip()


def translate_transcript_segments(
    segments: list[TranscriptSegment],
    source_language: str | None,
    target_language: str | None = None,
) -> list[TranscriptSegment]:
    """Translate transcript segment text and store it in translated_text."""
    translated = translate_texts([segment.text for segment in segments], source_language, target_language)

    return [
        segment.model_copy(update={"translated_text": translation})
        for segment, translation in zip(segments, translated, strict=False)
    ]
