import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowLeft, BookOpen, Languages, Loader2, Podcast, RotateCcw, Trash2 } from "lucide-react";

import { getApiError } from "../api/client";
import {
  clearTranscript,
  deleteJob,
  getJob,
  getParagraphs,
  getSegments,
  regenerateParagraphs,
  retryJob,
  translateParagraph,
  translateSegment,
  updateSegment,
} from "../api/jobs";
import { getParagraphSettings } from "../api/settings";
import ExportButtons from "../components/ExportButtons";
import JobStatusBadge from "../components/JobStatusBadge";
import ParagraphViewer from "../components/ParagraphViewer";
import PodcastNotesPanel from "../components/PodcastNotesPanel";
import TranscriptEditor from "../components/TranscriptEditor";
import type { JobStatus, ParagraphingMode, TranscriptParagraph, TranscriptSegment, TranslationLanguage } from "../types/job";
import { parseServerDate } from "../utils/date";

const progressByStatus: Record<JobStatus, number> = {
  queued: 8,
  downloading: 20,
  extracting_audio: 35,
  transcribing: 62,
  correcting: 70,
  diarizing: 80,
  aligning: 88,
  translating: 92,
  segmenting: 96,
  completed: 100,
  failed: 100,
};

const NO_SPEAKER_LABEL = "无说话人";
const TRANSLATION_LANGUAGE_OPTIONS: { value: TranslationLanguage; label: string }[] = [
  { value: "zh", label: "中文" },
  { value: "en", label: "English" },
  { value: "ja", label: "日本語" },
  { value: "ko", label: "한국어" },
  { value: "es", label: "Español" },
  { value: "fr", label: "Français" },
  { value: "de", label: "Deutsch" },
];

function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(parseServerDate(value));
}

