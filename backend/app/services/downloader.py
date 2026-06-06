import logging
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, status


logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def validate_public_http_url(url: str) -> None:
    """Validate that a URL is HTTP(S) and suitable for public user-provided media extraction."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="URL must be a valid http or https URL",
        )
    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="URLs with embedded credentials are not supported",
        )


def yt_dlp_command() -> list[str]:
    """Return a yt-dlp command, falling back to the current Python environment."""
    executable = shutil.which("yt-dlp")
    if executable:
        return [executable]
    venv_executable = Path(sys.prefix) / "bin" / "yt-dlp"
    if venv_executable.exists():
        return [str(venv_executable)]
    try:
        import yt_dlp  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on runtime env
        raise RuntimeError("yt-dlp is not installed or is not available on PATH") from exc
    return [sys.executable, "-m", "yt_dlp"]


def _is_bilibili_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith("bilibili.com") or host.endswith("b23.tv")


def _site_options(url: str) -> list[str]:
    """Return conservative site-specific yt-dlp options."""
    if not _is_bilibili_url(url):
        return []
    return [
        "--user-agent",
        BROWSER_USER_AGENT,
        "--referer",
        "https://www.bilibili.com/",
        "--add-header",
        "Origin:https://www.bilibili.com",
        "--add-header",
        "Accept-Language:zh-CN,zh;q=0.9,en;q=0.8",
        "--extractor-retries",
        "3",
        "--force-ipv4",
    ]


def download_audio_from_url(url: str, output_dir: str) -> str:
    """Download publicly accessible media audio with yt-dlp.

    This function does not pass cookies, credentials, or DRM bypass flags. It is intended only
    for public content or content the user has the right to process.
    """
    validate_public_http_url(url)
    yt_dlp = yt_dlp_command()
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    output_template = str(destination / "%(id)s.%(ext)s")
    command = [
        *yt_dlp,
        "--no-playlist",
        "--no-warnings",
        "--extract-audio",
        "--audio-format",
        "wav",
        "--audio-quality",
        "0",
        "-o",
        output_template,
        *_site_options(url),
        url,
    ]
    logger.info("Downloading URL audio with yt-dlp: %s", url)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        logger.error("yt-dlp failed: %s", result.stderr)
        site_hint = ""
        if _is_bilibili_url(url):
            site_hint = (
                " Bilibili sometimes returns HTTP 412 to non-browser public requests. "
                "This app will not use cookies, login credentials, paid-wall access, or DRM bypass."
            )
        raise RuntimeError(
            "Could not download audio from URL. The site may be unsupported, private, "
            f"DRM-protected, or temporarily unavailable.{site_hint} yt-dlp said: {result.stderr.strip()}"
        )

    candidates = sorted(destination.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".webm"}:
            return str(candidate)
    raise RuntimeError("yt-dlp completed but no downloadable audio file was found")
