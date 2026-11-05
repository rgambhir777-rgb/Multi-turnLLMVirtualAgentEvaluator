import { ArrowDown, ArrowLeft, ArrowUp, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button, Card, ErrorBox, Field, inputClass, PageHeader, Spinner, TagInput, Toast } from "../components/ui";
import { api, type Journey, type ScriptTurn, type TestScript } from "../lib/api";
import { CHANNEL_LABEL, CHANNELS, variantLabel } from "../lib/format";
import { useApi } from "../lib/hooks";

const emptyTurn = (): ScriptTurn => ({ customer: "", must_include: [], must_not_include: [], must_remember: [], notes: "" });

const blank: Omit<TestScript, "id" | "journey_name" | "turn_count"> = {
  name: "", journey_id: null, channel: "chat", variant: "standard", goal: "", email_subject: "",
  persona: { name: "", account: "", zip: "", description: "" }, turns: [emptyTurn()],
};

export default function ScriptEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const isNew = !id;
  const existing = useApi<TestScript>(isNew ? null : `/scripts/${id}`);
  const journeys = useApi<Journey[]>("/journeys");
  const meta = useApi<{ variants: Record<string, string> }>("/scripts/meta");
  const [script, setScript] = useState<typeof blank | null>(isNew ? structuredClone(blank) : null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (existing.data) setScript(structuredClone(existing.data));
  }, [existing.data]);

  if (existing.loading || !script) return existing.error ? <ErrorBox message={existing.error} onRetry={existing.reload} /> : <Spinner />;

  const setTurn = (i: number, patch: Partial<ScriptTurn>) =>
    setScript({ ...script, turns: script.turns.map((t, j) => (j === i ? { ...t, ...patch } : t)) });
  const move = (i: number, dir: -1 | 1) => {
    const turns = [...script.turns];
    [turns[i], turns[i + dir]] = [turns[i + dir], turns[i]];
    setScript({ ...script, turns });
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    const body = { ...script, turns: script.turns.filter((t) => t.customer.trim()) };
    try {
      if (isNew) {
        const created = await api.post<TestScript>("/scripts", body);
        navigate(`/scripts/${created.id}`, { replace: true });
      } else {
        await api.put<TestScript>(`/scripts/${id}`, body);
      }
      setToast("Script saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const persona = script.persona ?? {};
  return (
    <>
      <Link to="/scripts" className="mb-3 inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"><ArrowLeft className="h-4 w-4" />All scripts</Link>
      <PageHeader title={isNew ? "New test script" : script.name || "Untitled script"}
        description="Each customer turn is sent to the agent in order. The judge checks every reply against these expectations and the knowledge base."
        actions={<Button variant="primary" loading={saving} disabled={!script.name.trim()} onClick={() => void save()}><Save className="h-4 w-4" />Save script</Button>} />
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <div className="space-y-6">
          <Card title="Script">
            <div className="space-y-4">
              <Field label="Name"><input className={inputClass} value={script.name} onChange={(e) => setScript({ ...script, name: e.target.value })} /></Field>
              <Field label="Journey">
                <select className={inputClass} value={script.journey_id ?? ""} onChange={(e) => setScript({ ...script, journey_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">No journey</option>
                  {(journeys.data ?? []).map((j) => <option key={j.id} value={j.id}>{j.name}</option>)}
                </select>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Default channel">
                  <select className={inputClass} value={script.channel} onChange={(e) => setScript({ ...script, channel: e.target.value as TestScript["channel"] })}>
                    {CHANNELS.map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}
                  </select>
                </Field>
                <Field label="Variant">
                  <select className={inputClass} value={script.variant} onChange={(e) => setScript({ ...script, variant: e.target.value })}>
                    {Object.keys(meta.data?.variants ?? { standard: "" }).map((v) => <option key={v} value={v}>{variantLabel(v)}</option>)}
                  </select>
                </Field>
              </div>
              <Field label="Customer goal"><textarea className={inputClass} rows={2} value={script.goal} onChange={(e) => setScript({ ...script, goal: e.target.value })} /></Field>
              <Field label="Email subject" hint="Used when the script runs on the email channel."><input className={inputClass} value={script.email_subject} onChange={(e) => setScript({ ...script, email_subject: e.target.value })} /></Field>
            </div>
          </Card>
          <Card title="Persona">
            <div className="space-y-3">
              {(["name", "account", "zip", "description"] as const).map((key) => (
                <Field key={key} label={key === "zip" ? "ZIP code" : key[0].toUpperCase() + key.slice(1)}>
                  <input className={inputClass} value={String(persona[key] ?? "")} onChange={(e) => setScript({ ...script, persona: { ...persona, [key]: e.target.value } })} />
                </Field>
              ))}
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          {script.turns.map((turn, i) => (
            <div key={i} className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-indigo-600">Turn {i + 1}</span>
                <div className="flex gap-1">
                  <Button variant="ghost" className="px-2" disabled={i === 0} onClick={() => move(i, -1)} aria-label="Move up"><ArrowUp className="h-4 w-4" /></Button>
                  <Button variant="ghost" className="px-2" disabled={i === script.turns.length - 1} onClick={() => move(i, 1)} aria-label="Move down"><ArrowDown className="h-4 w-4" /></Button>
                  <Button variant="ghost" className="px-2" disabled={script.turns.length === 1} onClick={() => setScript({ ...script, turns: script.turns.filter((_, j) => j !== i) })} aria-label="Remove turn"><Trash2 className="h-4 w-4" /></Button>
                </div>
              </div>
              <Field label="Customer says"><textarea className={inputClass} rows={2} value={turn.customer} onChange={(e) => setTurn(i, { customer: e.target.value })} /></Field>
              <div className="mt-3 grid gap-3 lg:grid-cols-3">
                <Field label="Must include" hint="Use a|b for alternatives."><TagInput tone="green" values={turn.must_include} onChange={(v) => setTurn(i, { must_include: v })} placeholder="$59.99" /></Field>
                <Field label="Must NOT include"><TagInput tone="red" values={turn.must_not_include} onChange={(v) => setTurn(i, { must_not_include: v })} placeholder="$10 plan change fee" /></Field>
                <Field label="Must remember from earlier"><TagInput tone="indigo" values={turn.must_remember} onChange={(v) => setTurn(i, { must_remember: v })} placeholder="NW-123456" /></Field>
              </div>
              <div className="mt-3"><Field label="Reviewer notes"><input className={inputClass} value={turn.notes} onChange={(e) => setTurn(i, { notes: e.target.value })} placeholder="What this turn tests" /></Field></div>
            </div>
          ))}
          <Button onClick={() => setScript({ ...script, turns: [...script.turns, emptyTurn()] })}><Plus className="h-4 w-4" />Add turn</Button>
        </div>
      </div>
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </>
  );
}
