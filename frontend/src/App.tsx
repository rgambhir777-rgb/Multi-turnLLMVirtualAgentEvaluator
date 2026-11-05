import {
  BookOpen, Bot, FileText, GitCompareArrows, LayoutDashboard, ListChecks, Menu, Play, Route as RouteIcon, Settings as SettingsIcon, ShieldCheck, WifiOff, X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { cx } from "./components/ui";
import type { Status } from "./lib/api";
import { useApi } from "./lib/hooks";
import Agents from "./pages/Agents";
import Compare from "./pages/Compare";
import ConversationView from "./pages/ConversationView";
import Dashboard from "./pages/Dashboard";
import Journeys from "./pages/Journeys";
import KnowledgeBase from "./pages/KnowledgeBase";
import Reports from "./pages/Reports";
import RunDetail from "./pages/RunDetail";
import Runs from "./pages/Runs";
import ScriptEditor from "./pages/ScriptEditor";
import Scripts from "./pages/Scripts";
import Settings from "./pages/Settings";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/journeys", label: "Journeys", icon: RouteIcon },
  { to: "/scripts", label: "Test Scripts", icon: ListChecks },
  { to: "/kb", label: "Knowledge Base", icon: BookOpen },
  { to: "/runs", label: "Runs", icon: Play },
  { to: "/compare", label: "Compare", icon: GitCompareArrows },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

function Sidebar({ status, onNavigate }: { status: Status | null; onNavigate: () => void }) {
  return (
    <div className="flex h-full flex-col bg-sidebar text-slate-300">
      <Link to="/" onClick={onNavigate} className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500 text-white shadow-lg shadow-indigo-900/40">
          <ShieldCheck className="h-5 w-5" />
        </div>
        <div>
          <div className="text-[15px] font-semibold leading-tight text-white">AgentProof</div>
          <div className="text-[11px] text-indigo-200/70">Virtual agent evaluator</div>
        </div>
      </Link>
      <nav className="flex-1 space-y-0.5 px-3">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              cx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition",
                isActive ? "bg-sidebar-active font-medium text-white" : "hover:bg-sidebar-hover hover:text-white")
            }
          >
            <Icon className="h-4 w-4" /> {label}
          </NavLink>
        ))}
      </nav>
      <div className="m-3 rounded-lg border border-sidebar-line bg-sidebar-hover/40 p-3 text-xs">
        <div className="font-medium text-slate-200">Judge</div>
        <div className="mt-1 flex items-center gap-1.5">
          <span className={cx("h-2 w-2 rounded-full", status?.offline ? "bg-amber-400" : "bg-emerald-400")} />
          {status ? (status.effective_judge === "llm" ? `LLM · ${status.llm_model}` : "Offline heuristic") : "…"}
        </div>
        <div className="mt-2 text-[11px] text-slate-400">Northwind Telecom demo · NICE CXone QA</div>
      </div>
    </div>
  );
}

export default function App() {
  const location = useLocation();
  const status = useApi<Status>("/status");
  const [menuOpen, setMenuOpen] = useState(false);
  const s = status.data;
  const reloadStatus = status.reload;
  useEffect(() => {
    void reloadStatus();
  }, [location.pathname, reloadStatus]);

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-60 lg:block">
        <Sidebar status={s} onNavigate={() => undefined} />
      </aside>
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setMenuOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-64">
            <Sidebar status={s} onNavigate={() => setMenuOpen(false)} />
          </div>
        </div>
      )}
      <div className="lg:pl-60">
        <div className="sticky top-0 z-30 flex items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur lg:hidden">
          <button onClick={() => setMenuOpen((v) => !v)} aria-label="Menu">{menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}</button>
          <span className="font-semibold">AgentProof</span>
        </div>
        {s?.offline && (
          <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-6 py-2 text-sm text-amber-800">
            <WifiOff className="h-4 w-4 shrink-0" />
            <span>
              <strong>Offline mode.</strong> {s.offline_reason} Scores still work end to end.{" "}
              <Link to="/settings" className="font-medium underline">Add an API key</Link> to enable the LLM judge.
            </span>
          </div>
        )}
        <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/journeys" element={<Journeys />} />
            <Route path="/scripts" element={<Scripts />} />
            <Route path="/scripts/new" element={<ScriptEditor />} />
            <Route path="/scripts/:id" element={<ScriptEditor />} />
            <Route path="/kb" element={<KnowledgeBase />} />
            <Route path="/runs" element={<Runs />} />
            <Route path="/runs/:id" element={<RunDetail />} />
            <Route path="/conversations/:id" element={<ConversationView />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/settings" element={<Settings onSaved={() => void status.reload()} />} />
            <Route path="*" element={<div className="py-20 text-center text-slate-500">Page not found. <Link className="text-indigo-600 underline" to="/">Go to the dashboard</Link></div>} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
