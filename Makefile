.PHONY: help bootstrap dev test clean

help:
	@echo "Neuro-Sync — cross-language dev commands"
	@echo ""
	@echo "  make bootstrap   Install all deps (pnpm + uv venvs for Python apps)"
	@echo "  make dev         Start all apps (api, ai-server, web, mobile) in parallel via docker + turbo"
	@echo "  make dev-js      Start JS apps only (turbo)"
	@echo "  make dev-py      Start Python apps locally (uvicorn each)"
	@echo "  make test        Run tests for all apps"
	@echo "  make typecheck   Run typecheck for JS apps"
	@echo "  make lint        Run lint for all apps"
	@echo "  make clean       Remove all build artifacts and venvs"

bootstrap:
	@echo "→ JS workspaces..."
	pnpm install
	@echo "→ apps/api Python venv..."
	cd apps/api && uv sync
	@echo "→ apps/ai-server Python venv..."
	cd apps/ai-server && uv sync
	@echo "→ packages/shared-contracts/python..."
	cd packages/shared-contracts/python && uv sync
	@echo "✓ bootstrap complete"

dev:
	@echo "→ Starting full stack via docker-compose..."
	docker compose -f infra/deploy/docker-compose.yml up -d postgres redis
	@echo "→ Starting api, ai-server, web, mobile (Ctrl+C to stop)..."
	pnpm turbo run dev --parallel

dev-js:
	pnpm turbo run dev --parallel --filter='./apps/web' --filter='./apps/mobile'

dev-py:
	@echo "→ apps/api on :8000, apps/ai-server on :8001"
	cd apps/api && uv run uvicorn src.main:app --reload --port 8000 &
	cd apps/ai-server && uv run uvicorn src.main:app --reload --port 8001

test:
	pnpm turbo run test
	cd apps/api && uv run pytest
	cd apps/ai-server && uv run pytest

typecheck:
	pnpm turbo run typecheck

lint:
	pnpm turbo run lint
	cd apps/api && uv run ruff check src tests
	cd apps/ai-server && uv run ruff check src tests

clean:
	pnpm turbo run clean
	rm -rf node_modules
	find apps -type d -name ".venv" -exec rm -rf {} +
	find apps -type d -name "__pycache__" -exec rm -rf {} +
	find apps -type d -name ".pytest_cache" -exec rm -rf {} +
