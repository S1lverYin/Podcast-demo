from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.database import get_db
from app.schemas import (
    JOB_STATUSES,
    SUPPORTED_LANGUAGES,
    JobQueuedResponse,
    ParagraphRegenerateRequest,
    JobRead,
    ParagraphRead,
    SegmentRead,
    SegmentUpdate,
    PodcastNoteGenerateRequest,
    PodcastNoteRead,
    TranslateRequest,
    UrlJobRequest,
)
from app.services.downloader import validate_public_http_url
from app.services.paragraphing import build_transcript_paragraphs
from app.services.podcast_notes import generate_podcast_note
from app.services.translator import translate_text
from app.workers.tasks import process_transcription_job, run_job


router = APIRouter()

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".aac"}
ALLOWED_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def _validate_language(language: str | None) -> str:
    value = language or "auto"
    if value not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"language must be one of {sorted(SUPPORTED_LANGUAGES)}",
        )
    return value


def _safe_upload_path(job_id: str, filename: str) -> Path:
    settings = get_settings()
    safe_name = Path(filename or "upload.bin").name
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type {extension or '(none)'}. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )
    return settings.storage_path / "uploads" / f"{job_id}{extension}"


def _enqueue(job_id: str, background_tasks: BackgroundTasks, db: Session) -> None:
    settings = get_settings()
    if settings.run_tasks_inline:
        background_tasks.add_task(run_job, job_id)
        return

    try:
        process_transcription_job.delay(job_id)
    except Exception as exc:  # pragma: no cover - depends on Redis availability
        job = db.get(models.Job, job_id)
        if job:
            job.warning_message = f"Redis/Celery enqueue failed; running in FastAPI background task. {exc}"
            db.commit()
        background_tasks.add_task(run_job, job_id)


def _get_job_or_404(db: Session, job_id: str) -> models.Job:
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/upload", response_model=JobQueuedResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str | None = Form(default="auto"),
    enable_diarization: bool = Form(default=True),
    enable_translation: bool = Form(default=False),
    m1_optimized: bool = Form(default=False),
    db: Session = Depends(get_db),
) -> JobQueuedResponse:
    """Create a transcription job from an uploaded local media file."""
    language_value = _validate_language(language)
    job = models.Job(
        source_type="upload",
        original_filename=file.filename,
        language=language_value,
        enable_diarization=enable_diarization,
        enable_translation=enable_translation,
        m1_optimized=m1_optimized,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    destination = _safe_upload_path(job.id, file.filename or "upload")
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    try:
        with destination.open("wb") as output:
            written = 0
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(f"Uploaded file exceeds {get_settings().max_upload_mb} MB")
                output.write(chunk)
    except ValueError as exc:
        destination.unlink(missing_ok=True)
        job.status = "failed"
        job.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    except Exception as exc:
        destination.unlink(missing_ok=True)
        job.status = "failed"
        job.error_message = f"Could not save uploaded file: {exc}"
        db.commit()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=job.error_message) from exc
    finally:
        file.file.close()

    job.media_path = str(destination)
    db.commit()
    _enqueue(job.id, background_tasks, db)
    return JobQueuedResponse(job_id=job.id, status=job.status)


