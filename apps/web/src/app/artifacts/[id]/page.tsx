"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";

type Entity = { id: number; kind: string; value: string; span: unknown };
type Custody = { id: number; action: string; actor: string; ts: string; detail: string };
type TimelineEvent = {
  id: number;
  event_ts_utc: string;
  label: string | null;
  source_type: string;
  artifact_id: number;
};
type ArtifactDetail = {
  id: number;
  source_type: string;
  filename: string;
  sha256: string;
  ingest_ts: string;
  metadata: Record<string, unknown>;
  extracted_text: string | null;
  exif: Record<string, unknown>;
  entities: Entity[] | null;
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded border p-4">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
        {title}
      </h2>
      {children}
    </section>
  );
}

function KeyValue({ obj }: { obj: Record<string, unknown> }) {
  const entries = Object.entries(obj);
  if (entries.length === 0) return <p className="text-sm text-gray-400">—</p>;
  return (
    <dl className="grid grid-cols-[160px_1fr] gap-x-4 gap-y-1 text-sm">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="font-medium text-gray-600">{k}</dt>
          <dd className="break-all font-mono text-xs">{String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function ArtifactDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [artifact, setArtifact] = useState<ArtifactDetail | null>(null);
  const [custody, setCustody] = useState<Custody[]>([]);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`/api/artifacts/${id}`);
        if (res.status === 404) {
          setNotFound(true);
          return;
        }
        if (!res.ok) throw new Error(`artifact fetch failed: ${res.status}`);
        const data: ArtifactDetail = await res.json();
        setArtifact(data);
        const [cRes, tRes] = await Promise.all([
          fetch(`/api/artifacts/${id}/custody`),
          fetch("/api/timeline"),
        ]);
        if (cRes.ok) setCustody(await cRes.json());
        if (tRes.ok) {
          const all: TimelineEvent[] = await tRes.json();
          setEvents(all.filter((e) => e.artifact_id === Number(id)));
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load artifact");
      }
    })();
  }, [id]);

  if (notFound) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <h1 className="text-xl font-bold">Artifact not found</h1>
        <p className="mt-2 text-sm text-gray-500">
          No artifact with id <span className="font-mono">{id}</span> exists.
        </p>
        <Link href="/" className="mt-4 inline-block text-blue-600 underline">
          ← Back to evidence intake
        </Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      </div>
    );
  }

  if (!artifact) {
    return <p className="p-6 text-sm text-gray-500">Loading artifact…</p>;
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <div>
        <Link href="/" className="text-sm text-blue-600 underline">
          ← Evidence intake
        </Link>
        <h1 className="mt-1 text-2xl font-bold break-all">{artifact.filename}</h1>
        <p className="text-sm text-gray-500">
          #{artifact.id} · {artifact.source_type} · ingested {artifact.ingest_ts}
        </p>
      </div>

      <Section title="SHA-256 (integrity)">
        <p className="break-all font-mono text-sm">{artifact.sha256}</p>
      </Section>

      <Section title="Metadata">
        <KeyValue obj={artifact.metadata ?? {}} />
      </Section>

      <Section title="Extracted text">
        {artifact.extracted_text ? (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-sm">
            {artifact.extracted_text}
          </pre>
        ) : (
          <p className="text-sm text-gray-400">No text extracted.</p>
        )}
      </Section>

      <Section title="EXIF">
        <KeyValue obj={artifact.exif ?? {}} />
      </Section>

      <Section title={`Entities (${artifact.entities?.length ?? 0})`}>
        {artifact.entities && artifact.entities.length > 0 ? (
          <ul className="space-y-1 text-sm">
            {artifact.entities.map((e) => (
              <li key={e.id} className="flex gap-2">
                <span className="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs">
                  {e.kind}
                </span>
                <span className="break-all">{e.value}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-400">No entities extracted.</p>
        )}
      </Section>

      <Section title={`Timeline events (${events.length})`}>
        {events.length > 0 ? (
          <ul className="space-y-1 text-sm">
            {events.map((e) => (
              <li key={e.id} className="flex gap-3">
                <span className="font-mono text-xs whitespace-nowrap">
                  {e.event_ts_utc}
                </span>
                <span>{e.label}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-400">
            No extractable timestamps for this artifact.
          </p>
        )}
      </Section>

      <Section title={`Chain of custody (${custody.length})`}>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="p-2">Action</th>
              <th className="p-2">Actor</th>
              <th className="p-2">Time (UTC)</th>
              <th className="p-2">Detail</th>
            </tr>
          </thead>
          <tbody>
            {custody.map((c) => (
              <tr key={c.id} className="border-b">
                <td className="p-2 font-mono text-xs">{c.action}</td>
                <td className="p-2">{c.actor}</td>
                <td className="p-2 font-mono text-xs">{c.ts}</td>
                <td className="p-2 text-xs">{c.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}
