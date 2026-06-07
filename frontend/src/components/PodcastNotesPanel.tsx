import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, FileText, Loader2, Search, Sparkles, Trash2 } from "lucide-react";

import { autofillSpeakers, clearPodcastNotes, generatePodcastNote, getPodcastNotes } from "../api/jobs";
import { getApiError } from "../api/client";
import type { Job, PodcastNote, PodcastNoteGeneratePayload } from "../types/job";
import { parseServerDate } from "../utils/date";

type PodcastNotesPanelProps = {
  job: Job | null | undefined;
};

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function noteDate(value: string | null | undefined): string {
  if (!value) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parseServerDate(value));
}

function downloadMarkdown(markdown: string, title: string) {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${title.replace(/[\\/:*?"<>|]+/g, "-").slice(0, 80) || "podcast-notes"}.md`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export default function PodcastNotesPanel({ job }: PodcastNotesPanelProps) {
  const queryClient = useQueryClient();
  const [podcastSource, setPodcastSource] = useState("");
  const [originalTitle, setOriginalTitle] = useState("");
  const [publishedDate, setPublishedDate] = useState("");
  const [host, setHost] = useState("");
  const [guests, setGuests] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [chapterOutline, setChapterOutline] = useState("");
  const [clearExistingNotes, setClearExistingNotes] = useState(true);
  const [markdown, setMarkdown] = useState("");
  const [copyState, setCopyState] = useState<"idle" | "copied">("idle");
  const [autofillLoading, setAutofillLoading] = useState(false);
  const [autofillDone, setAutofillDone] = useState(false);

  const jobId = job?.id;
  const fallbackTitle = job?.original_filename ?? job?.source_url ?? "";

  useEffect(() => {
    setPodcastSource("");
    setOriginalTitle(fallbackTitle);
    setPublishedDate("");
    setHost("");
    setGuests("");
    setSourceUrl(job?.source_url ?? "");
    setChapterOutline("");
    setClearExistingNotes(true);
    setMarkdown("");
    setCopyState("idle");
  }, [fallbackTitle, job?.source_url, jobId]);

  const notesQuery = useQuery({
    queryKey: ["podcast-notes", jobId],
    queryFn: () => getPodcastNotes(jobId ?? ""),
    enabled: Boolean(jobId),
  });

  useEffect(() => {
    const latest = notesQuery.data?.[0];
    setMarkdown(latest?.markdown ?? "");
  }, [notesQuery.data, jobId]);

  const latestNote = notesQuery.data?.[0] as PodcastNote | undefined;
  const noteCount = notesQuery.data?.length ?? 0;
  const canGenerate = Boolean(jobId) && job?.status === "completed";

  const generateMutation = useMutation({
    mutationFn: (payload: PodcastNoteGeneratePayload) => generatePodcastNote(jobId ?? "", payload),
    onSuccess: (note) => {
      setMarkdown(note.markdown);
      queryClient.invalidateQueries({ queryKey: ["podcast-notes", jobId] });
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => clearPodcastNotes(jobId ?? ""),
    onSuccess: () => {
      setMarkdown("");
      queryClient.invalidateQueries({ queryKey: ["podcast-notes", jobId] });
    },
  });

  const outputTitle = useMemo(
    () => originalTitle.trim() || latestNote?.title || "podcast-notes",
    [latestNote?.title, originalTitle],
  );

  async function handleAutofillAll() {
    if (!jobId || autofillLoading) return;
    setAutofillLoading(true);
    try {
      const result = await autofillSpeakers(jobId);
      if (result.host) setHost(result.host);
      if (result.guests) setGuests(result.guests);
      if (result.podcast_source) setPodcastSource(result.podcast_source);
      if (result.original_title) setOriginalTitle(result.original_title);
      if (result.published_date) setPublishedDate(result.published_date);
      if (result.source_url) setSourceUrl(result.source_url);
      setAutofillDone(true);
      window.setTimeout(() => setAutofillDone(false), 1800);
    } catch (error) {
      console.error("autofill failed", error);
    } finally {
      setAutofillLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canGenerate) return;
    setCopyState("idle");
    generateMutation.mutate({
      podcast_source: emptyToNull(podcastSource),
      original_title: emptyToNull(originalTitle),
      published_date: emptyToNull(publishedDate),
      host: emptyToNull(host),
      guests: emptyToNull(guests),
      source_url: emptyToNull(sourceUrl),
      chapter_outline: emptyToNull(chapterOutline),
      auto_map_speakers: true,
      lookup_source_metadata: true,
      clear_existing_notes: clearExistingNotes,
      include_full_dialogue: true,
    });
  }

  async function handleCopy() {
    if (!markdown) return;
    await navigator.clipboard.writeText(markdown);
    setCopyState("copied");
    window.setTimeout(() => setCopyState("idle"), 1400);
  }

  if (!job) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
        请选择一个任务
      </div>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(320px,420px)_1fr]">
      <form
        className={[
          "space-y-4 rounded-md border border-slate-200 bg-white p-5 shadow-sm transition-opacity",
          autofillLoading ? "opacity-70" : "",
        ].join(" ")}
        onSubmit={handleSubmit}
      >
        <div className="flex items-center gap-2">
          <FileText size={18} aria-hidden="true" />
          <h2 className="text-base font-semibold text-slate-950">播客笔记</h2>
        </div>

        <label className="block text-sm font-medium text-slate-700">
          原标题
          <input
            className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            value={originalTitle}
            onChange={(event) => setOriginalTitle(event.target.value)}
          />
        </label>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
          <label className="block text-sm font-medium text-slate-700">
            播客源
            <input
              className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              value={podcastSource}
              onChange={(event) => setPodcastSource(event.target.value)}
            />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            播出日期
            <input
              className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              value={publishedDate}
              onChange={(event) => setPublishedDate(event.target.value)}
            />
          </label>
        </div>

        <label className="block text-sm font-medium text-slate-700">
          主持人
          <input
            className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            placeholder="主持人姓名，或 Speaker 1=姓名"
            value={host}
            onChange={(event) => setHost(event.target.value)}
          />
        </label>

        <label className="block text-sm font-medium text-slate-700">
          嘉宾/角色
          <textarea
            className="mt-1 min-h-20 w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            placeholder="每行一个；可写 Speaker 2=嘉宾名，职位"
            value={guests}
            onChange={(event) => setGuests(event.target.value)}
          />
        </label>

        <label className="block text-sm font-medium text-slate-700">
          原文链接
          <input
            className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
          />
        </label>

        <label className="block text-sm font-medium text-slate-700">
          章节小标题
          <textarea
            className="mt-1 min-h-28 w-full resize-y rounded-md border border-slate-300 px-3 py-2 font-mono text-xs outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            placeholder={"00:00:00 Intro\n00:04:32 Framework to Predict Tops & Bottoms"}
            value={chapterOutline}
            onChange={(event) => setChapterOutline(event.target.value)}
          />
        </label>

        <button
          className={[
            "inline-flex h-11 w-full items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold transition-all disabled:opacity-40",
            autofillDone
              ? "bg-emerald-700 text-white"
              : "bg-slate-800 text-white hover:bg-slate-900",
          ].join(" ")}
          type="button"
          disabled={autofillLoading || !jobId}
          onClick={() => void handleAutofillAll()}
        >
          {autofillLoading ? (
            <Loader2 className="animate-spin" size={18} aria-hidden="true" />
          ) : autofillDone ? (
            <span className="text-base">✓</span>
          ) : (
            <Search size={18} aria-hidden="true" />
          )}
          {autofillLoading ? "联网补全中…" : autofillDone ? "已补全 ✓" : "联网补全信息"}
        </button>

        <div className="space-y-2">
          <label className="flex min-h-10 items-center gap-2 rounded-md border border-slate-200 px-3 text-sm font-medium text-slate-700">
            <input
              className="h-4 w-4 accent-emerald-600"
              type="checkbox"
              checked={clearExistingNotes}
              onChange={(event) => setClearExistingNotes(event.target.checked)}
            />
            <Trash2 size={15} aria-hidden="true" />
            生成前清除历史
          </label>
        </div>

        {generateMutation.isError || clearMutation.isError ? (
          <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            {getApiError(generateMutation.error ?? clearMutation.error)}
          </div>
        ) : null}

        {!canGenerate ? (
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            任务完成后可生成
          </div>
        ) : null}

        <button
          className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-emerald-600 px-4 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          type="submit"
          disabled={!canGenerate || generateMutation.isPending}
        >
          {generateMutation.isPending ? (
            <Loader2 className="animate-spin" size={16} aria-hidden="true" />
          ) : (
            <Sparkles size={16} aria-hidden="true" />
          )}
          {generateMutation.isPending ? "生成中" : "生成播客笔记"}
        </button>
        <button
          className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 hover:border-rose-400 hover:text-rose-700 disabled:opacity-50"
          type="button"
          disabled={!jobId || noteCount === 0 || clearMutation.isPending || generateMutation.isPending}
          onClick={() => clearMutation.mutate()}
        >
          {clearMutation.isPending ? (
            <Loader2 className="animate-spin" size={16} aria-hidden="true" />
          ) : (
            <Trash2 size={16} aria-hidden="true" />
          )}
          {clearMutation.isPending ? "清除中" : `清除历史笔记${noteCount ? ` (${noteCount})` : ""}`}
        </button>
      </form>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Markdown</h2>
            <p className="mt-1 text-xs text-slate-500">
              {latestNote ? `最近生成：${noteDate(latestNote.created_at)}` : "暂无生成结果"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:border-emerald-500 hover:text-emerald-700 disabled:opacity-50"
              type="button"
              disabled={!markdown}
              onClick={() => void handleCopy()}
            >
              <Copy size={15} aria-hidden="true" />
              {copyState === "copied" ? "已复制" : "复制"}
            </button>
            <button
              className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:border-emerald-500 hover:text-emerald-700 disabled:opacity-50"
              type="button"
              disabled={!markdown}
              onClick={() => downloadMarkdown(markdown, outputTitle)}
            >
              <Download size={15} aria-hidden="true" />
              下载
            </button>
          </div>
        </div>

        <textarea
          className="min-h-[560px] w-full resize-y rounded-md border border-slate-300 bg-slate-50 px-4 py-3 font-mono text-xs leading-6 text-slate-900 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
          value={markdown}
          onChange={(event) => setMarkdown(event.target.value)}
          placeholder="生成后的播客笔记会出现在这里"
        />
      </section>
    </div>
  );
}
