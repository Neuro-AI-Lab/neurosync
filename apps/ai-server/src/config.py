"""Application settings loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
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
