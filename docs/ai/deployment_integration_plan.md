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

## 3. Deployment runbook (Docker) — DGX topology confirmed 2026-07-20

Confirmed topology (user, 2026-07-20): one DGX Spark host at `223.194.33.26` runs the DB
server and the AI server as separate containers with distinct external ports.

| Service | External | Internal | State |
|---|---|---|---|
| DB server (postgres, admin-managed container) | `223.194.33.26:28881` | 5432 | running |
| ai-server (this deployment) | `223.194.33.26:24855` | 8001 | to deploy |

The dev workstation (`192.168.68.62`) has no docker and needs none — deployment executes on
the DGX. Dedicated standalone compose file: `infra/deploy/docker-compose.dgx.yml`
(ai-server only; defines no postgres/api, distinct project+container name, production CMD,
no source mounts, `PROMPTS_BASE_DIR` pinned to the baked `/app/prompts` so the dev `.env`'s
workstation-relative value cannot leak in via env_file). Never combine it with the dev
`docker-compose.yml`.

On the DGX, as the account that runs the DB container:

```bash
git clone https://github.com/Neuro-AI-Lab/neurosync.git && cd neurosync   # or git pull
# place apps/ai-server/.env (operator copies from the dev workstation; never committed)
docker compose -f infra/deploy/docker-compose.dgx.yml up -d --build
curl -s localhost:24855/health
```

Verify: `/health` 200 → route smoke (`POST /ai/survey/plan`, `/ai/temporal/analyze`,
`/ai/handoff/report`) → DB preflight. If the container cannot reach the DB through the
host's external IP (hairpin), change the DSN host in `.env` to
`host.docker.internal:28881` (extra_hosts maps it) — env edit only.
Backend base URL: `http://223.194.33.26:24855`.

## 4. Gates
qa (CI-mirror + route contract tests + container build/boot smoke) → clinical-validator quick pass on /ai/survey/plan semantics (safety-net/SI-supplement decisions must match the validated behavior) → critic wording/regression check. Local commits only; publish on user's word.
