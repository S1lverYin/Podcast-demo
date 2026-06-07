import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Loader2, Plus, Search, Trash2 } from "lucide-react";

import { getApiError } from "../api/client";
import { addSubscription, deleteSubscription, listSubscriptions } from "../api/podcast";

export default function SubscriptionSourcesPanel() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [channelId, setChannelId] = useState("");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");

  const subscriptionsQuery = useQuery({
    queryKey: ["podcast-subscriptions"],
    queryFn: listSubscriptions,
  });

  const addMutation = useMutation({
    mutationFn: () =>
      addSubscription({
        channel_id: channelId.trim() || null,
        url: url.trim(),
        title: title.trim(),
      }),
    onSuccess: () => {
      setChannelId("");
      setUrl("");
      setTitle("");
      queryClient.invalidateQueries({ queryKey: ["podcast-subscriptions"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteSubscription(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["podcast-subscriptions"] }),
  });

  const subscriptions = subscriptionsQuery.data ?? [];
  const filteredSubscriptions = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return subscriptions;
    return subscriptions.filter((item) =>
      [item.title, item.url, item.channel_id].some((value) => value.toLowerCase().includes(needle)),
    );
  }, [query, subscriptions]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!url.trim() || !title.trim() || addMutation.isPending) return;
    addMutation.mutate();
  }

  return (
    <section className="rounded-md border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">订阅源管理</h2>
          <p className="mt-1 text-xs text-slate-500">这些频道会作为“订阅列表搜索”的候选来源。</p>
        </div>
        <span className="rounded-md bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
          {subscriptions.length} 个频道
        </span>
      </div>

      <form className="grid gap-3 lg:grid-cols-[minmax(160px,0.5fr)_1fr_minmax(180px,0.8fr)_auto]" onSubmit={handleSubmit}>
        <input
          className="h-10 rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
          placeholder="频道标题"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
        <input
          className="h-10 rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
          placeholder="频道网址"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
        />
        <input
          className="h-10 rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
          placeholder="频道 ID 可选"
          value={channelId}
          onChange={(event) => setChannelId(event.target.value)}
        />
        <button
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          type="submit"
          disabled={!url.trim() || !title.trim() || addMutation.isPending}
        >
          {addMutation.isPending ? <Loader2 className="animate-spin" size={16} aria-hidden="true" /> : <Plus size={16} aria-hidden="true" />}
          添加
        </button>
      </form>

      {addMutation.isError ? (
        <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {getApiError(addMutation.error)}
        </div>
      ) : null}

      <label className="mt-4 flex h-10 items-center gap-2 rounded-md border border-slate-300 px-3 text-sm text-slate-600 focus-within:border-emerald-500 focus-within:ring-2 focus-within:ring-emerald-100">
        <Search size={16} aria-hidden="true" />
        <input
          className="min-w-0 flex-1 outline-none"
          placeholder="搜索频道标题、ID 或网址"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>

      {subscriptionsQuery.isLoading ? (
        <div className="mt-4 flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="animate-spin" size={16} aria-hidden="true" />
          加载订阅源
        </div>
      ) : null}

      {subscriptionsQuery.isError ? (
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {getApiError(subscriptionsQuery.error)}
        </div>
      ) : null}

      {deleteMutation.isError ? (
        <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {getApiError(deleteMutation.error)}
        </div>
      ) : null}

      <div className="mt-4 max-h-96 overflow-auto rounded-md border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3 font-semibold">频道</th>
              <th className="px-4 py-3 font-semibold">ID</th>
              <th className="px-4 py-3 font-semibold">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredSubscriptions.map((item) => (
              <tr key={item.channel_id} className="align-top hover:bg-slate-50">
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-900">{item.title}</div>
                  <a className="mt-1 inline-flex items-center gap-1 text-xs text-emerald-700 hover:text-emerald-800" href={item.url} target="_blank" rel="noreferrer">
                    {item.url}
                    <ExternalLink size={12} aria-hidden="true" />
                  </a>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-600">{item.channel_id}</td>
                <td className="px-4 py-3">
                  <button
                    className="inline-flex h-8 items-center gap-2 rounded-md border border-rose-200 bg-white px-2 text-xs font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                    type="button"
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(item.channel_id)}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!subscriptionsQuery.isLoading && filteredSubscriptions.length === 0 ? (
          <div className="p-6 text-center text-sm text-slate-500">没有匹配的订阅源</div>
        ) : null}
      </div>
    </section>
  );
}
