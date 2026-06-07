import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Job(Base):
    """Database record for a transcription job."""

    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type = Column(String, nullable=False)
    source_url = Column(String, nullable=True)
    original_filename = Column(String, nullable=True)
    media_path = Column(String, nullable=True)
    audio_path = Column(String, nullable=True)
    status = Column(String, nullable=False, default="queued", index=True)
    language = Column(String, nullable=False, default="auto")
    enable_diarization = Column(Boolean, nullable=False, default=True)
    enable_translation = Column(Boolean, nullable=False, default=False)
    m1_optimized = Column(Boolean, nullable=False, default=False)
    transcription_mode = Column(String, nullable=False, default="hf")
    progress_percent = Column(Integer, nullable=True)
    eta_seconds = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    warning_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    segments = relationship(
        "TranscriptSegment",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.order_index",
    )
    podcast_notes = relationship(
        "PodcastNote",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="PodcastNote.created_at.desc()",
    )


class TranscriptSegment(Base):
    """Database record for a timestamped transcript segment."""

    __tablename__ = "transcript_segments"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    order_index = Column(Integer, nullable=False, default=0)
    start = Column(Float, nullable=False)
    end = Column(Float, nullable=False)
    speaker = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=True)
    language = Column(String, nullable=True)

    job = relationship("Job", back_populates="segments")


class TranscriptParagraph(Base):
    """Database record for a paragraph-level transcript view."""

    __tablename__ = "transcript_paragraphs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    order_index = Column(Integer, nullable=False, default=0)
    start = Column(Float, nullable=False)
    end = Column(Float, nullable=False)
    speaker = Column(String, nullable=True)
    title = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    text = Column(Text, nullable=False)
    translated_text = Column(Text, nullable=True)


class PodcastNote(Base):
    """Generated long-form podcast note for a transcription job."""

    __tablename__ = "podcast_notes"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=True)
    markdown = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship("Job", back_populates="podcast_notes")
