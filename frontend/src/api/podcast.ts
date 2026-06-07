import { apiClient } from "./client";
import type { PodcastRecommendation } from "../types/job";

export type PodcastSubscription = {
  channel_id: string;
  url: string;
  title: string;
};

export type PodcastSubscriptionPayload = {
  channel_id?: string | null;
  url: string;
  title: string;
};

export type PodcastRecommendationPayload = {
  links: string[];
  keywords?: string | null;
  max_results?: number;
  days?: number;
  search_subscriptions?: boolean;
};

export async function recommendPodcasts(payload: PodcastRecommendationPayload): Promise<PodcastRecommendation[]> {
  const response = await apiClient.post<PodcastRecommendation[]>("/podcast/recommendations", payload, {
    timeout: 300_000,
  });
  return response.data;
}

export async function listSubscriptions(): Promise<PodcastSubscription[]> {
  const response = await apiClient.get<PodcastSubscription[]>("/podcast/subscriptions");
  return response.data;
}

export async function addSubscription(payload: PodcastSubscriptionPayload): Promise<PodcastSubscription> {
  const response = await apiClient.post<PodcastSubscription>("/podcast/subscriptions", payload);
  return response.data;
}

export async function deleteSubscription(channelId: string): Promise<void> {
  await apiClient.delete(`/podcast/subscriptions/${encodeURIComponent(channelId)}`);
}

export async function generateCurationReport(
  items: PodcastRecommendation[],
  targetAudience?: string,
): Promise<string> {
  const response = await apiClient.post<{ markdown: string }>(
    "/podcast/curation-report",
    {
      items,
      target_audience: targetAudience || null,
    },
    { timeout: 420_000 },
  );
  return response.data.markdown;
}
