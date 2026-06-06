import logging
import inspect

from app.config import get_settings
from app.schemas import DiarizationSegment


logger = logging.getLogger(__name__)

DIARIZATION_MODEL_ID = "pyannote/speaker-diarization-community-1"


def _exception_chain_text(exc: BaseException) -> str:
    messages: list[str] = []
    current: BaseException | None = exc
    while current:
        messages.append(str(current))
        current = current.__cause__ or current.__context__
    return "\n".join(messages)


def diarize_audio(audio_path: str) -> list[DiarizationSegment]:
    """Run speaker diarization with pyannote.audio if HF_TOKEN is configured."""
    settings = get_settings()
    if not settings.hf_token:
        logger.info("Skipping speaker diarization because HF_TOKEN is not configured")
        return []

    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:  # pragma: no cover - depends on optional runtime deps
        raise RuntimeError("pyannote.audio is not installed. Install backend requirements first.") from exc

    logger.info("Loading pyannote speaker diarization pipeline")
    pipeline_kwargs = {"token": settings.hf_token}
    if "token" not in inspect.signature(Pipeline.from_pretrained).parameters:
        pipeline_kwargs = {"use_auth_token": settings.hf_token}
    try:
        pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL_ID, **pipeline_kwargs)
    except Exception as exc:
        details = _exception_chain_text(exc).lower()
        if "403" in details or "gated" in details or "forbidden" in details:
            raise RuntimeError(
                "Could not load pyannote speaker diarization pipeline. "
                "HF_TOKEN must have access to public gated Hugging Face repositories, "
                f"and the {DIARIZATION_MODEL_ID} model terms must be accepted."
            ) from exc
        raise RuntimeError(f"Could not load pyannote speaker diarization pipeline: {exc}") from exc
    if pipeline is None:
        raise RuntimeError("Could not load pyannote speaker diarization pipeline. Check HF_TOKEN and model access.")
    result = pipeline(audio_path)
    diarization = (
        getattr(result, "exclusive_speaker_diarization", None)
        or getattr(result, "speaker_diarization", None)
        or result
    )

    speaker_names: dict[str, str] = {}
    segments: list[DiarizationSegment] = []
    for turn, _, raw_speaker in diarization.itertracks(yield_label=True):
        if raw_speaker not in speaker_names:
            speaker_names[raw_speaker] = f"Speaker {len(speaker_names) + 1}"
        segments.append(
            DiarizationSegment(
                start=float(turn.start),
                end=float(turn.end),
                speaker=speaker_names[raw_speaker],
            )
        )
    logger.info("Diarization produced %s speaker segments", len(segments))
    return segments
