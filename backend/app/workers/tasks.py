import logging
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.database import SessionLocal
from app.services.alignment import assign_speakers_to_transcript
from app.services.asr import transcribe_audio
from app.services.diarization import diarize_audio
from app.services.downloader import download_audio_from_url
from app.services.media import extract_audio
from app.services.paragraphing import build_transcript_paragraphs
from app.services.transcript_correction import correct_transcript_segments
from app.services.translator import translate_transcript_segments
from app.services.youtube_transcript import fetch_youtube_transcript, repair_youtube_transcript_segments
from app.workers.celery_app import celery_app


logger = logging.getLogger(__name__)


def _set_status(
    db: Session,
    job: models.Job,
    status: str,
    message: str | None = None,
    progress_percent: int | None = None,
) -> None:
    job.status = status
    if progress_percent is not None:
        job.progress_percent = progress_percent
    if message:
        job.warning_message = message
    db.commit()
    logger.info("Job %s status -> %s", job.id, status)


def _stage_progress(
    db: Session,
    job: models.Job,
    stage_start: int,
    stage_end: int,
    stage_pct: int,
) -> None:
    """Compute overall progress from weighted stage boundaries and stage-internal 0-100 percent."""
    overall = int(stage_start + (stage_end - stage_start) * stage_pct / 100)
    clamped = min(100, max(0, overall))
    if job.progress_percent is not None and clamped < 100 and clamped <= job.progress_percent:
        return  # never go backwards
    job.progress_percent = clamped
    db.commit()


def _append_warning(job: models.Job, message: str) -> None:
    job.warning_message = f"{job.warning_message}\n{message}" if job.warning_message else message


