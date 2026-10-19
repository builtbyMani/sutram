"use client";

import { useCallback, useEffect, useState } from "react";

type Finding = {
  id: number;
  type: string; // finding-type contract (INTEGRATION-6.md); mirrors rule_or_model
  title: string;
  description: string;
  rule_or_model: string;
  confidence: number;
  artifact_ids: number[];
  snippet: string;
  created_ts: string;
};

type Summary = {
  summary: string;
  degraded?: boolean;
  reason?: string | null;
  model?: string | null;
  citations_dropped?: number;
};

type AuditEntry = {
  id: number;
  ts: string;
  actor: string;
  action: string;
  detail: Record<string, unknown>;
};

// NFR-02 UI gate: a finding is only rendered with its full provenance block.
// Anything missing provenance is suppressed with an explicit placeholder.
function hasProvenance(f: Finding) {
  return (
    Array.isArray(f.artifact_ids) &&
    f.artifact_ids.length > 0 &&
    !!f.rule_or_model &&
    !!f.snippet
  );
}

function confidenceBadge(conf: number) {
  const cls =
    conf >= 0.85
      ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
      : conf >= 0.6
        ? "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200"
        : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200";
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${cls}`}>
      {(conf * 100).toFixed(0)}%
    </span>
  );
}

function FindingCard({ finding }: { finding: Finding }) {
  const [open, setOpen] = useState(false);
  if (!hasProvenance(finding)) {
    return (
      <li className="rounded-lg border border-dashed border-zinc-300 p-4 text-sm text-zinc-500 dark:border-zinc-700">
        Finding #{finding.id}: provenance missing — suppressed
      </li>
    );
  }
  return (
    <li className="rounded-lg border border-zinc-200 p-4 text-sm dark:border-zinc-800">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{finding.title}</span>
        {confidenceBadge(finding.confidence)}
      </div>
      <div className="mt-1 flex flex-wrap gap-2 text-xs">
        <span className="rounded bg-zinc-100 px-2 py-0.5 font-mono dark:bg-zinc-800">
          {finding.rule_or_model}
        </span>
        {finding.artifact_ids.map((aid) => (
          <a
            key={aid}
            href={`/artifacts/${aid}`}
            className="rounded bg-blue-50 px-2 py-0.5 font-mono text-blue-700 hover:underline dark:bg-blue-950 dark:text-blue-300"
          >
            artifact:{aid}
          </a>
        ))}
      </div>
      {finding.description && (
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">
          {finding.description}
        </p>
      )}
      <button
        onClick={() => setOpen(!open)}
        className="mt-2 text-xs text-zinc-500 underline hover:text-zinc-700 dark:hover:text-zinc-300"
      >
        {open ? "Hide provenance" : "Show provenance"}
      </button>
      {open && (
        <div className="mt-2 rounded bg-zinc-50 p-3 dark:bg-zinc-900">
          <div className="text-xs uppercase tracking-wide text-zinc-500">
            Evidence snippet
          </div>
          <pre className="mt-1 whitespace-pre-wrap font-mono text-xs">
            {finding.snippet}
          </pre>
          <div className="mt-2 text-xs text-zinc-500">
            Rule/model: {finding.rule_or_model} · confidence:{" "}
            {finding.confidence.toFixed(2)} · created {finding.created_ts}
          </div>
        </div>
      )}
    </li>
  );
}

export default function FindingsPage() {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadFindings = useCallback(async () => {
    const res = await fetch("/api/findings");
    if (!res.ok) throw new Error(`findings failed: ${res.status}`);
    setFindings(await res.json());
  }, []);

  const loadAudit = useCallback(async () => {
    const res = await fetch("/api/audit");
    if (!res.ok) throw new Error(`audit failed: ${res.status}`);
    setAudit(await res.json());
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await Promise.all([loadFindings(), loadAudit()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
    } finally {
      setLoading(false);
    }
  }, [loadFindings, loadAudit]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onRebuild() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/analyze", { method: "POST" });
      if (!res.ok) throw new Error(`rebuild failed: ${res.status}`);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "rebuild failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSummarize() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/summaries", { method: "POST" });
      if (!res.ok) throw new Error(`summary failed: ${res.status}`);
      setSummary(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "summary failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Findings</h1>
          <p className="text-sm text-zinc-500">
            Every finding carries provenance — artifact ids, rule/model,
            confidence, evidence snippet
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onRebuild}
            disabled={busy}
            className="rounded-md bg-zinc-900 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {busy ? "Working…" : "Rebuild findings"}
          </button>
          <button
            onClick={onSummarize}
            disabled={busy}
            className="rounded-md border border-zinc-300 px-4 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-zinc-700"
          >
            {busy ? "Working…" : "Generate case summary"}
          </button>
        </div>
      </header>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      {summary && (
        <section className="mb-8 rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Case summary{" "}
            {summary.degraded ? (
              <span className="text-amber-600">(offline template)</span>
            ) : (
              <span className="text-green-600">(Gemini {summary.model})</span>
            )}
          </h2>
          {summary.degraded && summary.reason && (
            <p className="mb-2 text-xs text-amber-600">{summary.reason}</p>
          )}
          <p className="whitespace-pre-wrap text-sm">{summary.summary}</p>
        </section>
      )}

      <section className="mb-8">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Findings ({findings.length})
        </h2>
        {loading ? (
          <p className="text-sm text-zinc-500">Loading…</p>
        ) : findings.length === 0 ? (
          <p className="text-sm text-zinc-500">
            No findings yet. Run fraud analysis, then rebuild findings.
          </p>
        ) : (
          <ul className="space-y-3">
            {findings.map((f) => (
              <FindingCard key={f.id} finding={f} />
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Audit trail ({audit.length})
        </h2>
        {audit.length === 0 ? (
          <p className="text-sm text-zinc-500">No audited actions yet.</p>
        ) : (
          <ul className="space-y-1">
            {audit.map((a) => (
              <li
                key={a.id}
                className="flex flex-wrap gap-x-3 rounded border border-zinc-100 px-3 py-1.5 font-mono text-xs text-zinc-600 dark:border-zinc-900 dark:text-zinc-400"
              >
                <span className="text-zinc-400">{a.ts}</span>
                <span className="font-medium text-zinc-800 dark:text-zinc-200">
                  {a.action}
                </span>
                <span>
                  {a.actor} · {JSON.stringify(a.detail)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
