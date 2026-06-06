import { apiClient } from "./client";
import type { PodcastRecommendation } from "../types/job";

export type PodcastRecommendationPayload = {
  links: string[];
  keywords?: string | null;
  max_results?: number;
  days?: number;
};

export async function recommendPodcasts(payload: PodcastRecommendationPayload): Promise<PodcastRecommendation[]> {
  const response = await apiClient.post<PodcastRecommendation[]>("/podcast/recommendations", payload, {
    timeout: 300_000,
  });
  return response.data;
}
