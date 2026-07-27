# DGX deployment image for the clinician dashboard (Next.js standalone).
# Build from the monorepo root: docker build -f apps/web/Dockerfile ../.. (or
# via infra/deploy/docker-compose.dgx.yml, which sets context: ../.. already).

FROM node:20-alpine AS base

# Next.js/SWC native binaries need glibc compat on Alpine; curl is used by
# the HEALTHCHECK below (mirrors apps/api and apps/ai-server Dockerfiles).
RUN apk add --no-cache libc6-compat curl

# Pin the exact pnpm version the workspace uses (root package.json
# `packageManager: "pnpm@9.15.0"`) so lockfile resolution is reproducible.
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

WORKDIR /app

# ---------------------------------------------------------------------------
# deps — install only what @neuro-sync/web needs (itself + @neuro-sync/contracts)
# ---------------------------------------------------------------------------
FROM base AS deps

# Monorepo-relative depth preserved inside the image — same discipline as
# apps/api/Dockerfile and apps/ai-server/Dockerfile (PR #91): pnpm workspace
# resolution and the "@neuro-sync/contracts": "workspace:*" dependency are
# both root-relative, so every workspace manifest must land at the same path
# it occupies in the real checkout. Only manifests are copied in this stage
# (no app source), so this layer stays cached across source-only changes.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json .npmrc /app/
COPY apps/web/package.json /app/apps/web/package.json
COPY packages/shared-contracts/typescript/package.json /app/packages/shared-contracts/typescript/package.json
# pnpm-workspace.yaml also lists apps/mobile. pnpm's workspace resolver reads
# every manifest listed there even when installing a filtered subset, so its
# package.json must be present or `pnpm install` errors — its own
# dependencies are never installed (excluded by the --filter below), only
# this file is needed for the resolver to succeed.
COPY apps/mobile/package.json /app/apps/mobile/package.json

# Recursive selector: installs @neuro-sync/web plus its workspace dependency
# graph (@neuro-sync/contracts) only.
RUN pnpm install --filter "@neuro-sync/web..." --frozen-lockfile

# ---------------------------------------------------------------------------
# builder — full source + next build (standalone output)
# ---------------------------------------------------------------------------
FROM base AS builder

COPY --from=deps /app /app
COPY apps/web /app/apps/web
COPY packages/shared-contracts/typescript /app/packages/shared-contracts/typescript

WORKDIR /app/apps/web

ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm run build

# ---------------------------------------------------------------------------
# runner — standalone server only, non-root
# ---------------------------------------------------------------------------
FROM node:20-alpine AS runner

RUN apk add --no-cache curl && \
    addgroup -g 1001 -S app && \
    adduser -S app -u 1001 -G app

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# `output: "standalone"` + `outputFileTracingRoot` pinned at the monorepo
# root (next.config.ts) means the traced server bundle mirrors the on-disk
# depth: server.js lands at apps/web/server.js under the standalone root,
# not directly at /app/server.js.
COPY --from=builder --chown=app:app /app/apps/web/.next/standalone /app
COPY --from=builder --chown=app:app /app/apps/web/.next/static /app/apps/web/.next/static

USER app

EXPOSE 3000

# /login is a public, unauthenticated page (middleware.ts only gates
# /dashboard/**) — safe to hit without a session cookie.
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD curl --fail --silent http://localhost:3000/login || exit 1

CMD ["node", "apps/web/server.js"]
