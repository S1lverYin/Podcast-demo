import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app import models
from app.config import get_settings
from app.schemas import TranscriptSegment


logger = logging.getLogger(__name__)

TERMINAL_PUNCTUATION = (".", "?", "!", "。", "？", "！")
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?。？！])\s+")

STRONG_TOPIC_OPENERS = (
    "another ",
    "at the same time",
    "but before",
    "but of course",
    "but this is",
    "finally",
    "first,",
    "for example",
    "from here",
    "here is",
    "in contrast",
    "in summary",
    "in this lecture",
    "let's move",
    "moving on",
    "next,",
    "now ",
    "on the other hand",
    "second,",
    "something that",
    "that brings us",
    "the first ",
    "the main ",
    "the next ",
    "the second ",
    "the third ",
    "third,",
    "to summarize",
    "what about",
    "what does",
    "what if",
    "why does",
)


@dataclass
class ParagraphDraft:
    start: float
    end: float
    speaker: str | None
    title: str | None
    summary: str | None
    text: str
    translated_text: str | None


@dataclass
class SentenceUnit:
    start: float
    end: float
    speaker: str | None
    text: str
    translated_text: str | None
    language: str | None
    ends_sentence: bool


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _truncate_at_word(text: str, limit: int) -> str:
    normalized = _normalize_text(text)
    if len(normalized) <= limit:
        return normalized

    cut = normalized[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    if len(cut) < limit * 0.55:
        cut = normalized[:limit].rstrip(" ,;:-")
    return f"{cut}..."


def _ends_sentence(text: str | None) -> bool:
    return bool(text and text.strip().endswith(TERMINAL_PUNCTUATION))


def _sentence_title(text: str, limit: int = 90) -> str | None:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return None
    first_sentence = SENTENCE_BOUNDARY_PATTERN.split(normalized, maxsplit=1)[0]
    return _truncate_at_word(first_sentence, limit)


def _summary(text: str, limit: int = 220) -> str | None:
    normalized = _normalize_text(text)
    if not normalized:
        return None
    return _truncate_at_word(normalized, limit)


def _join_parts(parts: list[str]) -> str:
    return _normalize_text(" ".join(part.strip() for part in parts if part and part.strip()))


def _speaker_changed(left: str | None, right: str | None) -> bool:
    return bool(left and right and left != right)


def _split_segment_sentences(segment: TranscriptSegment) -> list[TranscriptSegment]:
    text = _normalize_text(segment.text)
    if not text:
        return []

    parts = [part for part in SENTENCE_BOUNDARY_PATTERN.split(text) if part.strip()]
    if len(parts) <= 1:
        return [segment]

    total_chars = sum(len(part) for part in parts)
    duration = max(segment.end - segment.start, 0.0)
    cursor = segment.start
    pieces: list[TranscriptSegment] = []

    for index, part in enumerate(parts):
        if index == len(parts) - 1:
            end = segment.end
        else:
            end = cursor + (duration * len(part) / total_chars if total_chars else 0)
        pieces.append(
            TranscriptSegment(
                start=cursor,
                end=end,
                speaker=segment.speaker,
                text=part,
                translated_text=None,
                language=segment.language,
            )
        )
        cursor = end
    return pieces


def _build_sentence_units(
    segments: list[TranscriptSegment],
    split_on_speaker: bool = True,
) -> list[SentenceUnit]:
    sentences: list[SentenceUnit] = []
    current: list[TranscriptSegment] = []

    def flush() -> None:
        if not current:
            return

        text = _join_parts([segment.text for segment in current])
        if not text:
            current.clear()
            return

        has_complete_translation = all(
            segment.translated_text and segment.translated_text.strip() for segment in current
        )
        translated_text = (
            _join_parts([segment.translated_text or "" for segment in current])
            if has_complete_translation
            else ""
        )
        speakers = {segment.speaker for segment in current if segment.speaker}
        ends_sentence = _ends_sentence(current[-1].text) or _ends_sentence(current[-1].translated_text)
        sentences.append(
            SentenceUnit(
                start=current[0].start,
                end=current[-1].end,
                speaker=next(iter(speakers)) if len(speakers) == 1 else None,
                text=text,
                translated_text=translated_text or None,
                language=current[0].language,
                ends_sentence=ends_sentence,
            )
        )
        current.clear()

    for raw_segment in segments:
        for segment in _split_segment_sentences(raw_segment):
            if not segment.text.strip():
                continue

            if split_on_speaker and current and _speaker_changed(current[-1].speaker, segment.speaker):
                flush()
            current.append(segment)
            text = _join_parts([item.text for item in current])
            duration = current[-1].end - current[0].start
            long_unpunctuated_sentence = len(text) >= 420 or duration >= 38.0
            if _ends_sentence(segment.text) or _ends_sentence(segment.translated_text) or long_unpunctuated_sentence:
                flush()

    flush()
    return sentences


def _draft_text(units: list[SentenceUnit], translated: bool = False) -> str:
    if translated:
        return _join_parts([unit.translated_text or "" for unit in units])
    return _join_parts([unit.text for unit in units])


def _starts_topic(unit: SentenceUnit) -> bool:
    text = _normalize_text(unit.text).lower()
    if not text:
        return False
    return any(text.startswith(opener) for opener in STRONG_TOPIC_OPENERS)


def _looks_like_question_turn(unit: SentenceUnit) -> bool:
    text = _normalize_text(unit.text).lower()
    return text.endswith("?") and text.startswith(("how ", "what ", "why ", "where ", "when "))


def _starts_with_fragment(unit: SentenceUnit) -> bool:
    text = _normalize_text(unit.text)
    if not text:
        return False
    if text[0].islower():
        return True
    return text.lower().startswith(("of ", "which ", "that ", "where ", "when ", "because "))


def _starts_with_close_connector(unit: SentenceUnit) -> bool:
    return _normalize_text(unit.text).startswith(
        ("And ", "I think ", "It ", "So ", "That ", "These ", "They ", "This ", "Those ")
    )


def _paragraph_stats(units: list[SentenceUnit]) -> tuple[int, float]:
    text_len = len(_draft_text(units))
    duration = units[-1].end - units[0].start
    return text_len, duration


def _should_break(
    current: list[SentenceUnit],
    next_unit: SentenceUnit,
    target_chars: int,
    max_chars: int,
    max_duration: float,
    split_on_speaker: bool = True,
) -> bool:
    if not current:
        return False

    previous = current[-1]
    text_len, duration = _paragraph_stats(current)
    gap = next_unit.start - previous.end
    speaker_changed = _speaker_changed(previous.speaker, next_unit.speaker)
    has_enough_body = text_len >= 420 or duration >= 28.0
    topic_start = _starts_topic(next_unit) or _looks_like_question_turn(next_unit)
    mid_sentence_boundary = not previous.ends_sentence or _starts_with_fragment(next_unit)
    close_connector = gap < 1.2 and _starts_with_close_connector(next_unit)

    if split_on_speaker and speaker_changed:
        return True
    if (mid_sentence_boundary or close_connector) and text_len < int(max_chars * 1.35) and duration < max_duration * 1.25:
        return False

    if text_len >= max_chars:
        return True
    if duration >= max_duration and text_len >= 360:
        return True
    if gap >= 2.4 and has_enough_body:
        return True
    if speaker_changed and has_enough_body:
        return True
    if topic_start and (text_len >= target_chars or (gap >= 1.4 and has_enough_body)):
        return True
    if text_len >= target_chars and duration >= 35.0:
        return True
    return False


def _build_paragraph(current: list[SentenceUnit]) -> ParagraphDraft:
    text = _draft_text(current)
    translated_text = _draft_text(current, translated=True) if all(unit.translated_text for unit in current) else None
    speakers = {unit.speaker for unit in current if unit.speaker}
    speaker = next(iter(speakers)) if len(speakers) == 1 else None
    return ParagraphDraft(
        start=current[0].start,
        end=current[-1].end,
        speaker=speaker,
        title=_sentence_title(text),
        summary=_summary(text),
        text=text,
        translated_text=translated_text,
    )


def _merge_paragraphs(left: ParagraphDraft, right: ParagraphDraft) -> ParagraphDraft:
    text = _join_parts([left.text, right.text])
    translated_text = (
        _join_parts([left.translated_text or "", right.translated_text or ""])
        if left.translated_text and right.translated_text
        else None
    )
    speakers = {speaker for speaker in (left.speaker, right.speaker) if speaker}
    return ParagraphDraft(
        start=left.start,
        end=right.end,
        speaker=next(iter(speakers)) if len(speakers) == 1 else None,
        title=_sentence_title(text),
        summary=_summary(text),
        text=text,
        translated_text=translated_text,
    )


def _merge_short_paragraphs(
    paragraphs: list[ParagraphDraft],
    min_chars: int = 300,
    min_duration: float = 16.0,
    max_merged_chars: int = 1450,
    split_on_speaker: bool = True,
) -> list[ParagraphDraft]:
    merged: list[ParagraphDraft] = []

    for paragraph in paragraphs:
        text_len = len(paragraph.text)
        duration = paragraph.end - paragraph.start
        if merged and (text_len < min_chars or duration < min_duration):
            previous = merged[-1]
            combined_len = len(previous.text) + text_len
            if combined_len <= max_merged_chars and not (
                split_on_speaker and _speaker_changed(previous.speaker, paragraph.speaker)
            ):
                merged[-1] = _merge_paragraphs(previous, paragraph)
                continue
        merged.append(paragraph)

    if len(merged) <= 1:
        return merged

    result: list[ParagraphDraft] = []
    index = 0
    while index < len(merged):
        paragraph = merged[index]
        text_len = len(paragraph.text)
        duration = paragraph.end - paragraph.start
        if (
            index + 1 < len(merged)
            and (text_len < min_chars or duration < min_duration)
            and text_len + len(merged[index + 1].text) <= max_merged_chars
            and not (split_on_speaker and _speaker_changed(paragraph.speaker, merged[index + 1].speaker))
        ):
            result.append(_merge_paragraphs(paragraph, merged[index + 1]))
            index += 2
            continue
        result.append(paragraph)
        index += 1
    return result


def _build_rule_paragraphs(
    sentence_units: list[SentenceUnit],
    max_chars: int = 1150,
    max_duration: float = 95.0,
    split_on_speaker: bool = True,
) -> list[ParagraphDraft]:
    paragraphs: list[ParagraphDraft] = []
    current: list[SentenceUnit] = []
    target_chars = max(720, int(max_chars * 0.68))

    for sentence in sentence_units:
        if _should_break(
            current,
            sentence,
            target_chars=target_chars,
            max_chars=max_chars,
            max_duration=max_duration,
            split_on_speaker=split_on_speaker,
        ):
            paragraphs.append(_build_paragraph(current))
            current = []
        current.append(sentence)

    if current:
        paragraphs.append(_build_paragraph(current))
    return _merge_short_paragraphs(paragraphs, split_on_speaker=split_on_speaker)


def _normalize_segments(segments: list[TranscriptSegment | models.TranscriptSegment]) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            start=segment.start,
            end=segment.end,
            speaker=segment.speaker,
            text=segment.text,
            translated_text=getattr(segment, "translated_text", None),
            language=segment.language,
        )
        for segment in segments
    ]


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


