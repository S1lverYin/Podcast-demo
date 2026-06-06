import { apiClient } from "./client";
import type {
  CreateUrlJobPayload,
  ExportFormat,
  Job,
  JobQueuedResponse,
  ParagraphingMode,
  PodcastNote,
  PodcastNoteGeneratePayload,
  TranscriptParagraph,
  TranscriptSegment,
  TranslationLanguage,
} from "../types/job";

export type JobOptions = {
  language: string;
  enableDiarization: boolean;
  enableTranslation: boolean;
};

export type RegenerateParagraphOptions = {
  mode?: ParagraphingMode;
  splitOnSpeaker?: boolean;
};

export async function uploadJob(file: File, options: JobOptions): Promise<JobQueuedResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("language", options.language);
  formData.append("enable_diarization", String(options.enableDiarization));
  formData.append("enable_translation", String(options.enableTranslation));
  const response = await apiClient.post<JobQueuedResponse>("/jobs/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function createUrlJob(payload: CreateUrlJobPayload): Promise<JobQueuedResponse> {
  const response = await apiClient.post<JobQueuedResponse>("/jobs/from-url", payload);
  return response.data;
}

export async function listJobs(): Promise<Job[]> {
  const response = await apiClient.get<Job[]>("/jobs");
  return response.data;
}

export async function getJob(jobId: string): Promise<Job> {
  const response = await apiClient.get<Job>(`/jobs/${jobId}`);
  return response.data;
}

export async function getSegments(jobId: string): Promise<TranscriptSegment[]> {
  const response = await apiClient.get<TranscriptSegment[]>(`/jobs/${jobId}/segments`);
  return response.data;
}

export async function getParagraphs(jobId: string): Promise<TranscriptParagraph[]> {
  const response = await apiClient.get<TranscriptParagraph[]>(`/jobs/${jobId}/paragraphs`);
  return response.data;
}

export async function getPodcastNotes(jobId: string): Promise<PodcastNote[]> {
  const response = await apiClient.get<PodcastNote[]>(`/jobs/${jobId}/podcast-notes`);
  return response.data;
}

export async function clearPodcastNotes(jobId: string): Promise<void> {
  await apiClient.delete(`/jobs/${jobId}/podcast-notes`);
}

export async function generatePodcastNote(
  jobId: string,
  payload: PodcastNoteGeneratePayload,
): Promise<PodcastNote> {
  const response = await apiClient.post<PodcastNote>(`/jobs/${jobId}/podcast-notes/generate`, payload, {
    timeout: 420_000,
  });
  return response.data;
}

export async function regenerateParagraphs(
  jobId: string,
  options: RegenerateParagraphOptions = {},
): Promise<TranscriptParagraph[]> {
  const response = await apiClient.post<TranscriptParagraph[]>(`/jobs/${jobId}/paragraphs/regenerate`, {
    mode: options.mode ?? "auto",
    split_on_speaker: options.splitOnSpeaker,
  });
  return response.data;
}

export async function updateSegment(
  jobId: string,
  segmentId: number,
  text: string,
): Promise<TranscriptSegment> {
  const response = await apiClient.patch<TranscriptSegment>(`/jobs/${jobId}/segments/${segmentId}`, {
    text,
  });
  return response.data;
}

export async function translateSegment(
  jobId: string,
  segmentId: number,
  force = false,
  targetLanguage?: TranslationLanguage,
): Promise<TranscriptSegment> {
  const response = await apiClient.post<TranscriptSegment>(`/jobs/${jobId}/segments/${segmentId}/translate`, {
    force,
    target_language: targetLanguage,
  });
  return response.data;
}

export async function translateParagraph(
  jobId: string,
  paragraphId: number,
  force = false,
  targetLanguage?: TranslationLanguage,
): Promise<TranscriptParagraph> {
  const response = await apiClient.post<TranscriptParagraph>(`/jobs/${jobId}/paragraphs/${paragraphId}/translate`, {
    force,
    target_language: targetLanguage,
  });
  return response.data;
}

export async function retryJob(jobId: string): Promise<JobQueuedResponse> {
  const response = await apiClient.post<JobQueuedResponse>(`/jobs/${jobId}/retry`);
  return response.data;
}

export async function clearTranscript(jobId: string): Promise<void> {
  await apiClient.delete(`/jobs/${jobId}/transcript`);
}

export async function deleteJob(jobId: string): Promise<void> {
  await apiClient.delete(`/jobs/${jobId}`);
}

export function exportJobUrl(jobId: string, format: ExportFormat): string {
  const baseURL = apiClient.defaults.baseURL ?? "";
  return `${baseURL}/jobs/${jobId}/export?format=${format}`;
}
