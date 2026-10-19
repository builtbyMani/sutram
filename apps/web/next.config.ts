import type { NextConfig } from "next";

// Server-only env var (never NEXT_PUBLIC_): compose sets API_URL=http://api:8000,
// local dev falls back to http://localhost:8000. Read at server start.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Disabled deliberately: Cache Components is a stale-data trap for a live
  // demo app where the artifact list must reflect uploads immediately.
  cacheComponents: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      {
        // Same-origin proxy: the browser only ever talks to Next.js; the
        // Next.js server forwards /api/* to FastAPI. Eliminates CORS as a
        // demo-day failure mode (STACK.md section 2).
        // NOTE: :path* captures only the part AFTER /api/, so the /api
        // prefix must be re-added in the destination.
        source: "/api/:path*",
        destination: `${API_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
