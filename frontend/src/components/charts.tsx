import { BarChart3, Table2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import type { TooltipProps } from "recharts";
import { Card, cx } from "./ui";

export interface TableColumn<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
}

/** A chart card with a Chart/Table toggle so values are never conveyed by colour alone. */
export function ChartCard<T>({ title, subtitle, rows, columns, children, height = 280 }: {
  title: string; subtitle?: string; rows: T[]; columns: TableColumn<T>[]; children: ReactNode; height?: number;
}) {
  const [table, setTable] = useState(false);
  return (
    <Card
      title={title}
      subtitle={subtitle}
      actions={
        <div className="inline-flex rounded-lg bg-slate-100 p-0.5 text-xs">
          <button onClick={() => setTable(false)} className={cx("inline-flex items-center gap-1 rounded-md px-2 py-1", !table && "bg-white shadow-sm")}><BarChart3 className="h-3.5 w-3.5" />Chart</button>
          <button onClick={() => setTable(true)} className={cx("inline-flex items-center gap-1 rounded-md px-2 py-1", table && "bg-white shadow-sm")}><Table2 className="h-3.5 w-3.5" />Table</button>
        </div>
      }
    >
      {table ? (
        <div className="overflow-x-auto" style={{ maxHeight: height + 20 }}>
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500">{columns.map((c) => <th key={c.key} className="px-2 py-1.5 font-medium">{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-t border-slate-100">{columns.map((c) => <td key={c.key} className="px-2 py-1.5 tabular-nums">{c.render(row)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ height }}>{children}</div>
      )}
    </Card>
  );
}

/** Tooltip styled with text tokens; the coloured swatch carries identity, never the text. */
export function ChartTooltip({ active, payload, label, format }: TooltipProps<number, string> & { format?: (v: number, name: string) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg">
      {label !== undefined && <div className="mb-1 font-medium text-slate-900">{label}</div>}
      {payload.map((p) => (
        <div key={String(p.dataKey)} className="flex items-center gap-2 text-slate-600">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: p.color }} />
          <span>{p.name}</span>
          <span className="ml-auto pl-3 font-semibold tabular-nums text-slate-900">
            {typeof p.value === "number" ? (format ? format(p.value, String(p.name)) : p.value.toFixed(2)) : p.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export const axisProps = { tickLine: false, axisLine: false, tick: { fontSize: 12, fill: "#64748b" } } as const;
