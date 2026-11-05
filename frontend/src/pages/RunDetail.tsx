import { AlertTriangle, ArrowLeft, CheckCircle2, FileDown, FileText, GitCompareArrows, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChannelTag } from "../components/channel";
import { Card, EmptyState, ErrorBox, inputClass, PageHeader, ScorePill, Spinner, VerdictBadge, cx } from "../components/ui";
import type { RunDetail as RunDetailData } from "../lib/api";
import { CHANNEL_LABEL, CHANNELS, fmtDate, fmtPct, fmtScore, variantLabel, VERDICT_STYLE } from "../lib/format";
import { useApi } from "../lib/hooks";
import { linkButton, ProgressBar, StatusBadge } from "../components/run";

export default function RunDetail() {
  const { id } = useParams();
  const run = useApi<RunDetailData>(`/runs/${id}`, { poll: (r) => r.status === "queued" || r.status === "running" });
  const [channel, setChannel] = useState("");
  const [onlyProblems, setOnlyProblems] = useState(false);

  const conversations = useMemo(() => {
    const list = (run.data?.conversations ?? []).filter((c) => (!channel || c.channel === channel) &&
      (!onlyProblems || c.critical_failures > 0 || c.hallucinated_turns > 0 || !c.task_completed));
    return [...list].sort((a, b) => a.avg_accuracy + a.avg_hallucination - (b.avg_accuracy + b.avg_hallucination));
  }, [run.data, channel, onlyProblems]);

  if (run.loading) return <Spinner />;
  if (run.error || !run.data) return <ErrorBox message={run.error ?? "Run not found."} onRetry={run.reload} />;
  const r = run.data;
  const s = r.summary;
  const m = s.metrics;
  const done = r.status === "completed";

  return (
    <>
      <Link to="/runs" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"><ArrowLeft className="h-4 w-4" />All runs</Link>
      <PageHeader
        title={`#${r.id} ${r.name}`}
        description={`${r.agent_name} · ${r.channels.length ? r.channels.map((c) => CHANNEL_LABEL[c]).join(", ") : "script default channels"} · judge ${r.judge_mode} · started ${fmtDate(r.started_at ?? r.created_at)}`}
        actions={done ? <>
          <a className={linkButton} href={`/api/runs/${r.id}/report.html`} target="_blank" rel="noreferrer"><FileText className="h-4 w-4" />HTML report</a>
          <a className={linkButton} href={`/api/runs/${r.id}/report.pdf`}><FileDown className="h-4 w-4" />PDF</a>
          <Link className={linkButton} to={`/compare?b=${r.id}`}><GitCompareArrows className="h-4 w-4" />Compare</Link>
        </> : undefined}
      />

      {!done && (
        <Card className="mb-6">
          <div className="flex flex-wrap items-center gap-4">
            <StatusBadge run={r} />
            <ProgressBar run={r} />
            <span className="text-sm text-slate-500">{r.status === "failed" ? r.error : "Conversations are executed and judged in the background. This page updates automatically."}</span>
          </div>
        </Card>
      )}
      {done && r.error && <div className="mb-4"><ErrorBox message={r.error} /></div>}
      {s.warnings?.map((w) => <div key={w} className="mb-4 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800"><AlertTriangle className="mt-0.5 h-4 w-4" />{w}</div>)}

      {done && s.verdict && m && (
        <div className="grid gap-4 xl:grid-cols-[1.1fr_1fr]">
          <div className={cx("rounded-xl p-5 ring-1 ring-inset", VERDICT_STYLE[s.verdict].bg, VERDICT_STYLE[s.verdict].ring)}>
            <div className="flex flex-wrap items-center gap-3">
              <VerdictBadge verdict={s.verdict} size="lg" />
              <span className={cx("text-sm font-medium", VERDICT_STYLE[s.verdict].text)}>{VERDICT_STYLE[s.verdict].label}</span>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-4 sm:grid-cols-6">
              {[["Accuracy", fmtScore(m.avg_accuracy)], ["Context", fmtScore(m.avg_context)], ["Halluc. rate", fmtPct(m.hallucination_rate)],
                ["Channel fit", fmtScore(m.avg_channel_fit)], ["Tasks done", fmtPct(m.task_completion_rate, 0)], ["Critical", String(m.critical_failures)]].map(([label, value]) => (
                <div key={label}><div className="text-xs text-slate-500">{label}</div><div className="text-lg font-semibold tabular-nums text-slate-900">{value}</div></div>
              ))}
            </div>
            <div className="mt-4 space-y-1 text-sm">
              {s.reasons?.map((reason) => (
                <div key={reason.text} className="flex gap-2 text-slate-700"><ShieldAlert className={cx("mt-0.5 h-4 w-4 shrink-0", reason.severity === "hard" ? "text-red-500" : "text-amber-500")} />{reason.text}</div>
              ))}
              {s.passed?.map((p) => <div key={p} className="flex gap-2 text-slate-600"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />{p}</div>)}
            </div>
            <p className="mt-3 text-xs text-slate-500">{m.conversations} conversations · {m.turns} turns · judged by {s.judges?.join(", ")}</p>
          </div>
          <Card title="Readiness by channel">
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th className="pb-2">Channel</th><th className="pb-2">Verdict</th><th className="pb-2">Acc.</th><th className="pb-2">Ctx.</th><th className="pb-2">Halluc.</th><th className="pb-2">Fit</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {Object.entries(s.by_channel ?? {}).map(([ch, d]) => (
                  <tr key={ch} title={d.reasons.map((x) => x.text).join("\n")}>
                    <td className="py-2"><ChannelTag channel={ch} /></td>
                    <td className="py-2"><VerdictBadge verdict={d.verdict} /></td>
                    <td className="py-2 tabular-nums">{fmtScore(d.metrics.avg_accuracy)}</td>
                    <td className="py-2 tabular-nums">{fmtScore(d.metrics.avg_context)}</td>
                    <td className="py-2 tabular-nums">{fmtPct(d.metrics.hallucination_rate)}</td>
                    <td className="py-2 tabular-nums">{fmtScore(d.metrics.avg_channel_fit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      <div className="mb-3 mt-8 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-slate-900">Conversations <span className="font-normal text-slate-500">(worst first)</span></h2>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" className="rounded text-indigo-600" checked={onlyProblems} onChange={(e) => setOnlyProblems(e.target.checked)} />Only problems</label>
          <select className={`${inputClass} w-36`} value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option value="">All channels</option>
            {CHANNELS.map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}
          </select>
        </div>
      </div>
      {!conversations.length ? <EmptyState title={r.conversations.length ? "No conversations match the filter" : "No conversations yet"} /> : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-card">
          <table className="min-w-full divide-y divide-slate-100 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-medium text-slate-500">
              <tr><th className="px-4 py-3">Script</th><th className="px-4 py-3">Channel</th><th className="px-4 py-3">Scores</th><th className="px-4 py-3">Task</th><th className="px-4 py-3">Issues</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {conversations.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3"><Link to={`/conversations/${c.id}`} className="font-medium text-slate-900 hover:text-indigo-600">{c.script_name}</Link><div className="text-xs text-slate-500">{c.journey_name} · {variantLabel(c.variant)}</div></td>
                  <td className="px-4 py-3"><ChannelTag channel={c.channel} /></td>
                  <td className="px-4 py-3"><div className="flex flex-wrap gap-1"><ScorePill label="C" value={c.avg_context} /><ScorePill label="A" value={c.avg_accuracy} /><ScorePill label="H" value={c.avg_hallucination} /><ScorePill label="F" value={c.avg_channel_fit} /></div></td>
                  <td className="px-4 py-3">{c.status === "failed" ? <span className="text-xs text-red-600">{c.error}</span> : c.task_completed ? <span className="text-emerald-700">✓ Completed</span> : <span className="text-red-600">✗ Not completed</span>}</td>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    {c.critical_failures > 0 && <div className="text-red-600">{c.critical_failures} critical</div>}
                    {c.hallucinated_turns > 0 && <div>{c.hallucinated_turns} hallucinated turn{c.hallucinated_turns === 1 ? "" : "s"}</div>}
                    {!c.critical_failures && !c.hallucinated_turns && "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
