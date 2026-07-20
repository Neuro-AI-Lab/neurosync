# Deployment & backend-integration plan — clinical multiagent F1-F5 on the AI server

> Status: APPROVED (user, 2026-07-20). Scope: make apps/ai-server deployment-ready (Docker) and
> backend-integrable (stateless compute API). Owner: conductor-orchestrated lightweight fleet.

## 1. Operational inventory (what ships)

| Asset | Path | Runtime image? |
|---|---|---|
| Production source (agents/schemas/routes/services/scoring/rag/adapters/engines F1-F5) | `apps/ai-server/src/` | yes |
| Pinned prompts (safety v2, dialogue v4, domain_inference v2, handoff v2/v3) | `docs/ai/prompts/` | **yes — Dockerfile gap G1** |
| Korean font assets (F5 PDF embedding) | `apps/ai-server/scripts/` + assets | **yes — gap G2** |
| Runtime data cache | `src/data/hira_efficacy_cache.json` | yes |
| Shared contracts | `packages/shared-contracts/python` | yes (already in Dockerfile) |
| `.env` (all keys; physically transferred, never committed) | operator-managed | env, not image |
| RAG corpus (case_card 1248 / qa 1789 / symptom 40 / disease 27 / pgvector 4096) | DB server (28881 ext / 5432 in-compose) | DB, not image |
| tests + scenario packs + personas | repo | CI only |
| `experiments/`, `_archive/` | local | never |

## 2. Refactoring set (this cycle)

| ID | Change | Design |
|---|---|---|
| R1 | `POST /ai/temporal/analyze` + `POST /ai/handoff/report` | Thin wrappers over the pure F4/F5 engines. Request carries the session series (stateless); response = temporal.json / report (md + PDF/FHIR as base64 or file refs). |
| R2 | Stateless compute principle | Backend owns patient/session identity + persistence; ai-server never stores session state. Resolves REV-001 "no server-side session persistence" structurally. |
| R3 | `POST /ai/survey/plan` | Exposes `resolve_effective_scale` + safety-net + SI-supplement decision (F2 output + crisis state in → administer-plan out). The APP administers items to the real patient. |
| R4 | Contracts promotion | Ledger-entry / temporal-request / report-request+response models → `packages/shared-contracts` so apps/api shares types. |
| G1-G3 | Dockerfile: COPY prompts + fonts, HEALTHCHECK; compose env passthrough for HIRA/KAKAO/LLM_TIMEOUT keys | |

Deferred (P2 backlog): idempotency guard, request_id propagation (REV-001 majors), narrative activation (gated), FHIR $validate external option.

## 3. Deployment runbook (Docker)

1. Local: `docker compose -f infra/deploy/docker-compose.yml build ai-server` → container smoke (boot, /health, route smoke).
2. Transfer: `docker save` → `ssh DGX docker load` (or private registry).
3. AI server: place `.env` (operator), `docker compose up -d`; in-compose DB via `postgres:5432`, external DB via 28881 if split later — env-DSN only.
4. Verify: `/health` 200, DB preflight, prompt SHA pins, one F1-turn + one F5-report smoke.

## 4. Gates
qa (CI-mirror + route contract tests + container build/boot smoke) → clinical-validator quick pass on /ai/survey/plan semantics (safety-net/SI-supplement decisions must match the validated behavior) → critic wording/regression check. Local commits only; publish on user's word.
