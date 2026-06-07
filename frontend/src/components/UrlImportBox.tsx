import { FormEvent, useState } from "react";
import { Captions, Link2, Loader2, Send } from "lucide-react";

import { getApiError } from "../api/client";
import { createUrlJob, type JobOptions } from "../api/jobs";

type Props = {
  options: JobOptions;
  onCreated: (jobId: string) => void;
};

export default function UrlImportBox({ options, onCreated }: Props) {
  const [url, setUrl] = useState("");
  const [submittingMode, setSubmittingMode] = useState<"hf" | "youtube_transcript" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function createJob(mode: "hf" | "youtube_transcript") {
    if (!url.trim() || submittingMode) return;
    setSubmittingMode(mode);
    setError(null);
    try {
      const response = await createUrlJob({
        url,
        language: options.language,
        enable_diarization: options.enableDiarization,
        enable_translation: options.enableTranslation,
        m1_optimized: options.m1Optimized,
        transcription_mode: mode,
      });
      onCreated(response.job_id);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setSubmittingMode(null);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await createJob("hf");
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">URL 导入</h2>
          <p className="mt-1 text-sm text-slate-500">YouTube, podcast RSS, embedded public media</p>
        </div>
        <Link2 className="text-cyan-600" size={22} aria-hidden="true" />
      </div>

      <label className="block">
        <span className="mb-2 block text-sm font-medium text-slate-700">链接</span>
        <input
          className="h-11 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-950 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
          type="url"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://www.youtube.com/watch?v=..."
          required
        />
      </label>

      {error ? <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <button
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          type="submit"
          disabled={Boolean(submittingMode)}
        >
          {submittingMode === "hf" ? <Loader2 className="animate-spin" size={16} aria-hidden="true" /> : <Send size={16} aria-hidden="true" />}
          HF/Whisper 转写
        </button>
        <button
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-cyan-300 bg-cyan-50 px-4 text-sm font-semibold text-cyan-800 transition hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-60"
          type="button"
          disabled={Boolean(submittingMode)}
          onClick={() => createJob("youtube_transcript")}
        >
          {submittingMode === "youtube_transcript" ? (
            <Loader2 className="animate-spin" size={16} aria-hidden="true" />
          ) : (
            <Captions size={16} aria-hidden="true" />
          )}
          快速字幕抽取
        </button>
      </div>
      <p className="mt-2 text-xs leading-5 text-slate-500">
        快速字幕抽取只适用于有字幕或自动字幕的 YouTube 链接；会用 LLM 修复字幕文本，开启 Speaker diarization 时会尝试区分说话人。
      </p>
    </form>
  );
}