def _coerce_range(value: Any, sentence_count: int) -> tuple[int, int] | None:
    if not isinstance(value, dict):
        return None

    start_value = value.get("start_id", value.get("start", value.get("from")))
    end_value = value.get("end_id", value.get("end", value.get("to")))
    if start_value is None or end_value is None:
        return None

    try:
        start = int(start_value)
        end = int(end_value)
    except (TypeError, ValueError):
        return None

    if start < 0 or end < 0 or start >= sentence_count:
        return None
    return start, min(end, sentence_count - 1)


def _sanitize_llm_ranges(payload: Any, sentence_count: int) -> list[tuple[int, int]]:
    raw_ranges = payload.get("paragraphs") if isinstance(payload, dict) else payload
    if not isinstance(raw_ranges, list):
        raise ValueError("LLM paragraphing response must contain a paragraphs list")

    ranges = [
        coerced
        for coerced in (_coerce_range(item, sentence_count) for item in raw_ranges)
        if coerced is not None
    ]
    if not ranges:
        raise ValueError("LLM paragraphing response did not include usable ranges")

    sanitized: list[tuple[int, int]] = []
    cursor = 0
    for start, end in sorted(ranges, key=lambda item: item[0]):
        if end < cursor:
            continue
        if start > cursor:
            sanitized.append((cursor, start - 1))
        sanitized.append((max(start, cursor), max(end, cursor)))
        cursor = max(end, cursor) + 1

    if cursor < sentence_count:
        sanitized.append((cursor, sentence_count - 1))

    if sanitized[0][0] != 0 or sanitized[-1][1] != sentence_count - 1:
        raise ValueError("LLM paragraphing ranges do not cover the transcript")
    return sanitized


