import logging
import os
import time

from app.config import get_settings
from app.schemas import TranscriptSegment


logger = logging.getLogger(__name__)


def transcribe_audio(
    audio_path: str,
    language: str | None = None,
    model_size: str = "large-v3",
    compute_type: str | None = None,
) -> list[TranscriptSegment]:
    """Transcribe an audio file with faster-whisper and return timestamped segments.

    Args:
        audio_path: Path to 16kHz mono WAV file.
        language: Language code or None for auto-detect.
        model_size: faster-whisper model size (tiny, base, small, medium, large-v3).
        compute_type: Optional override for faster-whisper compute_type (e.g. "int8").
                      When None, falls back to the global WHISPER_COMPUTE_TYPE setting.
    """
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on optional runtime deps
        raise RuntimeError("faster-whisper is not installed. Install backend requirements first.") from exc

    settings = get_settings()
    load_started = time.perf_counter()
    effective_compute_type = compute_type or settings.whisper_compute_type
    logger.info("Loading faster-whisper model '%s' (compute_type=%s)", model_size, effective_compute_type)
    model = WhisperModel(
        model_size,
        device=settings.whisper_device,
        compute_type=effective_compute_type,
    )
    logger.info("Loaded faster-whisper model in %.2fs", time.perf_counter() - load_started)

    inference_started = time.perf_counter()
    transcribe_kwargs: dict[str, object] = {
        "vad_filter": True,
        "word_timestamps": True,
    }
    if settings.whisper_initial_prompt and settings.whisper_initial_prompt.strip():
        transcribe_kwargs["initial_prompt"] = settings.whisper_initial_prompt.strip()
    if language and language != "auto":
        transcribe_kwargs["language"] = language

    segments_iter, info = model.transcribe(audio_path, **transcribe_kwargs)
    detected_language = getattr(info, "language", None)
    segments = [
        TranscriptSegment(
            start=float(segment.start),
            end=float(segment.end),
            text=segment.text.strip(),
            language=detected_language,
        )
        for segment in segments_iter
    ]
    logger.info("Transcribed %s segments in %.2fs", len(segments), time.perf_counter() - inference_started)
    return segments
