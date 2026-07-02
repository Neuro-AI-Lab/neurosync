"""Clinical Slot Extraction agent — extracts 12 standard slots from conversation.

역할 경계:
  - 대화 텍스트에서 구조화된 임상 슬롯을 추출한다.
  - 환자 대면 응답을 생성하지 않는다.
  - 위험도 판단은 SafetyClassifierAgent의 역할이다.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.adapters.base import ChatMessage, LLMAdapter
from src.agents.base import AgentInput, BaseAgent
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.clinical_slot import ClinicalSlotInput, ClinicalSlotOutput

logger = logging.getLogger(__name__)

# ── 12 Standard Clinical Slots ──────────────────────────────────────

ALL_SLOT_KEYS = [
    "encounter_metadata",            # 01. 진료 기본정보
    "chief_complaint",               # 02. 주호소
    "history_of_present_illness",    # 03. 현병력
    "past_psychiatric_history",      # 04. 정신과 과거력
    "medical_history",               # 05. 신체질환/신경학적 병력
    "personal_social_history",       # 06. 개인사/사회력
    "family_history",                # 07. 가족력
    "substance_use_history",         # 08. 음주·흡연·물질사용
    "mental_status_exam",            # 09. 정신상태검사
    "risk_assessment",               # 10. 위험평가
    "clinical_assessment",           # 11. 평가/진단적 인상
    "treatment_plan",                # 12. 치료계획/치료내용
]

ESSENTIAL_SLOT_KEYS = [
    "chief_complaint",               # 02. 주호소
    "history_of_present_illness",    # 03. 현병력
    "risk_assessment",               # 10. 위험평가
    "mental_status_exam",            # 09. 정신상태검사
    "clinical_assessment",           # 11. 평가/진단적 인상
]


class ClinicalSlotAgent(BaseAgent):
    """Extracts 12 standard clinical slots from conversation via LLM."""

    def __init__(self, model_router: ModelRouter, prompt_loader: PromptLoader) -> None:
        self._router = model_router
        self._prompt_loader = prompt_loader

    @property
    def agent_name(self) -> str:
        return "clinical_slot"

    async def run(self, inp: AgentInput, **kwargs: Any) -> ClinicalSlotOutput:
        start = time.perf_counter()

        if not isinstance(inp, ClinicalSlotInput):
            raise TypeError(f"Expected ClinicalSlotInput, got {type(inp).__name__}")

        # 1. Load system prompt
        try:
            system_prompt = self._prompt_loader.load_system_prompt("clinical_slot", "v1")
        except FileNotFoundError:
            logger.warning("clinical_slot prompt not found, using fallback")
            system_prompt = (
                "대화에서 임상 정보를 추출하세요. 12개 표준 슬롯 key로만 출력. "
                "값은 flat string 또는 null. 진단명 사용 금지. "
                "부정 응답(없다, 아니다)도 유의미한 값으로 기록."
            )

        # 2. Context: already collected slots
        slot_context = ""
        if inp.current_slots:
            filled = [k for k, v in inp.current_slots.items() if v]
            if filled:
                slot_context = (
                    f"\n\n[이미 수집된 슬롯: {', '.join(filled)}. "
                    "값이 변경된 경우에만 갱신하고, 미수집 슬롯에 집중하세요.]"
                )

        # 3. Build messages
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_prompt + slot_context),
        ]
        for turn in inp.conversation_history:
            messages.append(
                ChatMessage(role=turn.get("role", "user"), content=turn["content"])
            )

        # 4. Call LLM
        selection = self._router.select_model(self.agent_name, require_json=True)
        adapter = self._router.get_adapter(selection.adapter_name)
        assert isinstance(adapter, LLMAdapter)

        resp_format = None
        if selection.supports_json_schema or selection.supports_json_object:
            resp_format = {"type": "json_object"}

        try:
            resp = await adapter.chat_timed(
                messages,
                model=selection.model_id,
                temperature=0.1,
                max_tokens=2048,
                response_format=resp_format,
            )
            self._router.record_success(selection.adapter_name)
        except Exception as exc:
            logger.error("ClinicalSlot LLM failed: %s", exc)
            self._router.record_failure(selection.adapter_name, exc)
            latency_ms = (time.perf_counter() - start) * 1000
            return ClinicalSlotOutput(
                model_used="none",
                prompt_version="v1",
                latency_ms=latency_ms,
                reason_summary=f"LLM call failed: {exc}",
                missing_slots=ALL_SLOT_KEYS,
                essential_missing=ESSENTIAL_SLOT_KEYS,
            )

        # 5. Parse response — flat string values only
        try:
            data = json.loads(resp.content)
        except json.JSONDecodeError:
            logger.warning("ClinicalSlot JSON parse failed, returning empty")
            data = {}

        # Normalize: extract flat string values, handle {value: ...} fallback
        extracted: dict[str, Any] = {}
        for key in ALL_SLOT_KEYS:
            val = data.get(key)
            if val is None:
                continue
            if isinstance(val, str):
                stripped = val.strip()
                if stripped:
                    extracted[key] = stripped
                else:
                    logger.debug("Slot '%s' has empty string value — skipped", key)
            elif isinstance(val, dict) and "value" in val:
                inner = val["value"]
                if isinstance(inner, str) and inner.strip():
                    extracted[key] = inner.strip()
                else:
                    logger.debug("Slot '%s' has empty nested value — skipped", key)
            elif isinstance(val, bool):
                # safety_flag 등 bool 값은 무시 (Safety Agent 역할)
                continue
            else:
                logger.debug("Slot '%s' unexpected type %s — skipped", key, type(val).__name__)

        # Also capture any non-standard keys that map to standard ones
        _KEY_ALIASES = {
            "substance_use": "substance_use_history",
            "psychosocial_context": "personal_social_history",
            "risk_factors": "risk_assessment",
            "protective_factors": "risk_assessment",
        }
        for alias, standard_key in _KEY_ALIASES.items():
            if alias in data and standard_key not in extracted:
                val = data[alias]
                if isinstance(val, str) and val.strip():
                    extracted[standard_key] = val.strip()

        # 6. Compute coverage
        filled = [k for k in ALL_SLOT_KEYS if k in extracted]
        missing = [k for k in ALL_SLOT_KEYS if k not in extracted]
        essential_filled = [k for k in ESSENTIAL_SLOT_KEYS if k in filled]
        essential_missing = [k for k in ESSENTIAL_SLOT_KEYS if k not in filled]
        coverage = len(filled) / len(ALL_SLOT_KEYS) if ALL_SLOT_KEYS else 0.0

        latency_ms = (time.perf_counter() - start) * 1000

        return ClinicalSlotOutput(
            model_used=resp.model,
            prompt_version="v1",
            latency_ms=latency_ms,
            reason_summary=f"Extracted {len(filled)}/{len(ALL_SLOT_KEYS)} slots",
            extracted_slots=extracted,
            filled_slots=filled,
            missing_slots=missing,
            essential_filled=essential_filled,
            essential_missing=essential_missing,
            slot_coverage=round(coverage, 2),
        )
