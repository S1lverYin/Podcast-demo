from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.services.paragraphing import build_transcript_paragraphs
from app.services.exporter import ExportFormat, build_export


router = APIRouter()


@router.get("/{job_id}/export")
def export_job(
    job_id: str,
    format: ExportFormat = Query(default="txt"),
    db: Session = Depends(get_db),
) -> Response:
    """Export transcript segments in a supported text format."""
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    segments = list(
        db.scalars(
            select(models.TranscriptSegment)
            .where(models.TranscriptSegment.job_id == job_id)
            .order_by(models.TranscriptSegment.order_index, models.TranscriptSegment.start)
        ).all()
    )
    if not segments:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No transcript segments to export")

    paragraphs = list(
        db.scalars(
            select(models.TranscriptParagraph)
            .where(models.TranscriptParagraph.job_id == job_id)
            .order_by(models.TranscriptParagraph.order_index, models.TranscriptParagraph.start)
        ).all()
    )
    if format in {"paragraph_md", "paragraph_json"} and not paragraphs:
        paragraphs = [
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
            for index, paragraph in enumerate(build_transcript_paragraphs(segments))
        ]

    payload, media_type, extension = build_export(job, segments, format, paragraphs=paragraphs)
    filename = f"voicescribe-{job.id}.{extension}"
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
