import { Download } from "lucide-react";

import { exportJobUrl } from "../api/jobs";
import type { ExportFormat } from "../types/job";

const formats: Array<{ label: string; value: ExportFormat }> = [
  { label: "TXT", value: "txt" },
  { label: "SRT", value: "srt" },
  { label: "VTT", value: "vtt" },
  { label: "JSON", value: "json" },
  { label: "Markdown", value: "md" },
  { label: "段落 MD", value: "paragraph_md" },
  { label: "段落 JSON", value: "paragraph_json" },
];

export default function ExportButtons({ jobId, disabled }: { jobId: string; disabled?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {formats.map((format) => (
        <a
          key={format.value}
          className={[
            "inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 transition hover:border-emerald-500 hover:text-emerald-700",
            disabled ? "pointer-events-none opacity-50" : "",
          ].join(" ")}
          href={disabled ? undefined : exportJobUrl(jobId, format.value)}
          title={`Export ${format.label}`}
        >
          <Download size={15} aria-hidden="true" />
          {format.label}
        </a>
      ))}
    </div>
  );
}
