import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Podcast } from "lucide-react";

import { getApiError } from "../api/client";
import { listJobs } from "../api/jobs";
import PodcastNotesPanel from "../components/PodcastNotesPanel";
import PodcastRecommendationsPanel from "../components/PodcastRecommendationsPanel";

export default function PodcastPage() {
  const [selectedJobId, setSelectedJobId] = useState("");
  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: 5000,
  });

  const completedJobs = useMemo(
    () => (jobsQuery.data ?? []).filter((job) => job.status === "completed"),
    [jobsQuery.data],
  );
  const selectedJob = completedJobs.find((job) => job.id === selectedJobId) ?? completedJobs[0];

  useEffect(() => {
    if (!selectedJobId && completedJobs[0]) {
      setSelectedJobId(completedJobs[0].id);
    }
  }, [completedJobs, selectedJobId]);

  if (jobsQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-white p-5 text-sm text-slate-600">
        <Loader2 className="animate-spin" size={16} aria-hidden="true" />
        加载任务
      </div>
    );
  }

  if (jobsQuery.isError) {
    return (
      <div className="rounded-md border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
        {getApiError(jobsQuery.error)}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <Podcast size={20} aria-hidden="true" />
          <h1 className="text-base font-semibold text-slate-950">播客</h1>
        </div>
        <label className="flex min-w-72 items-center gap-2 text-sm font-medium text-slate-700">
          任务
          <select
            className="h-10 min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            value={selectedJob?.id ?? ""}
            onChange={(event) => setSelectedJobId(event.target.value)}
          >
            {completedJobs.length === 0 ? <option value="">暂无已完成任务</option> : null}
            {completedJobs.map((job) => (
              <option key={job.id} value={job.id}>
                {job.original_filename ?? job.source_url ?? job.id}
              </option>
            ))}
          </select>
        </label>
      </section>

      <PodcastRecommendationsPanel />

      <PodcastNotesPanel job={selectedJob} />
    </div>
  );
}
