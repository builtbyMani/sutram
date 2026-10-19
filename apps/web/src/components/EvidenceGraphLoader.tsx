"use client";

// Client-component wrapper: `next/dynamic` with `ssr: false` is not allowed
// in Server Components on Next 16, so the dynamic boundary lives here.
// The page (a Server Component) imports this loader directly.

import dynamic from "next/dynamic";

const EvidenceGraph = dynamic(() => import("./EvidenceGraph"), {
  ssr: false,
  loading: () => <p className="text-sm text-zinc-500">Loading graph…</p>,
});

export default function EvidenceGraphLoader() {
  return <EvidenceGraph />;
}
