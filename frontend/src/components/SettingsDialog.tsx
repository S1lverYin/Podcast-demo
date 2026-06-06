import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Loader2, Save, X } from "lucide-react";

import { getApiError } from "../api/client";
import { getParagraphSettings, updateParagraphSettings } from "../api/settings";
import type { ParagraphingMode } from "../types/job";

type ApiProvider = "openai" | "anthropic";

const MODEL_PRESETS = [
  { label: "自定义", value: "custom", provider: "openai", baseUrl: "", model: "" },
  {
    label: "OpenAI GPT-5.4 Mini",
    value: "openai-gpt-5.4-mini",
    provider: "openai",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5.4-mini",
  },
  {
    label: "OpenAI GPT-5.5",
    value: "openai-gpt-5.5",
    provider: "openai",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5.5",
  },
  {
    label: "DeepSeek V4 Flash",
    value: "deepseek-v4-flash",
    provider: "openai",
    baseUrl: "https://api.deepseek.com",
    model: "deepseek-v4-flash",
  },
  {
    label: "DeepSeek V4 Pro",
    value: "deepseek-v4-pro",
    provider: "openai",
    baseUrl: "https://api.deepseek.com",
    model: "deepseek-v4-pro",
  },
  {
    label: "Claude Haiku 4.5",
    value: "claude-haiku-4-5",
    provider: "anthropic",
    baseUrl: "https://api.anthropic.com/v1",
    model: "claude-haiku-4-5",
  },
  {
    label: "Claude Sonnet 4.6",
    value: "claude-sonnet-4-6",
    provider: "anthropic",
    baseUrl: "https://api.anthropic.com/v1",
    model: "claude-sonnet-4-6",
  },
  {
    label: "Claude Opus 4.8",
    value: "claude-opus-4-8",
    provider: "anthropic",
    baseUrl: "https://api.anthropic.com/v1",
    model: "claude-opus-4-8",
  },
  {
    label: "Gemini 2.5 Flash",
    value: "gemini-2.5-flash",
    provider: "openai",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-2.5-flash",
  },
  {
    label: "Gemini 2.5 Pro",
    value: "gemini-2.5-pro",
    provider: "openai",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-2.5-pro",
  },
  {
    label: "OpenRouter",
    value: "openrouter",
    provider: "openai",
    baseUrl: "https://openrouter.ai/api/v1",
    model: "",
  },
] satisfies Array<{
  label: string;
  value: string;
  provider: ApiProvider;
  baseUrl: string;
  model: string;
}>;

type Props = {
  open: boolean;
  onClose: () => void;
};

