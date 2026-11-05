import { Download, FileUp, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Button, Card, EmptyState, ErrorBox, Field, inputClass, Modal, PageHeader, Spinner, Toast } from "../components/ui";
import { api, type KBFact } from "../lib/api";
import { useApi } from "../lib/hooks";

export default function KnowledgeBase() {
  const facts = useApi<KBFact[]>("/kb");
  const [query, setQuery] = useState("");
  const [edit, setEdit] = useState<Partial<KBFact> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const [importMode, setImportMode] = useState("append");
  const fileRef = useRef<HTMLInputElement>(null);

  const grouped = useMemo(() => {
    const out: Record<string, KBFact[]> = {};
    for (const f of facts.data ?? []) {
      if (query && !`${f.category} ${f.title} ${f.content}`.toLowerCase().includes(query.toLowerCase())) continue;
      (out[f.category] ??= []).push(f);
    }
    return out;
  }, [facts.data, query]);

  const save = async () => {
    if (!edit) return;
    setBusy(true);
    setError(null);
    const body = { category: edit.category || "General", title: edit.title ?? "", content: edit.content ?? "", tags: edit.tags ?? [] };
    try {
      if (edit.id) await api.put(`/kb/${edit.id}`, body);
      else await api.post("/kb", body);
      setEdit(null);
      await facts.reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const importFile = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    form.append("mode", importMode);
    try {
      const res = await api.upload<{ imported: number }>("/kb/import", form);
      setToast({ message: `Imported ${res.imported} facts.`, tone: "success" });
      await facts.reload();
    } catch (e) {
      setToast({ message: (e as Error).message, tone: "error" });
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (f: KBFact) => {
    if (!window.confirm(`Delete "${f.title}"?`)) return;
    await api.del(`/kb/${f.id}`);
    await facts.reload();
  };

  const categories = Object.keys(facts.data?.reduce<Record<string, 1>>((acc, f) => ({ ...acc, [f.category]: 1 }), {}) ?? {});

  return (
    <>
      <PageHeader title="Knowledge base" description="Ground truth for the judge: every factual claim in an agent reply is checked against these facts. Prices, fees, timeframes and policies matter most."
        actions={<>
          <a href="/api/kb/export" download="knowledge_base.md" className="inline-flex items-center gap-1.5 rounded-lg bg-white px-3 py-2 text-sm font-medium text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50"><Download className="h-4 w-4" />Export Markdown</a>
          <Button variant="primary" onClick={() => { setError(null); setEdit({ category: categories[0] ?? "General" }); }}><Plus className="h-4 w-4" />Add fact</Button>
        </>} />

      <Card title="Import facts" subtitle="Markdown: '## Category' then '### Fact title' then the fact text. CSV: category,title,content[,tags].">
        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept=".md,.markdown,.txt,.csv" onChange={(e) => e.target.files?.[0] && void importFile(e.target.files[0])}
            className="block text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-indigo-700 hover:file:bg-indigo-100" />
          <select className={`${inputClass} w-56`} value={importMode} onChange={(e) => setImportMode(e.target.value)}>
            <option value="append">Append to existing facts</option>
            <option value="replace">Replace all facts</option>
          </select>
          <span className="inline-flex items-center gap-1 text-xs text-slate-500"><FileUp className="h-3.5 w-3.5" />Choosing a file imports it immediately.</span>
        </div>
      </Card>

      <div className="mb-4 mt-6 relative max-w-sm">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
        <input className={`${inputClass} pl-9`} placeholder="Search facts" value={query} onChange={(e) => setQuery(e.target.value)} />
      </div>

      {facts.loading ? <Spinner /> : facts.error ? <ErrorBox message={facts.error} onRetry={facts.reload} /> : !Object.keys(grouped).length ? (
        <EmptyState title={facts.data?.length ? "No facts match your search" : "The knowledge base is empty"}
          message="Without facts the judge cannot verify claims – every factual claim will be marked unsupported." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {Object.entries(grouped).map(([category, items]) => (
            <Card key={category} title={category} subtitle={`${items.length} fact${items.length === 1 ? "" : "s"}`}>
              <ul className="-my-2 divide-y divide-slate-100">
                {items.map((f) => (
                  <li key={f.id} className="group flex gap-3 py-2.5">
                    <div className="flex-1">
                      <div className="text-sm font-medium text-slate-800">{f.title}</div>
                      <div className="mt-0.5 text-sm text-slate-600">{f.content}</div>
                    </div>
                    <div className="flex shrink-0 gap-1 opacity-60 group-hover:opacity-100">
                      <Button variant="ghost" className="px-1.5" aria-label="Edit" onClick={() => { setError(null); setEdit(f); }}><Pencil className="h-4 w-4" /></Button>
                      <Button variant="ghost" className="px-1.5" aria-label="Delete" onClick={() => void remove(f)}><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}

      <Modal open={Boolean(edit)} onClose={() => setEdit(null)} title={edit?.id ? "Edit fact" : "Add fact"}
        footer={<><Button onClick={() => setEdit(null)}>Cancel</Button><Button variant="primary" loading={busy} disabled={!edit?.title?.trim() || !edit?.content?.trim()} onClick={() => void save()}>Save</Button></>}>
        {edit && (
          <div className="space-y-4">
            {error && <ErrorBox message={error} />}
            <Field label="Category">
              <input className={inputClass} list="kb-categories" value={edit.category ?? ""} onChange={(e) => setEdit({ ...edit, category: e.target.value })} />
              <datalist id="kb-categories">{categories.map((c) => <option key={c} value={c} />)}</datalist>
            </Field>
            <Field label="Title"><input className={inputClass} value={edit.title ?? ""} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></Field>
            <Field label="Fact" hint="State exact numbers (e.g. '$59.99 per month', '5-7 business days') so the judge can verify them.">
              <textarea className={inputClass} rows={4} value={edit.content ?? ""} onChange={(e) => setEdit({ ...edit, content: e.target.value })} />
            </Field>
          </div>
        )}
      </Modal>
      {toast && <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />}
    </>
  );
}
