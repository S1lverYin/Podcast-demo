import { FormEvent, useMemo, useState } from "react";
import { FileAudio, Loader2, Upload } from "lucide-react";

import { getApiError } from "../api/client";
import { uploadJob, type JobOptions } from "../api/jobs";

type Props = {
  options: JobOptions;
  onCreated: (jobId: string) => void;
};

const acceptTypes = [".mp4", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a", ".flac", ".aac"].join(",");

export default function UploadBox({ options, onCreated }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [isSubmitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileLabel = useMemo(() => {
    if (!file) return "未选择文件";
    const sizeMb = file.size / 1024 / 1024;
    return `${file.name} · ${sizeMb.toFixed(sizeMb >= 10 ? 0 : 1)} MB`;
  }, [file]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("请选择一个音频或视频文件");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const response = await uploadJob(file, options);
      onCreated(response.job_id);
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">本地文件</h2>
          <p className="mt-1 text-sm text-slate-500">mp4, mov, mkv, webm, mp3, wav, m4a, flac, aac</p>
        </div>
        <FileAudio className="text-emerald-600" size={22} aria-hidden="true" />
      </div>

      <label className="flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center transition hover:border-emerald-500 hover:bg-emerald-50">
        <Upload className="mb-3 text-slate-500" size={28} aria-hidden="true" />
        <span className="text-sm font-medium text-slate-700">{fileLabel}</span>
        <input
          className="sr-only"
          type="file"
          accept={acceptTypes}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </label>

      {error ? <p className="mt-3 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}

      <button
        className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-emerald-600 px-4 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
        type="submit"
        disabled={isSubmitting}
      >
        {isSubmitting ? <Loader2 className="animate-spin" size={16} aria-hidden="true" /> : <Upload size={16} aria-hidden="true" />}
        上传并转写
      </button>
    </form>
  );
}
