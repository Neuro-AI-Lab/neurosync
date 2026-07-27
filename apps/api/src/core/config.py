"""Application settings (pydantic-settings).

All secrets MUST come from environment variables. `.env.example` documents
the contract. Validators below ensure that production environments cannot
silently fall back to dev defaults (C-1, M-4).
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Dev fallback markers — keys starting with these strings are rejected in
# non-development environments.
DEV_KEY_MARKERS = ("dev-only-", "test-only-", "change-me-", "ZGV2LW9ubHkt")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "staging", "production"] = Field(
        default="development",
        description="Activate prod-grade validators when set to staging/production.",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://neurosync:dev@localhost:5432/neurosync",
        description="SQLAlchemy async URL. compose default differs (postgres host).",
    )

    # JWT — PRD §5.1 register response: access 15min, refresh 7d.
    # In dev these have safe-looking defaults so unit tests work without env;
    # the validator below forbids them being used outside `app_env=development`.
    jwt_secret_key: SecretStr = Field(
        default=SecretStr("dev-only-jwt-secret-change-me-in-real-env-min-32-bytes"),
        description="HMAC secret. MUST be a fresh secret in non-dev envs.",
    )
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = Field(default="HS256")
    jwt_issuer: str = Field(default="neuro-sync", description="JWT iss claim")
    jwt_audience: str = Field(default="neuro-sync-api", description="JWT aud claim")
    access_token_expire_minutes: int = Field(default=15)
    refresh_token_expire_days: int = Field(default=7)

    # Column encryption — AES-256-GCM. 32-byte key, base64-urlsafe encoded.
    encryption_key: SecretStr = Field(
        default=SecretStr("ZGV2LTMyLWJ5dGVzLW9ubHktRE8tTk9ULVVTRS1GT1I="),
        description="base64-urlsafe-encoded 32-byte AES-256 key. KMS rotation = Phase 2.",
    )

    # Password policy — PRD §4.5.2: min 12, Argon2id memory_cost≥64MB, iterations≥3.
    password_min_length: int = Field(default=12)
    password_max_length: int = Field(default=256, description="DoS guard for hash time")
    argon2_memory_cost_kib: int = Field(default=65536)  # 64 MiB
    argon2_time_cost: int = Field(default=3)
    argon2_parallelism: int = Field(default=4)

    # Age policy — FR-027 (Phase 2): under-14 guardian consent enforced.
    minor_age_cutoff: int = Field(default=14)

    # G3 — patient dashboard visibility default org assignment (docs/ai/
    # patient_org_visibility_decision.md 권고 ②). `PatientProfile.
    # target_hospital_id`'s only production writer is `auth.register`; the
    # mobile app currently never sends `targetHospitalId`, so every real
    # signup lands NULL and is excluded from every clinician org-scope
    # filter (services/clinician.py). This setting supplies a fallback org
    # for registrations that omit the field. A request-supplied
    # `targetHospitalId` always takes precedence. `None` (default)
    # preserves the exact prior behavior (NULL) — no behavior change until
    # an operator sets it. Org-scope security itself is unchanged: this is
    # purely a default *value* for the same field, not a new access path.
    default_target_hospital_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("DEFAULT_TARGET_HOSPITAL_ID"),
        description=(
            "Fallback PatientProfile.target_hospital_id for registrations "
            "that omit targetHospitalId. Unset by default (NULL, prior "
            "behavior). Malformed UUID strings fail Settings() construction "
            "at startup (pydantic type validation) rather than silently "
            "falling back."
        ),
    )

    # CORS — DEV permissive. Validator below forbids wildcard outside dev.
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    # WebSocket Origin whitelist (PRD C-7). Use ["*"] in dev only.
    cors_ws_origins: list[str] = Field(default_factory=lambda: ["*"])

    # Idempotency LRU cap (per WebSocket connection). Bounded to prevent OOM.
    ws_idempotency_cache_size: int = Field(default=200)
    ws_auth_handshake_seconds: float = Field(default=5.0)

    # AI server (apps/ai-server) location
    ai_server_url: str = Field(default="http://localhost:8001")
    # Handoff generation budget — PRD §4.1 p95 < 30s, allow margin.
    # BUG-068 (2026-07-23, live): the evidence-verifier's own worst-case
    # 3-attempt regenerate loop (ai-server `routes/handoff.py`,
    # `_MAX_REGENERATE_ATTEMPTS = 2`) was observed at 48.1s live, exceeding
    # the prior 45.0s client budget so apps/api gave up right as ai-server
    # was about to return a (degraded but content-bearing) 200. This call is
    # driven by `generate_report_task`, an async background task polled via
    # `/report/status` — no interactive user is blocked waiting on this
    # client call — so a generous margin over the observed worst case costs
    # nothing but a slightly later status flip. 90s ~= 1.9x the 48.1s
    # observed worst case.
    ai_handoff_timeout_seconds: float = Field(default=90.0)
    # Chat reply budget — first token < 800ms for an ORDINARY turn; the
    # budget itself must cover the rare turn where it does not stay
    # ordinary. BUG-081 (2026-07-25, live): when a turn crosses the
    # slot-coverage/risk-grounded threshold, ai-server's orchestrator runs
    # its ENTIRE post-dialogue pipeline (slot_extraction + handoff_
    # generation + the evidence-verifier's up-to-3-attempt regenerate loop
    # — the SAME chain BUG-068 measured at 48.1s worst case for the
    # regenerate loop alone) synchronously, inside this ONE
    # `/ai/chat/respond` call — confirmed by source read
    # (`OrchestratorAgent._execute_pipeline` awaits
    # `_run_post_dialogue_pipeline` directly; there is no background-task
    # split on the ai-server side for this pipeline, unlike apps/api's own
    # `services/chat.py::_extract_slots_bg`, which IS backgrounded). A live
    # instance ran ~30s and was still in progress when the prior 10.0s
    # budget gave up; the turn (including a genuine, already-computed SI
    # grounding) was silently dropped. 90.0s mirrors `ai_handoff_timeout_
    # seconds`'s margin (~1.9x the 48.1s BUG-068 worst case) since this is
    # structurally the same chain plus one extra LLM call (slot
    # extraction) — this only affects the tail latency of the rare
    # threshold-crossing turn; ordinary turns return long before this
    # budget is ever approached. Splitting the post-dialogue pipeline out
    # of the synchronous request/response cycle (background task + a
    # distinct WS frame) remains the preferred longer-term fix (see
    # BUG-081's fix direction) — out of scope for this timeout-alignment
    # pass.
    ai_chat_timeout_seconds: float = Field(default=90.0)
    # STT budget — PRD §4.1 SLA < 2,000ms, allow margin for the vendor chain.
    ai_stt_timeout_seconds: float = Field(default=8.0)
    # v3 FR-039 — 도메인 추정. BUG-091 (2026-07-26, live-verified): 4.5s는
    # `/ai/domain/infer`(solar-pro3, mode=rag, 20 chunks 근거) 실제 latency
    # (2/2 실세션 20.2s~30.6s, 둘 다 예산 초과로 PHQ4 오폴백 — 한 세션은
    # 이미 정답 domain=depression을 냈으나 무시됨)의 1/5도 못 미친다.
    # BUG-068(handoff 45→90s)/BUG-081(chat 10→90s)과 같은 margin-over-
    # observed-p95 원칙(관측 worst case의 ~2배)으로 60.0s — 관측
    # 30.6s worst case 대비 ~2x 여유. NFR v3-3의 구(舊) "5초 상한" 설계는
    # 폐기되었다 — 모바일 쪽은 증상확인 게이지 UX(FR-041 2단계, `chat.tsx`
    # `SURVEY_GAUGE_*`)가 20-60s 대기를 실시간 프리페치 진행률로 흡수하는
    # 구조로 바뀌었으므로 "5초 안에 끝나야 한다"는 전제 자체가 더 이상
    # 유효하지 않다(PRD_frontend_v3.md FR-041/NFR v3-3 문서 현행화는 writer
    # 담당 — 별도 보고).
    ai_domain_timeout_seconds: float = Field(default=60.0)
    # F1 슬롯 추출 — 대화 배경 작업이라 짧게 끊고 실패는 무시한다.
    ai_slots_timeout_seconds: float = Field(default=6.0)
    # OCR — Upstage Document Parse 왕복 + 큰 파일 업로드라 여유 있게.
    ai_ocr_timeout_seconds: float = Field(default=30.0)
    # F4 종단 추론 — 직전/이번 방문 비교(LLM 서사 포함). 리포트 열람 경로라 짧게.
    ai_temporal_timeout_seconds: float = Field(default=8.0)
    # 병원 찾기(FR-049) — HIRA 외부 API를 거치므로 여유 있게.
    ai_nearby_timeout_seconds: float = Field(default=8.0)
    # 카카오맵 JS 키 — 플랫폼이 지도 HTML을 렌더할 때 사용. ai-server .env와 동일한
    # KAKAO_JS_KEY_ENCODED 이름을 받아들인다(운영 편의). 미설정이면 안내 화면으로 저하.
    kakao_map_javascript_key: str = Field(
        default="",
        validation_alias=AliasChoices("KAKAO_JS_KEY_ENCODED", "KAKAO_MAP_JAVASCRIPT_KEY"),
    )
    # ADR-041: 병원 검색 데이터는 플랫폼(apps/api)이 직접 조회한다(ai-server 미경유).
    # Kakao Local REST 키 — 근처 '정신건강의학과' 키워드 검색용(backend only).
    kakao_rest_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "KAKAO_REST_KEY_ENCODED", "KAKAO_REST_API_KEY", "KAKAO_REST_API_KEY_ACTUAL"
        ),
    )
    kakao_local_base_url: str = Field(default="https://dapi.kakao.com")

    # FR-048/028 — 대화 중 첨부(처방전) 업로드 상한. Upstage 50MB보다 보수적.
    ocr_max_bytes: int = Field(default=20 * 1024 * 1024)  # 20MB (FR-028)

    # Safety classify budget — BUG-080 (2026-07-25, live): `safety_classify`
    # previously used the bare `httpx.AsyncClient(timeout=2.0)` constructor
    # default (no dedicated setting, unlike every other AIClient method).
    # ai-server's `/ai/safety/classify` unconditionally makes a real Upstage
    # LLM call (`_llm_classify`, unless the rule-level is already >= high);
    # observed live latency was 952-4373ms across 2 sessions/9 turns. A 2.0s
    # budget caused 6/9 turns (67%) to trip the client-side timeout and
    # fail-open into `classifier_unavailable` full-block on ordinary,
    # non-crisis turns. 6.0s gives >1.4x margin over the observed 4.373s
    # worst case.
    ai_safety_timeout_seconds: float = Field(default=6.0)

    # STT audio (FR-033/036). S3 SSE-KMS is Phase 2; demo writes to local disk.
    audio_storage_dir: str = Field(default=".audio_store")
    audio_max_bytes: int = Field(default=2 * 1024 * 1024)  # 2MB (PRD §5.1)
    audio_max_duration_ms: int = Field(default=30_000)  # 30s
    audio_retention_hours: int = Field(default=48)  # FR-036
    stt_min_confidence: float = Field(default=0.6)  # FR-037 fallback threshold
    # FR-036 in-process purge scheduler interval (seconds); 0 disables (use cron
    # / Celery Beat instead via scripts/purge_audio.py).
    audio_purge_interval_seconds: int = Field(default=3600)

    # ---------- Validators ----------

    @field_validator("argon2_memory_cost_kib")
    @classmethod
    def _argon2_memory_meets_floor(cls, v: int) -> int:
        # PRD §4.5.2: memory_cost ≥ 64 MB (= 65536 KiB).
        # Allow weakening only when APP_ENV=development|test.
        env = os.getenv("APP_ENV", "development").lower()
        if env in ("development", "test"):
            return v
        if v < 65536:
            raise ValueError(
                f"argon2_memory_cost_kib must be >= 65536 in app_env={env} (PRD §4.5.2)"
            )
        return v

    @field_validator("argon2_time_cost")
    @classmethod
    def _argon2_time_meets_floor(cls, v: int) -> int:
        env = os.getenv("APP_ENV", "development").lower()
        if env in ("development", "test"):
            return v
        if v < 3:
            raise ValueError(
                f"argon2_time_cost must be >= 3 in app_env={env} (PRD §4.5.2)"
            )
        return v

    @field_validator("password_min_length")
    @classmethod
    def _password_min_meets_floor(cls, v: int) -> int:
        env = os.getenv("APP_ENV", "development").lower()
        if env in ("development", "test"):
            return v
        if v < 12:
            raise ValueError(
                f"password_min_length must be >= 12 in app_env={env} (PRD §4.5.2)"
            )
        return v

    @model_validator(mode="after")
    def _reject_dev_secrets_in_prod(self) -> Settings:
        if self.app_env in ("development", "test"):
            # In dev, just emit a warning so devs know they're on the fallback.
            if self.jwt_secret_key.get_secret_value().startswith(DEV_KEY_MARKERS):
                logger.warning(
                    "Using dev-only JWT secret. Set JWT_SECRET_KEY for any non-dev run."
                )
            if self.encryption_key.get_secret_value().startswith(DEV_KEY_MARKERS):
                logger.warning(
                    "Using dev-only encryption key. Set ENCRYPTION_KEY for any non-dev run."
                )
            return self

        # Non-dev: reject hard.
        if self.jwt_secret_key.get_secret_value().startswith(DEV_KEY_MARKERS):
            raise ValueError(
                f"JWT_SECRET_KEY is a dev fallback in app_env={self.app_env}. Set a fresh secret."
            )
        if self.encryption_key.get_secret_value().startswith(DEV_KEY_MARKERS):
            raise ValueError(
                f"ENCRYPTION_KEY is a dev fallback in app_env={self.app_env}. Set a fresh key."
            )
        if "*" in self.cors_origins:
            raise ValueError(
                f"cors_origins must not contain '*' in app_env={self.app_env}."
            )
        if "*" in self.cors_ws_origins:
            raise ValueError(
                f"cors_ws_origins must not contain '*' in app_env={self.app_env}."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
