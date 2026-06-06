import { FormEvent, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ExternalLink, Loader2, Search } from "lucide-react";

import { getApiError } from "../api/client";
import { recommendPodcasts } from "../api/podcast";
import type { PodcastRecommendation } from "../types/job";

function parseLinks(value: string): string[] {
  const seen = new Set<string>();
  return value
    .split(/\s+/)
    .map((link) => link.trim())
    .filter((link) => {
      if (!link || seen.has(link)) return false;
      seen.add(link);
      return true;
    })
    .slice(0, 10);
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return "";
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  if (minutes < 60) {
    return `${minutes}:${String(remaining).padStart(2, "0")}`;
  }
  const hours = Math.floor(minutes / 60);
  const hourMinutes = minutes % 60;
  return `${hours}:${String(hourMinutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
}

export default function PodcastRecommendationsPanel() {
  const [linksText, setLinksText] = useState("");
  const [keywords, setKeywords] = useState("");
  const [days, setDays] = useState(7);
  const [maxResults, setMaxResults] = useState(5);
  const [recommendations, setRecommendations] = useState<PodcastRecommendation[]>([]);
  const links = useMemo(() => parseLinks(linksText), [linksText]);
  const cleanedKeywords = keywords.trim();
  const canSearch = links.length > 0 || cleanedKeywords.length > 0;

  const recommendationMutation = useMutation({
    mutationFn: () =>
      recommendPodcasts({
        links,
        keywords: cleanedKeywords || null,
        max_results: maxResults,
        days,
      }),
    onSuccess: (items) => setRecommendations(items),
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSearch || recommendationMutation.isPending) return;
    recommendationMutation.mutate();
  }

  return (
    <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Search size={18} aria-hidden="true" />
          <h2 className="text-base font-semibold text-slate-950">近期推荐</h2>
        </div>
        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
          {days} 天内 / {maxResults} 条
        </span>
      </div>

      <form className="grid gap-3 lg:grid-cols-[minmax(240px,0.75fr)_minmax(320px,1fr)_auto]" onSubmit={handleSubmit}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
          <label className="block text-sm font-medium text-slate-700">
            关键词
            <input
              className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              placeholder="AI 芯片 / Bitcoin 宏观 / 创业访谈"
              value={keywords}
              onChange={(event) => setKeywords(event.target.value)}
            />
          </label>
          <div className="grid gap-2 rounded-md border border-slate-200 bg-slate-50 p-2 sm:grid-cols-2">
            <label className="block text-xs font-semibold text-slate-600">
              时间跨度
              <input
                className="mt-1 h-8 w-full rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-900 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                type="number"
                min={1}
                max={30}
                value={days}
                onChange={(event) => setDays(Math.min(30, Math.max(1, Number(event.target.value) || 1)))}
              />
            </label>
            <label className="block text-xs font-semibold text-slate-600">
              推荐条数
              <input
                className="mt-1 h-8 w-full rounded-md border border-slate-300 bg-white px-2 text-sm text-slate-900 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                type="number"
                min={1}
                max={10}
                value={maxResults}
                onChange={(event) => setMaxResults(Math.min(10, Math.max(1, Number(event.target.value) || 1)))}
              />
            </label>
            <p className="sm:col-span-2 text-xs leading-5 text-slate-600">
              可只填关键词，也可同时加入链接提高相似度。
            </p>
          </div>
        </div>
        <label className="block text-sm font-medium text-slate-700">
          参考链接
          <textarea
            className="mt-1 min-h-24 w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm leading-6 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            placeholder="每行一个链接，最多 10 个"
            value={linksText}
            onChange={(event) => setLinksText(event.target.value)}
          />
        </label>
        <button
          className="inline-flex h-10 items-center justify-center gap-2 self-end rounded-md bg-slate-900 px-4 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          type="submit"
          disabled={!canSearch || recommendationMutation.isPending}
        >
          {recommendationMutation.isPending ? (
            <Loader2 className="animate-spin" size={16} aria-hidden="true" />
          ) : (
            <Search size={16} aria-hidden="true" />
          )}
          {recommendationMutation.isPending ? "搜索中" : "搜索推荐"}
        </button>
      </form>

      {recommendationMutation.isError ? (
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {getApiError(recommendationMutation.error)}
        </div>
      ) : null}

      {recommendationMutation.isSuccess && recommendations.length === 0 ? (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          暂未找到具体条目，可调大时间跨度或换一组关键词
        </div>
      ) : null}

      {recommendations.length > 0 ? (
        <div className="mt-5 grid gap-3 lg:grid-cols-5">
          {recommendations.map((item) => {
            const duration = formatDuration(item.duration);
            return (
              <article key={item.url} className="rounded-md border border-slate-200 bg-slate-50 p-3">
                <div className="mb-2 flex items-start justify-between gap-2">
                  <h3 className="line-clamp-3 text-sm font-semibold leading-5 text-slate-950">{item.title}</h3>
                  <a
                    className="shrink-0 rounded-md p-1 text-slate-500 hover:bg-white hover:text-emerald-700"
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    title="打开链接"
                  >
                    <ExternalLink size={15} aria-hidden="true" />
                  </a>
                </div>
                <p className="text-xs font-medium text-slate-600">
                  {[item.source, item.published_date, duration].filter(Boolean).join(" · ")}
                </p>
                <p className="mt-2 text-xs leading-5 text-slate-700">{item.reason}</p>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