export default function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [speakerFilter, setSpeakerFilter] = useState("all");
  const [viewMode, setViewMode] = useState<"segments" | "paragraphs" | "podcast">("segments");
  const [draftText, setDraftText] = useState<Record<number, string>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [translatingSegmentIds, setTranslatingSegmentIds] = useState<Set<number>>(new Set());
  const [translatingParagraphIds, setTranslatingParagraphIds] = useState<Set<number>>(new Set());
  const [paragraphingMode, setParagraphingMode] = useState<ParagraphingMode>("rules");
  const [splitParagraphsOnSpeaker, setSplitParagraphsOnSpeaker] = useState(true);
  const [translationTarget, setTranslationTarget] = useState<TranslationLanguage>("zh");
  const [translateError, setTranslateError] = useState<string | null>(null);

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId ?? ""),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && !["completed", "failed"].includes(status) ? 2500 : false;
    },
  });

  const segmentsQuery = useQuery({
    queryKey: ["segments", jobId],
    queryFn: () => getSegments(jobId ?? ""),
    enabled: Boolean(jobId),
    refetchInterval: jobQuery.data?.status && !["completed", "failed"].includes(jobQuery.data.status) ? 2500 : false,
  });

  const paragraphsQuery = useQuery({
    queryKey: ["paragraphs", jobId],
    queryFn: () => getParagraphs(jobId ?? ""),
    enabled: Boolean(jobId),
    refetchInterval: jobQuery.data?.status && !["completed", "failed"].includes(jobQuery.data.status) ? 2500 : false,
  });

  const paragraphSettingsQuery = useQuery({
    queryKey: ["paragraph-settings"],
    queryFn: getParagraphSettings,
    staleTime: 30_000,
  });

  useEffect(() => {
    const nextDraft: Record<number, string> = {};
    for (const segment of segmentsQuery.data ?? []) {
      nextDraft[segment.id] = segment.text;
    }
    setDraftText(nextDraft);
  }, [segmentsQuery.data]);

  useEffect(() => {
    if (!paragraphSettingsQuery.data) return;
    setParagraphingMode(paragraphSettingsQuery.data.paragraphing_mode);
    setSplitParagraphsOnSpeaker(paragraphSettingsQuery.data.paragraphing_split_on_speaker);
  }, [paragraphSettingsQuery.data]);

  const saveMutation = useMutation({
    mutationFn: async (segmentId: number) => {
      setSavingId(segmentId);
      return updateSegment(jobId ?? "", segmentId, draftText[segmentId] ?? "");
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["segments", jobId] }),
    onSettled: () => setSavingId(null),
  });

  const retryMutation = useMutation({
    mutationFn: () => retryJob(jobId ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      queryClient.invalidateQueries({ queryKey: ["segments", jobId] });
      queryClient.invalidateQueries({ queryKey: ["paragraphs", jobId] });
      queryClient.invalidateQueries({ queryKey: ["podcast-notes", jobId] });
    },
  });

  const clearTranscriptMutation = useMutation({
    mutationFn: () => clearTranscript(jobId ?? ""),
    onSuccess: () => {
      setDraftText({});
      queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      queryClient.invalidateQueries({ queryKey: ["segments", jobId] });
      queryClient.invalidateQueries({ queryKey: ["paragraphs", jobId] });
      queryClient.invalidateQueries({ queryKey: ["podcast-notes", jobId] });
    },
  });

  const deleteJobMutation = useMutation({
    mutationFn: () => deleteJob(jobId ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.removeQueries({ queryKey: ["job", jobId] });
      queryClient.removeQueries({ queryKey: ["segments", jobId] });
      queryClient.removeQueries({ queryKey: ["paragraphs", jobId] });
      queryClient.removeQueries({ queryKey: ["podcast-notes", jobId] });
      navigate("/jobs");
    },
  });

  const regenerateParagraphsMutation = useMutation({
    mutationFn: (options: { mode: ParagraphingMode; splitOnSpeaker: boolean }) =>
      regenerateParagraphs(jobId ?? "", options),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["paragraphs", jobId] }),
  });

  async function handleTranslateSegment(segmentId: number, force = false) {
    if (!jobId) return;
    setTranslateError(null);
    setTranslatingSegmentIds((current) => new Set(current).add(segmentId));
    try {
      const updated = await translateSegment(jobId, segmentId, force, translationTarget);
      queryClient.setQueryData<TranscriptSegment[]>(["segments", jobId], (current) =>
        current?.map((segment) => (segment.id === updated.id ? updated : segment)),
      );
    } catch (error) {
      setTranslateError(getApiError(error));
    } finally {
      setTranslatingSegmentIds((current) => {
        const next = new Set(current);
        next.delete(segmentId);
        return next;
      });
    }
  }

  async function handleTranslateParagraph(paragraphId: number, force = false) {
    if (!jobId) return;
    setTranslateError(null);
    setTranslatingParagraphIds((current) => new Set(current).add(paragraphId));
    try {
      const updated = await translateParagraph(jobId, paragraphId, force, translationTarget);
      queryClient.setQueryData<TranscriptParagraph[]>(["paragraphs", jobId], (current) =>
        current?.map((paragraph) => (paragraph.id === updated.id ? updated : paragraph)),
      );
    } catch (error) {
      setTranslateError(getApiError(error));
    } finally {
      setTranslatingParagraphIds((current) => {
        const next = new Set(current);
        next.delete(paragraphId);
        return next;
      });
    }
  }

  async function translateVisibleMissingSegments() {
    for (const segment of filteredSegments.filter((item) => !item.translated_text)) {
      await handleTranslateSegment(segment.id);
    }
  }

  async function translateMissingParagraphs() {
    for (const paragraph of (paragraphsQuery.data ?? []).filter((item) => !item.translated_text)) {
      await handleTranslateParagraph(paragraph.id);
    }
  }

  function handleClearTranscript() {
    if (!segments.length || clearTranscriptMutation.isPending) return;
    const confirmed = window.confirm("确定删除这个任务的转写片段、语段版和播客笔记吗？任务和音频文件会保留。");
    if (confirmed) {
      clearTranscriptMutation.mutate();
    }
  }

  function handleDeleteJob() {
    if (!jobId || deleteJobMutation.isPending) return;
    const confirmed = window.confirm("确定删除这个任务和它的音频/媒体文件吗？这会同时删除转写内容和播客笔记，无法撤销。");
    if (confirmed) {
      deleteJobMutation.mutate();
    }
  }

  const segments = segmentsQuery.data ?? [];
  const speakerOptions = useMemo(() => {
    const speakers = new Set(segments.map((segment) => segment.speaker ?? NO_SPEAKER_LABEL));
    return ["all", ...Array.from(speakers).sort()];
  }, [segments]);
  const filteredSegments = speakerFilter === "all"
    ? segments
    : segments.filter((segment) => (segment.speaker ?? NO_SPEAKER_LABEL) === speakerFilter);

  if (jobQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-white p-5 text-sm text-slate-600">
        <Loader2 className="animate-spin" size={16} aria-hidden="true" />
        加载任务详情
      </div>
    );
  }

  if (jobQuery.isError || !jobQuery.data) {
    return (
      <div className="rounded-md border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
        {getApiError(jobQuery.error)}
      </div>
    );
  }

  const job = jobQuery.data;
  const transcriptionProgress = job.status === "transcribing" && typeof job.progress_percent === "number"
    ? Math.round(job.progress_percent)
    : null;
  const progress = transcriptionProgress === null
    ? progressByStatus[job.status]
    : Math.min(70, Math.max(35, 35 + transcriptionProgress * 0.35));
  const canExport = segments.length > 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/jobs"
          className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:border-emerald-500 hover:text-emerald-700"
        >
          <ArrowLeft size={15} aria-hidden="true" />
          返回任务
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          {job.status === "failed" ? (
            <button
              className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:border-emerald-500 hover:text-emerald-700 disabled:opacity-50"
              type="button"
              disabled={retryMutation.isPending}
              onClick={() => retryMutation.mutate()}
            >
              <RotateCcw size={15} aria-hidden="true" />
              重试
            </button>
          ) : null}
          <button
            className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:border-rose-400 hover:text-rose-700 disabled:opacity-50"
            type="button"
            disabled={segments.length === 0 || clearTranscriptMutation.isPending || !["completed", "failed"].includes(job.status)}
            onClick={handleClearTranscript}
          >
            {clearTranscriptMutation.isPending ? (
              <Loader2 className="animate-spin" size={15} aria-hidden="true" />
            ) : (
              <Trash2 size={15} aria-hidden="true" />
            )}
            {clearTranscriptMutation.isPending ? "删除中" : "删除转写内容"}
          </button>
          <button
            className="inline-flex h-9 items-center gap-2 rounded-md border border-rose-300 bg-white px-3 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-50"
            type="button"
            disabled={deleteJobMutation.isPending}
            onClick={handleDeleteJob}
          >
            {deleteJobMutation.isPending ? (
              <Loader2 className="animate-spin" size={15} aria-hidden="true" />
            ) : (
              <Trash2 size={15} aria-hidden="true" />
            )}
            {deleteJobMutation.isPending ? "删除中" : "删除任务和音频"}
          </button>
          <ExportButtons jobId={job.id} disabled={!canExport} />
        </div>
      </div>

      <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="break-all text-lg font-semibold text-slate-950">
              {job.original_filename ?? job.source_url ?? job.id}
            </h1>
            <p className="mt-1 font-mono text-xs text-slate-500">{job.id}</p>
          </div>
          <JobStatusBadge status={job.status} progressPercent={job.progress_percent} />
        </div>

        <div className="mb-2 flex items-center justify-between gap-3 text-xs font-medium text-slate-500">
          <span>{job.status === "transcribing" ? "Transcribing progress" : "Workflow progress"}</span>
          <span>{transcriptionProgress === null ? `${progress}%` : `${transcriptionProgress}%`}</span>
        </div>

        <div className="mb-4 h-2 overflow-hidden rounded-md bg-slate-100">
          <div
            className={job.status === "failed" ? "h-full bg-rose-500" : "h-full bg-emerald-600"}
            style={{ width: `${progress}%` }}
          />
        </div>

        <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-slate-500">Mode</dt>
            <dd className="font-medium text-slate-900">
              {job.transcription_mode === "youtube_transcript" ? "YouTube Transcript" : "HF/Whisper"}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Language</dt>
            <dd className="font-medium text-slate-900">{job.language}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Created</dt>
            <dd className="font-medium text-slate-900">{formatDate(job.created_at)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Completed</dt>
            <dd className="font-medium text-slate-900">{formatDate(job.completed_at)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Segments</dt>
            <dd className="font-medium text-slate-900">{segments.length}</dd>
          </div>
        </dl>

        {job.warning_message ? (
          <div className="mt-4 flex gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            <AlertCircle className="mt-0.5 shrink-0" size={16} aria-hidden="true" />
            <span className="whitespace-pre-line">{job.warning_message}</span>
          </div>
        ) : null}

        {job.error_message ? (
          <div className="mt-4 flex gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            <AlertCircle className="mt-0.5 shrink-0" size={16} aria-hidden="true" />
            <span>{job.error_message}</span>
          </div>
        ) : null}
      </section>

      <section className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-white p-1">
          <button
            className={[
              "h-8 rounded-md px-3 text-sm font-semibold",
              viewMode === "segments" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100",
            ].join(" ")}
            type="button"
            onClick={() => setViewMode("segments")}
          >
            转写片段
          </button>
          <button
            className={[
              "inline-flex h-8 items-center gap-2 rounded-md px-3 text-sm font-semibold",
              viewMode === "paragraphs" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100",
            ].join(" ")}
            type="button"
            onClick={() => setViewMode("paragraphs")}
          >
            <BookOpen size={15} aria-hidden="true" />
            语段版
          </button>
          <button
            className={[
              "inline-flex h-8 items-center gap-2 rounded-md px-3 text-sm font-semibold",
              viewMode === "podcast" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100",
            ].join(" ")}
            type="button"
            onClick={() => setViewMode("podcast")}
          >
            <Podcast size={15} aria-hidden="true" />
            播客笔记
          </button>
        </div>

        {viewMode === "segments" ? (
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              译为
              <select
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                value={translationTarget}
                onChange={(event) => setTranslationTarget(event.target.value as TranslationLanguage)}
              >
                {TRANSLATION_LANGUAGE_OPTIONS.map((language) => (
                  <option key={language.value} value={language.value}>
                    {language.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:border-emerald-500 hover:text-emerald-700 disabled:opacity-50"
              type="button"
              disabled={filteredSegments.every((segment) => segment.translated_text) || translatingSegmentIds.size > 0}
              onClick={() => void translateVisibleMissingSegments()}
            >
              {translatingSegmentIds.size > 0 ? (
                <Loader2 className="animate-spin" size={15} aria-hidden="true" />
              ) : (
                <Languages size={15} aria-hidden="true" />
              )}
              翻译当前缺失
            </button>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              Speaker
              <select
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                value={speakerFilter}
                onChange={(event) => setSpeakerFilter(event.target.value)}
              >
                {speakerOptions.map((speaker) => (
                  <option key={speaker} value={speaker}>
                    {speaker === "all" ? "All" : speaker}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : viewMode === "paragraphs" ? (
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              译为
              <select
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                value={translationTarget}
                onChange={(event) => setTranslationTarget(event.target.value as TranslationLanguage)}
              >
                {TRANSLATION_LANGUAGE_OPTIONS.map((language) => (
                  <option key={language.value} value={language.value}>
                    {language.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:border-emerald-500 hover:text-emerald-700 disabled:opacity-50"
              type="button"
              disabled={
                (paragraphsQuery.data ?? []).every((paragraph) => paragraph.translated_text) ||
                translatingParagraphIds.size > 0
              }
              onClick={() => void translateMissingParagraphs()}
            >
              {translatingParagraphIds.size > 0 ? (
                <Loader2 className="animate-spin" size={15} aria-hidden="true" />
              ) : (
                <Languages size={15} aria-hidden="true" />
              )}
              翻译全部语段
            </button>
            <div className="flex h-9 items-center rounded-md border border-slate-200 bg-white p-1">
              {(["rules", "llm"] as ParagraphingMode[]).map((mode) => (
                <button
                  key={mode}
                  className={[
                    "h-7 min-w-12 rounded-md px-3 text-sm font-semibold",
                    paragraphingMode === mode
                      ? "bg-slate-900 text-white"
                      : "text-slate-600 hover:bg-slate-100",
                  ].join(" ")}
                  type="button"
                  onClick={() => setParagraphingMode(mode)}
                >
                  {mode === "rules" ? "规则" : "LLM"}
                </button>
              ))}
            </div>
            <label className="flex h-9 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700">
              <input
                className="h-4 w-4 accent-emerald-600"
                type="checkbox"
                checked={splitParagraphsOnSpeaker}
                onChange={(event) => setSplitParagraphsOnSpeaker(event.target.checked)}
              />
              按 speaker
            </label>
            <button
              className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:border-emerald-500 hover:text-emerald-700 disabled:opacity-50"
              type="button"
              disabled={regenerateParagraphsMutation.isPending || segments.length === 0}
              onClick={() =>
                regenerateParagraphsMutation.mutate({
                  mode: paragraphingMode,
                  splitOnSpeaker: splitParagraphsOnSpeaker,
                })
              }
            >
              {regenerateParagraphsMutation.isPending ? (
                <Loader2 className="animate-spin" size={15} aria-hidden="true" />
              ) : (
                <RotateCcw size={15} aria-hidden="true" />
              )}
              {regenerateParagraphsMutation.isPending ? "生成中" : "重新生成语段"}
            </button>
          </div>
        ) : null}
      </section>

      {translateError ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {translateError}
        </div>
      ) : null}

      {regenerateParagraphsMutation.isError ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {getApiError(regenerateParagraphsMutation.error)}
        </div>
      ) : null}

      {clearTranscriptMutation.isError ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {getApiError(clearTranscriptMutation.error)}
        </div>
      ) : null}

      {deleteJobMutation.isError ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {getApiError(deleteJobMutation.error)}
        </div>
      ) : null}

      {viewMode === "podcast" ? (
        <PodcastNotesPanel job={job} />
      ) : viewMode === "segments" && segmentsQuery.isLoading ? (
        <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-white p-5 text-sm text-slate-600">
          <Loader2 className="animate-spin" size={16} aria-hidden="true" />
          加载转写片段
        </div>
      ) : viewMode === "segments" && segmentsQuery.isError ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
          {getApiError(segmentsQuery.error)}
        </div>
      ) : viewMode === "segments" ? (
        <TranscriptEditor
          segments={filteredSegments}
          draftText={draftText}
          savingId={savingId}
          translatingIds={translatingSegmentIds}
          onChange={(segmentId, text) => setDraftText((current) => ({ ...current, [segmentId]: text }))}
          onSave={(segmentId) => saveMutation.mutate(segmentId)}
          onTranslate={(segmentId, force) => void handleTranslateSegment(segmentId, force)}
        />
      ) : paragraphsQuery.isLoading ? (
        <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-white p-5 text-sm text-slate-600">
          <Loader2 className="animate-spin" size={16} aria-hidden="true" />
          加载语段版
        </div>
      ) : paragraphsQuery.isError ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
          {getApiError(paragraphsQuery.error)}
        </div>
      ) : (
        <ParagraphViewer
          paragraphs={paragraphsQuery.data ?? []}
          translatingIds={translatingParagraphIds}
          onTranslate={(paragraphId, force) => void handleTranslateParagraph(paragraphId, force)}
        />
      )}

      {saveMutation.isError ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {getApiError(saveMutation.error)}
        </div>
      ) : null}
    </div>
  );
}
