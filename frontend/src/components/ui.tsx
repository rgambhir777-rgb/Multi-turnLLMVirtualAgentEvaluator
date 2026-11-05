import { AlertTriangle, CheckCircle2, Inbox, Loader2, X, XCircle } from "lucide-react";
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from "react";
import type { Verdict } from "../lib/api";
import { scoreTone, VERDICT_STYLE } from "../lib/format";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function Card({ children, className, title, actions, subtitle }: {
  children: ReactNode; className?: string; title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode;
}) {
  return (
    <section className={cx("rounded-xl border border-slate-200 bg-white shadow-card", className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-slate-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
export function Button({ variant = "secondary", loading, className, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant; loading?: boolean;
}) {
  const styles: Record<ButtonVariant, string> = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm disabled:bg-indigo-300",
    secondary: "bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:text-slate-400",
    danger: "bg-white text-red-600 ring-1 ring-inset ring-red-200 hover:bg-red-50 disabled:text-red-300",
    ghost: "text-slate-600 hover:bg-slate-100 disabled:text-slate-300",
  };
  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={cx("inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed", styles[variant], className)}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500">
      <Loader2 className="h-5 w-5 animate-spin text-indigo-500" /> {label}
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1">{message}</div>
      {onRetry && <button className="font-medium underline" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function EmptyState({ title, message, action }: { title: string; message?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
      <Inbox className="h-8 w-8 text-slate-300" />
      <h3 className="mt-3 text-sm font-semibold text-slate-800">{title}</h3>
      {message && <p className="mt-1 max-w-md text-sm text-slate-500">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", className || "bg-slate-50 text-slate-600 ring-slate-200")}>{children}</span>;
}

export function VerdictBadge({ verdict, size = "sm" }: { verdict: Verdict | null | undefined; size?: "sm" | "lg" }) {
  if (!verdict) return <Badge>Not scored</Badge>;
  const style = VERDICT_STYLE[verdict];
  const Icon = verdict === "GO" ? CheckCircle2 : verdict === "CONDITIONAL" ? AlertTriangle : XCircle;
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full font-semibold ring-1 ring-inset", style.bg, style.text, style.ring,
      size === "lg" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs")}>
      <Icon className={size === "lg" ? "h-4 w-4" : "h-3.5 w-3.5"} /> {verdict}
    </span>
  );
}

export function ScorePill({ value, label }: { value: number; label?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold tabular-nums ring-1 ring-inset", scoreTone(value))} title={label}>
      {label && <span className="font-normal opacity-75">{label}</span>}
      {value.toFixed(1)}
    </span>
  );
}

export function Modal({ open, onClose, title, children, footer, wide }: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 pt-[6vh]" onMouseDown={onClose}>
      <div className={cx("w-full rounded-xl bg-white shadow-xl", wide ? "max-w-4xl" : "max-w-xl")} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          <button onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" aria-label="Close"><X className="h-5 w-5" /></button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-slate-700">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "block w-full rounded-lg border-0 bg-white px-3 py-2 text-sm text-slate-900 ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-inset focus:ring-indigo-500";

export function Toast({ message, tone = "success", onClose }: { message: string; tone?: "success" | "error"; onClose: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onClose, 4000);
    return () => window.clearTimeout(timer);
  }, [onClose, message]);
  return (
    <div className={cx("fixed bottom-5 right-5 z-50 flex max-w-sm items-start gap-2 rounded-lg px-4 py-3 text-sm shadow-lg ring-1",
      tone === "success" ? "bg-white text-slate-800 ring-emerald-200" : "bg-white text-red-700 ring-red-200")}>
      {tone === "success" ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-600" /> : <XCircle className="mt-0.5 h-4 w-4" />}
      <span className="flex-1">{message}</span>
      <button onClick={onClose} className="text-slate-400 hover:text-slate-600"><X className="h-4 w-4" /></button>
    </div>
  );
}

/** A comma/Enter separated list editor used for expectations and keywords. */
export function TagInput({ values, onChange, placeholder, tone = "slate" }: {
  values: string[]; onChange: (v: string[]) => void; placeholder?: string; tone?: "slate" | "green" | "red" | "indigo";
}) {
  const tones = { slate: "bg-slate-100 text-slate-700", green: "bg-emerald-50 text-emerald-700", red: "bg-red-50 text-red-700", indigo: "bg-indigo-50 text-indigo-700" };
  return (
    <div className="flex min-h-[38px] flex-wrap items-center gap-1 rounded-lg bg-white px-2 py-1.5 ring-1 ring-inset ring-slate-300 focus-within:ring-2 focus-within:ring-indigo-500">
      {values.map((v, i) => (
        <span key={`${v}-${i}`} className={cx("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs", tones[tone])}>
          {v}
          <button type="button" onClick={() => onChange(values.filter((_, j) => j !== i))} className="opacity-60 hover:opacity-100" aria-label={`Remove ${v}`}><X className="h-3 w-3" /></button>
        </span>
      ))}
      <input
        className="min-w-[120px] flex-1 border-0 bg-transparent p-0.5 text-sm focus:outline-none focus:ring-0"
        placeholder={values.length ? "" : placeholder}
        onKeyDown={(e) => {
          const target = e.currentTarget;
          if ((e.key === "Enter" || e.key === ",") && target.value.trim()) {
            e.preventDefault();
            onChange([...values, target.value.trim()]);
            target.value = "";
          } else if (e.key === "Backspace" && !target.value && values.length) {
            onChange(values.slice(0, -1));
          }
        }}
        onBlur={(e) => {
          if (e.currentTarget.value.trim()) {
            onChange([...values, e.currentTarget.value.trim()]);
            e.currentTarget.value = "";
          }
        }}
      />
    </div>
  );
}
