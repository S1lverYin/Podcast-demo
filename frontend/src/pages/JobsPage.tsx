import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Eye, Loader2 } from "lucide-react";

import { getApiError } from "../api/client";
import { listJobs } from "../api/jobs";
import JobStatusBadge from "../components/JobStatusBadge";
import { parseServerDate } from "../utils/date";

function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(parseServerDate(value));
}

export default function JobsPage() {
  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: 3000,
  });

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
      <div className="flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
        <AlertCircle size={16} aria-hidden="true" />
        {getApiError(jobsQuery.error)}
      </div>
    );
  }

  const jobs = jobsQuery.data ?? [];
  if (jobs.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 bg-white p-8 text-center">
        <p className="text-sm text-slate-500">暂无任务</p>
        <Link className="mt-4 inline-flex rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white" to="/">
          创建任务
        </Link>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-5 py-4">
        <h1 className="text-base font-semibold text-slate-950">任务列表</h1>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3 font-semibold">Job</th>
              <th className="px-5 py-3 font-semibold">来源</th>
              <th className="px-5 py-3 font-semibold">状态</th>
              <th className="px-5 py-3 font-semibold">创建时间</th>
              <th className="px-5 py-3 font-semibold">完成时间</th>
              <th className="px-5 py-3 font-semibold">错误</th>
              <th className="px-5 py-3 font-semibold">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {jobs.map((job) => (
              <tr key={job.id} className="align-top hover:bg-slate-50">
                <td className="px-5 py-4 font-mono text-xs text-slate-600">{job.id.slice(0, 8)}</td>
                <td className="max-w-sm px-5 py-4 text-slate-800">
                  <span className="line-clamp-2">{job.original_filename ?? job.source_url ?? job.source_type}</span>
                </td>
                <td className="px-5 py-4">
                  <JobStatusBadge status={job.status} />
                </td>
                <td className="px-5 py-4 text-slate-600">{formatDate(job.created_at)}</td>
                <td className="px-5 py-4 text-slate-600">{formatDate(job.completed_at)}</td>
                <td className="max-w-xs px-5 py-4 text-rose-700">{job.error_message ?? "-"}</td>
                <td className="px-5 py-4">
                  <Link
                    className="inline-flex h-9 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 hover:border-emerald-500 hover:text-emerald-700"
                    to={`/jobs/${job.id}`}
                  >
                    <Eye size={15} aria-hidden="true" />
                    查看
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
