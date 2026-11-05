import { Play, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ProgressBar, StatusBadge } from "../components/run";
import { Button, Card, EmptyState, ErrorBox, Field, inputClass, PageHeader, Spinner, Toast, VerdictBadge, cx } from "../components/ui";
import { api, type Agent, type Run, type TestScript } from "../lib/api";
import { CHANNEL_LABEL, CHANNELS, fmtDate, fmtPct, fmtScore, variantLabel } from "../lib/format";
import { useApi } from "../lib/hooks";

export default function Runs() {
  const navigate = useNavigate();
  const runs = useApi<Run[]>("/runs", { poll: (rs) => rs.some((r) => r.status === "queued" || r.status === "running") });
  const agents = useApi<Agent[]>("/agents");
  const scripts = useApi<TestScript[]>("/scripts");
  const [agentId, setAgentId] = useState<number | "">("");
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [judgeMode, setJudgeMode] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    // Select every script by default once the list first loads.
    if (scripts.data) setSelected((prev) => (prev.length ? prev : scripts.data!.map((s) => s.id)));
  }, [scripts.data]);
  useEffect(() => {
    if (agents.data?.length && agentId === "") setAgentId(agents.data[agents.data.length > 2 ? 2 : 0].id);
  }, [agents.data, agentId]);

  const conversations = useMemo(() => {
    const chosen = (scripts.data ?? []).filter((s) => selected.includes(s.id));
    return channels.length ? chosen.length * channels.length : chosen.length;
  }, [scripts.data, selected, channels]);

  const start = async () => {
    if (agentId === "") return;
    setStarting(true);
    setError(null);
    try {
      const run = await api.post<Run>("/runs", { name, agent_id: agentId, script_ids: selected, channels, judge_mode: judgeMode || null });
      navigate(`/runs/${run.id}`);
    } catch (e) {
      setError((e as Error).message);
      setStarting(false);
    }
  };

  const remove = async (run: Run) => {
    if (!window.confirm(`Delete run "${run.name}" and all its scores?`)) return;
    try {
      await api.del(`/runs/${run.id}`);
      await runs.reload();
    } catch (e) {
      setToast((e as Error).message);
    }
  };

  const allChecked = scripts.data && selected.length === scripts.data.length;
  return (
    <>
      <PageHeader title="Runs" description="Run a test suite – selected scripts × one agent × channels. Runs execute in the background; every agent turn is judged as it completes." />

      <Card title="Start a run">
        {agents.loading || scripts.loading ? <Spinner /> : (
          <div className="grid gap-6 xl:grid-cols-[340px_1fr]">
            <div className="space-y-4">
              {error && <ErrorBox message={error} />}
              <Field label="Agent">
                <select className={inputClass} value={agentId} onChange={(e) => setAgentId(Number(e.target.value))}>
                  {(agents.data ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </Field>
              <Field label="Run name (optional)"><input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Pre-release regression" /></Field>
              <Field label="Channels" hint="None selected = each script runs on its own default channel.">
                <div className="flex flex-wrap gap-2">
                  {CHANNELS.map((c) => (
                    <button key={c} type="button" onClick={() => setChannels(channels.includes(c) ? channels.filter((x) => x !== c) : [...channels, c])}
                      className={cx("rounded-lg px-3 py-1.5 text-sm ring-1 ring-inset", channels.includes(c) ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-50")}>
                      {CHANNEL_LABEL[c]}
                    </button>
                  ))}
                </div>
              </Field>
              <Field label="Judge">
                <select className={inputClass} value={judgeMode} onChange={(e) => setJudgeMode(e.target.value)}>
                  <option value="">Default from Settings</option>
                  <option value="auto">Auto (LLM if a key is set, else offline)</option>
                  <option value="llm">LLM-as-judge</option>
                  <option value="heuristic">Offline heuristic</option>
                </select>
              </Field>
              <div className="rounded-lg bg-indigo-50 px-3 py-2 text-sm text-indigo-800">{conversations} conversation{conversations === 1 ? "" : "s"} will be run and scored.</div>
              <Button variant="primary" className="w-full" loading={starting} disabled={agentId === "" || !selected.length} onClick={() => void start()}><Play className="h-4 w-4" />Start run</Button>
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-medium text-slate-700">Scripts ({selected.length} selected)</span>
                <button className="text-xs font-medium text-indigo-600" onClick={() => setSelected(allChecked ? [] : (scripts.data ?? []).map((s) => s.id))}>{allChecked ? "Clear all" : "Select all"}</button>
              </div>
              {!scripts.data?.length ? <EmptyState title="No scripts" message="Create test scripts first." action={<Link className="text-sm text-indigo-600 underline" to="/scripts">Go to Test Scripts</Link>} /> : (
                <div className="grid max-h-[360px] gap-1 overflow-y-auto rounded-lg border border-slate-200 p-2 sm:grid-cols-2">
                  {scripts.data.map((s) => (
                    <label key={s.id} className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-slate-50">
                      <input type="checkbox" className="mt-0.5 rounded text-indigo-600" checked={selected.includes(s.id)}
                        onChange={(e) => setSelected(e.target.checked ? [...selected, s.id] : selected.filter((x) => x !== s.id))} />
                      <span><span className="text-slate-800">{s.name}</span><span className="block text-xs text-slate-500">{CHANNEL_LABEL[s.channel]} · {variantLabel(s.variant)} · {s.turn_count} turns</span></span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </Card>

      <h2 className="mb-3 mt-8 text-sm font-semibold text-slate-900">Run history</h2>
      {runs.loading ? <Spinner /> : runs.error ? <ErrorBox message={runs.error} onRetry={runs.reload} /> : !runs.data?.length ? (
        <EmptyState title="No runs yet" message="Start your first run above." />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-card">
          <table className="min-w-full divide-y divide-slate-100 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-medium text-slate-500">
              <tr><th className="px-4 py-3">Run</th><th className="px-4 py-3">Status</th><th className="px-4 py-3">Verdict</th><th className="px-4 py-3">Accuracy</th><th className="px-4 py-3">Context</th><th className="px-4 py-3">Halluc.</th><th className="px-4 py-3">Judge</th><th className="px-4 py-3">Started</th><th /></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {runs.data.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3"><Link to={`/runs/${r.id}`} className="font-medium text-slate-900 hover:text-indigo-600">#{r.id} {r.name}</Link><div className="text-xs text-slate-500">{r.agent_name}</div></td>
                  <td className="px-4 py-3"><div className="flex flex-col gap-1"><StatusBadge run={r} />{r.status !== "completed" && <ProgressBar run={r} />}</div></td>
                  <td className="px-4 py-3">{r.status === "completed" ? <VerdictBadge verdict={r.verdict} /> : r.error ? <span className="text-xs text-red-600">{r.error.slice(0, 60)}</span> : "—"}</td>
                  <td className="px-4 py-3 tabular-nums">{fmtScore(r.metrics.avg_accuracy)}</td>
                  <td className="px-4 py-3 tabular-nums">{fmtScore(r.metrics.avg_context)}</td>
                  <td className="px-4 py-3 tabular-nums">{fmtPct(r.metrics.hallucination_rate)}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">{r.judge_mode}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">{fmtDate(r.started_at ?? r.created_at)}</td>
                  <td className="px-4 py-3 text-right"><Button variant="ghost" className="px-2" aria-label="Delete run" onClick={() => void remove(r)}><Trash2 className="h-4 w-4" /></Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {toast && <Toast message={toast} tone="error" onClose={() => setToast(null)} />}
    </>
  );
}