@router.post("/from-url", response_model=JobQueuedResponse, status_code=status.HTTP_202_ACCEPTED)
def create_from_url(
    payload: UrlJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobQueuedResponse:
    """Create a transcription job from a public URL handled by yt-dlp."""
    validate_public_http_url(payload.url)
    job = models.Job(
        source_type="url",
        source_url=payload.url,
        language=payload.language,
        enable_diarization=payload.enable_diarization,
        enable_translation=payload.enable_translation,
        m1_optimized=payload.m1_optimized,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    _enqueue(job.id, background_tasks, db)
    return JobQueuedResponse(job_id=job.id, status=job.status)


@router.get("", response_model=list[JobRead])
def list_jobs(db: Session = Depends(get_db)) -> list[models.Job]:
    """Return jobs ordered by newest first."""
    return list(db.scalars(select(models.Job).order_by(models.Job.created_at.desc())).all())


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Session = Depends(get_db)) -> models.Job:
    """Return a single job."""
    return _get_job_or_404(db, job_id)


@router.get("/{job_id}/segments", response_model=list[SegmentRead])
def list_segments(job_id: str, db: Session = Depends(get_db)) -> list[models.TranscriptSegment]:
    """Return transcript segments for a job."""
    _get_job_or_404(db, job_id)
    statement = (
        select(models.TranscriptSegment)
        .where(models.TranscriptSegment.job_id == job_id)
        .order_by(models.TranscriptSegment.order_index, models.TranscriptSegment.start)
    )
    return list(db.scalars(statement).all())


@router.patch("/{job_id}/segments/{segment_id}", response_model=SegmentRead)
def update_segment(
    job_id: str,
    segment_id: int,
    payload: SegmentUpdate,
    db: Session = Depends(get_db),
) -> models.TranscriptSegment:
    """Save an edited transcript segment."""
    _get_job_or_404(db, job_id)
    segment = db.get(models.TranscriptSegment, segment_id)
    if not segment or segment.job_id != job_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")
    segment.text = payload.text
    if "translated_text" in payload.model_fields_set:
        segment.translated_text = payload.translated_text
    db.commit()
    db.refresh(segment)
    return segment


@router.post("/{job_id}/segments/{segment_id}/translate", response_model=SegmentRead)
def translate_segment(
    job_id: str,
    segment_id: int,
    payload: TranslateRequest | None = None,
    db: Session = Depends(get_db),
) -> models.TranscriptSegment:
    """Translate one transcript segment on demand."""
    job = _get_job_or_404(db, job_id)
    segment = db.get(models.TranscriptSegment, segment_id)
    if not segment or segment.job_id != job_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")
    request = payload or TranslateRequest()
    if segment.translated_text and not request.force:
        return segment
    try:
        segment.translated_text = translate_text(
            segment.text,
            source_language=segment.language or job.language,
            target_language=request.target_language,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(segment)
    return segment


@router.post("/{job_id}/retry", response_model=JobQueuedResponse)
def retry_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobQueuedResponse:
    """Clear transcript segments and enqueue the job again."""
    job = _get_job_or_404(db, job_id)
    if job.status not in JOB_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job status")
    db.execute(delete(models.TranscriptSegment).where(models.TranscriptSegment.job_id == job_id))
    db.execute(delete(models.TranscriptParagraph).where(models.TranscriptParagraph.job_id == job_id))
    db.execute(delete(models.PodcastNote).where(models.PodcastNote.job_id == job_id))
    job.status = "queued"
    job.error_message = None
    job.warning_message = None
    job.completed_at = None
    db.commit()
    _enqueue(job_id, background_tasks, db)
    return JobQueuedResponse(job_id=job.id, status=job.status)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a job, transcript rows, and known generated files."""
    job = _get_job_or_404(db, job_id)
    for path_value in (job.media_path, job.audio_path):
        if not path_value:
            continue
        try:
            Path(path_value).unlink(missing_ok=True)
        except OSError:
            pass
    db.delete(job)
    db.commit()


@router.delete("/{job_id}/transcript", status_code=status.HTTP_204_NO_CONTENT)
def clear_transcript(job_id: str, db: Session = Depends(get_db)) -> None:
    """Delete transcript-derived text for a job while keeping the job and audio files."""
    job = _get_job_or_404(db, job_id)
    if job.status not in {"completed", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete transcript content while the job is still running",
        )
    db.execute(delete(models.TranscriptSegment).where(models.TranscriptSegment.job_id == job_id))
    db.execute(delete(models.TranscriptParagraph).where(models.TranscriptParagraph.job_id == job_id))
    db.execute(delete(models.PodcastNote).where(models.PodcastNote.job_id == job_id))
    db.commit()


@router.get("/{job_id}/paragraphs", response_model=list[ParagraphRead])
def list_paragraphs(job_id: str, db: Session = Depends(get_db)) -> list[models.TranscriptParagraph]:
    """Return paragraph-level transcript output for a job."""
    _get_job_or_404(db, job_id)
    statement = (
        select(models.TranscriptParagraph)
        .where(models.TranscriptParagraph.job_id == job_id)
        .order_by(models.TranscriptParagraph.order_index, models.TranscriptParagraph.start)
    )
    return list(db.scalars(statement).all())


@router.post("/{job_id}/paragraphs/regenerate", response_model=list[ParagraphRead])
def regenerate_paragraphs(
    job_id: str,
    payload: ParagraphRegenerateRequest | None = None,
    db: Session = Depends(get_db),
) -> list[models.TranscriptParagraph]:
    """Regenerate paragraph-level transcript output from current transcript segments."""
    _get_job_or_404(db, job_id)
    segments = list(
        db.scalars(
            select(models.TranscriptSegment)
            .where(models.TranscriptSegment.job_id == job_id)
            .order_by(models.TranscriptSegment.order_index, models.TranscriptSegment.start)
        ).all()
    )
    if not segments:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No transcript segments to segment")

    selected_mode = payload.mode if payload and payload.mode not in {None, "auto"} else None
    try:
        paragraph_drafts = build_transcript_paragraphs(
            segments,
            mode=selected_mode,
            split_on_speaker=payload.split_on_speaker if payload else None,
            allow_llm_fallback=selected_mode != "llm",
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.execute(delete(models.TranscriptParagraph).where(models.TranscriptParagraph.job_id == job_id))
    for index, paragraph in enumerate(paragraph_drafts):
        db.add(
            models.TranscriptParagraph(
                job_id=job_id,
                order_index=index,
                start=paragraph.start,
                end=paragraph.end,
                speaker=paragraph.speaker,
                title=paragraph.title,
                summary=paragraph.summary,
                text=paragraph.text,
                translated_text=paragraph.translated_text,
            )
        )
    db.commit()
    statement = (
        select(models.TranscriptParagraph)
        .where(models.TranscriptParagraph.job_id == job_id)
        .order_by(models.TranscriptParagraph.order_index, models.TranscriptParagraph.start)
    )
    return list(db.scalars(statement).all())


@router.get("/{job_id}/podcast-notes", response_model=list[PodcastNoteRead])
def list_podcast_notes(job_id: str, db: Session = Depends(get_db)) -> list[models.PodcastNote]:
    """Return generated podcast notes for a job, newest first."""
    _get_job_or_404(db, job_id)
    statement = (
        select(models.PodcastNote)
        .where(models.PodcastNote.job_id == job_id)
        .order_by(models.PodcastNote.created_at.desc(), models.PodcastNote.id.desc())
    )
    return list(db.scalars(statement).all())


@router.delete("/{job_id}/podcast-notes", status_code=status.HTTP_204_NO_CONTENT)
def clear_podcast_notes(job_id: str, db: Session = Depends(get_db)) -> None:
    """Delete all generated podcast notes for a job."""
    _get_job_or_404(db, job_id)
    db.execute(delete(models.PodcastNote).where(models.PodcastNote.job_id == job_id))
    db.commit()


@router.post("/{job_id}/podcast-notes/generate", response_model=PodcastNoteRead)
def generate_job_podcast_note(
    job_id: str,
    payload: PodcastNoteGenerateRequest | None = None,
    db: Session = Depends(get_db),
) -> models.PodcastNote:
    """Generate and persist a long-form podcast note from current transcript rows."""
    job = _get_job_or_404(db, job_id)
    segments = list(
        db.scalars(
            select(models.TranscriptSegment)
            .where(models.TranscriptSegment.job_id == job_id)
            .order_by(models.TranscriptSegment.order_index, models.TranscriptSegment.start)
        ).all()
    )
    if not segments:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No transcript segments for podcast notes")

    paragraphs = list(
        db.scalars(
            select(models.TranscriptParagraph)
            .where(models.TranscriptParagraph.job_id == job_id)
            .order_by(models.TranscriptParagraph.order_index, models.TranscriptParagraph.start)
        ).all()
    )
    request = payload or PodcastNoteGenerateRequest()
    title = request.original_title or job.original_filename or job.source_url
    source_url = request.source_url or job.source_url
    try:
        draft = generate_podcast_note(
            segments=segments,
            paragraphs=paragraphs,
            podcast_source=request.podcast_source,
            original_title=title,
            published_date=request.published_date,
            host=request.host,
            guests=request.guests,
            source_url=source_url,
            chapter_outline=request.chapter_outline,
            auto_map_speakers=request.auto_map_speakers,
            lookup_source_metadata=request.lookup_source_metadata,
            include_full_dialogue=request.include_full_dialogue,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if request.clear_existing_notes:
        db.execute(delete(models.PodcastNote).where(models.PodcastNote.job_id == job_id))

    note = models.PodcastNote(
        job_id=job_id,
        title=draft.title,
        markdown=draft.markdown,
        metadata_json=draft.metadata_json,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.post("/{job_id}/paragraphs/{paragraph_id}/translate", response_model=ParagraphRead)
def translate_paragraph(
    job_id: str,
    paragraph_id: int,
    payload: TranslateRequest | None = None,
    db: Session = Depends(get_db),
) -> models.TranscriptParagraph:
    """Translate one paragraph-level transcript block on demand."""
    job = _get_job_or_404(db, job_id)
    paragraph = db.get(models.TranscriptParagraph, paragraph_id)
    if not paragraph or paragraph.job_id != job_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paragraph not found")
    request = payload or TranslateRequest()
    if paragraph.translated_text and not request.force:
        return paragraph
    try:
        paragraph.translated_text = translate_text(
            paragraph.text,
            source_language=job.language,
            target_language=request.target_language,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(paragraph)
    return paragraph
