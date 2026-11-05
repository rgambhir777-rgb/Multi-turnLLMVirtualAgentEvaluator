import { KeyRound, Plug, RotateCcw, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, Card, ErrorBox, Field, inputClass, PageHeader, Spinner, Toast } from "../components/ui";
import { api, type SettingsData } from "../lib/api";
import { useApi } from "../lib/hooks";

const GROUPS: { title: string; subtitle: string; keys: { key: string; label: string; placeholder?: string }[] }[] = [
  {
    title: "LLM provider",
    subtitle: "Used by the LLM judge, LLM journey labelling and the LLM stand-in agent. Stored only in your local .env file.",
    keys: [
      { key: "ANTHROPIC_API_KEY", label: "Anthropic API key", placeholder: "sk-ant-…" },
      { key: "ANTHROPIC_MODEL", label: "Anthropic model", placeholder: "claude-opus-5-5" },
      { key: "OPENAI_API_KEY", label: "OpenAI-compatible API key", placeholder: "sk-…" },
      { key: "OPENAI_BASE_URL", label: "OpenAI-compatible base URL", placeholder: "https://api.openai.com/v1" },
      { key: "OPENAI_MODEL", label: "OpenAI-compatible model", placeholder: "gpt-4o-mini" },
      { key: "LLM_PROVIDER", label: "Preferred provider (auto | anthropic | openai)", placeholder: "auto" },
      { key: "VOICE_ROUNDTRIP", label: "Real TTS→STT round trip for voice (true/false, needs OpenAI key)", placeholder: "false" },
    ],
  },
  {
    title: "NICE CXone",
    subtitle: "Credentials for the NICE CXone adapter (Digital / Bot). Never stored in the database.",
    keys: [
      { key: "CXONE_AUTH_URL", label: "Auth URL", placeholder: "https://cxone.niceincontact.com/auth/token" },
      { key: "CXONE_API_BASE_URL", label: "API base URL", placeholder: "https://api-<area>.niceincontact.com" },
      { key: "CXONE_CLIENT_ID", label: "Client ID" },
      { key: "CXONE_CLIENT_SECRET", label: "Client secret" },
      { key: "CXONE_ACCESS_KEY_ID", label: "Access key ID" },
      { key: "CXONE_ACCESS_KEY_SECRET", label: "Access key secret" },
      { key: "CXONE_BUSINESS_UNIT", label: "Business unit" },
      { key: "CXONE_CHANNEL_ID", label: "Digital channel ID" },
      { key: "CXONE_POINT_OF_CONTACT", label: "Point of contact (optional)" },
    ],
  },
];