export default function SettingsDialog({ open, onClose }: Props) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<Exclude<ParagraphingMode, "auto">>("rules");
  const [correctionMode, setCorrectionMode] = useState<"off" | "rules" | "llm">("rules");
  const [provider, setProvider] = useState<ApiProvider>("openai");
  const [baseUrl, setBaseUrl] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [maxSentences, setMaxSentences] = useState(220);
  const [correctionBatchSize, setCorrectionBatchSize] = useState(80);
  const [initialPrompt, setInitialPrompt] = useState("");
  const [splitOnSpeaker, setSplitOnSpeaker] = useState(true);
  const [clearApiKey, setClearApiKey] = useState(false);
  const [modelPreset, setModelPreset] = useState("custom");

  const settingsQuery = useQuery({
    queryKey: ["paragraph-settings"],
    queryFn: getParagraphSettings,
    enabled: open,
  });

  useEffect(() => {
    if (!settingsQuery.data) return;
    setMode(settingsQuery.data.paragraphing_mode);
    setCorrectionMode(settingsQuery.data.transcript_correction_mode);
    setProvider(settingsQuery.data.paragraphing_api_provider);
    setBaseUrl(settingsQuery.data.paragraphing_api_base_url);
    setModel(settingsQuery.data.paragraphing_api_model ?? "");
    setMaxSentences(settingsQuery.data.paragraphing_api_max_sentences);
    setCorrectionBatchSize(settingsQuery.data.transcript_correction_batch_size);
    setInitialPrompt(settingsQuery.data.whisper_initial_prompt ?? "");
    setSplitOnSpeaker(settingsQuery.data.paragraphing_split_on_speaker);
    setApiKey("");
    setClearApiKey(false);
    setModelPreset(
      MODEL_PRESETS.find(
        (preset) =>
          preset.model &&
          preset.model === settingsQuery.data?.paragraphing_api_model &&
          preset.provider === settingsQuery.data.paragraphing_api_provider &&
          preset.baseUrl === settingsQuery.data.paragraphing_api_base_url,
      )?.value ?? "custom",
    );
  }, [settingsQuery.data]);

  const updateMutation = useMutation({
    mutationFn: () =>
      updateParagraphSettings({
        paragraphing_mode: mode,
        transcript_correction_mode: correctionMode,
        transcript_correction_batch_size: correctionBatchSize,
        whisper_initial_prompt: initialPrompt,
        paragraphing_api_provider: provider,
        paragraphing_api_base_url: baseUrl,
        paragraphing_api_model: model,
        paragraphing_api_key: apiKey,
        paragraphing_api_max_sentences: maxSentences,
        paragraphing_split_on_speaker: splitOnSpeaker,
        clear_paragraphing_api_key: clearApiKey,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["paragraph-settings"] });
      setApiKey("");
      setClearApiKey(false);
      onClose();
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    updateMutation.mutate();
  }

  function handlePresetChange(value: string) {
    setModelPreset(value);
    const preset = MODEL_PRESETS.find((item) => item.value === value);
    if (!preset || preset.value === "custom") return;
    setProvider(preset.provider);
    setBaseUrl(preset.baseUrl);
    if (preset.model) {
      setModel(preset.model);
    }
  }

  if (!open) return null;

  const hasKey = settingsQuery.data?.paragraphing_api_key_configured ?? false;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 px-4 py-6">
      <div className="w-full max-w-lg rounded-md border border-slate-200 bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-2">
            <KeyRound size={18} aria-hidden="true" />
            <h2 className="text-base font-semibold text-slate-950">设置</h2>
          </div>
          <button
            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-950"
            type="button"
            onClick={onClose}
            title="关闭"
          >
            <X size={17} aria-hidden="true" />
          </button>
        </div>

        {settingsQuery.isLoading ? (
          <div className="flex items-center gap-2 p-5 text-sm text-slate-600">
            <Loader2 className="animate-spin" size={16} aria-hidden="true" />
            加载设置
          </div>
        ) : (
          <form className="space-y-4 p-5" onSubmit={handleSubmit}>
            <label className="block text-sm font-medium text-slate-700">
              默认语段模式
              <select
                className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                value={mode}
                onChange={(event) => setMode(event.target.value as Exclude<ParagraphingMode, "auto">)}
              >
                <option value="rules">规则</option>
                <option value="llm">LLM</option>
              </select>
            </label>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-sm font-medium text-slate-700">
                转写纠错
                <select
                  className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                  value={correctionMode}
                  onChange={(event) => setCorrectionMode(event.target.value as "off" | "rules" | "llm")}
                >
                  <option value="off">关闭</option>
                  <option value="rules">本地规则</option>
                  <option value="llm">LLM/API</option>
                </select>
              </label>

              <label className="block text-sm font-medium text-slate-700">
                纠错批大小
                <input
                  className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                  min={10}
                  max={220}
                  type="number"
                  value={correctionBatchSize}
                  onChange={(event) => setCorrectionBatchSize(Number(event.target.value))}
                />
              </label>
            </div>

            <label className="block text-sm font-medium text-slate-700">
              Whisper 提示词
              <textarea
                className="mt-1 min-h-20 w-full resize-y rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                value={initialPrompt}
                onChange={(event) => setInitialPrompt(event.target.value)}
              />
            </label>

            <label className="block text-sm font-medium text-slate-700">
              模型预设
              <select
                className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                value={modelPreset}
                onChange={(event) => handlePresetChange(event.target.value)}
              >
                {MODEL_PRESETS.map((preset) => (
                  <option key={preset.value} value={preset.value}>
                    {preset.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm font-medium text-slate-700">
              API Base URL
              <input
                className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                value={baseUrl}
                onChange={(event) => {
                  setBaseUrl(event.target.value);
                  setModelPreset("custom");
                }}
              />
            </label>

            <label className="block text-sm font-medium text-slate-700">
              API 类型
              <select
                className="mt-1 h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                value={provider}
                onChange={(event) => {
                  setProvider(event.target.value as ApiProvider);
                  setModelPreset("custom");
                }}
              >
                <option value="openai">OpenAI-compatible</option>
                <option value="anthropic">Anthropic Messages</option>
              </select>
            </label>

            <label className="block text-sm font-medium text-slate-700">
              Model
              <input
                className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                placeholder="gpt-4o-mini"
                value={model}
                onChange={(event) => {
                  setModel(event.target.value);
                  setModelPreset("custom");
                }}
              />
            </label>

            <label className="block text-sm font-medium text-slate-700">
              API Key
              <input
                className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                placeholder={hasKey ? "已配置，留空不修改" : "sk-..."}
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
              />
            </label>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-sm font-medium text-slate-700">
                每批句子数
                <input
                  className="mt-1 h-10 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                  min={20}
                  max={500}
                  type="number"
                  value={maxSentences}
                  onChange={(event) => setMaxSentences(Number(event.target.value))}
                />
              </label>

              <div className="flex items-end">
                <label className="flex h-10 w-full items-center gap-2 rounded-md border border-slate-300 px-3 text-sm font-medium text-slate-700">
                  <input
                    className="h-4 w-4 accent-emerald-600"
                    type="checkbox"
                    checked={splitOnSpeaker}
                    onChange={(event) => setSplitOnSpeaker(event.target.checked)}
                  />
                  按 speaker 切分
                </label>
              </div>
            </div>

            {hasKey ? (
              <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
                <input
                  className="h-4 w-4 accent-rose-600"
                  type="checkbox"
                  checked={clearApiKey}
                  onChange={(event) => setClearApiKey(event.target.checked)}
                />
                清除已保存 Key
              </label>
            ) : null}

            {settingsQuery.isError || updateMutation.isError ? (
              <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                {getApiError(settingsQuery.error ?? updateMutation.error)}
              </div>
            ) : null}

            <div className="flex justify-end gap-2 border-t border-slate-200 pt-4">
              <button
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:border-emerald-500 hover:text-emerald-700"
                type="button"
                onClick={onClose}
              >
                取消
              </button>
              <button
                className="inline-flex h-9 items-center gap-2 rounded-md bg-emerald-600 px-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                type="submit"
                disabled={updateMutation.isPending}
              >
                {updateMutation.isPending ? (
                  <Loader2 className="animate-spin" size={15} aria-hidden="true" />
                ) : (
                  <Save size={15} aria-hidden="true" />
                )}
                保存
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
