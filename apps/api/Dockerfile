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

COPY apps/api/pyproject.toml ./
COPY apps/api/src ./src
COPY apps/api/tests ./tests

RUN uv pip install --system -e . && \
    uv pip install --system -e /workspace/packages/shared-contracts/python && \
    chown -R app:app /app /workspace

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD curl --fail --silent http://localhost:8000/health || exit 1

# Production default. `--reload` is enabled in infra/deploy/docker-compose.yml for dev only.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
