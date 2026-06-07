import { apiClient } from "./client";
import type { ParagraphSettings, ParagraphSettingsUpdate } from "../types/settings";

export async function getParagraphSettings(): Promise<ParagraphSettings> {
  const response = await apiClient.get<ParagraphSettings>("/settings/paragraphing");
  return response.data;
}

export async function updateParagraphSettings(payload: ParagraphSettingsUpdate): Promise<ParagraphSettings> {
  const response = await apiClient.put<ParagraphSettings>("/settings/paragraphing", payload);
  return response.data;
}

export async function getDiarizationSettings(): Promise<import("../types/settings").DiarizationSettings> {
  const response = await apiClient.get("/settings/diarization");
  return response.data;
}

export async function updateDiarizationSettings(
  payload: import("../types/settings").DiarizationSettingsUpdate,
): Promise<import("../types/settings").DiarizationSettings> {
  const response = await apiClient.put("/settings/diarization", payload);
  return response.data;
}
