"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

type Artifact = {
  id: number;
  source_type: string;
  filename: string;
  sha256: string;
  ingest_ts: string;
  metadata: { size?: number; content_type?: string | null };
};

const SOURCE_TYPES = [
  "document",
  "chat",
  "chat_export",
  "log",
  "pcap",
  "image",
  "video",
  "other",
];

function shortHash(h: string) {
  return h.length > 20 ? `${h.slice(0, 12)}…${h.slice(-6)}` : h;
}

/** Extract a human-readable message from an error response body. */
async function errorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.text();
  try {
    const parsed = JSON.parse(body);
    if (typeof parsed?.detail === "string") return parsed.detail;
  } catch {
    /* not JSON — fall through */
  }
  return body ? `${fallback} (${res.status}): ${body.slice(0, 200)}` : `${fallback} (${res.status})`;
}

export default function Home() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [sourceType, setSourceType] = useState("document");
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [osintInput, setOsintInput] = useState("");
  const [osintMode, setOsintMode] = useState<"url" | "keyword">("url");
  const [osintLoading, setOsintLoading] = useState(false);
  const [osintStatus, setOsintStatus] = useState<string | null>(null);
  const [osintError, setOsintError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadArtifacts = useCallback(async () => {
    try {
      const res = await fetch("/api/artifacts");
      if (!res.ok) throw new Error(await errorMessage(res, "list failed"));
      setArtifacts(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load artifacts");
    }
  }, []);

  useEffect(() => {
    loadArtifacts();
  }, [loadArtifacts]);

  async function onUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Choose a file first.");
      return;
    }
    setUploading(true);
    setError(null);
    setStatus(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("source_type", sourceType);
      const res = await fetch("/api/artifacts", { method: "POST", body: form });
      if (!res.ok) throw new Error(await errorMessage(res, "upload failed"));
      const created: Artifact = await res.json();
      setStatus(`Stored #${created.id} — sha256 ${shortHash(created.sha256)}`);
      if (fileRef.current) fileRef.current.value = "";
      await loadArtifacts();
    } catch (e) {
      setError(e instanceof Error ? e.message : "upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function onOsintFetch(e: React.FormEvent) {
    e.preventDefault();
    const value = osintInput.trim();
    if (!value) {
      setOsintError(osintMode === "url" ? "Enter a URL first." : "Enter a keyword first.");
      return;
    }
    setOsintLoading(true);
    setOsintError(null);
    setOsintStatus(null);
    try {
      const payload =
        osintMode === "url" ? { url: value } : { keyword: value };
      const res = await fetch("/api/osint/fetch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await errorMessage(res, "OSINT fetch failed"));
      const data: {
        artifacts: Artifact[];
        failures: { url: string; reason: string }[];
      } = await res.json();
      const ids = data.artifacts.map((a) => `#${a.id}`).join(", ");
      const failNote =
        data.failures.length > 0
          ? ` — ${data.failures.length} failed: ${data.failures[0].reason}`
          : "";
      setOsintStatus(`Fetched ${data.artifacts.length} page(s) as ${ids}${failNote}`);
      setOsintInput("");
      await loadArtifacts();
    } catch (e) {
      setOsintError(e instanceof Error ? e.message : "OSINT fetch failed");
    } finally {
      setOsintLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-bold">SUTRAM Forensics Workbench</h1>
        <p className="text-sm text-zinc-500">
          Evidence intake + extraction: upload → hash → store → extract entities
        </p>
      </header>

      <section className="mb-8 rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Ingest evidence
        </h2>
        <form onSubmit={onUpload} className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-zinc-500">File</span>
            <input
              ref={fileRef}
              type="file"
              className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-zinc-900 file:px-3 file:py-1.5 file:text-sm file:text-white dark:file:bg-zinc-100 dark:file:text-zinc-900"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-zinc-500">Source type</span>
            <select
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value)}
              className="rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 text-sm dark:border-zinc-700"
            >
              {SOURCE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            disabled={uploading}
            className="rounded-md bg-zinc-900 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </form>
        {status && <p className="mt-3 text-sm text-green-600">{status}</p>}
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </section>

      <section className="mb-8 rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Add web source (OSINT)
        </h2>
        <form onSubmit={onOsintFetch} className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-zinc-500">Mode</span>
            <select
              value={osintMode}
              onChange={(e) =>
                setOsintMode(e.target.value as "url" | "keyword")
              }
              className="rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 text-sm dark:border-zinc-700"
            >
              <option value="url">Page URL</option>
              <option value="keyword">News keyword</option>
            </select>
          </label>
          <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
            <span className="text-zinc-500">
              {osintMode === "url" ? "URL" : "Keyword"}
            </span>
            <input
              type="text"
              value={osintInput}
              onChange={(e) => setOsintInput(e.target.value)}
              placeholder={
                osintMode === "url"
                  ? "https://example.com/article"
                  : "cyber fraud India"
              }
              className="rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 text-sm dark:border-zinc-700"
            />
          </label>
          <button
            type="submit"
            disabled={osintLoading}
            className="rounded-md bg-zinc-900 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {osintLoading ? "Fetching…" : "Fetch"}
          </button>
        </form>
        <p className="mt-2 text-xs text-zinc-500">
          Pages are fetched over HTTP with robots.txt obeyed; failures are
          reported, never stored.
        </p>
        {osintStatus && (
          <p className="mt-3 text-sm text-green-600">{osintStatus}</p>
        )}
        {osintError && <p className="mt-3 text-sm text-red-600">{osintError}</p>}
      </section>

      <section>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Artifacts ({artifacts.length})
        </h2>
        {artifacts.length === 0 ? (
          <p className="text-sm text-zinc-500">No artifacts ingested yet.</p>
        ) : (
          <ul className="space-y-2">
            {artifacts.map((a) => (
              <li key={a.id}>
                <Link
                  href={`/artifacts/${a.id}`}
                  className="block rounded-lg border border-zinc-200 p-3 text-sm transition-colors hover:border-zinc-400 dark:border-zinc-800 dark:hover:border-zinc-600"
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-medium">
                      #{a.id} {a.filename}
                    </span>
                    <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs dark:bg-zinc-800">
                      {a.source_type}
                    </span>
                  </div>
                  <div
                    className="mt-1 font-mono text-xs text-zinc-500"
                    title={a.sha256}
                  >
                    sha256: {shortHash(a.sha256)}
                  </div>
                  <div className="mt-0.5 text-xs text-zinc-500">
                    ingested {new Date(a.ingest_ts).toLocaleString()}
                    {typeof a.metadata.size === "number" &&
                      ` · ${a.metadata.size.toLocaleString()} bytes`}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
