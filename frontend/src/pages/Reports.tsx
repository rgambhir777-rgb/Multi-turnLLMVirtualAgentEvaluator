import { Braces, FileDown, FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";
import { Card, EmptyState, ErrorBox, PageHeader, Spinner, VerdictBadge } from "../components/ui";
import type { Run } from "../lib/api";
import { fmtDate, fmtPct, fmtScore } from "../lib/format";
import { useApi } from "../lib/hooks";
import { linkButton } from "../components/run";

export default function Reports() {
  const runs = useApi<Run[]>("/runs");
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<number | null>(null);
  const completed = (runs.data ?? []).filter((r) => r.status === "completed");

  const downloadPdf = async (run: Run) => {
    setPdfError(null);
    setDownloading(run.id);
    try {
      const res = await fetch(`/api/runs/${run.id}/report.pdf`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: "PDF generation failed." }));
        throw new Error(body.detail);
      }
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `agentproof_run${run.id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setPdfError(`${(e as Error).message} The HTML report always works.`);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <>
      <PageHeader title="Reports" description="Stakeholder-ready readiness reports (executive summary, verdict, key risks, example failures with transcripts) and raw turn-score exports." />
      {pdfError && <div className="mb-4"><ErrorBox message={pdfError} /></div>}
      {runs.loading ? <Spinner /> : runs.error ? <ErrorBox message={runs.error} onRetry={runs.reload} /> : !completed.length ? (
        <EmptyState title="No completed runs" message="Reports become available when a run completes." />
      ) : (
        <div className="space-y-3">
          {completed.map((r) => (
            <Card key={r.id}>
              <div className="flex flex-wrap items-center gap-4">
                <div className="min-w-[240px] flex-1">
                  <div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-slate-900">#{r.id} {r.name}</span><VerdictBadge verdict={r.verdict} /></div>
                  <div className="mt-0.5 text-xs text-slate-500">
                    {r.agent_name} · finished {fmtDate(r.finished_at)} · accuracy {fmtScore(r.metrics.avg_accuracy)} · hallucination {fmtPct(r.metrics.hallucination_rate)} · {r.metrics.turns} turns
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <a className={linkButton} href={`/api/runs/${r.id}/report.html`} target="_blank" rel="noreferrer"><FileText className="h-4 w-4" />View HTML</a>
                  <a className={linkButton} href={`/api/runs/${r.id}/report.html?download=true`}><FileDown className="h-4 w-4" />Download HTML</a>
                  <button className={linkButton} onClick={() => void downloadPdf(r)} disabled={downloading === r.id}><FileDown className="h-4 w-4" />{downloading === r.id ? "Building PDF…" : "PDF"}</button>
                  <a className={linkButton} href={`/api/runs/${r.id}/export.csv`}><FileSpreadsheet className="h-4 w-4" />CSV</a>
                  <a className={linkButton} href={`/api/runs/${r.id}/export.json`}><Braces className="h-4 w-4" />JSON</a>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
