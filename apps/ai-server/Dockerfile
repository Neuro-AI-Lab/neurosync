FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir uv && \
    useradd --create-home --shell /bin/bash --uid 1001 app

COPY packages/shared-contracts/python /workspace/packages/shared-contracts/python

COPY apps/ai-server/pyproject.toml ./
COPY apps/ai-server/src ./src

# Pinned prompts (docs/ai/deployment_integration_plan.md G1) — safety v2,
# dialogue v4, domain_inference v2, handoff v2/v3, etc. ADR-041 T4: prompts
# now live inside the deploy unit (apps/ai-server/prompts/, moved from
# repo-root docs/ai/prompts/). `PromptLoader` resolves relative to
# `PROMPTS_BASE_DIR` at request time; the ENV below is only the
# IN-CONTAINER default (pydantic-settings env-var precedence over
# `.env`-file values, src/config.py) — a host run's own `.env` value still
# overrides it, unaffected by this image default.
COPY apps/ai-server/prompts /app/prompts
ENV PROMPTS_BASE_DIR=/app/prompts

# Korean font assets for F5 PDF embedding (docs/ai/deployment_integration_plan.md
# G2) — the SAME committed, SHA256-pinned TTF subsets
# `src/services/f5_report.py::_register_korean_fonts` already reads from
# `apps/ai-server/assets/fonts` at import-relative path resolution
# (`Path(__file__).resolve().parents[2] / "assets" / "fonts"` ==
# `/app/assets/fonts` once `src/` lands at `/app/src`); shipping the
# committed build script alongside them (never regenerated at build time —
# regeneration requires this host's own installed Noto CJK KR fonts, not
# guaranteed reproducible inside the image) preserves provenance/audit
# traceability for anyone inspecting the running container.
COPY apps/ai-server/assets/fonts /app/assets/fonts
COPY apps/ai-server/scripts/build_korean_fonts.py /app/scripts/build_korean_fonts.py

RUN uv pip install --system -e . && \
    uv pip install --system -e /workspace/packages/shared-contracts/python && \
    chown -R app:app /app /workspace

USER app

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD curl --fail --silent http://localhost:8001/health || exit 1

# Production default. `--reload` is enabled in infra/deploy/docker-compose.yml for dev only.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
