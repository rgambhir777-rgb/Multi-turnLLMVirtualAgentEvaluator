import { AlertOctagon, ArrowLeft, Bot, CheckCircle2, CircleHelp, Mail, Mic, Smartphone, User, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChannelTag } from "../components/channel";
import { Badge, Card, ErrorBox, PageHeader, ScorePill, Spinner, cx } from "../components/ui";
import type { Claim, ConversationDetail, Turn } from "../lib/api";
import { variantLabel } from "../lib/format";
import { useApi } from "../lib/hooks";

function worst(turn: Turn): number {
  return Math.min(turn.context_score, turn.accuracy_score, turn.hallucination_score);
}

function toneRing(turn: Turn): string {
  if (turn.critical) return "ring-red-400 bg-red-50/60";
  const w = worst(turn);
  if (w >= 4) return "ring-emerald-300 bg-emerald-50/40";
  if (w >= 2.5) return "ring-amber-300 bg-amber-50/50";
  return "ring-red-300 bg-red-50/50";
}

const CLAIM_STYLE: Record<Claim["label"], { icon: typeof CheckCircle2; cls: string }> = {
  Supported: { icon: CheckCircle2, cls: "text-emerald-700 bg-emerald-50 ring-emerald-200" },
  Contradicted: { icon: XCircle, cls: "text-red-700 bg-red-50 ring-red-200" },
  Unsupported: { icon: CircleHelp, cls: "text-amber-700 bg-amber-50 ring-amber-200" },
};

function AgentBubble({ turn, channel, selected, onSelect }: { turn: Turn; channel: string; selected: boolean; onSelect: () => void }) {
  const sms = channel === "sms";
  return (
    <button onClick={onSelect} className={cx("w-full text-left transition", selected ? "scale-[1.005]" : "hover:scale-[1.003]")}>
      <div className={cx("rounded-2xl px-4 py-3 ring-2", toneRing(turn), selected && "shadow-md outline outline-2 outline-offset-2 outline-indigo-500",
        channel === "email" && "rounded-lg", sms && "rounded-3xl")}>
        <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
          {channel === "voice" ? <Mic className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
          <span className="font-medium">{channel === "voice" ? "Agent (spoken response)" : channel === "email" ? "Reply from agent" : "Agent"}</span>
          <span className="ml-auto flex gap-1"><ScorePill label="C" value={turn.context_score} /><ScorePill label="A" value={turn.accuracy_score} /><ScorePill label="H" value={turn.hallucination_score} /><ScorePill label="F" value={turn.channel_fit_score} /></span>
        </div>
        <div className={cx("whitespace-pre-wrap text-sm text-slate-800", channel === "email" && "font-serif leading-relaxed")}>{turn.agent_text || <em className="text-red-600">No reply</em>}</div>
        {sms && <div className="mt-1.5 text-right text-[11px] text-slate-500">{turn.agent_text.length} chars · {Math.max(1, Math.ceil(turn.agent_text.length / 160))} segment(s)</div>}
        {turn.critical && <div className="mt-2 flex items-start gap-1.5 text-xs font-medium text-red-700"><AlertOctagon className="mt-0.5 h-3.5 w-3.5 shrink-0" />{turn.critical_reason}</div>}
      </div>
    </button>
  );
}

function CustomerBubble({ turn, channel }: { turn: Turn; channel: string }) {
  if (channel === "email") {
    return (
      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-2 text-xs text-slate-500"><Mail className="h-3.5 w-3.5" />Customer email</div>
        <div className="whitespace-pre-wrap px-4 py-3 font-serif text-sm leading-relaxed text-slate-800">{turn.customer_rendered}</div>
      </div>
    );
  }
  return (
    <div className="flex justify-end">
      <div className={cx("max-w-[85%] px-4 py-2.5 text-sm", channel === "sms" ? "rounded-3xl bg-emerald-500 text-white" : "rounded-2xl bg-indigo-600 text-white")}>
        {channel === "voice" && <div className="mb-1 flex items-center gap-1 text-[11px] uppercase tracking-wide text-indigo-200"><Mic className="h-3 w-3" />Transcript (speech-to-text)</div>}
        <div className="whitespace-pre-wrap">{turn.customer_rendered}</div>
        {channel === "voice" && turn.customer_text !== turn.customer_rendered && <div className="mt-1.5 border-t border-white/20 pt-1.5 text-[11px] text-indigo-100">Scripted: “{turn.customer_text}”</div>}
      </div>
    </div>
  );
}

function ScoreBlock({ label, score, text, applicable }: { label: string; score: number; text: string; applicable?: boolean }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-800">{label}</span>
        <ScorePill value={score} />
      </div>
      <p className="mt-1.5 text-sm text-slate-600">{text}</p>
      {applicable === false && <p className="mt-1 text-[11px] text-slate-500">Not counted in the context average (no earlier context needed).</p>}
    </div>
  );
}

