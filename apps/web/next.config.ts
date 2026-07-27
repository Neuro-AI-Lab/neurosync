import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@neuro-sync/contracts"],
  // Standalone server bundle for container deployment (DGX docker-compose —
  // infra/deploy/docker-compose.dgx.yml). Produces .next/standalone with a
  // minimal node_modules + server.js, avoiding a full node_modules copy into
  // the runtime image.
  output: "standalone",
  // pnpm-workspace.yaml + pnpm-lock.yaml live two levels up from apps/web
  // (monorepo root). Pinning this explicitly avoids Next.js's root-inference
  // warning and keeps the traced output layout (and therefore the Dockerfile
  // COPY paths) deterministic regardless of build environment.
  outputFileTracingRoot: path.join(__dirname, "../.."),
};

export default nextConfig;
