import type { Run } from "../lib/api";
import { Badge, cx } from "./ui";

export const linkButton =
  "inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-2 text-sm font-medium text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50";

export function StatusBadge({ run }: { run: Run }) {
  const styles: Record<Run["status"], string> = {
    queued: "bg-slate-50 text-slate-600 ring-slate-200",
    running: "bg-indigo-50 text-indigo-700 ring-indigo-200",
    completed: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    failed: "bg-red-50 text-red-700 ring-red-200",
  };
  return (
    <Badge className={styles[run.status]}>
      {run.status === "running" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" />}
      {run.status}
    </Badge>
  );
}

export function ProgressBar({ run }: { run: Run }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-28 rounded-full bg-slate-100">
        <div className={cx("h-1.5 rounded-full transition-all", run.status === "failed" ? "bg-red-400" : "bg-indigo-500")}
          style={{ width: `${Math.round(run.progress * 100)}%` }} />
      </div>
      <span className="text-xs tabular-nums text-slate-500">{run.completed_conversations}/{run.total_conversations}</span>
    </div>
  );
}
