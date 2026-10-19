// Phase 3: evidence graph page. The canvas component touches `window` at
// import time, so it loads client-only: this Server Component renders
// EvidenceGraphLoader, which holds the `ssr: false` dynamic boundary
// (Next 16 forbids `ssr: false` in Server Components).

import EvidenceGraphLoader from "@/components/EvidenceGraphLoader";

export default function GraphPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">Evidence graph</h1>
        <p className="text-sm text-zinc-500">
          Cross-source entity resolution — nodes are resolved identities,
          edges are relations. Click a node to drill down into its artifacts.
        </p>
      </header>
      <EvidenceGraphLoader />
    </main>
  );
}
