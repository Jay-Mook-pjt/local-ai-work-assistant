import type { NextConfig } from "next";

import { BACKEND_URL } from "./src/lib/backend";

// The backend binds to localhost only. The browser (possibly on another LAN
// device) talks to this Next.js server, which forwards /api/* to the backend.
// Large audio uploads bypass this rewrite: see src/app/api/meetings/[id]/audio/route.ts.

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    // `fallback` = applied only after every app route (incl. dynamic Route Handlers
    // such as the streaming audio upload) failed to match.
    return { beforeFiles: [], afterFiles: [], fallback: [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }] };
  },
};

export default nextConfig;
