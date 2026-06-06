import { Link, NavLink, Route, Routes } from "react-router-dom";
import { useState } from "react";
import { AudioLines, ListChecks, Podcast, Settings } from "lucide-react";

import SettingsDialog from "./components/SettingsDialog";
import HomePage from "./pages/HomePage";
import JobDetailPage from "./pages/JobDetailPage";
import JobsPage from "./pages/JobsPage";
import PodcastPage from "./pages/PodcastPage";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  [
    "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition",
    isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
  ].join(" ");

export default function App() {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="min-h-screen bg-zinc-50 text-slate-950">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6 lg:px-8">
          <Link to="/" className="inline-flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-md bg-emerald-600 text-white">
              <AudioLines size={22} aria-hidden="true" />
            </span>
            <span>
              <span className="block text-lg font-semibold">VoiceScribe WebUI</span>
              <span className="block text-xs text-slate-500">Transcription workspace</span>
            </span>
          </Link>
          <nav className="flex items-center gap-2">
            <NavLink to="/" className={navLinkClass}>
              <AudioLines size={16} aria-hidden="true" />
              新任务
            </NavLink>
            <NavLink to="/jobs" className={navLinkClass}>
              <ListChecks size={16} aria-hidden="true" />
              任务
            </NavLink>
            <NavLink to="/podcast" className={navLinkClass}>
              <Podcast size={16} aria-hidden="true" />
              播客
            </NavLink>
            <button
              className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"
              type="button"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings size={16} aria-hidden="true" />
              设置
            </button>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          <Route path="/podcast" element={<PodcastPage />} />
        </Routes>
      </main>
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
