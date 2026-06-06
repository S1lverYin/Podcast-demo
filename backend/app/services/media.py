import logging
import shutil
import subprocess
from pathlib import Path


logger = logging.getLogger(__name__)


def ensure_ffmpeg() -> str:
    """Return the ffmpeg executable path or raise a clear error."""
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("ffmpeg is not installed or is not available on PATH")
    return executable


def extract_audio(input_path: str, output_path: str) -> str:
    """Extract media audio as 16 kHz mono WAV using ffmpeg."""
    ffmpeg = ensure_ffmpeg()
    source = Path(input_path)
    destination = Path(output_path)
    if not source.exists():
        raise FileNotFoundError(f"Input media file does not exist: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    command = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(destination),
    ]
    logger.info("Extracting audio with ffmpeg: %s -> %s", source, destination)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.error("ffmpeg failed: %s", result.stderr)
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip() or 'unknown error'}")
    return str(destination)
