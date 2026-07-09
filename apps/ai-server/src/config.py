"""Application settings loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    skt_a_x_api_key: str = Field(default="", description="SKT A.X API key")
    skt_a_x_rest_base_url: str = Field(
        default="https://awf-gw.adot.ai",
        description="SKT A.X REST gateway base URL",
    )
    skt_a_x_ws_base_url: str = Field(
        default="",
        description="SKT A.X WebSocket base URL for streaming STT",
    )
    skt_a_x_llm_model: str = Field(
        default="A.X-K1",
        description="SKT A.X LLM model identifier",
    )
    skt_a_x_stt_streaming_model: str = Field(
        default="",
        description="SKT A.X streaming STT model",
    )
    skt_a_x_stt_batch_model: str = Field(
        default="",
        description="SKT A.X batch STT model",
    )

    # ── Paths ─────────────────────────────────────────────────────────
    model_registry_path: str | None = Field(
        default=None,
        description="Override path for agent_model_registry.yaml",
    )
    prompts_base_dir: str = Field(
        default="docs/ai/prompts",
        description="Base directory for prompt templates (relative to project root)",
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
    hira_hospital_service_url: str = Field(
        default="https://apis.data.go.kr/B551182/hospInfoServicev2",
        description="HIRA 병원정보서비스 base endpoint",
    )
    hira_pharmacy_service_url: str = Field(
        default="https://apis.data.go.kr/B551182/pharmacyInfoService",
        description="HIRA 약국정보서비스 base endpoint",
    )

    # ── Kakao (좌표 보정 · 지도 SDK) ────────────────────────────────────
    # .env에서 KAKAO_REST_KEY_ENCODED / KAKAO_JS_KEY_ENCODED 로 저장한
    # 실제 키 값을 우선 로드. KAKAO_REST_API_KEY / KAKAO_MAP_JAVASCRIPT_KEY
    # 이름 관례 (docs)도 병행 지원.
    kakao_rest_api_key: str = Field(
        default="",
        description="Kakao Local REST API 키 (backend only). address geocoding용",
        validation_alias=AliasChoices(
            "KAKAO_REST_KEY_ENCODED",
            "KAKAO_REST_API_KEY_ACTUAL",
        ),
    )
    kakao_map_javascript_key: str = Field(
        default="",
        description="Kakao Maps JavaScript SDK 키 (Web client에서 사용)",
        validation_alias=AliasChoices(
            "KAKAO_JS_KEY_ENCODED",
            "KAKAO_MAP_JAVASCRIPT_KEY",
        ),
    )
    kakao_local_rest_base_url: str = Field(
        default="https://dapi.kakao.com",
        description="Kakao Local REST API base URL",
    )

    # ── Application ───────────────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Enable debug mode")

    def resolve_registry_path(self) -> Path:
        """Return the resolved path to the model registry YAML."""
        if self.model_registry_path:
            return Path(self.model_registry_path)
        return Path(__file__).parent / "routing" / "agent_model_registry.yaml"

    def resolve_prompts_dir(self) -> Path:
        """Return the resolved prompts base directory."""
        return Path(self.prompts_base_dir)