function TurnDetail({ turn }: { turn: Turn }) {
  const e = turn.expectations;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Turn {turn.index + 1}</h3>
        <Badge className="bg-violet-50 text-violet-700 ring-violet-200">Judge: {turn.judge}</Badge>
        {turn.latency_ms > 0 && <Badge>{turn.latency_ms} ms</Badge>}
      </div>
      {turn.critical && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"><strong>Critical failure:</strong> {turn.critical_reason}</div>}
      <ScoreBlock label="Context awareness" score={turn.context_score} text={turn.context_justification} applicable={turn.context_applicable} />
      <ScoreBlock label="Accuracy" score={turn.accuracy_score} text={turn.accuracy_justification} />
      <ScoreBlock label="Hallucination" score={turn.hallucination_score} text={turn.hallucination_justification} />
      <ScoreBlock label="Channel fit" score={turn.channel_fit_score} text={turn.channel_justification} />

      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Claims ({turn.claims.length})</div>
        {!turn.claims.length ? <p className="text-sm text-slate-500">No checkable factual claims in this reply.</p> : (
          <div className="overflow-hidden rounded-lg border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-3 py-2">Claim</th><th className="px-3 py-2">Label</th><th className="px-3 py-2">Evidence</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {turn.claims.map((c) => {
                  const style = CLAIM_STYLE[c.label];
                  const Icon = style.icon;
                  return (
                    <tr key={c.id}>
                      <td className="px-3 py-2 align-top text-slate-800">{c.text}</td>
                      <td className="px-3 py-2 align-top"><span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", style.cls)}><Icon className="h-3.5 w-3.5" />{c.label}</span></td>
                      <td className="px-3 py-2 align-top text-xs text-slate-600">{c.evidence}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Expectations for this turn</div>
        <div className="space-y-1.5 text-sm">
          {[["Must include", e.must_include, "bg-emerald-50 text-emerald-700"], ["Must NOT include", e.must_not_include, "bg-red-50 text-red-700"], ["Must remember", e.must_remember, "bg-indigo-50 text-indigo-700"]].map(([label, values, cls]) => (
            <div key={label as string} className="flex flex-wrap items-center gap-1.5">
              <span className="w-32 shrink-0 text-xs text-slate-500">{label as string}</span>
              {(values as string[] | undefined)?.length ? (values as string[]).map((v) => <span key={v} className={cx("rounded px-1.5 py-0.5 text-xs", cls as string)}>{v}</span>) : <span className="text-xs text-slate-400">—</span>}
            </div>
          ))}
          {e.notes && <p className="text-xs text-slate-500">Notes: {e.notes}</p>}
        </div>
      </div>
      {turn.channel_flags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">{turn.channel_flags.map((f) => <Badge key={f} className="bg-amber-50 text-amber-700 ring-amber-200">{f}</Badge>)}</div>
      )}
    </div>
  );
}

export default function ConversationView() {
  const { id } = useParams();
  const conv = useApi<ConversationDetail>(`/conversations/${id}`);
  const [selected, setSelected] = useState(0);

  useEffect(() => {
    // Open on the first problematic turn so reviewers land on the evidence.
    const turns = conv.data?.turns ?? [];
    const bad = turns.findIndex((t) => t.critical || t.hallucinated || worst(t) < 4);
    setSelected(bad >= 0 ? bad : 0);
  }, [conv.data]);

  if (conv.loading) return <Spinner />;
  if (conv.error || !conv.data) return <ErrorBox message={conv.error ?? "Conversation not found."} onRetry={conv.reload} />;
  const c = conv.data;
  const turn = c.turns[selected];
  const ChannelIcon = c.channel === "sms" ? Smartphone : c.channel === "voice" ? Mic : c.channel === "email" ? Mail : User;

  return (
    <>
      <Link to={`/runs/${c.run_id}`} className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"><ArrowLeft className="h-4 w-4" />{c.run_name}</Link>
      <PageHeader title={c.script_name} description={`${c.agent_name} · ${c.journey_name || "No journey"} · ${variantLabel(c.variant)} · Goal: ${c.goal}`} />
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <ChannelTag channel={c.channel} />
        <span className={c.task_completed ? "text-emerald-700" : "text-red-600"}>{c.task_justification}</span>
        {c.persona?.name && <span className="text-slate-500">Persona: {c.persona.description || c.persona.name}</span>}
      </div>
      <div className="grid gap-6 xl:grid-cols-[1fr_480px]">
        <Card title={<span className="inline-flex items-center gap-2"><ChannelIcon className="h-4 w-4" />{c.channel === "email" ? `Email thread – ${c.email_subject}` : c.channel === "sms" ? "SMS conversation" : c.channel === "voice" ? "Voice call transcript" : "Chat transcript"}</span>}
          subtitle="Click an agent turn to see its scores, justifications and claim-by-claim check. Colour = worst of context, accuracy and hallucination scores.">
          <div className={cx("space-y-4", c.channel === "sms" && "mx-auto max-w-md rounded-[2rem] border-8 border-slate-800 bg-slate-50 p-4")}>
            {c.turns.map((t, i) => (
              <div key={t.id} className="space-y-2">
                <CustomerBubble turn={t} channel={c.channel} />
                <div className={c.channel === "email" ? "" : "max-w-[92%]"}><AgentBubble turn={t} channel={c.channel} selected={i === selected} onSelect={() => setSelected(i)} /></div>
              </div>
            ))}
            {c.error && <ErrorBox message={c.error} />}
          </div>
        </Card>
        <div className="xl:sticky xl:top-6 xl:self-start">
          <Card>{turn ? <TurnDetail turn={turn} /> : <p className="text-sm text-slate-500">No turns.</p>}</Card>
        </div>
      </div>
    </>
  );
}
