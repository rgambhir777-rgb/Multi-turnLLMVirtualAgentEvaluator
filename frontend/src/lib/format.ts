import type { Verdict } from "./api";

export const CHANNELS = ["chat", "sms", "email", "voice"] as const;

export const CHANNEL_LABEL: Record<string, string> = { chat: "Chat", sms: "SMS", email: "Email", voice: "Voice" };

// Categorical series colours (validated first-three slots of the reference palette, all-pairs CVD safe).
export const SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a"];

/** Colour follows the entity: an agent keeps its colour across every chart. */
export function agentColor(name: string, agents: string[]): string {
  const index = agents.indexOf(name);
  return SERIES_COLORS[(index >= 0 ? index : 0) % SERIES_COLORS.length];
}

export const VERDICT_STYLE: Record<Verdict, { bg: string; text: string; ring: string; dot: string; label: string }> = {
  GO: { bg: "bg-emerald-50", text: "text-emerald-700", ring: "ring-emerald-200", dot: "#0ca30c", label: "Ready for real customers" },
  CONDITIONAL: { bg: "bg-amber-50", text: "text-amber-700", ring: "ring-amber-200", dot: "#fab219", label: "Go live with conditions" },
  "NO-GO": { bg: "bg-red-50", text: "text-red-700", ring: "ring-red-200", dot: "#d03b3b", label: "Not ready" },
};

export const fmtScore = (v: number | undefined | null) => (v === undefined || v === null ? "—" : v.toFixed(2));
export const fmtPct = (v: number | undefined | null, digits = 1) =>
  v === undefined || v === null ? "—" : `${(v * 100).toFixed(digits)}%`;

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Tailwind classes for a 0–5 score: red < 2.5 ≤ amber < 4 ≤ green. */
export function scoreTone(score: number): string {
  if (score >= 4) return "bg-emerald-50 text-emerald-700 ring-emerald-200";
  if (score >= 2.5) return "bg-amber-50 text-amber-700 ring-amber-200";
  return "bg-red-50 text-red-700 ring-red-200";
}

export function variantLabel(v: string): string {
  return v.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