def _persist_transcript(db: Session, job: models.Job, transcript_segments) -> None:
    paragraph_drafts = build_transcript_paragraphs(transcript_segments)

    db.execute(delete(models.TranscriptSegment).where(models.TranscriptSegment.job_id == job.id))
    db.execute(delete(models.TranscriptParagraph).where(models.TranscriptParagraph.job_id == job.id))
    for index, segment in enumerate(transcript_segments):
        db.add(
            models.TranscriptSegment(
                job_id=job.id,
                order_index=index,
                start=segment.start,
                end=segment.end,
                speaker=segment.speaker,
                text=segment.text,
                translated_text=segment.translated_text,
                language=segment.language,
            )
        )
    for index, paragraph in enumerate(paragraph_drafts):
        db.add(
            models.TranscriptParagraph(
                job_id=job.id,
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


def run_job(job_id: str) -> None:
    """Run the complete transcription workflow for a job."""
    settings = get_settings()
    db = SessionLocal()
    try:
        job = db.get(models.Job, job_id)
        if not job:
            logger.warning("Job %s no longer exists", job_id)
            return

        job.error_message = None
        job.completed_at = None
        job.progress_percent = 0
        db.commit()

        if job.source_type == "url" and job.transcription_mode == "youtube_transcript":
            # YouTube mode weights: transcribing(fetch)=0-20, correcting(repair)=20-85, translating=85-95, segmenting=95-100
            _set_status(db, job, "transcribing", progress_percent=0)
            _stage_progress(db, job, 0, 20, 5)
            requested_language = None if job.language == "auto" else job.language
            transcript_segments = fetch_youtube_transcript(job.source_url or "", language=requested_language)
            _stage_progress(db, job, 0, 20, 100)

            _set_status(db, job, "correcting", progress_percent=20)
            transcript_segments, repair_warning = repair_youtube_transcript_segments(
                transcript_segments,
                infer_speakers=job.enable_diarization,
                progress_callback=lambda percent: _stage_progress(db, job, 20, 85, percent),
            )
            if repair_warning:
                _append_warning(job, repair_warning)
                db.commit()

            if job.enable_translation:
                try:
                    _set_status(db, job, "translating")
                    _stage_progress(db, job, 85, 95, 0)
                    detected_language = transcript_segments[0].language if transcript_segments else job.language
                    transcript_segments = translate_transcript_segments(
                        transcript_segments,
                        source_language=detected_language,
                        target_language=settings.translation_target_language,
                        progress_callback=lambda percent: _stage_progress(db, job, 85, 95, percent),
                    )
                except Exception as exc:
                    _append_warning(job, f"Translation skipped: {exc}")
                    db.commit()

            _set_status(db, job, "segmenting")
            _stage_progress(db, job, 95, 100, 50)
            _persist_transcript(db, job, transcript_segments)
            detail = " with LLM speaker labeling" if job.enable_diarization else ""
            _append_warning(job, f"Used fast YouTube transcript/subtitle extraction{detail}; no HF/Whisper audio transcription was run.")
            job.status = "completed"
            job.progress_percent = 100
            job.completed_at = datetime.utcnow()
            db.commit()
            logger.info("Job %s completed from YouTube transcript with %s segments", job.id, len(transcript_segments))
            return

        # HF mode stage weights: downloading=0-5, extract=5-10, transcribe=10-50, correct=50-62,
        #   diarize=62-77, align=77-85, translate=85-95, segment=95-100
        if job.source_type == "url" and not job.media_path:
            _set_status(db, job, "downloading")
            _stage_progress(db, job, 0, 5, 5)
            output_dir = settings.storage_path / "downloads" / job.id
            job.media_path = download_audio_from_url(job.source_url or "", str(output_dir))
            _stage_progress(db, job, 0, 5, 100)
            db.commit()

        if not job.media_path:
            raise RuntimeError("Job has no media file to process")

        _set_status(db, job, "extracting_audio")
        _stage_progress(db, job, 5, 10, 5)
        audio_path = settings.storage_path / "audio" / f"{job.id}.wav"
        job.audio_path = extract_audio(job.media_path, str(audio_path))
        _stage_progress(db, job, 5, 10, 100)
        db.commit()

        _set_status(db, job, "transcribing", progress_percent=10)
        _stage_progress(db, job, 10, 50, 0)
        requested_language = None if job.language == "auto" else job.language
        effective_model_size = "small" if job.m1_optimized else settings.whisper_model_size
        effective_compute_type = "int8" if job.m1_optimized else None
        transcript_segments = transcribe_audio(
            job.audio_path,
            language=requested_language,
            model_size=effective_model_size,
            compute_type=effective_compute_type,
            progress_callback=lambda percent: _stage_progress(db, job, 10, 50, percent),
        )

        _set_status(db, job, "correcting")
        _stage_progress(db, job, 50, 62, 0)
        transcript_segments, correction_warning = correct_transcript_segments(
            transcript_segments,
            progress_callback=lambda percent: _stage_progress(db, job, 50, 62, percent),
        )
        if correction_warning:
            _append_warning(job, correction_warning)
            db.commit()

        if job.enable_diarization:
            if not settings.hf_token:
                _append_warning(job, "Speaker diarization skipped because HF_TOKEN is not configured.")
                db.commit()
            else:
                try:
                    _set_status(db, job, "diarizing")
                    _stage_progress(db, job, 62, 77, 5)
                    hint = [{"start": s.start, "end": s.end, "text": s.text} for s in transcript_segments[:50]]
                    diarization_segments = diarize_audio(job.audio_path, transcript_hint=hint)
                    _stage_progress(db, job, 62, 77, 100)
                except Exception as exc:
                    _append_warning(job, f"Speaker diarization skipped: {exc}")
                    db.commit()
                else:
                    if diarization_segments:
                        _set_status(db, job, "aligning")
                        _stage_progress(db, job, 77, 85, 0)
                        transcript_segments = assign_speakers_to_transcript(
                            transcript_segments,
                            diarization_segments,
                            progress_callback=lambda percent: _stage_progress(db, job, 77, 85, percent),
                        )
                    else:
                        _append_warning(job, "Speaker diarization returned no speaker segments.")
                        db.commit()

        if job.enable_translation:
            try:
                _set_status(db, job, "translating")
                _stage_progress(db, job, 85, 95, 0)
                detected_language = transcript_segments[0].language if transcript_segments else job.language
                transcript_segments = translate_transcript_segments(
                    transcript_segments,
                    source_language=detected_language,
                    target_language=settings.translation_target_language,
                    progress_callback=lambda percent: _stage_progress(db, job, 85, 95, percent),
                )
            except Exception as exc:
                _append_warning(job, f"Translation skipped: {exc}")
                db.commit()

        _set_status(db, job, "segmenting")
        _stage_progress(db, job, 95, 100, 50)
        _persist_transcript(db, job, transcript_segments)

        job.status = "completed"
        job.progress_percent = 100
        job.completed_at = datetime.utcnow()
        db.commit()
        logger.info("Job %s completed with %s segments", job.id, len(transcript_segments))
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        job = db.get(models.Job, job_id)
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.process_transcription_job")
def process_transcription_job(job_id: str) -> None:
    """Celery task entrypoint for transcription jobs."""
    run_job(job_id)
