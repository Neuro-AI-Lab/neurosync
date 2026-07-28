FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

# curl(healthcheck) + chromium(F5 editorial handoff PDF, `services/editorial_handoff.py`
# → Chrome --headless --print-to-pdf) + fonts-noto-cjk(Chrome는 시스템 폰트를 쓰므로
# 한글 리포트 렌더에 필수). chromium 없으면 `_find_chrome()`가 None → editorial 렌더가
# 스킵되고 F5 ReportLab 폴백 PDF가 저장된다(= DGX에서 편집형 PDF가 안 나오던 원인).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl chromium fonts-noto-cjk && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir uv && \
    useradd --create-home --shell /bin/bash --uid 1001 app

# Monorepo-relative depth preserved inside the image. `apps/ai-server/
# pyproject.toml` pins `[tool.uv.sources] neuro-sync-contracts path =
# "../../packages/shared-contracts/python"` — a monorepo-root-relative path.
# Flattening pyproject.toml straight into WORKDIR /app (1 level under the
# image root) made `../..` normalize past filesystem root; `uv` refused with
# "cannot normalize a relative path beyond the base directory" (live DGX
# build failure). Placing pyproject.toml at /app/apps/ai-server instead (2
# levels deep, mirroring the repo checkout) makes `../../packages/...`
# resolve to /app/packages/... exactly, matching this COPY layout. Editable
# installs (`-e .` / `-e <contracts path>`) bake this on-disk layout into the
# install itself, so /app/apps/ai-server and /app/packages/... must stay in
# place at runtime, not just at build time.
COPY packages/shared-contracts/python /app/packages/shared-contracts/python

COPY apps/ai-server/pyproject.toml /app/apps/ai-server/pyproject.toml
COPY apps/ai-server/src /app/apps/ai-server/src

# Pinned prompts (docs/ai/deployment_integration_plan.md G1) — safety v2,
# dialogue v4, domain_inference v2, handoff v2/v3, etc. ADR-041 T4: prompts
# now live inside the deploy unit (apps/ai-server/prompts/, moved from
# repo-root docs/ai/prompts/). `PromptLoader` resolves relative to
# `PROMPTS_BASE_DIR` at request time; the ENV below is only the
# IN-CONTAINER default (pydantic-settings env-var precedence over
# `.env`-file values, src/config.py) — a host run's own `.env` value still
# overrides it, unaffected by this image default. Kept at the top-level
# /app/prompts (not nested under /app/apps/ai-server) since PROMPTS_BASE_DIR
# is always an explicit absolute override here — never subject to the
# monorepo-relative-depth fix above.
COPY apps/ai-server/prompts /app/prompts
ENV PROMPTS_BASE_DIR=/app/prompts

# Korean font assets for F5 PDF embedding (docs/ai/deployment_integration_plan.md
# G2) — the SAME committed, SHA256-pinned TTF subsets
# `src/services/f5_report.py::_register_korean_fonts` already reads from
# `apps/ai-server/assets/fonts` at import-relative path resolution
# (`Path(__file__).resolve().parents[2] / "assets" / "fonts"`, code
# unchanged) — with `src/` now landing at `/app/apps/ai-server/src`,
# `parents[2]` resolves to `/app/apps/ai-server`, so the asset COPY target
# below moves alongside it (was `/app/assets/fonts` when src sat directly
# under `/app`). Shipping the committed build script alongside them (never
# regenerated at build time — regeneration requires this host's own
# installed Noto CJK KR fonts, not guaranteed reproducible inside the image)
# preserves provenance/audit traceability for anyone inspecting the running
# container.
COPY apps/ai-server/assets/fonts /app/apps/ai-server/assets/fonts
COPY apps/ai-server/scripts/build_korean_fonts.py /app/apps/ai-server/scripts/build_korean_fonts.py

# F5 editorial handoff 템플릿(HTML/CSS/JS + build_report_json/make_charts 스크립트 +
# 번들 trend_plotter_editorial). `services/editorial_handoff.py::_template_dir()`가
# `_repo_root()/docs/ai/handoff_template`로 해석하며, 컨테이너에선 `_repo_root()`가
# `/app`이므로 여기로 복사한다. 이게 없으면 Chrome이 있어도 편집형 렌더가 실패한다.
COPY docs/ai/handoff_template /app/docs/ai/handoff_template

WORKDIR /app/apps/ai-server

RUN uv pip install --system -e . && \
    uv pip install --system -e /app/packages/shared-contracts/python && \
    chown -R app:app /app

USER app

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD curl --fail --silent http://localhost:8001/health || exit 1

# Production default. `--reload` is enabled in infra/deploy/docker-compose.yml for dev only.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
