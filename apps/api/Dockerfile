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

# Monorepo-relative depth preserved inside the image. `apps/api/pyproject.toml`
# pins `[tool.uv.sources] neuro-sync-contracts path =
# "../../packages/shared-contracts/python"` — a monorepo-root-relative path.
# Flattening pyproject.toml straight into WORKDIR /app (1 level under the
# image root) made `../..` normalize past filesystem root; `uv` refused with
# "cannot normalize a relative path beyond the base directory" (live DGX
# build failure). Placing pyproject.toml at /app/apps/api instead (2 levels
# deep, mirroring the repo checkout) makes `../../packages/...` resolve to
# /app/packages/... exactly, matching this COPY layout. Editable installs
# (`-e .` / `-e <contracts path>`) bake this on-disk layout into the install
# itself, so /app/apps/api and /app/packages/... must stay in place at
# runtime, not just at build time.
COPY packages/shared-contracts/python /app/packages/shared-contracts/python

COPY apps/api/pyproject.toml /app/apps/api/pyproject.toml
COPY apps/api/src /app/apps/api/src
COPY apps/api/tests /app/apps/api/tests

WORKDIR /app/apps/api

RUN uv pip install --system -e . && \
    uv pip install --system -e /app/packages/shared-contracts/python && \
    chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD curl --fail --silent http://localhost:8000/health || exit 1

# Production default. `--reload` is enabled in infra/deploy/docker-compose.yml for dev only.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
