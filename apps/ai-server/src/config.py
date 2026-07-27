"""Application settings loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_prompts_base_dir() -> str:
    """ADR-041 T4 addendum: prompts now live inside the deploy unit
    (`apps/ai-server/prompts/`, moved from repo-root `docs/ai/prompts/`).
    Anchored to this file's own location (mirrors `resolve_registry_path`'s
    existing `Path(__file__).parent`-anchored discipline) so the default is
    correct regardless of process CWD (repo root or `apps/ai-server`) —
    unlike the old bare relative-string default, which only resolved
    correctly from one specific CWD. An explicit `PROMPTS_BASE_DIR` env var
    (e.g. the container's `/app/prompts`) still overrides this unchanged,
    with its pre-existing CWD-relative-or-absolute resolution semantics.
    """
    return str(Path(__file__).resolve().parents[1] / "prompts")


class Settings(BaseSettings):
    """Central configuration — every secret/URL comes from env vars, never hardcoded."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Upstage Solar Pro3 ─────────────────────────────────────────────
    upstage_api_key: str = Field(default="", description="Upstage API key")
    upstage_base_url: str = Field(
        default="https://api.upstage.ai/v1",
        description="Upstage OpenAI-compatible base URL",
    )
    upstage_chat_model: str = Field(
        default="solar-pro3",
        description="Default Upstage chat model name",
    )

    # ── LG K-EXAONE (Friendli) ────────────────────────────────────────
    lg_k_exaone_api_key: str = Field(default="", description="Friendli API key for K-EXAONE")
    lg_k_exaone_endpoint_id: str = Field(
        default="",
        description="Friendli dedicated endpoint ID (used as model param)",
    )
    lg_k_exaone_base_url: str = Field(
        default="https://api.friendli.ai/dedicated/v1",
        description="Friendli dedicated base URL",
    )

    # ── SKT A.X ───────────────────────────────────────────────────────
    # Accept both SKT_A_X_API_KEY (docs canonical) and SKT_A_X_K1 (local .env legacy)
    # for the same field to keep back-compat.
    skt_a_x_api_key: str = Field(
        default="",
        description="SKT A.X API key (LLM + STT — single key for both)",
        validation_alias=AliasChoices("SKT_A_X_API_KEY", "SKT_A_X_K1"),
    )
    skt_a_x_rest_base_url: str = Field(
        default="https://awf-gw.adot.ai",
        description="SKT A.X REST gateway base URL",
        validation_alias=AliasChoices("SKT_A_X_REST_BASE_URL", "SKT_A_X_BASE_URL"),
    )
    skt_a_x_ws_base_url: str = Field(
        default="wss://awf-gw.adot.ai",
        description="SKT A.X WebSocket base URL for streaming STT",
    )
    skt_a_x_llm_model: str = Field(
        default="A.X-K1",
        description="SKT A.X LLM model identifier",
    )
    skt_a_x_stt_streaming_model: str = Field(
        default="A.X_STT_note_streaming",
        description="SKT A.X streaming STT model",
    )
    skt_a_x_stt_batch_model: str = Field(
        default="A.X_STT_note_batch",
        description="SKT A.X batch STT model",
    )

    # ── Paths ─────────────────────────────────────────────────────────
    model_registry_path: str | None = Field(
        default=None,
        description="Override path for agent_model_registry.yaml",
    )
    prompts_base_dir: str = Field(
        default_factory=_default_prompts_base_dir,
        description=(
            "Base directory for prompt templates. Default is an absolute "
            "path anchored to this file (apps/ai-server/prompts/), CWD-"
            "independent. Override via PROMPTS_BASE_DIR (e.g. Docker's "
            "/app/prompts)."
        ),
    )

    # ── Database (RAG 이전으로 ai-server가 직접 접속) ───────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://neurosync:dev@localhost:5432/neurosync",
        description="Postgres DSN (async: +asyncpg). RAG 검색·시뮬 적재에 사용",
    )
    encryption_key: str = Field(
        default="",
        description="AES-256-GCM 키 (base64-urlsafe 32B). **api와 동일 값**이어야 앱이 복호화 가능",
    )

    # ── HIRA (건강보험심사평가원 병원/약국) ────────────────────────────
    # 공공데이터포털 Open API. Backend only — Service Key는 client에 노출 금지.
    hira_service_key: str = Field(
        default="",
        description="HIRA Open API 일반 인증키 (공공데이터포털 발급)",
    )
    hira_drug_efficacy_service_url: str = Field(
        default="https://apis.data.go.kr/B551182/msupCmpnMeftInfoService",
        description=(
            "HIRA 의약품성분약효정보조회서비스 — 일반명코드(gnlNmCd)로 약효분류번호"
            "(meftDivNo)·분류명(divNm) 조회. getMajorCmpnNmCdList endpoint. "
            "정신과 약물 판정의 authoritative 소스 (하드코딩 카탈로그 대체)."
        ),
    )

    # ── Application ───────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Enable debug mode")

    # ── LLM adapters (REV-001 Issue 5, critic, `discussion.md`) ─────────
    # `openai.AsyncOpenAI`'s SDK default is a 10-minute client timeout — a
    # hung call on the safety-classification path can stall a live session
    # for up to 10 minutes before `routing.fallback_policy`'s circuit
    # breaker/fallback ever engages (a timeout raises `openai.APITimeoutError`,
    # already classified `is_transient` there — this setting only shortens
    # WHEN that classification fires, it changes no fallback/circuit-breaker
    # logic). Applied identically to all three OpenAI-SDK-shaped adapters
    # (`ak_llm.py`/`solar_pro3.py`/`k_exaone.py`) via one shared setting so
    # they can never silently drift to different values.
    llm_client_timeout_s: float = Field(
        default=60.0,
        description=(
            "Client-side request timeout (seconds) for all three OpenAI-SDK "
            "LLM adapters (SKT A.X, Upstage Solar Pro3, LG K-EXAONE). "
            "Overrides the openai SDK's 10-minute default — a hung call on "
            "the safety-critical path must not stall a live session for "
            "that long before the existing fallback/circuit-breaker path "
            "(routing.fallback_policy) engages."
        ),
    )

    def resolve_registry_path(self) -> Path:
        """Return the resolved path to the model registry YAML."""
        if self.model_registry_path:
            return Path(self.model_registry_path)
        return Path(__file__).parent / "routing" / "agent_model_registry.yaml"

    def resolve_prompts_dir(self) -> Path:
        """Return the resolved prompts base directory."""
        return Path(self.prompts_base_dir)
