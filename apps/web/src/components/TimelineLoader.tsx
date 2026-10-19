"use client";

// Client-component wrapper: `next/dynamic` with `ssr: false` is not allowed
// in Server Components on Next 16, so the dynamic boundary lives here.
// The page (a Server Component) imports this loader directly.

import dynamic from "next/dynamic";

const TimelineView = dynamic(() => import("./TimelineView"), {
  ssr: false,
  loading: () => <p className="p-6 text-sm text-gray-500">Loading timeline…</p>,
});

export default function TimelineLoader() {
  return <TimelineView />;
}