def _split_ranges_on_speaker(
    ranges: list[tuple[int, int]],
    sentence_units: list[SentenceUnit],
) -> list[tuple[int, int]]:
    split_ranges: list[tuple[int, int]] = []
    for start, end in ranges:
        range_start = start
        previous = sentence_units[start]
        for index in range(start + 1, end + 1):
            current = sentence_units[index]
            if _speaker_changed(previous.speaker, current.speaker):
                split_ranges.append((range_start, index - 1))
                range_start = index
            previous = current
        split_ranges.append((range_start, end))
    return split_ranges


def _paragraphing_api_config() -> tuple[str, str, str, str]:
    settings = get_settings()
    provider = settings.paragraphing_api_provider.lower().strip()
    if provider not in {"openai", "anthropic"}:
        provider = "openai"
    base_url = (settings.paragraphing_api_base_url or settings.translation_api_base_url).rstrip("/")
    api_key = settings.paragraphing_api_key or settings.translation_api_key
    model = settings.paragraphing_api_model or settings.translation_api_model

    if not api_key:
        raise RuntimeError("PARAGRAPHING_API_KEY or TRANSLATION_API_KEY is required for LLM paragraphing")
    if not model:
        raise RuntimeError("PARAGRAPHING_API_MODEL or TRANSLATION_API_MODEL is required for LLM paragraphing")
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


