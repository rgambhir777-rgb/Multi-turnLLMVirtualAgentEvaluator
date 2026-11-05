// Typed client for the AgentProof FastAPI backend.

export type Channel = "chat" | "voice" | "email" | "sms";
export type Verdict = "GO" | "CONDITIONAL" | "NO-GO";

export interface Metrics {
  turns: number;
  conversations: number;
  avg_accuracy: number;
  avg_context: number;
  context_turns?: number;
  avg_hallucination: number;
  hallucination_rate: number;
  hallucinated_turns: number;
  avg_channel_fit: number;
  task_completion_rate: number;
  critical_failures: number;
}

export interface Reason {
  severity: "soft" | "hard";
  text: string;
}

export interface ChannelSummary {
  metrics: Metrics;
  verdict: Verdict;
  reasons: Reason[];
  passed: string[];
}

export interface RunSummary {
  metrics?: Metrics;
  verdict?: Verdict;
  reasons?: Reason[];
  passed?: string[];
  by_channel?: Record<string, ChannelSummary>;
  judges?: string[];
  warnings?: string[];
}

export interface Agent {
  id: number;
  name: string;
  adapter_type: "mock" | "http" | "llm" | "cxone";
  description: string;
  config: Record<string, unknown>;
  created_at: string;
}

export interface AgentMeta {
  adapter_types: Record<string, string>;
  mock_presets: Record<string, Record<string, number | string | boolean>>;
  mock_settings: Record<string, string>;
  cxone_settings: string[];
  config_templates: Record<string, Record<string, unknown>>;
}

export interface KBFact {
  id: number;
  category: string;
  title: string;
  content: string;
  tags: string[];
}

export interface Journey {
  id: number;
  name: string;
  description: string;
  intent: string;
  keywords: string[];
  frequency: number;
  avg_turns: number;
  example_utterances: string[];
  source: string;
  labeler: string;
  script_count: number;
}

export interface ScriptTurn {
  customer: string;
  must_include: string[];
  must_not_include: string[];
  must_remember: string[];
  notes: string;
}

export interface TestScript {
  id: number;
  name: string;
  journey_id: number | null;
  journey_name: string;
  channel: Channel;
  variant: string;
  persona: Record<string, string>;
  goal: string;
  email_subject: string;
  turns: ScriptTurn[];
  turn_count: number;
}

export interface Run {
  id: number;
  name: string;
  agent_id: number | null;
  agent_name: string;
  status: "queued" | "running" | "completed" | "failed";
  script_ids: number[];
  channels: Channel[];
  judge_mode: string;
  total_conversations: number;
  completed_conversations: number;
  progress: number;
  verdict: Verdict | null;
  metrics: Partial<Metrics>;
  summary: RunSummary;
  error: string;
  active: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ConversationBrief {
  id: number;
  run_id: number;
  script_id: number | null;
  script_name: string;
  journey_name: string;
  variant: string;
  channel: Channel;
  status: string;
  task_completed: boolean;
  task_score: number;
  avg_context: number;
  avg_accuracy: number;
  avg_hallucination: number;
  avg_channel_fit: number;
  critical_failures: number;
  hallucinated_turns: number;
  turn_count: number;
  error: string;
}

export interface RunDetail extends Run {
  conversations: ConversationBrief[];
}

export interface Claim {
  id: number;
  text: string;
  label: "Supported" | "Contradicted" | "Unsupported";
  evidence: string;
}

export interface Turn {
  id: number;
  index: number;
  customer_text: string;
  customer_rendered: string;
  agent_text: string;
  latency_ms: number;
  expectations: { must_include?: string[]; must_not_include?: string[]; must_remember?: string[]; notes?: string };
  context_score: number;
  context_applicable: boolean;
  accuracy_score: number;
  hallucination_score: number;
  channel_fit_score: number;
  context_justification: string;
  accuracy_justification: string;
  hallucination_justification: string;
  channel_justification: string;
  channel_flags: string[];
  hallucinated: boolean;
  critical: boolean;
  critical_reason: string;
  judge: string;
  claims: Claim[];
}

export interface ConversationDetail extends ConversationBrief {
  email_subject: string;
  persona: Record<string, string>;
  goal: string;
  task_justification: string;
  run_name: string;
  agent_name: string;
  turns: Turn[];
}

export interface Dashboard {
  cards: {
    agent_id: number;
    agent_name: string;
    run_id: number;
    run_name: string;
    finished_at: string | null;
    verdict: Verdict;
    metrics: Metrics;
    reasons: Reason[];
    channels: Record<string, Verdict>;
  }[];
  kpis: { runs: number; conversations: number; turns: number; latest: Run | null };
  trends: ({ run_id: number; label: string; agent: string; date: string | null } & Partial<Metrics>)[];
  channel_scores: Record<string, number | string>[];
  agents: string[];
  worst_journeys: { journey: string; avg_accuracy: number; hallucination_rate: number; critical: number; turns: number }[];
  thresholds: Record<string, number>;
}

export interface CompareResult {
  a: Run;
  b: Run;
  deltas: Record<string, number>;
  by_channel: { channel: string; a: Partial<Metrics>; b: Partial<Metrics>; verdict_a?: Verdict; verdict_b?: Verdict }[];
  journeys: { journey: string; a?: { avg_accuracy: number; hallucination_rate: number }; b?: { avg_accuracy: number; hallucination_rate: number } }[];
  conversations: { script_name: string; channel: Channel; a: ConversationBrief; b: ConversationBrief }[];
}

export interface Status {
  version: string;
  judge_mode: string;
  effective_judge: "llm" | "heuristic";
  llm_provider: string | null;
  llm_model: string;
  llm_error: string;
  offline: boolean;
  offline_reason: string;
}

export interface SettingsData {
  env: Record<string, { value: string; set: boolean; secret: boolean }>;
  judge_mode: string;
  judge_modes: string[];
  thresholds: Record<string, number>;
  threshold_labels: Record<string, string>;
  default_thresholds: Record<string, number>;
}

export interface DiscoverResult {
  transcripts: number;
  journeys: Journey[];
  labeler: string;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const item = d as { loc?: (string | number)[]; msg?: string };
        const where = (item.loc || []).filter((p) => p !== "body").join(" → ");
        return where ? `${where}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }
  return "Request failed";
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  let response: Response;
  try {
    response = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError(0, "Cannot reach the AgentProof server. Is it still running?");
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let data: unknown = text;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* plain-text responses (e.g. Markdown export) */
  }
  if (!response.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(response.status, detail ? describe(detail) : `Server error ${response.status}`);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: (path: string) => request<void>("DELETE", path),
  upload: <T>(path: string, form: FormData) => request<T>("POST", path, form),
};