export default function Settings({ onSaved }: { onSaved: () => void }) {
  const settings = useApi<SettingsData>("/settings");
  const [envValues, setEnvValues] = useState<Record<string, string>>({});
  const [judgeMode, setJudgeMode] = useState("auto");
  const [thresholds, setThresholds] = useState<Record<string, number>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);

  useEffect(() => {
    if (!settings.data) return;
    setEnvValues(Object.fromEntries(Object.entries(settings.data.env).map(([k, v]) => [k, v.value])));
    setJudgeMode(settings.data.judge_mode);
    setThresholds(settings.data.thresholds);
  }, [settings.data]);

  if (settings.loading) return <Spinner />;
  if (settings.error || !settings.data) return <ErrorBox message={settings.error ?? "Could not load settings."} onRetry={settings.reload} />;
  const s = settings.data;

  const save = async () => {
    setSaving(true);
    setError(null);
    const changed = Object.fromEntries(Object.entries(envValues).filter(([k, v]) => v !== s.env[k]?.value));
    try {
      const updated = await api.put<SettingsData>("/settings", { env: changed, judge_mode: judgeMode, thresholds });
      settings.setData(updated);
      setToast({ message: "Settings saved.", tone: "success" });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const testLlm = async () => {
    setTesting(true);
    try {
      const res = await api.post<{ ok: boolean; message: string }>("/settings/test-llm");
      setToast({ message: res.message, tone: res.ok ? "success" : "error" });
      onSaved();
    } catch (e) {
      setToast({ message: (e as Error).message, tone: "error" });
    } finally {
      setTesting(false);
    }
  };

  const reset = async () => {
    if (!window.confirm("Reset ALL data to the Northwind demo? Your agents, scripts, KB edits and runs will be replaced.")) return;
    setResetting(true);
    try {
      await api.post("/settings/reset-demo");
      setToast({ message: "Demo data restored.", tone: "success" });
      await settings.reload();
    } catch (e) {
      setToast({ message: (e as Error).message, tone: "error" });
    } finally {
      setResetting(false);
    }
  };

  return (
    <>
      <PageHeader title="Settings" description="API keys and CXone credentials are written to the local .env file and masked here. Thresholds and judge mode are stored in the app database."
        actions={<Button variant="primary" loading={saving} onClick={() => void save()}><Save className="h-4 w-4" />Save settings</Button>} />
      {error && <div className="mb-4"><ErrorBox message={error} /></div>}
      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Judge" subtitle="Auto uses the LLM judge when a key is configured and falls back to the offline heuristic judge on any error.">
          <div className="space-y-3">
            {s.judge_modes.map((mode) => (
              <label key={mode} className="flex items-start gap-3 rounded-lg border border-slate-200 px-3 py-2">
                <input type="radio" name="judge" className="mt-1 text-indigo-600" checked={judgeMode === mode} onChange={() => setJudgeMode(mode)} />
                <span>
                  <span className="text-sm font-medium text-slate-800">{mode === "auto" ? "Auto" : mode === "llm" ? "LLM-as-judge" : "Offline heuristic"}</span>
                  <span className="block text-xs text-slate-500">
                    {mode === "auto" ? "LLM when available, otherwise heuristic." : mode === "llm" ? "Strict rubric, JSON validated, retried on invalid output; falls back to heuristic if the LLM fails." : "Keyword, entity and number matching against the KB and earlier turns. Always available, fully deterministic."}
                  </span>
                </span>
              </label>
            ))}
            <Button onClick={() => void testLlm()} loading={testing}><Plug className="h-4 w-4" />Test LLM connection</Button>
          </div>
        </Card>
        <Card title="Readiness thresholds" subtitle="Used for the GO / CONDITIONAL / NO-GO verdict of every run that finishes after you save.">
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries(s.threshold_labels).map(([key, label]) => (
              <Field key={key} label={label} hint={`Default ${s.default_thresholds[key]}`}>
                <input type="number" step="0.01" className={inputClass} value={thresholds[key] ?? ""} onChange={(e) => setThresholds({ ...thresholds, [key]: Number(e.target.value) })} />
              </Field>
            ))}
          </div>
        </Card>
        {GROUPS.map((group) => (
          <Card key={group.title} title={<span className="inline-flex items-center gap-2"><KeyRound className="h-4 w-4 text-indigo-500" />{group.title}</span>} subtitle={group.subtitle}>
            <div className="space-y-3">
              {group.keys.map(({ key, label, placeholder }) => (
                <Field key={key} label={label} hint={s.env[key]?.secret && s.env[key]?.set ? "Saved (masked). Replace the whole value to change it, or clear it and save to remove the key." : undefined}>
                  <input className={`${inputClass} font-mono text-xs`} type="text" autoComplete="off" spellCheck={false} placeholder={placeholder}
                    value={envValues[key] ?? ""} onChange={(e) => setEnvValues({ ...envValues, [key]: e.target.value })} />
                </Field>
              ))}
            </div>
          </Card>
        ))}
        <Card title="Demo data" subtitle="Restore the Northwind Telecom demo: KB, 220 transcripts, journeys, 15 scripts, agents and three completed runs.">
          <Button variant="danger" loading={resetting} onClick={() => void reset()}><RotateCcw className="h-4 w-4" />Reset demo data</Button>
        </Card>
      </div>
      {toast && <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />}
    </>
  );
}
