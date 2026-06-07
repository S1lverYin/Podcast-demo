import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Cpu, Languages, Mic2, Sparkles } from "lucide-react";

import UploadBox from "../components/UploadBox";
import UrlImportBox from "../components/UrlImportBox";

const languages = [
  { label: "Auto detect", value: "auto" },
  { label: "中文", value: "zh" },
  { label: "English", value: "en" },
  { label: "日本語", value: "ja" },
  { label: "한국어", value: "ko" },
  { label: "Español", value: "es" },
  { label: "Français", value: "fr" },
  { label: "Deutsch", value: "de" },
];

export default function HomePage() {
  const navigate = useNavigate();
  const [language, setLanguage] = useState("auto");
  const [enableDiarization, setEnableDiarization] = useState(true);
  const [enableTranslation, setEnableTranslation] = useState(false);
  const [m1Optimized, setM1Optimized] = useState(false);

  const options = useMemo(
    () => ({ language, enableDiarization, enableTranslation, m1Optimized }),
    [enableDiarization, enableTranslation, language, m1Optimized],
  );

  return (
    <div className="space-y-6">
      <section className="grid gap-4 rounded-md border border-slate-200 bg-white p-5 shadow-sm lg:grid-cols-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-700">
            <Languages size={16} aria-hidden="true" />
            语言
          </div>
          <select
            className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-950 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            value={language}
            onChange={(event) => setLanguage(event.target.value)}
          >
            {languages.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        <label className="flex min-h-20 items-center gap-3 rounded-md border border-slate-200 px-4">
          <input
            className="h-4 w-4 accent-emerald-600"
            type="checkbox"
            checked={enableDiarization}
            onChange={(event) => setEnableDiarization(event.target.checked)}
          />
          <span>
            <span className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <Mic2 size={16} aria-hidden="true" />
              Speaker diarization
            </span>
            <span className="text-xs text-slate-500">HF_TOKEN 未配置时自动跳过</span>
          </span>
        </label>

        <label className="flex min-h-20 items-center gap-3 rounded-md border border-slate-200 px-4">
          <input
            className="h-4 w-4 accent-emerald-600"
            type="checkbox"
            checked={enableTranslation}
            onChange={(event) => setEnableTranslation(event.target.checked)}
          />
          <span>
            <span className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <Sparkles size={16} aria-hidden="true" />
              Translation
            </span>
            <span className="text-xs text-slate-500">英转中；支持 local 或 API 模式</span>
          </span>
        </label>

        <label className="flex min-h-20 items-center gap-3 rounded-md border border-amber-200 bg-amber-50 px-4">
          <input
            className="h-4 w-4 accent-amber-600"
            type="checkbox"
            checked={m1Optimized}
            onChange={(event) => setM1Optimized(event.target.checked)}
          />
          <span>
            <span className="flex items-center gap-2 text-sm font-semibold text-amber-900">
              <Cpu size={16} aria-hidden="true" />
              M1 优化
            </span>
            <span className="text-xs text-amber-700">small 模型 + int8 量化 · M1/M2 提速 5-10x</span>
          </span>
        </label>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <UploadBox options={options} onCreated={(jobId) => navigate(`/jobs/${jobId}`)} />
        <UrlImportBox options={options} onCreated={(jobId) => navigate(`/jobs/${jobId}`)} />
      </section>
    </div>
  );
}
