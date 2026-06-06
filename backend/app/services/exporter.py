import json
from typing import Literal

from app import models
from app.utils.time_format import display_timestamp, srt_timestamp, vtt_timestamp


ExportFormat = Literal["txt", "srt", "vtt", "json", "md", "paragraph_md", "paragraph_json"]


def _speaker_prefix(segment: models.TranscriptSegment) -> str:
    return f"{segment.speaker}: " if segment.speaker else ""


def _txt(segments: list[models.TranscriptSegment]) -> str:
    lines = []
    for segment in segments:
        lines.append(
            f"[{display_timestamp(segment.start)} - {display_timestamp(segment.end)}] "
            f"{_speaker_prefix(segment)}{segment.text}"
        )
        if segment.translated_text:
            lines.append(f"译文: {segment.translated_text}")
    return "\n".join(lines) + "\n"


def _srt(segments: list[models.TranscriptSegment]) -> str:
    blocks = []
    for index, segment in enumerate(segments, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{srt_timestamp(segment.start)} --> {srt_timestamp(segment.end)}",
                    f"{_speaker_prefix(segment)}{segment.text}",
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def _vtt(segments: list[models.TranscriptSegment]) -> str:
    blocks = ["WEBVTT\n"]
    for segment in segments:
        blocks.append(
            "\n".join(
                [
                    f"{vtt_timestamp(segment.start)} --> {vtt_timestamp(segment.end)}",
                    f"{_speaker_prefix(segment)}{segment.text}",
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def _json(job: models.Job, segments: list[models.TranscriptSegment]) -> str:
    payload = {
        "job": {
            "id": job.id,
            "source_type": job.source_type,
            "source_url": job.source_url,
            "original_filename": job.original_filename,
            "language": job.language,
            "status": job.status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        },
        "segments": [
            {
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "speaker": segment.speaker,
                "text": segment.text,
                "translated_text": segment.translated_text,
                "language": segment.language,
            }
            for segment in segments
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _markdown(job: models.Job, segments: list[models.TranscriptSegment]) -> str:
    title = job.original_filename or job.source_url or job.id
    lines = [f"# Transcript: {title}", ""]
    for segment in segments:
        lines.extend(
            [
                f"**{display_timestamp(segment.start)} - {display_timestamp(segment.end)} "
                f"{segment.speaker or 'Speaker 1'}**",
                "",
                segment.text,
                "",
            ]
        )
        if segment.translated_text:
            lines.extend([f"> {segment.translated_text}", ""])
    return "\n".join(lines).strip() + "\n"


def _paragraph_json(job: models.Job, paragraphs: list[models.TranscriptParagraph]) -> str:
    payload = {
        "job": {
            "id": job.id,
            "source_type": job.source_type,
            "source_url": job.source_url,
            "original_filename": job.original_filename,
            "language": job.language,
            "status": job.status,
        },
        "paragraphs": [
            {
                "id": paragraph.id,
                "start": paragraph.start,
                "end": paragraph.end,
                "speaker": paragraph.speaker,
                "title": paragraph.title,
                "summary": paragraph.summary,
                "text": paragraph.text,
                "translated_text": paragraph.translated_text,
            }
            for paragraph in paragraphs
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _paragraph_markdown(job: models.Job, paragraphs: list[models.TranscriptParagraph]) -> str:
    title = job.original_filename or job.source_url or job.id
    lines = [f"# Paragraph Transcript: {title}", ""]
    for paragraph in paragraphs:
        heading = paragraph.title or f"{display_timestamp(paragraph.start)} - {display_timestamp(paragraph.end)}"
        lines.extend(
            [
                f"## {heading}",
                "",
                f"`{display_timestamp(paragraph.start)} - {display_timestamp(paragraph.end)}`"
                + (f" `{paragraph.speaker}`" if paragraph.speaker else ""),
                "",
            ]
        )
        if paragraph.translated_text:
            lines.extend([paragraph.translated_text, "", "<details>", "<summary>Original</summary>", "", paragraph.text, "", "</details>", ""])
        else:
            lines.extend([paragraph.text, ""])
    return "\n".join(lines).strip() + "\n"


def build_export(
    job: models.Job,
    segments: list[models.TranscriptSegment],
    format: ExportFormat,
    paragraphs: list[models.TranscriptParagraph] | None = None,
) -> tuple[str, str, str]:
    """Build export content, media type, and file extension for a job."""
    if format == "txt":
        return _txt(segments), "text/plain; charset=utf-8", "txt"
    if format == "srt":
        return _srt(segments), "application/x-subrip; charset=utf-8", "srt"
    if format == "vtt":
        return _vtt(segments), "text/vtt; charset=utf-8", "vtt"
    if format == "json":
        return _json(job, segments), "application/json; charset=utf-8", "json"
    if format == "md":
        return _markdown(job, segments), "text/markdown; charset=utf-8", "md"
    if format == "paragraph_json":
        return _paragraph_json(job, paragraphs or []), "application/json; charset=utf-8", "paragraphs.json"
    if format == "paragraph_md":
        return _paragraph_markdown(job, paragraphs or []), "text/markdown; charset=utf-8", "paragraphs.md"
    raise ValueError(f"Unsupported export format: {format}")
