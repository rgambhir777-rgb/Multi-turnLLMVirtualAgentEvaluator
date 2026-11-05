import { FileUp, Pencil, Plus, RefreshCw, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, inputClass, Modal, PageHeader, Spinner, TagInput, Toast } from "../components/ui";
import { api, type DiscoverResult, type Journey, type TestScript } from "../lib/api";
import { CHANNEL_LABEL, CHANNELS, variantLabel } from "../lib/format";
import { useApi } from "../lib/hooks";

interface Stats { total: number; by_channel: Record<string, number> }
interface Meta { variants: Record<string, string>; channels: string[] }
const INTENTS = ["billing", "plan_change", "outage", "password_reset", "cancellation", "refund", "general", "other"];

export default function Journeys() {
  const navigate = useNavigate();
  const journeys = useApi<Journey[]>("/journeys");
  const stats = useApi<Stats>("/transcripts/stats");
  const meta = useApi<Meta>("/scripts/meta");
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [k, setK] = useState("");
  const [useLlm, setUseLlm] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [edit, setEdit] = useState<Partial<Journey> | null>(null);
  const [gen, setGen] = useState<{ journey: Journey; variants: string[]; channel: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const discover = async (withFile: boolean) => {
    setDiscovering(true);
    setDiscoverError(null);
    const form = new FormData();
    if (withFile && file) form.append("file", file);
    if (k) form.append("k", k);
    form.append("use_llm", String(useLlm));
    try {
      const res = await api.upload<DiscoverResult>("/journeys/discover", form);
      setToast(`Discovered ${res.journeys.length} journeys from ${res.transcripts} transcripts (${res.labeler.startsWith("llm") ? "LLM labels" : "offline labels"}).`);
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      await Promise.all([journeys.reload(), stats.reload()]);
    } catch (e) {
      setDiscoverError((e as Error).message);
    } finally {
      setDiscovering(false);
    }
  };

  const saveJourney = async () => {
    if (!edit?.name) return;
    setBusy(true);
    setError(null);
    const body = { name: edit.name, description: edit.description ?? "", intent: edit.intent ?? "other",
      keywords: edit.keywords ?? [], example_utterances: edit.example_utterances ?? [] };
    try {
      if (edit.id) await api.put(`/journeys/${edit.id}`, body);
      else await api.post("/journeys", body);
      setEdit(null);
      await journeys.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    if (!gen) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.post<TestScript[]>(`/journeys/${gen.journey.id}/generate-scripts`, { variants: gen.variants, channel: gen.channel });
      setGen(null);
      setToast(`Created ${created.length} test script(s).`);
      await journeys.reload();
      if (created.length === 1) navigate(`/scripts/${created[0].id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (j: Journey) => {
    if (!window.confirm(`Delete journey "${j.name}"? Its scripts are kept.`)) return;
    await api.del(`/journeys/${j.id}`).catch((e: Error) => setToast(e.message));
    await journeys.reload();
  };

  const list = journeys.data ?? [];
  const maxFreq = Math.max(1, ...list.map((j) => j.frequency));

  return (
    <>
      <PageHeader title="Journeys" description="Discover what customers actually contact you about, then turn each journey into multi-turn test conversations."
        actions={<Button variant="primary" onClick={() => { setError(null); setEdit({ intent: "other", keywords: [], example_utterances: [] }); }}><Plus className="h-4 w-4" />New journey</Button>} />

      <Card title="Discover journeys from transcripts" subtitle="TF-IDF + KMeans clustering offline; LLM labelling when an API key is configured.">
        <div className="grid gap-6 lg:grid-cols-[1fr_auto]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Transcript file (CSV or JSON)">
                <input ref={fileRef} type="file" accept=".csv,.json" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="block text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-indigo-700 hover:file:bg-indigo-100" />
              </Field>
              <Field label="Clusters (blank = auto)">
                <input className={`${inputClass} w-28`} type="number" min={2} max={20} value={k} onChange={(e) => setK(e.target.value)} placeholder="auto" />
              </Field>
              <label className="mb-2 flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" className="rounded text-indigo-600" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> Use LLM labels if available
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" disabled={!file} loading={discovering && Boolean(file)} onClick={() => void discover(true)}><FileUp className="h-4 w-4" />Upload & discover</Button>
              <Button disabled={!stats.data?.total} loading={discovering && !file} onClick={() => void discover(false)}><RefreshCw className="h-4 w-4" />Re-cluster stored transcripts</Button>
            </div>
            {discoverError && <ErrorBox message={discoverError} />}
            <p className="text-xs text-slate-500">Accepted formats: JSON list of <code>{"{id, channel, turns: [{speaker, text}]}"}</code>; CSV with <code>transcript_id, speaker, text</code> (one row per turn) or <code>id, transcript</code> with “Customer:” / “Agent:” lines. A 220-transcript sample is in <code>sample_data/</code>.</p>
          </div>
          <div className="min-w-[200px] rounded-lg bg-slate-50 p-4 text-sm">
            <div className="text-xs font-medium text-slate-500">Stored transcripts</div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">{stats.data?.total ?? "—"}</div>
            <div className="mt-2 space-y-0.5 text-xs text-slate-600">
              {Object.entries(stats.data?.by_channel ?? {}).map(([ch, n]) => <div key={ch} className="flex justify-between"><span>{CHANNEL_LABEL[ch] ?? ch}</span><span className="tabular-nums">{n}</span></div>)}
            </div>
          </div>
        </div>
      </Card>

      <div className="mt-6">
        {journeys.loading ? <Spinner /> : journeys.error ? <ErrorBox message={journeys.error} onRetry={journeys.reload} /> : !list.length ? (
          <EmptyState title="No journeys yet" message="Upload transcripts to discover journeys, or create one manually." />
        ) : (
          <div className="grid gap-4 xl:grid-cols-2">
            {list.map((j) => (
              <div key={j.id} className="rounded-xl border border-slate-200 bg-white p-5 shadow-card">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-slate-900">{j.name}</h3>
                    <p className="mt-0.5 text-sm text-slate-500">{j.description}</p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button variant="ghost" className="px-2" aria-label="Edit" onClick={() => { setError(null); setEdit(j); }}><Pencil className="h-4 w-4" /></Button>
                    <Button variant="ghost" className="px-2" aria-label="Delete" onClick={() => void remove(j)}><Trash2 className="h-4 w-4" /></Button>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                  <Badge>{j.source === "discovered" ? "Discovered" : "Manual"}</Badge>
                  {j.labeler.startsWith("llm") && <Badge className="bg-violet-50 text-violet-700 ring-violet-200"><Sparkles className="h-3 w-3" />LLM label</Badge>}
                  <Badge>Intent: {j.intent}</Badge>
                  <Badge>{j.script_count} script{j.script_count === 1 ? "" : "s"}</Badge>
                </div>
                {j.source === "discovered" && (
                  <div className="mt-4 grid grid-cols-[auto_1fr_auto] items-center gap-3 text-xs text-slate-500">
                    <span>Frequency</span>
                    <div className="h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-indigo-500" style={{ width: `${(j.frequency / maxFreq) * 100}%` }} /></div>
                    <span className="tabular-nums text-slate-700">{j.frequency} transcripts · {j.avg_turns} turns avg</span>
                  </div>
                )}
                {j.keywords.length > 0 && <div className="mt-3 flex flex-wrap gap-1">{j.keywords.slice(0, 8).map((kw) => <span key={kw} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{kw}</span>)}</div>}
                {j.example_utterances.length > 0 && (
                  <ul className="mt-3 space-y-1 text-sm text-slate-700">
                    {j.example_utterances.slice(0, 3).map((u) => <li key={u} className="rounded-lg bg-slate-50 px-3 py-1.5">“{u}”</li>)}
                  </ul>
                )}
                <div className="mt-4">
                  <Button onClick={() => { setError(null); setGen({ journey: j, variants: ["standard"], channel: "chat" }); }}><Wand2 className="h-4 w-4" />Generate test scripts</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Modal open={Boolean(edit)} onClose={() => setEdit(null)} title={edit?.id ? "Edit journey" : "New journey"}
        footer={<><Button onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" loading={busy} disabled={!edit?.name?.trim()} onClick={() => void saveJourney()}>Save</Button></>}>
        {edit && (
          <div className="space-y-4">
            {error && <ErrorBox message={error} />}
            <Field label="Name"><input className={inputClass} value={edit.name ?? ""} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Description"><textarea className={inputClass} rows={2} value={edit.description ?? ""} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field>
            <Field label="Intent" hint="Known intents get hand-tuned script templates; 'other' uses the example utterances.">
              <select className={inputClass} value={edit.intent ?? "other"} onChange={(e) => setEdit({ ...edit, intent: e.target.value })}>
                {INTENTS.map((i) => <option key={i} value={i}>{i}</option>)}
              </select>
            </Field>
            <Field label="Keywords"><TagInput values={edit.keywords ?? []} onChange={(v) => setEdit({ ...edit, keywords: v })} placeholder="Type and press Enter" /></Field>
            <Field label="Example utterances"><TagInput values={edit.example_utterances ?? []} onChange={(v) => setEdit({ ...edit, example_utterances: v })} placeholder="Type and press Enter" tone="indigo" /></Field>
          </div>
        )}
      </Modal>

      <Modal open={Boolean(gen)} onClose={() => setGen(null)} title={`Generate scripts – ${gen?.journey.name ?? ""}`}
        footer={<><Button onClick={() => setGen(null)}>Cancel</Button><Button variant="primary" loading={busy} disabled={!gen?.variants.length} onClick={() => void generate()}>Generate {gen?.variants.length ?? 0}</Button></>}>
        {gen && meta.data && (
          <div className="space-y-4">
            {error && <ErrorBox message={error} />}
            <div className="space-y-2">
              {Object.entries(meta.data.variants).map(([v, desc]) => (
                <label key={v} className="flex items-start gap-3 rounded-lg border border-slate-200 px-3 py-2 hover:bg-slate-50">
                  <input type="checkbox" className="mt-0.5 rounded text-indigo-600" checked={gen.variants.includes(v)}
                    onChange={(e) => setGen({ ...gen, variants: e.target.checked ? [...gen.variants, v] : gen.variants.filter((x) => x !== v) })} />
                  <span><span className="text-sm font-medium text-slate-800">{variantLabel(v)}</span><span className="block text-xs text-slate-500">{desc}</span></span>
                </label>
              ))}
            </div>
            <Field label="Default channel">
              <select className={inputClass} value={gen.channel} onChange={(e) => setGen({ ...gen, channel: e.target.value })}>
                {CHANNELS.map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}
              </select>
            </Field>
          </div>
        )}
      </Modal>
      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </>
  );
}
