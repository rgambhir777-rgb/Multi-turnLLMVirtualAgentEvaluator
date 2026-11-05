import { ArrowRight, Bot, MessagesSquare, Play, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { axisProps, ChartCard, ChartTooltip } from "../components/charts";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner, VerdictBadge, cx } from "../components/ui";
import type { Dashboard as DashboardData } from "../lib/api";
import { agentColor, CHANNEL_LABEL, fmtDay, fmtPct, fmtScore, VERDICT_STYLE } from "../lib/format";
import { useApi } from "../lib/hooks";

const METRIC_SERIES = [
  { key: "avg_accuracy", name: "Accuracy", color: "#6250d6" },
  { key: "avg_context", name: "Context awareness", color: "#e87ba4" },
  { key: "avg_channel_fit", name: "Channel fit", color: "#eda100" },
] as const;

function Kpi({ icon: Icon, label, value, hint }: { icon: typeof Bot; label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500"><Icon className="h-4 w-4 text-indigo-500" />{label}</div>
      <div className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

function Metric({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div>
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className={cx("text-sm font-semibold tabular-nums", ok ? "text-slate-900" : "text-red-600")}>{value}</div>
    </div>
  );
}

export default function Dashboard() {
  const { data, error, loading, reload } = useApi<DashboardData>("/dashboard");
  if (loading) return <Spinner label="Loading dashboard…" />;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return null;
  const th = data.thresholds;

  if (!data.cards.length) {
    return (
      <>
        <PageHeader title="Readiness dashboard" />
        <EmptyState title="No completed runs yet" message="Start a test run to see readiness verdicts, trends and risks here."
          action={<Link to="/runs" className="rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white">Start a run</Link>} />
      </>
    );
  }

  const latest = data.kpis.latest;
  const hallucinationRows = data.channel_scores.map((row) => {
    const out: Record<string, number | string> = { channel: CHANNEL_LABEL[String(row.channel)] };
    data.agents.forEach((a) => (out[a] = Number(row[`${a}__hallucination_rate`] ?? 0)));
    return out;
  });
  const accuracyRows = data.channel_scores.map((row) => ({ ...row, channel: CHANNEL_LABEL[String(row.channel)] }));

  return (
    <>
      <PageHeader
        title="Readiness dashboard"
        description="Go / No-Go evidence for each virtual agent: every agent turn is scored for context awareness, accuracy against the knowledge base, hallucination and channel fit."
        actions={<Link to="/runs" className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"><Play className="h-4 w-4" />New run</Link>}
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.cards.map((card) => {
          const m = card.metrics;
          const style = VERDICT_STYLE[card.verdict];
          return (
            <Link key={card.agent_id} to={`/runs/${card.run_id}`} className={cx("group rounded-xl border bg-white p-5 shadow-card ring-1 ring-inset transition hover:shadow-md", style.ring, "border-transparent")}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: agentColor(card.agent_name, data.agents) }} />
                    <h3 className="font-semibold text-slate-900">{card.agent_name}</h3>
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">Last run {fmtDay(card.finished_at)} · {m.conversations} conversations · {m.turns} turns</p>
                </div>
                <VerdictBadge verdict={card.verdict} size="lg" />
              </div>
              <p className={cx("mt-3 text-sm font-medium", style.text)}>{style.label}</p>
              <div className="mt-3 grid grid-cols-3 gap-3 sm:grid-cols-6">
                <Metric label="Accuracy" value={fmtScore(m.avg_accuracy)} ok={m.avg_accuracy >= th.min_accuracy} />
                <Metric label="Context" value={fmtScore(m.avg_context)} ok={m.avg_context >= th.min_context} />
                <Metric label="Halluc." value={fmtPct(m.hallucination_rate)} ok={m.hallucination_rate <= th.max_hallucination_rate} />
                <Metric label="Channel" value={fmtScore(m.avg_channel_fit)} ok={m.avg_channel_fit >= th.min_channel_fit} />
                <Metric label="Tasks" value={fmtPct(m.task_completion_rate, 0)} ok={m.task_completion_rate >= th.min_task_completion} />
                <Metric label="Critical" value={String(m.critical_failures)} ok={m.critical_failures <= th.max_critical_failures} />
              </div>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {Object.entries(card.channels).map(([ch, v]) => (
                  <span key={ch} className={cx("rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset", VERDICT_STYLE[v].bg, VERDICT_STYLE[v].text, VERDICT_STYLE[v].ring)}>
                    {CHANNEL_LABEL[ch]}: {v}
                  </span>
                ))}
              </div>
              {card.reasons.length > 0 && (
                <ul className="mt-3 space-y-1 text-xs text-slate-600">
                  {card.reasons.slice(0, 3).map((r) => (
                    <li key={r.text} className="flex gap-1.5"><ShieldAlert className={cx("mt-0.5 h-3.5 w-3.5 shrink-0", r.severity === "hard" ? "text-red-500" : "text-amber-500")} />{r.text}</li>
                  ))}
                </ul>
              )}
              <div className="mt-4 flex items-center gap-1 text-xs font-medium text-indigo-600 opacity-80 group-hover:opacity-100">View run <ArrowRight className="h-3.5 w-3.5" /></div>
            </Link>
          );
        })}
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi icon={Play} label="Completed runs" value={String(data.kpis.runs)} />
        <Kpi icon={MessagesSquare} label="Conversations tested" value={data.kpis.conversations.toLocaleString()} />
        <Kpi icon={Bot} label="Agent turns scored" value={data.kpis.turns.toLocaleString()} />
        <Kpi icon={ShieldAlert} label="Latest run hallucination rate" value={fmtPct(latest?.metrics.hallucination_rate)}
          hint={latest ? `${latest.agent_name} · limit ${fmtPct(th.max_hallucination_rate)}` : undefined} />
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        <ChartCard
          title="Score trends across runs"
          subtitle={`Average per run (0–5). Dashed line = ${th.min_accuracy.toFixed(1)} readiness threshold.`}
          rows={data.trends}
          columns={[
            { key: "run", label: "Run", render: (r) => r.label },
            { key: "date", label: "Date", render: (r) => fmtDay(r.date) },
            { key: "acc", label: "Accuracy", render: (r) => fmtScore(r.avg_accuracy) },
            { key: "ctx", label: "Context", render: (r) => fmtScore(r.avg_context) },
            { key: "fit", label: "Channel fit", render: (r) => fmtScore(r.avg_channel_fit) },
          ]}
        >
          <ResponsiveContainer>
            <LineChart data={data.trends} margin={{ top: 8, right: 16, left: -12, bottom: 0 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="label" {...axisProps} interval={0} tickFormatter={(v: string) => (v.length > 22 ? `${v.slice(0, 21)}…` : v)} />
              <YAxis domain={[0, 5]} ticks={[0, 1, 2, 3, 4, 5]} {...axisProps} />
              <Tooltip content={<ChartTooltip />} />
              <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
              <ReferenceLine y={th.min_accuracy} stroke="#94a3b8" strokeDasharray="4 4" />
              {METRIC_SERIES.map((s) => (
                <Line key={s.key} isAnimationActive={false} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: "#fff" }} activeDot={{ r: 6 }} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Accuracy by channel"
          subtitle="Latest run per agent, average accuracy (0–5)."
          rows={accuracyRows}
          columns={[{ key: "ch", label: "Channel", render: (r) => String(r.channel) },
            ...data.agents.map((a) => ({ key: a, label: a, render: (r: Record<string, number | string>) => fmtScore(Number(r[a])) }))]}
        >
          <ResponsiveContainer>
            <BarChart data={accuracyRows} margin={{ top: 8, right: 8, left: -12, bottom: 0 }} barGap={2}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="channel" {...axisProps} />
              <YAxis domain={[0, 5]} ticks={[0, 1, 2, 3, 4, 5]} {...axisProps} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "#f1f5f9" }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <ReferenceLine y={th.min_accuracy} stroke="#94a3b8" strokeDasharray="4 4" />
              {data.agents.map((a) => <Bar key={a} isAnimationActive={false} dataKey={a} name={a} fill={agentColor(a, data.agents)} radius={[4, 4, 0, 0]} maxBarSize={28} />)}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Hallucination rate by channel"
          subtitle={`Share of turns with a contradicted or unsupported claim. Dashed line = ${fmtPct(th.max_hallucination_rate)} limit.`}
          rows={hallucinationRows}
          columns={[{ key: "ch", label: "Channel", render: (r) => String(r.channel) },
            ...data.agents.map((a) => ({ key: a, label: a, render: (r: Record<string, number | string>) => fmtPct(Number(r[a])) }))]}
        >
          <ResponsiveContainer>
            <BarChart data={hallucinationRows} margin={{ top: 8, right: 8, left: -6, bottom: 0 }} barGap={2}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="channel" {...axisProps} />
              <YAxis tickFormatter={(v: number) => `${Math.round(v * 100)}%`} {...axisProps} />
              <Tooltip content={<ChartTooltip format={(v) => fmtPct(v)} />} cursor={{ fill: "#f1f5f9" }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <ReferenceLine y={th.max_hallucination_rate} stroke="#94a3b8" strokeDasharray="4 4" />
              {data.agents.map((a) => <Bar key={a} isAnimationActive={false} dataKey={a} name={a} fill={agentColor(a, data.agents)} radius={[4, 4, 0, 0]} maxBarSize={28} />)}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Worst journeys"
          subtitle="Lowest average accuracy across each agent's latest run."
          rows={data.worst_journeys}
          columns={[
            { key: "j", label: "Journey", render: (r) => r.journey },
            { key: "a", label: "Accuracy", render: (r) => fmtScore(r.avg_accuracy) },
            { key: "h", label: "Halluc. rate", render: (r) => fmtPct(r.hallucination_rate) },
            { key: "c", label: "Critical", render: (r) => r.critical },
          ]}
        >
          <ResponsiveContainer>
            <BarChart data={data.worst_journeys} layout="vertical" margin={{ top: 4, right: 40, left: 8, bottom: 0 }}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" domain={[0, 5]} ticks={[0, 1, 2, 3, 4, 5]} {...axisProps} />
              <YAxis type="category" dataKey="journey" width={190} {...axisProps} tickFormatter={(v: string) => (v.length > 28 ? `${v.slice(0, 27)}…` : v)} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "#f1f5f9" }} />
              <Bar isAnimationActive={false} dataKey="avg_accuracy" name="Accuracy" fill="#6250d6" radius={[0, 4, 4, 0]} maxBarSize={18}
                label={{ position: "right", fontSize: 11, fill: "#334155", formatter: (v: number) => v.toFixed(2) }} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <Card className="mt-6" title="How the verdict is decided">
        <p className="text-sm text-slate-600">
          <strong>GO</strong> requires accuracy ≥ {th.min_accuracy}, context awareness ≥ {th.min_context}, hallucination rate ≤ {fmtPct(th.max_hallucination_rate)},
          channel fit ≥ {th.min_channel_fit}, task completion ≥ {fmtPct(th.min_task_completion, 0)} and at most {th.max_critical_failures} critical failures.
          Narrow misses give <strong>CONDITIONAL</strong>; wider misses or any critical failure give <strong>NO-GO</strong>. Thresholds are editable in <Link to="/settings" className="text-indigo-600 underline">Settings</Link>.
        </p>
      </Card>
    </>
  );
}
