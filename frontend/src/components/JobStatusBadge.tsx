import type { JobStatus } from "../types/job";

const statusLabels: Record<JobStatus, string> = {
  queued: "Queued",
  downloading: "Downloading",
  extracting_audio: "Extracting",
  transcribing: "Transcribing",
  correcting: "Correcting",
  diarizing: "Diarizing",
  aligning: "Aligning",
  translating: "Translating",
  segmenting: "Segmenting",
  completed: "Completed",
  failed: "Failed",
};

const statusClasses: Record<JobStatus, string> = {
  queued: "border-slate-300 bg-slate-100 text-slate-700",
  downloading: "border-sky-200 bg-sky-50 text-sky-700",
  extracting_audio: "border-cyan-200 bg-cyan-50 text-cyan-700",
  transcribing: "border-amber-200 bg-amber-50 text-amber-800",
  correcting: "border-orange-200 bg-orange-50 text-orange-800",
  diarizing: "border-fuchsia-200 bg-fuchsia-50 text-fuchsia-700",
  aligning: "border-indigo-200 bg-indigo-50 text-indigo-700",
  translating: "border-violet-200 bg-violet-50 text-violet-700",
  segmenting: "border-lime-200 bg-lime-50 text-lime-800",
  completed: "border-emerald-200 bg-emerald-50 text-emerald-700",
  failed: "border-rose-200 bg-rose-50 text-rose-700",
};

export default function JobStatusBadge({
  status,
  progressPercent,
}: {
  status: JobStatus;
  progressPercent?: number | null;
}) {
  const showProgress = status === "transcribing" && typeof progressPercent === "number";

  return (
    <span
      className={[
        "inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold",
        statusClasses[status],
      ].join(" ")}
    >
      {statusLabels[status]}
      {showProgress ? ` ${Math.round(progressPercent)}%` : ""}
    </span>
  );
}
