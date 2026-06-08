import json
import random
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from app.config import get_settings
from app.schemas import TranscriptSegment
from app.services.downloader import _anti_bot_options, BROWSER_USER_AGENT, validate_public_http_url, yt_dlp_command
from app.services.transcript_correction import (
    _anthropic_completion,
    _api_config,
    _extract_json_payload,
    _openai_compatible_completion,
)


LANGUAGE_FALLBACKS = {
    "auto": ["zh-Hans", "zh-Hant", "zh", "en", "en-US", "en-GB"],
    "zh": ["zh-Hans", "zh-Hant", "zh", "en"],
    "en": ["en", "en-US", "en-GB"],
}


@dataclass
class TranscriptBlock:
    id: int
    start: float
    end: float
    text: str
    language: str | None


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _run_metadata(url: str) -> dict[str, Any]:
    command = [
        *yt_dlp_command(),
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        "--no-playlist",
        *_anti_bot_options(url),
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not fetch YouTube metadata")
    return json.loads(result.stdout)


def _language_preferences(language: str | None) -> list[str]:
    value = language or "auto"
    preferences = LANGUAGE_FALLBACKS.get(value, [value, "en"])
    unique: list[str] = []
    seen: set[str] = set()
    for item in [value, *preferences, "en", "zh-Hans", "zh-Hant", "zh"]:
        if item and item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def _subtitle_candidates(raw: dict[str, Any], language: str | None) -> list[dict[str, Any]]:
    subtitles = raw.get("subtitles") if isinstance(raw.get("subtitles"), dict) else {}
    automatic = raw.get("automatic_captions") if isinstance(raw.get("automatic_captions"), dict) else {}
    candidates: list[dict[str, Any]] = []
    for source_name, source in (("subtitle", subtitles), ("automatic subtitle", automatic)):
        for language_code in _language_preferences(language):
            tracks = source.get(language_code) if isinstance(source, dict) else None
            if not isinstance(tracks, list):
                continue
            for track in tracks:
                if isinstance(track, dict) and track.get("url"):
                    candidates.append({**track, "_language": language_code, "_source": source_name})
    return sorted(candidates, key=lambda item: 0 if item.get("ext") == "json3" else 1 if item.get("ext") == "vtt" else 2)


def _fetch_text(url: str) -> str:
    """Fetch subtitle text with browser headers, retry, and backoff.

    YouTube CDN servers may reject requests that lack a plausible User-Agent,
    Referer, or Accept-Language header.  On 429 / 403 we retry with exponential
    backoff + jitter; connection errors also retry.
    """
    settings = get_settings()
    headers = {
        "User-Agent": settings.ytdlp_user_agent or BROWSER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Referer": "https://www.youtube.com/",
    }
    retries = max(1, settings.ytdlp_retries)
    proxy = settings.http_proxy or None
    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        try:
            with httpx.Client(
                timeout=60,
                follow_redirects=True,
                headers=headers,
                proxy=proxy,
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (429, 403) and attempt < retries:
                delay = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(delay)
                continue
            raise
        except httpx.RequestError as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(1 + random.uniform(0, 2))
                continue
    raise last_exc  # type: ignore[misc]


def _parse_json3(payload: str, language: str | None) -> list[TranscriptSegment]:
    data = json.loads(payload)
    events = data.get("events") if isinstance(data, dict) else []
    segments: list[TranscriptSegment] = []
    for event in events:
        if not isinstance(event, dict) or "segs" not in event:
            continue
        text = _clean_text("".join(str(seg.get("utf8") or "") for seg in event.get("segs", []) if isinstance(seg, dict)))
        if not text:
            continue
        start = float(event.get("tStartMs") or 0) / 1000
        duration = float(event.get("dDurationMs") or 0) / 1000
        end = start + duration if duration > 0 else start + 2.5
        segments.append(TranscriptSegment(start=start, end=end, text=text, language=language))
    return segments


def _timestamp_seconds(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    seconds = float(parts[-1])
    if len(parts) >= 2:
        seconds += int(parts[-2]) * 60
    if len(parts) >= 3:
        seconds += int(parts[-3]) * 3600
    return seconds


def _parse_vtt(payload: str, language: str | None) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    blocks = re.split(r"\n\s*\n", payload.replace("\r\n", "\n"))
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((index for index, line in enumerate(lines) if "-->" in line), -1)
        if timing_index < 0:
            continue
        timing = lines[timing_index]
        match = re.match(r"(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}\s+-->\s+((\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3})", timing)
        if not match:
            continue
        start_text, end_text = timing.split("-->", 1)
        text = _clean_text(re.sub(r"<[^>]+>", "", " ".join(lines[timing_index + 1 :])))
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=_timestamp_seconds(start_text.strip().split()[0]),
                end=_timestamp_seconds(end_text.strip().split()[0]),
                text=text,
                language=language,
            )
        )
    return segments


def fetch_youtube_transcript(url: str, language: str | None = None) -> list[TranscriptSegment]:
    """Fetch YouTube subtitles or auto captions without running a speech model."""
    clean_url = _clean_text(url)
    validate_public_http_url(clean_url)
    raw = _run_metadata(clean_url)
    for candidate in _subtitle_candidates(raw, language):
        ext = candidate.get("ext")
        try:
            payload = _fetch_text(candidate["url"])
            track_language = candidate.get("_language") or language
            segments = _parse_json3(payload, track_language) if ext == "json3" else _parse_vtt(payload, track_language)
        except Exception:
            continue
        if segments:
            return segments
    raise RuntimeError("No usable YouTube transcript/subtitle track was found. Use HF/Whisper transcription instead.")


def _build_transcript_blocks(
    segments: list[TranscriptSegment],
    *,
    max_duration: float = 45.0,
    max_chars: int = 1400,
) -> list[TranscriptBlock]:
    blocks: list[TranscriptBlock] = []
    current: list[TranscriptSegment] = []

    def flush() -> None:
        if not current:
            return
        text = _clean_text(" ".join(segment.text for segment in current))
        if text:
            blocks.append(
                TranscriptBlock(
                    id=len(blocks),
                    start=current[0].start,
                    end=current[-1].end,
                    text=text,
                    language=current[0].language,
                )
            )
        current.clear()

    for segment in segments:
        if not _clean_text(segment.text):
            continue
        if current:
            duration = segment.end - current[0].start
            char_count = sum(len(item.text) for item in current) + len(segment.text)
            if duration >= max_duration or char_count >= max_chars:
                flush()
        current.append(segment)
    flush()
    return blocks


def _sanitize_repaired_blocks(payload: Any, originals: list[TranscriptBlock]) -> dict[int, tuple[str, str | None]]:
    raw_items = payload.get("items", payload.get("segments")) if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        raise ValueError("LLM YouTube transcript repair response must contain an items list")

    original_by_id = {block.id: block.text for block in originals}
    repaired: dict[int, tuple[str, str | None]] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if item_id not in original_by_id:
            continue
        text = _clean_text(str(item.get("text") or item.get("corrected_text") or ""))
        original = original_by_id[item_id]
        max_len = max(120, len(original) * 2 + 240)
        raw_speaker = _clean_text(str(item.get("speaker") or ""))
        speaker = raw_speaker if re.fullmatch(r"Speaker \d{1,2}", raw_speaker) else None
        if text and len(text) <= max_len:
            repaired[item_id] = (text, speaker)
    return repaired


def _repair_batch_with_llm(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: dict[str, Any],
    batch: list[TranscriptBlock],
) -> dict[int, tuple[str, str | None]]:
    content = (
        _anthropic_completion(base_url, api_key, model, system_prompt, user_prompt)
        if provider == "anthropic"
        else _openai_compatible_completion(base_url, api_key, model, system_prompt, user_prompt)
    )
    if not _clean_text(content):
        raise ValueError("LLM returned an empty repair response")
    return _sanitize_repaired_blocks(_extract_json_payload(content), batch)


def _strict_repair_batch_with_llm(
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    user_prompt: dict[str, Any],
    batch: list[TranscriptBlock],
) -> dict[int, tuple[str, str | None]]:
    strict_system_prompt = (
        "Return valid JSON only. No markdown, no commentary, no explanation. "
        "Schema: {\"items\":[{\"id\":0,\"speaker\":\"Speaker 1\",\"text\":\"repaired transcript block\"}]}. "
        "Preserve every input id. Speaker must be null or Speaker N. Do not translate, summarize, add facts, or invent names."
    )
    strict_prompt = {
        **user_prompt,
        "retry_instruction": "Previous response was invalid. Return only parseable JSON matching the schema.",
    }
    return _repair_batch_with_llm(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=strict_system_prompt,
        user_prompt=strict_prompt,
        batch=batch,
    )


def repair_youtube_transcript_segments(
    segments: list[TranscriptSegment],
    *,
    infer_speakers: bool = False,
    progress_callback: Callable[[int], None] | None = None,
) -> tuple[list[TranscriptSegment], str | None]:
    """Merge and LLM-repair fast YouTube captions into readable transcript blocks."""
    blocks = _build_transcript_blocks(segments)
    if not blocks:
        return segments, None

    grouped_segments = [
        TranscriptSegment(
            start=block.start,
            end=block.end,
            text=block.text,
            language=block.language,
            speaker="Speaker 1" if infer_speakers else None,
        )
        for block in blocks
    ]

    try:
        provider, base_url, api_key, model = _api_config()
    except Exception as exc:
        return grouped_segments, f"YouTube transcript LLM repair skipped; grouped raw captions were used. {exc}"

    system_prompt = (
        "You are repairing YouTube auto-caption transcript blocks for an editorial transcription app. "
        "Only fix formatting and transcript quality: word boundaries, punctuation, capitalization, line noise, obvious caption glitches, and crypto/finance terms. "
        "Do not translate, summarize, expand, add facts, remove meaning, or invent real speaker names. "
        "Keep each block in the same language as the input. Preserve the id. "
        "If speaker labeling is requested, assign stable generic labels such as Speaker 1, Speaker 2 based only on clear dialogue cues, quote markers, Q&A flow, or topic turns; if uncertain use Speaker 1. "
        "Return JSON only: {\"items\":[{\"id\":0,\"speaker\":\"Speaker 1\",\"text\":\"repaired transcript block\"}]}."
    )

    repaired_by_id: dict[int, tuple[str, str | None]] = {}
    repair_errors: list[str] = []
    batches = _chunks(blocks, 4)
    for batch_index, batch in enumerate(batches):
        try:
            user_prompt = {
                "instructions": [
                    "Return exactly one repaired text for each input id.",
                    "If the input is already fine, return it with only punctuation/capitalization improvements.",
                    "Keep timestamps implicit; do not include timestamps in text.",
                    "Keep quoted speech markers only if they are part of the transcript.",
                    "Speaker labeling requested: yes." if infer_speakers else "Speaker labeling requested: no; speaker may be null.",
                ],
                "items": [
                    {
                        "id": block.id,
                        "start": round(block.start, 2),
                        "end": round(block.end, 2),
                        "language": block.language,
                        "text": block.text,
                    }
                    for block in batch
                ],
            }
            try:
                repaired_by_id.update(
                    _repair_batch_with_llm(
                        provider=provider,
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        batch=batch,
                    )
                )
            except Exception:
                repaired_by_id.update(
                    _strict_repair_batch_with_llm(
                        provider=provider,
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        user_prompt=user_prompt,
                        batch=batch,
                    )
                )
        except Exception as exc:
            repair_errors.append(f"batch {batch[0].id}-{batch[-1].id}: {exc}")
        if progress_callback:
            progress_callback(round(((batch_index + 1) / len(batches)) * 100))

    repaired_segments = [
        TranscriptSegment(
            start=block.start,
            end=block.end,
            text=repaired_by_id.get(block.id, (block.text, None))[0],
            language=block.language,
            speaker=repaired_by_id.get(block.id, (block.text, None))[1] if infer_speakers else None,
        )
        for block in blocks
    ]
    if repair_errors and not repaired_by_id:
        return grouped_segments, f"YouTube transcript LLM repair failed; grouped raw captions were used. {'; '.join(repair_errors[:3])}"
    if repair_errors:
        return repaired_segments, f"YouTube transcript LLM repair partially failed; raw grouped captions were used for some blocks. {'; '.join(repair_errors[:3])}"
    return repaired_segments, None