def _llm_paragraph_ranges(
    sentence_units: list[SentenceUnit],
    split_on_speaker: bool = True,
) -> list[tuple[int, int]]:
    provider, base_url, api_key, model = _paragraphing_api_config()
    items = [
        {
            "id": index,
            "start": round(unit.start, 2),
            "end": round(unit.end, 2),
            "speaker": unit.speaker,
            "text": _truncate_at_word(unit.text, 520),
        }
        for index, unit in enumerate(sentence_units)
    ]
    system_prompt = (
        "You split lecture transcripts into natural paragraphs. Return only JSON with this shape: "
        "{\"paragraphs\":[{\"start_id\":0,\"end_id\":4}]}. "
        "Each range is inclusive. Cover every sentence id exactly once in order. "
        "Prefer coherent topic paragraphs over mechanical time cuts. Avoid tiny paragraphs unless there is a clear transition. "
        "When speaker_split is true, never put different known speakers in the same paragraph. "
        "Do not rewrite transcript text."
    )
    user_prompt = {
        "guidelines": {
            "ideal_duration_seconds": "35-90",
            "ideal_length_chars": "700-1200",
            "allow_longer_when_topic_requires": True,
            "speaker_split": split_on_speaker,
        },
        "sentences": items,
    }
    content = (
        _anthropic_completion(base_url, api_key, model, system_prompt, user_prompt)
        if provider == "anthropic"
        else _openai_compatible_completion(base_url, api_key, model, system_prompt, user_prompt)
    )
    ranges = _sanitize_llm_ranges(_extract_json_payload(content), len(sentence_units))
    return _split_ranges_on_speaker(ranges, sentence_units) if split_on_speaker else ranges


def _build_llm_paragraphs(
    sentence_units: list[SentenceUnit],
    split_on_speaker: bool = True,
) -> list[ParagraphDraft]:
    settings = get_settings()
    max_sentences = max(20, settings.paragraphing_api_max_sentences)
    paragraphs: list[ParagraphDraft] = []

    for offset in range(0, len(sentence_units), max_sentences):
        chunk = sentence_units[offset : offset + max_sentences]
        ranges = _llm_paragraph_ranges(chunk, split_on_speaker=split_on_speaker)
        paragraphs.extend(_build_paragraph(chunk[start : end + 1]) for start, end in ranges)

    return _merge_short_paragraphs(paragraphs, split_on_speaker=split_on_speaker)


def build_transcript_paragraphs(
    segments: list[TranscriptSegment | models.TranscriptSegment],
    max_chars: int = 1150,
    max_duration: float = 95.0,
    mode: str | None = None,
    split_on_speaker: bool | None = None,
    allow_llm_fallback: bool = True,
) -> list[ParagraphDraft]:
    """Build a paragraph-level transcript view from timestamped segments."""
    settings = get_settings()
    speaker_split = settings.paragraphing_split_on_speaker if split_on_speaker is None else split_on_speaker
    sentence_units = _build_sentence_units(_normalize_segments(segments), split_on_speaker=speaker_split)
    if not sentence_units:
        return []

    selected_mode = (mode or settings.paragraphing_mode).lower().strip()
    if selected_mode in {"llm", "api"}:
        try:
            return _build_llm_paragraphs(sentence_units, split_on_speaker=speaker_split)
        except Exception as exc:
            if not allow_llm_fallback:
                raise
            logger.warning("LLM paragraphing failed; falling back to rules: %s", exc)
    elif selected_mode not in {"", "auto", "rule", "rules", "local"}:
        logger.warning("Unknown paragraphing mode '%s'; using rules", selected_mode)

    return _build_rule_paragraphs(
        sentence_units,
        max_chars=max_chars,
        max_duration=max_duration,
        split_on_speaker=speaker_split,
    )
