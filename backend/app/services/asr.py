import logging
import os
import sys
import time
from collections.abc import Callable

from app.config import get_settings
from app.schemas import TranscriptSegment


logger = logging.getLogger(__name__)


def _ensure_cublas_on_path() -> None:
    """Register nvidia cublas DLL directory so ctranslate2 can load it on GPU.

    On Windows, the nvidia namespace package has __file__ = None, so we walk
    sys.path to locate the cublas bin directory.
    """
    for base in sys.path:
        candidate = os.path.join(base, "nvidia", "cublas", "bin")
        if os.path.isdir(candidate):
            try:
                os.add_dll_directory(candidate)
            except (AttributeError, OSError):
                pass
            os.environ["PATH"] = candidate + os.pathsep + os.environ.get("PATH", "")
            logger.debug("Registered cublas DLL directory: %s", candidate)
            return
    logger.debug("nvidia-cublas-cu12 not found on sys.path, cublas DLL not registered")


def transcribe_audio(
    audio_path: str,
    language: str | None = None,
    model_size: str = "large-v3",
    compute_type: str | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> list[TranscriptSegment]:
    """Transcribe an audio file with faster-whisper and return timestamped segments.

    Args:
        audio_path: Path to 16kHz mono WAV file.
        language: Language code or None for auto-detect.
        model_size: faster-whisper model size (tiny, base, small, medium, large-v3).
        compute_type: Optional override for faster-whisper compute_type (e.g. "int8", "float16", "auto").
                      When None, falls back to the global WHISPER_COMPUTE_TYPE setting.
        progress_callback: Called with 0-100 percent during transcription.
    """
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

    # Register CUDA libs BEFORE importing ctranslate2 / faster-whisper
    _ensure_cublas_on_path()

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("faster-whisper is not installed. Install backend requirements first.") from exc

    settings = get_settings()
    load_started = time.perf_counter()
    effective_compute_type = compute_type or settings.whisper_compute_type
    logger.info("Loading faster-whisper model '%s' device=%s compute_type=%s",
                model_size, settings.whisper_device, effective_compute_type)
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

    if progress_callback:
        progress_callback(0)

    segments_iter, info = model.transcribe(audio_path, **transcribe_kwargs)
    detected_language = getattr(info, "language", None)
    duration = float(getattr(info, "duration", 0.0) or 0.0)
    last_progress = -1
    segments: list[TranscriptSegment] = []
    for segment in segments_iter:
        segments.append(
            TranscriptSegment(
                start=float(segment.start),
                end=float(segment.end),
                text=segment.text.strip(),
                language=detected_language,
            )
        )
        if progress_callback and duration > 0:
            progress = min(99, max(0, int((float(segment.end) / duration) * 100)))
            if progress >= last_progress + 2:
                progress_callback(progress)
                last_progress = progress

    if progress_callback:
        progress_callback(100)
    logger.info("Transcribed %s segments in %.2fs", len(segments), time.perf_counter() - inference_started)
    return segments
