import { Bot, CheckCircle2, Cloud, Globe, Pencil, Plug, Plus, Sparkles, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { Badge, Button, EmptyState, ErrorBox, Field, inputClass, Modal, PageHeader, Spinner, Toast } from "../components/ui";
import { api, type Agent, type AgentMeta } from "../lib/api";
import { useApi } from "../lib/hooks";

const ICONS = { mock: Bot, http: Globe, llm: Sparkles, cxone: Cloud };

interface Draft {
  id?: number;
  name: string;
  adapter_type: Agent["adapter_type"];
  description: string;
  config: Record<string, unknown>;
  configText: string;
}

function toDraft(agent?: Agent): Draft {
  const config = agent?.config ?? { preset: "v3" };
  return { id: agent?.id, name: agent?.name ?? "", adapter_type: agent?.adapter_type ?? "mock", description: agent?.description ?? "",
    config, configText: JSON.stringify(config, null, 2) };
}

function MockConfig({ draft, meta, onChange }: { draft: Draft; meta: AgentMeta; onChange: (c: Record<string, unknown>) => void }) {
  const preset = String(draft.config.preset ?? "v3");
  const defaults = meta.mock_presets[preset] ?? {};
  const value = (k: string) => (draft.config[k] ?? defaults[k]) as number | string | boolean;
  return (
    <div className="space-y-4">
      <Field label="Preset" hint="Presets set every flaw rate below; override any of them for your own experiments.">
        <select className={inputClass} value={preset} onChange={(e) => onChange({ preset: e.target.value })}>
          <option value="v1">v1 – weak (many flaws)</option>
          <option value="v2">v2 – improving (few flaws)</option>
          <option value="v3">v3 – ready (no deliberate flaws)</option>
        </select>
      </Field>
      {(["context_loss_rate", "wrong_fact_rate", "hallucination_rate", "channel_awareness"] as const).map((k) => (
        <Field key={k} label={`${meta.mock_settings[k]}: ${Number(value(k)).toFixed(2)}`}>
          <input type="range" min={0} max={1} step={0.01} value={Number(value(k))} className="w-full accent-indigo-600"
            onChange={(e) => onChange({ ...draft.config, [k]: Number(e.target.value) })} />
        </Field>
      ))}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Hallucination style">
          <select className={inputClass} value={String(value("hallucination_style"))} onChange={(e) => onChange({ ...draft.config, hallucination_style: e.target.value })}>
            <option value="policy">Invented policies only</option>
            <option value="mixed">Policies, numbers and off-topic answers</option>
          </select>
        </Field>
        <label className="mt-6 flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" className="rounded text-indigo-600" checked={Boolean(value("severe_context_loss"))}
            onChange={(e) => onChange({ ...draft.config, severe_context_loss: e.target.checked })} />
          Allow severe context loss (superseded plan/account)
        </label>
      </div>
    </div>
  );
}

export default function Agents() {
  const agents = useApi<Agent[]>("/agents");
  const meta = useApi<AgentMeta>("/agents/meta");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [results, setResults] = useState<Record<number, { ok: boolean; message: string; sample_reply: string }>>({});
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);

  if (agents.loading || meta.loading) return <Spinner />;
  if (agents.error) return <ErrorBox message={agents.error} onRetry={agents.reload} />;
  if (meta.error || !meta.data) return <ErrorBox message={meta.error ?? "Could not load adapter metadata."} onRetry={meta.reload} />;
  const m = meta.data;

  const save = async () => {
    if (!draft) return;
    let config = draft.config;
    if (draft.adapter_type !== "mock") {
      try {
        config = JSON.parse(draft.configText || "{}");
      } catch {
        setFormError("Configuration must be valid JSON.");
        return;
      }
    }
    setSaving(true);
    setFormError(null);
    const body = { name: draft.name, adapter_type: draft.adapter_type, description: draft.description, config };
    try {
      if (draft.id) await api.put(`/agents/${draft.id}`, body);
      else await api.post("/agents", body);
      setDraft(null);
      setToast({ message: "Agent saved.", tone: "success" });
      await agents.reload();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const test = async (agent: Agent) => {
    setTesting(agent.id);
    try {
      const res = await api.post<{ ok: boolean; message: string; sample_reply: string }>(`/agents/${agent.id}/test`);
      setResults((r) => ({ ...r, [agent.id]: res }));
    } catch (e) {
      setResults((r) => ({ ...r, [agent.id]: { ok: false, message: (e as Error).message, sample_reply: "" } }));
    } finally {
      setTesting(null);
    }
  };

  const remove = async (agent: Agent) => {
    if (!window.confirm(`Delete agent "${agent.name}"? Past runs keep their results.`)) return;
    try {
      await api.del(`/agents/${agent.id}`);
      await agents.reload();
    } catch (e) {
      setToast({ message: (e as Error).message, tone: "error" });
    }
  };

  const list = agents.data ?? [];
  return (
    <>
      <PageHeader
        title="Agents"
        description="Virtual agent connections under test. Mock agents work offline; HTTP, LLM and NICE CXone adapters connect to real bots."
        actions={<Button variant="primary" onClick={() => { setFormError(null); setDraft(toDraft()); }}><Plus className="h-4 w-4" />Add agent</Button>}
      />
      {!list.length ? (
        <EmptyState title="No agents yet" message="Add a mock agent to try AgentProof offline, or connect your bot." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {list.map((agent) => {
            const Icon = ICONS[agent.adapter_type] ?? Bot;
            const result = results[agent.id];
            return (
              <div key={agent.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-card">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600"><Icon className="h-5 w-5" /></div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-slate-900">{agent.name}</h3>
                      <Badge>{m.adapter_types[agent.adapter_type]}</Badge>
                    </div>
                    <p className="mt-1 text-sm text-slate-500">{agent.description || "No description."}</p>
                    {agent.adapter_type === "mock" && <p className="mt-1 text-xs text-slate-500">Preset: {String(agent.config.preset ?? "v3")}</p>}
                    {agent.adapter_type === "http" && <p className="mt-1 truncate font-mono text-xs text-slate-500">{String(agent.config.url ?? "")}</p>}
                  </div>
                </div>
                {result && (
                  <div className={`mt-4 rounded-lg px-3 py-2 text-sm ${result.ok ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-700"}`}>
                    <div className="flex items-start gap-2">
                      {result.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0" />}
                      <span>{result.message}</span>
                    </div>
                    {result.sample_reply && <p className="mt-2 whitespace-pre-wrap rounded bg-white/70 px-2 py-1.5 text-xs text-slate-700">“{result.sample_reply}”</p>}
                  </div>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button onClick={() => void test(agent)} loading={testing === agent.id}><Plug className="h-4 w-4" />Test connection</Button>
                  <Button variant="ghost" onClick={() => { setFormError(null); setDraft(toDraft(agent)); }}><Pencil className="h-4 w-4" />Edit</Button>
                  <Button variant="ghost" onClick={() => void remove(agent)}><Trash2 className="h-4 w-4" />Delete</Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Modal open={Boolean(draft)} onClose={() => setDraft(null)} title={draft?.id ? "Edit agent" : "Add agent"}
        footer={<><Button onClick={() => setDraft(null)}>Cancel</Button><Button variant="primary" loading={saving} disabled={!draft?.name.trim()} onClick={() => void save()}>Save</Button></>}>
        {draft && (
          <div className="space-y-4">
            {formError && <ErrorBox message={formError} />}
            <Field label="Name"><input className={inputClass} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="e.g. Billing bot – staging" /></Field>
            <Field label="Adapter">
              <select className={inputClass} value={draft.adapter_type}
                onChange={(e) => {
                  const type = e.target.value as Agent["adapter_type"];
                  const template = m.config_templates[type] ?? {};
                  setDraft({ ...draft, adapter_type: type, config: template, configText: JSON.stringify(template, null, 2) });
                }}>
                {Object.entries(m.adapter_types).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select>
            </Field>
            <Field label="Description"><textarea className={inputClass} rows={2} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
            {draft.adapter_type === "mock" ? (
              <MockConfig draft={draft} meta={m} onChange={(config) => setDraft({ ...draft, config })} />
            ) : (
              <Field label="Configuration (JSON)" hint={
                draft.adapter_type === "http" ? "Placeholders {{message}}, {{channel}}, {{session_id}} are filled per turn. response_path is a dotted path into the reply JSON. Header values can use ${ENV_VAR}."
                  : draft.adapter_type === "cxone" ? `Credentials come from Settings (.env): ${m.cxone_settings.join(", ")}. Values here override them.`
                  : "provider: auto | anthropic | openai. Leave system_prompt empty to use the built-in Northwind prompt; {kb} inserts the knowledge base."}>
                <textarea className={`${inputClass} font-mono text-xs`} rows={10} value={draft.configText} onChange={(e) => setDraft({ ...draft, configText: e.target.value })} />
              </Field>
            )}
          </div>
        )}
      </Modal>
      {toast && <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />}
    </>
  );
}
