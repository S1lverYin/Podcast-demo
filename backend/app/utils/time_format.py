def _split_seconds(seconds: float) -> tuple[int, int, int, int]:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return hours, minutes, whole_seconds, milliseconds


def display_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS for transcript display."""
    hours, minutes, whole_seconds, _ = _split_seconds(seconds)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}"


def srt_timestamp(seconds: float) -> str:
    """Format seconds as an SRT timestamp."""
    hours, minutes, whole_seconds, milliseconds = _split_seconds(seconds)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def vtt_timestamp(seconds: float) -> str:
    """Format seconds as a WebVTT timestamp."""
    hours, minutes, whole_seconds, milliseconds = _split_seconds(seconds)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
