import { ArrowDownRight, ArrowRight, ArrowUpRight, Minus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChannelTag } from "../components/channel";
import { Card, EmptyState, ErrorBox, Field, inputClass, PageHeader, ScorePill, Spinner, VerdictBadge, cx } from "../components/ui";
import type { CompareResult, Run } from "../lib/api";
import { fmtDay, fmtPct, fmtScore } from "../lib/format";
import { useApi } from "../lib/hooks";

const METRICS: { key: string; label: string; pct?: boolean; lowerBetter?: boolean; int?: boolean }[] = [
  { key: "avg_accuracy", label: "Accuracy" },
  { key: "avg_context", label: "Context awareness" },
  { key: "avg_hallucination", label: "Hallucination score" },
  { key: "hallucination_rate", label: "Hallucination rate", pct: true, lowerBetter: true },
  { key: "avg_channel_fit", label: "Channel fit" },
  { key: "task_completion_rate", label: "Task completion", pct: true },
  { key: "critical_failures", label: "Critical failures", lowerBetter: true, int: true },
];

function fmt(v: number | undefined, m: (typeof METRICS)[number]): string {
  if (v === undefined) return "—";
  return m.pct ? fmtPct(v) : m.int ? String(v) : fmtScore(v);
}

function Delta({ value, metric }: { value: number; metric: (typeof METRICS)[number] }) {
  if (Math.abs(value) < 1e-9) return <span className="inline-flex items-center gap-0.5 text-xs text-slate-500"><Minus className="h-3.5 w-3.5" />no change</span>;
  const better = metric.lowerBetter ? value < 0 : value > 0;
  const Icon = value > 0 ? ArrowUpRight : ArrowDownRight;
  const text = metric.pct ? `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)} pts` : metric.int ? `${value > 0 ? "+" : ""}${value}` : `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
  return <span className={cx("inline-flex items-center gap-0.5 text-xs font-semibold", better ? "text-emerald-700" : "text-red-600")}><Icon className="h-3.5 w-3.5" />{text}<span className="font-normal">{better ? " better" : " worse"}</span></span>;
}

export default function Compare() {
  const [params, setParams] = useSearchParams();
  const runs = useApi<Run[]>("/runs");
  const completed = (runs.data ?? []).filter((r) => r.status === "completed");
  const [a, setA] = useState<number | null>(params.get("a") ? Number(params.get("a")) : null);
  const [b, setB] = useState<number | null>(params.get("b") ? Number(params.get("b")) : null);

  useEffect(() => {
    if (!completed.length) return;
    const oldest = completed[completed.length - 1].id;
    const newest = completed[0].id;
    if (a === null) setA(b === oldest ? newest : oldest);
    if (b === null) setB(a === newest ? oldest : newest);
  }, [completed, a, b]);

  useEffect(() => {
    if (a !== null && b !== null) setParams({ a: String(a), b: String(b) }, { replace: true });
  }, [a, b, setParams]);

  const result = useApi<CompareResult>(a !== null && b !== null && a !== b ? `/compare?a=${a}&b=${b}` : null);

  if (runs.loading) return <Spinner />;
  if (runs.error) return <ErrorBox message={runs.error} onRetry={runs.reload} />;
  if (completed.length < 2) return (<><PageHeader title="Compare runs" /><EmptyState title="Need at least two completed runs" message="Run another agent or a new build to compare them side by side." /></>);

  const r = result.data;
  return (
    <>
      <PageHeader title="Compare runs" description="Side-by-side readiness of two runs – for example Agent v1 vs Agent v3, or last week's build vs today's." />
      <Card>
        <div className="grid items-end gap-4 md:grid-cols-[1fr_auto_1fr]">
          <Field label="Baseline (A)">
            <select className={inputClass} value={a ?? ""} onChange={(e) => setA(Number(e.target.value))}>
              {completed.map((run) => <option key={run.id} value={run.id}>#{run.id} {run.name} ({fmtDay(run.finished_at)})</option>)}
            </select>
          </Field>
          <ArrowRight className="mb-2.5 hidden h-5 w-5 text-slate-400 md:block" />
          <Field label="Candidate (B)">
            <select className={inputClass} value={b ?? ""} onChange={(e) => setB(Number(e.target.value))}>
              {completed.map((run) => <option key={run.id} value={run.id}>#{run.id} {run.name} ({fmtDay(run.finished_at)})</option>)}
            </select>
          </Field>
        </div>
        {a === b && <p className="mt-3 text-sm text-amber-700">Pick two different runs.</p>}
      </Card>

      {result.loading && <Spinner />}
      {result.error && <div className="mt-4"><ErrorBox message={result.error} onRetry={result.reload} /></div>}
      {r && (
        <>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {[r.a, r.b].map((run, i) => (
              <div key={run.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-card">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{i === 0 ? "Baseline (A)" : "Candidate (B)"}</div>
                <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                  <Link to={`/runs/${run.id}`} className="font-semibold text-slate-900 hover:text-indigo-600">#{run.id} {run.agent_name}</Link>
                  <VerdictBadge verdict={run.verdict} size="lg" />
                </div>
                <ul className="mt-3 space-y-1 text-xs text-slate-600">{(run.summary.reasons ?? []).slice(0, 4).map((x) => <li key={x.text}>• {x.text}</li>)}{!run.summary.reasons?.length && <li>All readiness thresholds met.</li>}</ul>
              </div>
            ))}
          </div>

          <Card className="mt-6" title="Metric deltas (B vs A)">
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs text-slate-500"><tr><th className="pb-2">Metric</th><th className="pb-2">A</th><th className="pb-2">B</th><th className="pb-2">Change</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {METRICS.map((m) => (
                    <tr key={m.key}>
                      <td className="py-2 text-slate-700">{m.label}</td>
                      <td className="py-2 tabular-nums">{fmt(r.a.metrics[m.key as keyof typeof r.a.metrics] as number, m)}</td>
                      <td className="py-2 font-semibold tabular-nums">{fmt(r.b.metrics[m.key as keyof typeof r.b.metrics] as number, m)}</td>
                      <td className="py-2"><Delta value={r.deltas[m.key] ?? 0} metric={m} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="mt-6 grid gap-6 xl:grid-cols-2">
            <Card title="By channel">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs text-slate-500"><tr><th className="pb-2">Channel</th><th className="pb-2">Verdict A → B</th><th className="pb-2">Accuracy A → B</th><th className="pb-2">Halluc. A → B</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {r.by_channel.map((c) => (
                    <tr key={c.channel}>
                      <td className="py-2"><ChannelTag channel={c.channel} /></td>
                      <td className="py-2"><span className="inline-flex items-center gap-1"><VerdictBadge verdict={c.verdict_a} /><ArrowRight className="h-3 w-3 text-slate-400" /><VerdictBadge verdict={c.verdict_b} /></span></td>
                      <td className="py-2 tabular-nums">{fmtScore(c.a.avg_accuracy)} → <strong>{fmtScore(c.b.avg_accuracy)}</strong></td>
                      <td className="py-2 tabular-nums">{fmtPct(c.a.hallucination_rate)} → <strong>{fmtPct(c.b.hallucination_rate)}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card title="By journey">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs text-slate-500"><tr><th className="pb-2">Journey</th><th className="pb-2">Accuracy A → B</th><th className="pb-2">Halluc. A → B</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {r.journeys.map((j) => (
                    <tr key={j.journey}>
                      <td className="py-2 text-slate-700">{j.journey}</td>
                      <td className="py-2 tabular-nums">{fmtScore(j.a?.avg_accuracy)} → <strong>{fmtScore(j.b?.avg_accuracy)}</strong></td>
                      <td className="py-2 tabular-nums">{fmtPct(j.a?.hallucination_rate)} → <strong>{fmtPct(j.b?.hallucination_rate)}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          <Card className="mt-6" title="Same script, both runs" subtitle="Open either side to inspect the turn-level evidence.">
            {!r.conversations.length ? <p className="text-sm text-slate-500">The two runs share no script/channel pairs.</p> : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="text-left text-xs text-slate-500"><tr><th className="pb-2">Script</th><th className="pb-2">Channel</th><th className="pb-2">A (accuracy · halluc.)</th><th className="pb-2">B (accuracy · halluc.)</th></tr></thead>
                  <tbody className="divide-y divide-slate-100">
                    {r.conversations.map((p) => (
                      <tr key={`${p.script_name}-${p.channel}`}>
                        <td className="py-2 text-slate-700">{p.script_name}</td>
                        <td className="py-2"><ChannelTag channel={p.channel} /></td>
                        <td className="py-2"><Link to={`/conversations/${p.a.id}`} className="inline-flex gap-1 hover:opacity-80"><ScorePill label="A" value={p.a.avg_accuracy} /><ScorePill label="H" value={p.a.avg_hallucination} /></Link></td>
                        <td className="py-2"><Link to={`/conversations/${p.b.id}`} className="inline-flex gap-1 hover:opacity-80"><ScorePill label="A" value={p.b.avg_accuracy} /><ScorePill label="H" value={p.b.avg_hallucination} /></Link></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </>
  );
}
