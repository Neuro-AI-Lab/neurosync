"""Clinical Slot Extraction agent — extracts structured slots from conversation text.

Reads the conversation history and extracts 13+ clinical slots with evidence
citations. Does NOT generate patient-facing text — extraction only.
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

# 13 essential + supplementary slots
ALL_SLOT_KEYS = [
    "chief_complaint",
    "history_of_present_illness",
    "past_psychiatric_history",
    "current_medications",
    "risk_factors",
    "symptoms.sleep",
    "symptoms.appetite",
    "symptoms.mood",
    "symptoms.concentration",
    "symptoms.energy",
    "symptoms.anxiety",
    "psychosocial_context",
    "substance_use",
]

ESSENTIAL_SLOT_KEYS = [
    "chief_complaint",
    "history_of_present_illness",
    "risk_factors",
    "symptoms.sleep",
    "symptoms.mood",
]


class ClinicalSlotAgent(BaseAgent):
    """Extracts structured clinical slots from conversation via LLM."""

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

        try:
            system_prompt = self._prompt_loader.load_system_prompt("clinical_slot", "v1")
        except FileNotFoundError:
            logger.warning("clinical_slot prompt not found, using minimal fallback")
            system_prompt = (
                "대화에서 임상 정보를 추출하세요. JSON으로 출력하세요. "
                "언급되지 않은 정보는 null. 진단명 사용 금지."
            )

        # Build context about what's already collected
        slot_context = ""
        if inp.current_slots:
            filled = [k for k, v in inp.current_slots.items() if v]
            if filled:
                slot_context = (
                    "\n\n[이미 수집된 슬롯: "
                    f"{', '.join(filled)}. 이미 수집된 슬롯은 건너뛰고 "
                    "미수집 슬롯에 집중하세요.]"
                )

        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_prompt + slot_context),
        ]

        # Add full conversation
        for turn in inp.conversation_history:
            messages.append(
                ChatMessage(role=turn.get("role", "user"), content=turn["content"])
            )

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

        # Parse response
        try:
            data = json.loads(resp.content)
        except json.JSONDecodeError:
            logger.warning("ClinicalSlot JSON parse failed, returning empty")
            data = {}

        # Analyze slot coverage
        extracted = data
        filled = []
        missing = []

        for key in ALL_SLOT_KEYS:
            val = _get_nested(extracted, key)
            if val is not None and val != "" and val != []:
                # Check if it has a "value" sub-field (structured format)
                if isinstance(val, dict) and "value" in val:
                    if val["value"] is not None:
                        filled.append(key)
                    else:
                        missing.append(key)
                else:
                    filled.append(key)
            else:
                missing.append(key)

        essential_filled = [k for k in ESSENTIAL_SLOT_KEYS if k in filled]
        essential_missing = [k for k in ESSENTIAL_SLOT_KEYS if k in missing]
        coverage = len(filled) / len(ALL_SLOT_KEYS) if ALL_SLOT_KEYS else 0.0

        # Check safety flag
        safety_flag = False
        safety_reason = None
        risk_val = _get_nested(extracted, "risk_factors")
        if risk_val:
            if isinstance(risk_val, dict) and risk_val.get("value"):
                safety_flag = True
                safety_reason = "risk_factors populated"
            elif isinstance(risk_val, list) and len(risk_val) > 0:
                safety_flag = True
                safety_reason = "risk_factors populated"

        sf = _get_nested(extracted, "safety_flag")
        if sf is True:
            safety_flag = True
            safety_reason = extracted.get("safety_flag_reason", "safety_flag=true from LLM")

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
            safety_flag=safety_flag,
            safety_flag_reason=safety_reason,
        )


def _get_nested(data: dict, key: str) -> Any:
    """Get a nested value from a dict using dot notation."""
    parts = key.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current
