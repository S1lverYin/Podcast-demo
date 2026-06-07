import functools
import inspect
import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.schemas import DiarizationSegment

logger = logging.getLogger(__name__)
DIARIZATION_MODEL_ID = "pyannote/speaker-diarization-community-1"


def _patch_hf_hub_download():
    try:
        from huggingface_hub import hf_hub_download as _orig
    except ImportError:
        return
    if "use_auth_token" in inspect.signature(_orig).parameters:
        return
    @functools.wraps(_orig)
    def _patched(*args, **kwargs):
        if "use_auth_token" in kwargs:
            kwargs["token"] = kwargs.pop("use_auth_token")
        return _orig(*args, **kwargs)
    import huggingface_hub
    huggingface_hub.hf_hub_download = _patched


def _llm_diarize(segments_text, provider, base_url, api_key, model):
    system_prompt = (
    "You are a precise speaker diarization system. "
    "Given transcript segments, assign the correct speaker name to each segment. "
    "1. Extract REAL names from self-introductions (e.g. I am John Smith, CEO of...), NOT generic Speaker A. "
    "2. If no name found, use a role label like Host, Interviewer, Guest, Expert. "
    "3. Maintain CONSISTENT labels for the same person across all segments. "
    "4. Look for turn-taking and question-answer patterns. "
    '5. Return ONLY a JSON object: {"segments":[{"start":0.0,"end":5.0,"speaker":"Name"},...]}. '
    "6. Include every input segment, do not skip or reorder. "
    "7. Keep original start/end values exactly."
)

    items = [
        {"id": i, "start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"]}
        for i, s in enumerate(segments_text)
    ]

    if provider == "anthropic":
        resp = httpx.post(
            f"{base_url}/messages",
            headers={
                "x-api-key": api_key, "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model, "max_tokens": 8192, "temperature": 0,
                "system": system_prompt,
                "messages": [{"role": "user", "content": json.dumps({"segments": items}, ensure_ascii=False)}],
            },
            timeout=300,
        )
    else:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model, "temperature": 0,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps({"segments": items}, ensure_ascii=False)},
                ],
            },
            timeout=300,
        )
    resp.raise_for_status()

    if provider == "anthropic":
        blocks = resp.json().get("content", [])
        raw = "\n".join(str(b.get("text", "")) for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    else:
        raw = resp.json()["choices"][0]["message"]["content"]

    for bracket in ("```json", "```"):
        if bracket in raw:
            raw = raw.split(bracket, 1)[1].split("```", 1)[0].strip()
            break

    json_match = None
    if raw.startswith("{"):
        try:
            json_match = json.loads(raw)
        except json.JSONDecodeError:
            import re as _re
            m = _re.search(r"\{[\s\S]*\}", raw)
            if m:
                try:
                    json_match = json.loads(m.group())
                except json.JSONDecodeError:
                    pass

    if not json_match or not isinstance(json_match, dict):
        raise RuntimeError("LLM diarization returned unparseable response")

    segs = json_match.get("segments", json_match.get("items", []))
    if not isinstance(segs, list):
        raise RuntimeError("LLM diarization response missing segments list")

    return [
        DiarizationSegment(
            start=float(s.get("start", 0)),
            end=float(s.get("end", 0)),
            speaker=str(s.get("speaker", "Unknown")),
        )
        for s in segs if isinstance(s, dict)
    ]


def diarize_audio(audio_path, transcript_hint=None):
    """Run speaker diarization. Falls back to LLM if pyannote is unavailable."""
    settings = get_settings()
    if not settings.hf_token:
        logger.info("Skipping diarization: HF_TOKEN not configured")
        return []

    # Try pyannote first
    try:
        _patch_hf_hub_download()
        from pyannote.audio import Pipeline
    except ImportError:
        pass
    else:
        try:
            import torchaudio
            _ = torchaudio.load(audio_path)
        except Exception:
            pass
        else:
            try:
                logger.info("Loading pyannote pipeline")
                kwargs = {"use_auth_token": settings.hf_token}
                pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL_ID, **kwargs)
                result = pipeline(audio_path)
                diarization = (
                    getattr(result, "exclusive_speaker_diarization", None)
                    or getattr(result, "speaker_diarization", None)
                    or result
                )
                speaker_names = {}
                segments = []
                for turn, _, raw_speaker in diarization.itertracks(yield_label=True):
                    if raw_speaker not in speaker_names:
                        speaker_names[raw_speaker] = f"Speaker {len(speaker_names) + 1}"
                    segments.append(DiarizationSegment(
                        start=float(turn.start), end=float(turn.end),
                        speaker=speaker_names[raw_speaker],
                    ))
                logger.info("pyannote: %s segments", len(segments))
                return segments
            except Exception as exc:
                logger.warning("pyannote failed: %s", exc)

    # LLM fallback
    if transcript_hint and len(transcript_hint) >= 2:
        provider = (settings.diarization_api_provider or settings.paragraphing_api_provider).lower().strip()
        if provider not in {"openai", "anthropic"}:
            provider = "openai"
        base_url = (settings.diarization_api_base_url or settings.paragraphing_api_base_url or settings.translation_api_base_url).rstrip("/")
        api_key = settings.diarization_api_key or settings.paragraphing_api_key or settings.translation_api_key
        model = settings.diarization_api_model or settings.paragraphing_api_model or settings.translation_api_model

        if api_key and model:
            logger.info("Using LLM diarization fallback")
            return _llm_diarize(transcript_hint, provider, base_url, api_key, model)
        else:
            raise RuntimeError("pyannote unavailable and no LLM API key configured for fallback")
    else:
        raise RuntimeError("pyannote unavailable and no transcript for LLM fallback")
