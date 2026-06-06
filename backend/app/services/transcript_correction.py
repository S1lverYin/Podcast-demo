import json
import logging
import re
from typing import Any, TypeVar

import httpx

from app.config import get_settings
from app.schemas import TranscriptSegment


logger = logging.getLogger(__name__)
T = TypeVar("T")

CHINESE_PHRASE_CORRECTIONS = {
    "朱元章": "朱元璋",
    "主家": "朱家",
    "大名": "大明",
    "坚群": "建群",
    "朱弟": "朱棣",
    "云文": "允炆",
    "勇勒": "永乐",
    "好旺角": "好望角",
    "政和下西洋": "郑和下西洋",
    "静难之意": "靖难之役",
    "削翻": "削藩",
    "东场": "东厂",
}

PROTECTED_TERMS = {
    "朱元璋",
    "朱棣",
    "朱允炆",
    "大明",
    "建群",
    "群名",
    "永乐盛世",
    "郑和下西洋",
    "好望角",
    "靖难之役",
    "东厂",
    "削藩",
}


def _chunks(items: list[T], size: int) -> list[list[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _normalize_spacing(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    normalized = re.sub(r"\s+([,.!?;:，。！？；：])", r"\1", normalized)
    normalized = re.sub(r"([（(])\s+", r"\1", normalized)
    normalized = re.sub(r"\s+([）)])", r"\1", normalized)
    return normalized


def _apply_rule_corrections(text: str) -> str:
    corrected = _normalize_spacing(text)
    for source, target in CHINESE_PHRASE_CORRECTIONS.items():
        corrected = corrected.replace(source, target)
    return corrected


def _strip_json_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_payload(content: str) -> Any:
    text = _strip_json_fences(content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start_candidates = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if not start_candidates:
            raise
        start = min(start_candidates)
        end = max(text.rfind("}"), text.rfind("]"))
        if end <= start:
            raise
        return json.loads(text[start : end + 1])


def _api_config() -> tuple[str, str, str, str]:
    settings = get_settings()
    provider = settings.paragraphing_api_provider.lower().strip()
    if provider not in {"openai", "anthropic"}:
        provider = "openai"
    base_url = (settings.paragraphing_api_base_url or settings.translation_api_base_url).rstrip("/")
    api_key = settings.paragraphing_api_key or settings.translation_api_key
    model = settings.paragraphing_api_model or settings.translation_api_model

    if not api_key:
        raise RuntimeError("PARAGRAPHING_API_KEY or TRANSLATION_API_KEY is required for LLM transcript correction")
    if not model:
        raise RuntimeError("PARAGRAPHING_API_MODEL or TRANSLATION_API_MODEL is required for LLM transcript correction")
    return provider, base_url, api_key, model


def _openai_compatible_completion(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: dict[str, Any],
) -> str:
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
        },
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _anthropic_completion(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: dict[str, Any],
) -> str:
    response = httpx.post(
        f"{base_url}/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 8192,
            "temperature": 0,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
        },
        timeout=180,
    )
    response.raise_for_status()
    content = response.json().get("content", [])
    return "\n".join(
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def _sanitize_corrections(payload: Any, originals: list[TranscriptSegment]) -> dict[int, str]:
    raw_items = payload.get("items", payload.get("corrections")) if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raise ValueError("LLM correction response must be a JSON list or contain an items list")

    original_by_id = {index: segment.text for index, segment in enumerate(originals)}
    corrections: dict[int, str] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        raw_text = item.get("text", item.get("corrected_text", item.get("correction")))
        try:
            item_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if item_id not in original_by_id or raw_text is None:
            continue
        corrected = _normalize_spacing(str(raw_text))
        original = original_by_id[item_id]
        max_len = max(32, len(original) * 3 + 80)
        loses_protected_term = any(term in original and term not in corrected for term in PROTECTED_TERMS)
        if corrected and len(corrected) <= max_len and not loses_protected_term:
            corrections[item_id] = corrected
    return corrections


def _llm_correct_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    settings = get_settings()
    provider, base_url, api_key, model = _api_config()
    batch_size = max(10, min(settings.transcript_correction_batch_size, 220))
    corrected_segments: list[TranscriptSegment] = []

    system_prompt = (
        "You are a transcript correction editor for ASR output. Correct recognition errors in Chinese and English, "
        "especially homophones, names, terminology, casing, punctuation, and obvious word boundary errors. "
        "Make the smallest useful edit. Keep the original language. Do not translate, summarize, expand, censor, or add facts. "
        "Do not replace protected terms from the glossary with more generic words. "
        "Preserve each item's id and meaning. Return only JSON: "
        "{\"items\":[{\"id\":0,\"text\":\"corrected transcript\"}]}."
    )

    glossary = (
        settings.whisper_initial_prompt
        or "常见中文历史词：朱元璋、朱棣、朱允炆、大明、明朝、永乐盛世、郑和下西洋、好望角、靖难之役、东厂、削藩、建群、群名。"
    )

    for batch in _chunks(segments, batch_size):
        items = [
            {
                "id": index,
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "speaker": segment.speaker,
                "language": segment.language,
                "text": segment.text,
            }
            for index, segment in enumerate(batch)
        ]
        user_prompt = {
            "glossary_or_context": glossary,
            "instructions": [
                "Fix ASR mistakes only when the correction is strongly supported by nearby context.",
                "If unsure, keep the original text.",
                "Return exactly one corrected text for each input id.",
            ],
            "items": items,
        }
        content = (
            _anthropic_completion(base_url, api_key, model, system_prompt, user_prompt)
            if provider == "anthropic"
            else _openai_compatible_completion(base_url, api_key, model, system_prompt, user_prompt)
        )
        corrections = _sanitize_corrections(_extract_json_payload(content), batch)
        corrected_segments.extend(
            segment.model_copy(update={"text": corrections.get(index, segment.text)})
            for index, segment in enumerate(batch)
        )

    return corrected_segments


def correct_transcript_segments(
    segments: list[TranscriptSegment],
) -> tuple[list[TranscriptSegment], str | None]:
    """Correct ASR transcript text while preserving timestamps and speakers."""
    settings = get_settings()
    mode = settings.transcript_correction_mode.lower().strip()
    if mode in {"", "off", "none", "disabled"}:
        return segments, None

    rule_corrected = [
        segment.model_copy(update={"text": _apply_rule_corrections(segment.text)})
        for segment in segments
    ]
    if mode in {"rule", "rules", "local"}:
        return rule_corrected, None
    if mode not in {"llm", "api"}:
        logger.warning("Unknown transcript correction mode '%s'; using rules", mode)
        return rule_corrected, None

    try:
        return _llm_correct_segments(rule_corrected), None
    except Exception as exc:
        logger.warning("LLM transcript correction failed; using rule corrections: %s", exc)
        return rule_corrected, f"LLM transcript correction skipped; rule corrections were used. {exc}"
