import { Languages, Loader2, Save } from "lucide-react";

import type { TranscriptSegment } from "../types/job";

const NO_SPEAKER_LABEL = "无说话人";

function formatTime(seconds: number): string {
  const safeSeconds = Math.max(0, seconds);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const wholeSeconds = Math.floor(safeSeconds % 60);
  return [hours, minutes, wholeSeconds].map((value) => String(value).padStart(2, "0")).join(":");
}

type Props = {
  segments: TranscriptSegment[];
  draftText: Record<number, string>;
  savingId: number | null;
  translatingIds: Set<number>;
  onChange: (segmentId: number, text: string) => void;
  onSave: (segmentId: number) => void;
  onTranslate: (segmentId: number, force?: boolean) => void;
};

export default function TranscriptEditor({
  segments,
  draftText,
  savingId,
  translatingIds,
  onChange,
  onSave,
  onTranslate,
}: Props) {
  if (segments.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
        暂无转写片段
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {segments.map((segment) => {
        const text = draftText[segment.id] ?? segment.text;
        const hasChanges = text !== segment.text;
        const isTranslating = translatingIds.has(segment.id);
        return (
          <article key={segment.id} className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="rounded-md bg-slate-100 px-2 py-1 font-mono text-xs text-slate-700">
                  {formatTime(segment.start)} - {formatTime(segment.end)}
                </span>
                <span className="rounded-md bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">
                  {segment.speaker ?? NO_SPEAKER_LABEL}
                </span>
                {segment.language ? (
                  <span className="rounded-md bg-cyan-50 px-2 py-1 text-xs font-semibold text-cyan-700">
                    {segment.language}
                  </span>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="inline-flex h-8 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-xs font-semibold text-slate-700 transition hover:border-emerald-500 hover:text-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  disabled={isTranslating}
                  onClick={() => onTranslate(segment.id, Boolean(segment.translated_text))}
                  title={segment.translated_text ? "重新翻译此片段" : "翻译此片段"}
                >
                  {isTranslating ? (
                    <Loader2 className="animate-spin" size={14} aria-hidden="true" />
                  ) : (
                    <Languages size={14} aria-hidden="true" />
                  )}
                  {isTranslating ? "翻译中" : segment.translated_text ? "重译" : "翻译"}
                </button>
                <button
                  className="inline-flex h-8 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-xs font-semibold text-slate-700 transition hover:border-emerald-500 hover:text-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  disabled={!hasChanges || savingId === segment.id}
                  onClick={() => onSave(segment.id)}
                  title="保存此片段"
                >
                  <Save size={14} aria-hidden="true" />
                  {savingId === segment.id ? "保存中" : "保存"}
                </button>
              </div>
            </div>
            <textarea
              className="min-h-24 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm leading-6 text-slate-900 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              value={text}
              onChange={(event) => onChange(segment.id, event.target.value)}
            />
            {segment.translated_text ? (
              <div className="mt-3 rounded-md border border-emerald-100 bg-emerald-50 px-3 py-2 text-sm leading-6 text-emerald-950">
                {segment.translated_text}
              </div>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
