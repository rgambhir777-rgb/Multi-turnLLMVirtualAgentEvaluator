import { Copy, Plus, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChannelTag } from "../components/channel";
import { Badge, Button, EmptyState, ErrorBox, inputClass, PageHeader, Spinner, Toast } from "../components/ui";
import { api, type TestScript } from "../lib/api";
import { CHANNEL_LABEL, CHANNELS, variantLabel } from "../lib/format";
import { useApi } from "../lib/hooks";

export default function Scripts() {
  const navigate = useNavigate();
  const scripts = useApi<TestScript[]>("/scripts");
  const [query, setQuery] = useState("");
  const [channel, setChannel] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  const filtered = useMemo(() => (scripts.data ?? []).filter((s) =>
    (!channel || s.channel === channel) &&
    (!query || `${s.name} ${s.journey_name} ${s.variant} ${s.goal}`.toLowerCase().includes(query.toLowerCase()))), [scripts.data, query, channel]);

  const duplicate = async (s: TestScript) => {
    const copy = await api.post<TestScript>(`/scripts/${s.id}/duplicate`);
    navigate(`/scripts/${copy.id}`);
  };
  const remove = async (s: TestScript) => {
    if (!window.confirm(`Delete script "${s.name}"?`)) return;
    try {
      await api.del(`/scripts/${s.id}`);
      await scripts.reload();
    } catch (e) {
      setToast((e as Error).message);
    }
  };

  return (
    <>
      <PageHeader title="Test scripts" description="Multi-turn test conversations with per-turn expectations: facts that must appear, facts that must not, and details the agent must remember."
        actions={<Button variant="primary" onClick={() => navigate("/scripts/new")}><Plus className="h-4 w-4" />New script</Button>} />
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input className={`${inputClass} pl-9`} placeholder="Search scripts" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <select className={`${inputClass} w-40`} value={channel} onChange={(e) => setChannel(e.target.value)}>
          <option value="">All channels</option>
          {CHANNELS.map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}
        </select>
      </div>
      {scripts.loading ? <Spinner /> : scripts.error ? <ErrorBox message={scripts.error} onRetry={scripts.reload} /> : !filtered.length ? (
        <EmptyState title={scripts.data?.length ? "No scripts match your filters" : "No test scripts yet"}
          message="Generate scripts from a journey or write one from scratch." />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-card">
          <table className="min-w-full divide-y divide-slate-100 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-medium text-slate-500">
              <tr><th className="px-4 py-3">Script</th><th className="px-4 py-3">Journey</th><th className="px-4 py-3">Variant</th><th className="px-4 py-3">Channel</th><th className="px-4 py-3">Turns</th><th className="px-4 py-3" /></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((s) => {
                return (
                  <tr key={s.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <Link to={`/scripts/${s.id}`} className="font-medium text-slate-900 hover:text-indigo-600">{s.name}</Link>
                      <div className="mt-0.5 max-w-md truncate text-xs text-slate-500">{s.goal}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{s.journey_name || "—"}</td>
                    <td className="px-4 py-3"><Badge className={s.variant === "standard" ? undefined : "bg-violet-50 text-violet-700 ring-violet-200"}>{variantLabel(s.variant)}</Badge></td>
                    <td className="px-4 py-3"><ChannelTag channel={s.channel} /></td>
                    <td className="px-4 py-3 tabular-nums text-slate-600">{s.turn_count}</td>
                    <td className="px-4 py-3 text-right">
                      <Button variant="ghost" className="px-2" aria-label="Duplicate" onClick={() => void duplicate(s)}><Copy className="h-4 w-4" /></Button>
                      <Button variant="ghost" className="px-2" aria-label="Delete" onClick={() => void remove(s)}><Trash2 className="h-4 w-4" /></Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {toast && <Toast message={toast} tone="error" onClose={() => setToast(null)} />}
    </>
  );
}
