"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import CaseTimeline, { type TimelineEvent } from "@/components/CaseTimeline";

function fmtTs(ts: string) {
  try {
    return new Date(ts).toLocaleString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return ts;
  }
}

export default function TimelineView() {
  const router = useRouter();
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/timeline");
      if (!res.ok) throw new Error(`timeline failed: ${res.status}`);
      setEvents(await res.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load timeline");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function extractAll() {
    setExtracting(true);
    try {
      const res = await fetch("/api/timeline/extract-all", { method: "POST" });
      if (!res.ok) throw new Error(`extract-all failed: ${res.status}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "extract-all failed");
    } finally {
      setExtracting(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Case Timeline</h1>
          <p className="text-sm text-gray-500">
            All events normalized to UTC. One lane per evidence source type.
            Click an event to open its source artifact.
          </p>
        </div>
        <button
          onClick={extractAll}
          disabled={extracting}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {extracting ? "Extracting…" : "Extract events (all)"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="rounded border p-2">
        {events.length === 0 ? (
          <p className="p-4 text-sm text-gray-500">
            No events yet. Upload artifacts, then click “Extract events (all)”.
          </p>
        ) : (
          <CaseTimeline
            events={events}
            onSelect={(artifactId) => router.push(`/artifacts/${artifactId}`)}
          />
        )}
      </div>

      {/* Keyboard / AT fallback: same events as a plain table with links. */}
      <h2 className="mt-8 text-lg font-semibold">All events</h2>
      <table className="mt-2 w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="p-2">UTC time</th>
            <th className="p-2">Source</th>
            <th className="p-2">Event</th>
            <th className="p-2">Artifact</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id} className="border-b">
              <td className="p-2 font-mono whitespace-nowrap">{fmtTs(e.event_ts_utc)}</td>
              <td className="p-2">{e.source_type}</td>
              <td className="p-2">{e.label}</td>
              <td className="p-2">
                <a
                  href={`/artifacts/${e.artifact_id}`}
                  className="text-blue-600 underline"
                >
                  #{e.artifact_id}
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
