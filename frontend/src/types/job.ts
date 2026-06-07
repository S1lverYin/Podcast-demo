export type JobStatus =
  | "queued"
  | "downloading"
  | "extracting_audio"
  | "transcribing"
  | "correcting"
  | "diarizing"
  | "aligning"
  | "translating"
  | "segmenting"
  | "completed"
  | "failed";

export type Job = {
  id: string;
  source_type: "upload" | "url";
  source_url: string | null;
  original_filename: string | null;
  media_path: string | null;
  audio_path: string | null;
  status: JobStatus;
  language: string;
  enable_diarization: boolean;
  enable_translation: boolean;
  m1_optimized: boolean;
  transcription_mode: "hf" | "youtube_transcript";
  progress_percent: number | null;
  error_message: string | null;
  warning_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type TranscriptSegment = {
  id: number;
  job_id: string;
  order_index: number;
  start: number;
  end: number;
  speaker: string | null;
  text: string;
  translated_text: string | null;
  language: string | null;
};

export type TranscriptParagraph = {
  id: number;
  job_id: string;
  order_index: number;
  start: number;
  end: number;
  speaker: string | null;
  title: string | null;
  summary: string | null;
  text: string;
  translated_text: string | null;
};

export type PodcastNote = {
  id: number;
  job_id: string;
  title: string | null;
  markdown: string;
  metadata_json: string | null;
  created_at: string;
  updated_at: string;
};

export type PodcastRecommendation = {
  title: string;
  url: string;
  source: string | null;
  published_date: string | null;
  duration: number | null;
  reason: string;
  query: string | null;
};

export type PodcastNoteGeneratePayload = {
  podcast_source?: string | null;
  original_title?: string | null;
  published_date?: string | null;
  host?: string | null;
  guests?: string | null;
  source_url?: string | null;
  chapter_outline?: string | null;
  auto_map_speakers: boolean;
  lookup_source_metadata: boolean;
  clear_existing_notes: boolean;
  include_full_dialogue: boolean;
};

export type ParagraphingMode = "auto" | "rules" | "llm";
export type TranslationLanguage = "zh" | "en" | "ja" | "ko" | "es" | "fr" | "de";

export type CreateUrlJobPayload = {
  url: string;
  language: string;
  enable_diarization: boolean;
  enable_translation: boolean;
  m1_optimized: boolean;
  transcription_mode?: "hf" | "youtube_transcript";
};

export type JobQueuedResponse = {
  job_id: string;
  status: JobStatus;
};

export type ExportFormat = "txt" | "srt" | "vtt" | "json" | "md" | "paragraph_md" | "paragraph_json";
