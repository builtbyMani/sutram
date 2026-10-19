"use client";

// Phase 3: interactive evidence graph (COR-02, COR-03).
// Loaded via next/dynamic(..., { ssr: false }) from app/graph/page.tsx —
// this module is never evaluated on the server (STACK.md §3).

import { useCallback, useEffect, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";

type GraphNode = {
  id: number;
  kind: string;
  canonical_value: string;
  artifact_count: number;
};

type GraphEdge = {
  a: number;
  b: number;
  relation_type: string;
  confidence: number;
};

type IdentityArtifact = {
  id: number;
  filename: string;
  source_type: string;
  sha256: string;
};

const KIND_COLORS: Record<string, string> = {
  PERSON: "#3b82f6",
  ORG: "#8b5cf6",
  PHONE: "#22c55e",
  EMAIL: "#f59e0b",
  IP: "#ef4444",
};

function nodeColor(kind: string): string {
  return KIND_COLORS[kind] ?? "#9ca3af";
}

export default function EvidenceGraph() {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedLabel, setSelectedLabel] = useState("");
  const [drilldown, setDrilldown] = useState<IdentityArtifact[]>([]);
  const [drilldownLoading, setDrilldownLoading] = useState(false);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/graph");
      if (!res.ok) throw new Error(`graph failed: ${res.status}`);
      const data = await res.json();
      setNodes(data.nodes ?? []);
      setEdges(data.edges ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load graph");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  const selectNode = useCallback(async (id: number, label: string) => {
    setSelectedId(id);
    setSelectedLabel(label);
    setDrilldownLoading(true);
    try {
      const res = await fetch(`/api/identities/${id}/artifacts`);
      if (!res.ok) throw new Error(`drill-down failed: ${res.status}`);
      const data = await res.json();
      setDrilldown(data.artifacts ?? []);
    } catch {
      setDrilldown([]);
    } finally {
      setDrilldownLoading(false);
    }
  }, []);

  if (loading) return <p className="text-sm text-zinc-500">Loading graph…</p>;
  if (error)
    return (
      <div className="rounded-xl border border-red-200 p-5 text-sm text-red-600">
        {error} — run the correlation engine (POST /api/correlate) and{" "}
        <button className="underline" onClick={loadGraph}>
          retry
        </button>
        .
      </div>
    );

  return (
    <div className="flex gap-4">
      <div className="min-w-0 flex-1 rounded-xl border border-zinc-200 dark:border-zinc-800">
        <ForceGraph2D<GraphNode, GraphEdge>
          graphData={{ nodes, links: edges }}
          linkSource="a"
          linkTarget="b"
          height={560}
          nodeLabel={(n) =>
            `${n.kind}: ${n.canonical_value} · ${n.artifact_count} artifact${
              n.artifact_count === 1 ? "" : "s"
            }`
          }
          nodeColor={(n) => nodeColor(n.kind)}
          nodeCanvasObject={(node, ctx, globalScale) => {
            const color = nodeColor(node.kind);
            const x = node.x ?? 0;
            const y = node.y ?? 0;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(x, y, 6, 0, 2 * Math.PI);
            ctx.fill();
            const fontSize = 12 / globalScale;
            ctx.font = `${fontSize}px sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillStyle = "#52525b";
            ctx.fillText(node.canonical_value, x, y + 9);
          }}
          linkLabel={(l) => `${l.relation_type} (${l.confidence.toFixed(2)})`}
          linkColor={() => "#a1a1aa"}
          onNodeClick={(node) => selectNode(node.id, node.canonical_value)}
          onBackgroundClick={() => {
            setSelectedId(null);
            setDrilldown([]);
          }}
        />
      </div>

      <aside className="w-80 shrink-0 rounded-xl border border-zinc-200 p-4 text-sm dark:border-zinc-800">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Identity drill-down
          </h2>
          <button
            onClick={loadGraph}
            className="rounded-md border border-zinc-300 px-2 py-1 text-xs dark:border-zinc-700"
          >
            Refresh
          </button>
        </div>
        {selectedId === null ? (
          <p className="text-zinc-500">
            Click a node to list every artifact mentioning that identity.
          </p>
        ) : drilldownLoading ? (
          <p className="text-zinc-500">Loading artifacts…</p>
        ) : (
          <>
            <p className="mb-2 font-medium">{selectedLabel}</p>
            {drilldown.length === 0 ? (
              <p className="text-zinc-500">No artifacts found.</p>
            ) : (
              <ul className="space-y-2">
                {drilldown.map((a) => (
                  <li
                    key={a.id}
                    className="rounded-lg border border-zinc-200 p-2 dark:border-zinc-800"
                  >
                    <a
                      href={`/artifacts/${a.id}`}
                      className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                    >
                      #{a.id} {a.filename}
                    </a>
                    <div className="text-xs text-zinc-500">{a.source_type}</div>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-800">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Legend
          </p>
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(KIND_COLORS).map(([kind, color]) => (
              <span key={kind} className="inline-flex items-center gap-1">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: color }}
                />
                {kind}
              </span>
            ))}
          </div>
          <p className="mt-2 text-xs text-zinc-500">
            {nodes.length} identities · {edges.length} relations
          </p>
        </div>
      </aside>
    </div>
  );
}
