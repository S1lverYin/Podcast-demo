import { Languages, Loader2 } from "lucide-react";

import type { TranscriptParagraph } from "../types/job";

function formatTime(seconds: number): string {
  const safeSeconds = Math.max(0, seconds);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const wholeSeconds = Math.floor(safeSeconds % 60);
  return [hours, minutes, wholeSeconds].map((value) => String(value).padStart(2, "0")).join(":");
}

type Props = {
  paragraphs: TranscriptParagraph[];
  translatingIds: Set<number>;
  onTranslate: (paragraphId: number, force?: boolean) => void;
};

export default function ParagraphViewer({ paragraphs, translatingIds, onTranslate }: Props) {
  if (paragraphs.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
        暂无语段版内容
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {paragraphs.map((paragraph) => (
        <article key={paragraph.id} className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-slate-100 px-2 py-1 font-mono text-xs text-slate-700">
                {formatTime(paragraph.start)} - {formatTime(paragraph.end)}
              </span>
              {paragraph.speaker ? (
                <span className="rounded-md bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">
                  {paragraph.speaker}
                </span>
              ) : null}
            </div>
            <button
              className="inline-flex h-8 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-xs font-semibold text-slate-700 transition hover:border-emerald-500 hover:text-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
              type="button"
              disabled={translatingIds.has(paragraph.id)}
              onClick={() => onTranslate(paragraph.id, Boolean(paragraph.translated_text))}
              title={paragraph.translated_text ? "重新翻译此语段" : "翻译此语段"}
            >
              {translatingIds.has(paragraph.id) ? (
                <Loader2 className="animate-spin" size={14} aria-hidden="true" />
              ) : (
                <Languages size={14} aria-hidden="true" />
              )}
              {translatingIds.has(paragraph.id) ? "翻译中" : paragraph.translated_text ? "重译" : "翻译"}
            </button>
          </div>
          {paragraph.title ? <h3 className="mb-2 text-sm font-semibold text-slate-950">{paragraph.title}</h3> : null}
          {paragraph.summary ? <p className="mb-3 text-sm text-slate-500">{paragraph.summary}</p> : null}
          {paragraph.translated_text ? (
            <p className="whitespace-pre-wrap text-sm leading-7 text-slate-950">{paragraph.translated_text}</p>
          ) : (
            <p className="whitespace-pre-wrap text-sm leading-7 text-slate-950">{paragraph.text}</p>
          )}
          {paragraph.translated_text ? (
            <details className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
              <summary className="cursor-pointer font-medium">Original</summary>
              <p className="mt-2 whitespace-pre-wrap leading-7">{paragraph.text}</p>
            </details>
          ) : null}
        </article>
      ))}
    </div>
  );
}
