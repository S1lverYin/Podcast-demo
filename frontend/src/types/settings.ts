import type { ParagraphingMode } from "./job";

export type ParagraphSettings = {
  paragraphing_mode: Exclude<ParagraphingMode, "auto">;
  transcript_correction_mode: "off" | "rules" | "llm";
  transcript_correction_batch_size: number;
  whisper_initial_prompt: string | null;
  paragraphing_api_provider: "openai" | "anthropic";
  paragraphing_api_base_url: string;
  paragraphing_api_model: string | null;
  paragraphing_api_key_configured: boolean;
  paragraphing_api_max_sentences: number;
  paragraphing_split_on_speaker: boolean;
};

export type ParagraphSettingsUpdate = {
  paragraphing_mode?: Exclude<ParagraphingMode, "auto">;
  transcript_correction_mode?: "off" | "rules" | "llm";
  transcript_correction_batch_size?: number;
  whisper_initial_prompt?: string;
  paragraphing_api_provider?: "openai" | "anthropic";
  paragraphing_api_base_url?: string;
  paragraphing_api_key?: string;
  paragraphing_api_model?: string;
  paragraphing_api_max_sentences?: number;
  paragraphing_split_on_speaker?: boolean;
  clear_paragraphing_api_key?: boolean;
};

export type DiarizationSettings = {
  diarization_api_provider: "openai" | "anthropic";
  diarization_api_base_url: string;
  diarization_api_model: string | null;
  diarization_api_key_configured: boolean;
};

export type DiarizationSettingsUpdate = {
  diarization_api_provider?: "openai" | "anthropic";
  diarization_api_base_url?: string;
  diarization_api_key?: string;
  diarization_api_model?: string;
  clear_diarization_api_key?: boolean;
};
