from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SUPPORTED_LANGUAGES = {"auto", "zh", "en", "ja", "ko", "es", "fr", "de"}
SUPPORTED_TRANSLATION_LANGUAGES = {"zh", "en", "ja", "ko", "es", "fr", "de"}
TRANSCRIPTION_MODES = {"hf", "youtube_transcript"}
JOB_STATUSES = {
    "queued",
    "downloading",
    "extracting_audio",
    "transcribing",
    "correcting",
    "diarizing",
    "aligning",
    "translating",
    "segmenting",
    "completed",
    "failed",
}


class TranscriptSegment(BaseModel):
    """In-memory transcript segment used by ASR and alignment services."""

    start: float
    end: float
    text: str
    translated_text: str | None = None
    language: str | None = None
    speaker: str | None = None


class DiarizationSegment(BaseModel):
    """In-memory diarization segment returned by pyannote."""

    start: float
    end: float
    speaker: str


class UrlJobRequest(BaseModel):
    url: str
    language: str = "auto"
    enable_diarization: bool = True
    enable_translation: bool = False
    m1_optimized: bool = False
    transcription_mode: Literal["hf", "youtube_transcript"] = "hf"

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language must be one of {sorted(SUPPORTED_LANGUAGES)}")
        return value


class JobQueuedResponse(BaseModel):
    job_id: str
    status: str


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_type: Literal["upload", "url"]
    source_url: str | None = None
    original_filename: str | None = None
    media_path: str | None = None
    audio_path: str | None = None
    status: str
    language: str
    enable_diarization: bool
    enable_translation: bool
    m1_optimized: bool
    transcription_mode: Literal["hf", "youtube_transcript"] = "hf"
    progress_percent: int | None = None
    error_message: str | None = None
    warning_message: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class SegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    order_index: int
    start: float
    end: float
    speaker: str | None = None
    text: str
    translated_text: str | None = None
    language: str | None = None


class ParagraphRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    order_index: int
    start: float
    end: float
    speaker: str | None = None
    title: str | None = None
    summary: str | None = None
    text: str
    translated_text: str | None = None


class SegmentUpdate(BaseModel):
    text: str = Field(min_length=0)
    translated_text: str | None = None


class TranslateRequest(BaseModel):
    target_language: str | None = None
    force: bool = False

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_TRANSLATION_LANGUAGES:
            raise ValueError(f"target_language must be one of {sorted(SUPPORTED_TRANSLATION_LANGUAGES)}")
        return value


class ParagraphRegenerateRequest(BaseModel):
    mode: Literal["auto", "rules", "llm"] | None = None
    split_on_speaker: bool | None = None


class PodcastNoteGenerateRequest(BaseModel):
    podcast_source: str | None = None
    original_title: str | None = None
    published_date: str | None = None
    host: str | None = None
    guests: str | None = None
    source_url: str | None = None
    chapter_outline: str | None = None
    auto_map_speakers: bool = True
    lookup_source_metadata: bool = False
    clear_existing_notes: bool = False
    include_full_dialogue: bool = True


class PodcastNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    title: str | None = None
    markdown: str
    metadata_json: str | None = None
    created_at: datetime
    updated_at: datetime


class PodcastRecommendationRequest(BaseModel):
    links: list[str] = Field(default_factory=list, max_length=10)
    keywords: str | None = None
    max_results: int = Field(default=5, ge=1, le=10)
    days: int = Field(default=7, ge=1, le=30)
    search_subscriptions: bool = False

    @model_validator(mode="after")
    def validate_seed_input(self) -> "PodcastRecommendationRequest":
        links = [link.strip() for link in self.links if link.strip()]
        keywords = (self.keywords or "").strip()
        if not links and not keywords and not self.search_subscriptions:
            raise ValueError("At least one link, keyword, or subscription-list search is required")
        self.links = links
        self.keywords = keywords or None
        return self


class PodcastRecommendationRead(BaseModel):
    title: str
    url: str
    source: str | None = None
    published_date: str | None = None
    duration: int | None = None
    reason: str
    query: str | None = None


class ParagraphSettingsRead(BaseModel):
    paragraphing_mode: Literal["rules", "llm"]
    transcript_correction_mode: Literal["off", "rules", "llm"]
    transcript_correction_batch_size: int
    whisper_initial_prompt: str | None = None
    paragraphing_api_provider: Literal["openai", "anthropic"]
    paragraphing_api_base_url: str
    paragraphing_api_model: str | None = None
    paragraphing_api_key_configured: bool
    paragraphing_api_max_sentences: int
    paragraphing_split_on_speaker: bool


class ParagraphSettingsUpdate(BaseModel):
    paragraphing_mode: Literal["rules", "llm"] | None = None
    transcript_correction_mode: Literal["off", "rules", "llm"] | None = None
    transcript_correction_batch_size: int | None = Field(default=None, ge=10, le=220)
    whisper_initial_prompt: str | None = None
    paragraphing_api_provider: Literal["openai", "anthropic"] | None = None
    paragraphing_api_base_url: str | None = None
    paragraphing_api_key: str | None = None
    paragraphing_api_model: str | None = None
    paragraphing_api_max_sentences: int | None = Field(default=None, ge=20, le=500)
    paragraphing_split_on_speaker: bool | None = None
    clear_paragraphing_api_key: bool = False




class DiarizationSettingsRead(BaseModel):
    diarization_api_provider: Literal["openai", "anthropic"]
    diarization_api_base_url: str
    diarization_api_model: str | None = None
    diarization_api_key_configured: bool


class DiarizationSettingsUpdate(BaseModel):
    diarization_api_provider: Literal["openai", "anthropic"] | None = None
    diarization_api_base_url: str | None = None
    diarization_api_key: str | None = None
    diarization_api_model: str | None = None
    clear_diarization_api_key: bool = False

class PodcastSubscriptionRead(BaseModel):
    channel_id: str
    url: str
    title: str


class PodcastSubscriptionCreate(BaseModel):
    channel_id: str | None = None
    url: str
    title: str


class PodcastCurationReportRequest(BaseModel):
    items: list[PodcastRecommendationRead] = Field(default_factory=list, max_length=20)
    target_audience: str | None = None


class PodcastCurationReportRead(BaseModel):
    markdown: str


class ErrorResponse(BaseModel):
    detail: str
