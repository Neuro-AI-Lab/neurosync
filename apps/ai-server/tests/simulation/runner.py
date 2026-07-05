"""Simulation Runner — Patient LLM ↔ Clinical Pipeline 턴 반복 + 검증.

독립성 원칙: Clinical agent는 Patient LLM의 존재를 모른다.
Runner가 둘 사이를 중계하며 모든 턴을 기록한다.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agents.clinical_slot import ClinicalSlotAgent
from src.agents.safety_classifier import SafetyClassifierAgent
from src.dependencies import get_model_router, get_prompt_loader
from src.schemas.clinical_slot import ClinicalSlotInput, ClinicalSlotOutput
from src.schemas.dialogue import DialogueOutput
from src.schemas.safety import SafetyInput, SafetyOutput
from tests.simulation.patient_llm import PatientLLM

ESSENTIAL_SLOTS = ["chief_complaint", "duration", "functional_impairment", "onset", "risk_factors"]

logger = logging.getLogger(__name__)


def _extract_natural_response(text: str) -> str:
    """Extract natural language from a possibly JSON-wrapped response.

    Dialogue LLM sometimes returns raw JSON like:
      {"assistant_response": "실제 응답 텍스트", "slot_updates": {...}, ...}
    This function extracts the assistant_response field if the text looks like JSON,
    otherwise returns it as-is.
    """
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict) and "assistant_response" in data:
                return data["assistant_response"]
        except json.JSONDecodeError:
            pass
    return text


@dataclass
class TurnRecord:
    """Single turn in the simulation."""

    turn: int
    patient_utterance: str
    safety_result: dict[str, Any]
    ctrs_level: int
    risk_level: str
    crisis_activated: bool
    assistant_response: str
    slot_updates: dict[str, str]
    latency_ms: float
    timestamp: str = ""


@dataclass
class SimulationResult:
    """Complete simulation result."""

    persona_id: str
    persona_name: str
    expected_ctrs: int
    total_turns: int
    turns: list[TurnRecord] = field(default_factory=list)
    crisis_triggered: bool = False
    crisis_turn: int | None = None
    final_slots: dict[str, str] = field(default_factory=dict)
    final_risk_level: str = "none"
    final_ctrs_level: int = 5
    total_latency_ms: float = 0.0
    started_at: str = ""
    ended_at: str = ""
    clinical_slot_result: dict[str, Any] | None = None
    clinical_slot_coverage: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def slot_coverage(self) -> float:
        """Fraction of slots filled (out of 13 total)."""
        total_slots = 13
        filled = sum(1 for v in self.final_slots.values() if v)
        return filled / total_slots

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "persona_name": self.persona_name,
            "expected_ctrs": self.expected_ctrs,
            "total_turns": self.total_turns,
            "crisis_triggered": self.crisis_triggered,
            "crisis_turn": self.crisis_turn,
            "final_slots": self.final_slots,
            "slot_coverage": round(self.slot_coverage, 2),
            "final_risk_level": self.final_risk_level,
            "final_ctrs_level": self.final_ctrs_level,
            "total_latency_ms": round(self.total_latency_ms, 1),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "clinical_slot_result": self.clinical_slot_result,
            "clinical_slot_coverage": self.clinical_slot_coverage,
            "errors": self.errors,
            "turns": [
                {
                    "turn": t.turn,
                    "patient": t.patient_utterance[:200],
                    "assistant": t.assistant_response[:200],
                    "ctrs": t.ctrs_level,
                    "risk": t.risk_level,
                    "crisis": t.crisis_activated,
                    "slots": t.slot_updates,
                    "latency_ms": round(t.latency_ms, 1),
                }
                for t in self.turns
            ],
        }


async def _call_clinical_pipeline(
    user_message: str,
    conversation_history: list[dict[str, str]],
    filled_slots: dict[str, str],
    session_id: str,
) -> tuple[SafetyOutput, DialogueOutput | None]:
    """Call the real clinical pipeline (Safety + Dialogue).

    Returns (safety_result, dialogue_result).
    dialogue_result is None if crisis was activated.
    """

    model_router = get_model_router()
    prompt_loader = get_prompt_loader()
    safety_agent = SafetyClassifierAgent(
        model_router=model_router, prompt_loader=prompt_loader
    )

    # Run safety classification
    safety_input = SafetyInput(
        session_id=session_id,
        user_message=user_message,
        conversation_history=conversation_history,
    )
    safety_result = await safety_agent.run(safety_input)

    # Check crisis
    if safety_result.crisis_protocol_activated:
        return safety_result, None

    # Run dialogue (reuse the chat route logic inline)
    import json as _json

    from src.adapters.base import ChatMessage, LLMAdapter
    from src.schemas.dialogue import DialogueLLMResponse

    try:
        system_prompt = prompt_loader.load_system_prompt("dialogue", "v1")
    except FileNotFoundError:
        system_prompt = (
            "당신은 정신건강 사전 문진 AI입니다. 환자의 이야기를 경청하고 따뜻하게 응답합니다. "
            "JSON으로 응답: {assistant_response, slot_updates, risk_level, "
            "requires_human_review, reason_summary}"
        )

    # Build slot context — show filled AND missing to guide questions
    slot_ctx = ""
    filled_list = [k for k, v in filled_slots.items() if v]
    all_essential = [
        "chief_complaint",
        "onset",
        "duration",
        "functional_impairment",
        "risk_factors",
    ]
    missing_essential = [s for s in all_essential if s not in filled_list]

    parts = []
    if filled_list:
        parts.append(f"이미 수집된 슬롯: {', '.join(filled_list)}")
    if missing_essential:
        parts.append(
            f"아직 미수집된 필수 슬롯: {', '.join(missing_essential)}. "
            "이 중 하나를 자연스럽게 물어보세요."
        )
    if parts:
        slot_ctx = "\n\n[" + " | ".join(parts) + "]"

    messages = [ChatMessage(role="system", content=system_prompt + slot_ctx)]
    for turn in conversation_history[-8:]:
        messages.append(ChatMessage(role=turn.get("role", "user"), content=turn["content"]))
    messages.append(ChatMessage(role="user", content=user_message))

    selection = model_router.select_model("dialogue", require_json=True)
    adapter = model_router.get_adapter(selection.adapter_name)
    assert isinstance(adapter, LLMAdapter)

    resp_format = (
        {"type": "json_object"}
        if (selection.supports_json_schema or selection.supports_json_object)
        else None
    )

    resp = await adapter.chat_timed(
        messages,
        model=selection.model_id,
        temperature=0.4,
        max_tokens=1024,
        response_format=resp_format,
    )

    try:
        data = _json.loads(resp.content)
        llm_resp = DialogueLLMResponse.model_validate(data)
    except Exception:
        llm_resp = DialogueLLMResponse(
            assistant_response=resp.content[:300],
            reason_summary="JSON parse fallback",
        )

    merged_slots = dict(filled_slots)
    merged_slots.update(llm_resp.slot_updates)

    dialogue_output = DialogueOutput(
        model_used=resp.model,
        prompt_version="v1",
        latency_ms=resp.latency_ms,
        reason_summary=llm_resp.reason_summary,
        assistant_response=llm_resp.assistant_response,
        slot_updates=llm_resp.slot_updates,
        risk_level=llm_resp.risk_level,
        requires_human_review=llm_resp.requires_human_review,
        all_slots=merged_slots,
    )

    return safety_result, dialogue_output


async def run_simulation(
    patient: PatientLLM,
    max_turns: int = 12,
    session_id: str = "sim_001",
) -> SimulationResult:
    """Run a full Patient LLM ↔ Clinical Pipeline simulation."""

    result = SimulationResult(
        persona_id=patient.persona.persona_id,
        persona_name=patient.persona.name,
        expected_ctrs=patient.persona.ctrs_expected,
        total_turns=0,
        started_at=datetime.now().isoformat(),
    )

    conversation_history: list[dict[str, str]] = []
    filled_slots: dict[str, str] = {}

    # Patient starts the conversation
    logger.info(
        "=== Simulation Start: %s (%s) ===",
        patient.persona.persona_id,
        patient.persona.name,
    )

    try:
        patient_text = await patient.start_conversation()
    except Exception as e:
        result.errors.append(f"Patient LLM start failed: {e}")
        result.ended_at = datetime.now().isoformat()
        return result

    for turn_num in range(1, max_turns + 1):
        turn_start = time.perf_counter()
        logger.info("--- Turn %d: Patient says: %s", turn_num, patient_text[:100])

        try:
            safety_out, dialogue_out = await _call_clinical_pipeline(
                user_message=patient_text,
                conversation_history=conversation_history,
                filled_slots=filled_slots,
                session_id=session_id,
            )
        except Exception as e:
            result.errors.append(f"Turn {turn_num} clinical pipeline error: {e}")
            break

        turn_latency = (time.perf_counter() - turn_start) * 1000

        # Crisis check
        crisis = safety_out.crisis_protocol_activated
        assistant_response = ""
        slot_updates = {}

        if crisis:
            assistant_response = (
                "지금 많이 힘드시군요. 당신의 이야기를 듣고 있습니다. "
                "자살예방상담전화 109, 응급전화 119로 연락해 주세요."
            )
            result.crisis_triggered = True
            result.crisis_turn = turn_num
            logger.warning(
                "!!! CRISIS ACTIVATED at turn %d (CTRS=%d) !!!",
                turn_num,
                safety_out.ctrs_level,
            )
        elif dialogue_out:
            assistant_response = _extract_natural_response(dialogue_out.assistant_response)
            slot_updates = dialogue_out.slot_updates
            filled_slots.update(slot_updates)

        record = TurnRecord(
            turn=turn_num,
            patient_utterance=patient_text,
            safety_result={
                "risk_level": str(safety_out.risk_level),
                "ctrs_level": safety_out.ctrs_level,
                "categories": safety_out.categories,
                "flagged_phrases": safety_out.flagged_phrases,
                "confidence": safety_out.confidence,
                "rule_triggered": safety_out.rule_triggered,
            },
            ctrs_level=safety_out.ctrs_level,
            risk_level=str(safety_out.risk_level),
            crisis_activated=crisis,
            assistant_response=assistant_response,
            slot_updates=slot_updates,
            latency_ms=turn_latency,
            timestamp=datetime.now().isoformat(),
        )
        result.turns.append(record)
        result.total_turns = turn_num
        result.final_risk_level = str(safety_out.risk_level)
        result.final_ctrs_level = safety_out.ctrs_level
        result.total_latency_ms += turn_latency

        # Update conversation history
        conversation_history.append({"role": "user", "content": patient_text})
        conversation_history.append({"role": "assistant", "content": assistant_response})

        # Stop if crisis
        if crisis:
            logger.info("Simulation stopped — crisis protocol activated")
            break

        # Get next patient response
        try:
            patient_text = await patient.respond(assistant_response)
        except Exception as e:
            result.errors.append(f"Turn {turn_num} patient LLM error: {e}")
            break

    # ── Post-dialogue: ClinicalSlotAgent extraction ────────────────
    if conversation_history and not result.crisis_triggered:
        logger.info("Running ClinicalSlotAgent on full conversation...")
        try:
            slot_agent = ClinicalSlotAgent(
                model_router=get_model_router(),
                prompt_loader=get_prompt_loader(),
            )
            slot_input = ClinicalSlotInput(
                session_id=session_id,
                conversation_history=conversation_history,
                current_slots=filled_slots,
            )
            slot_result: ClinicalSlotOutput = await slot_agent.run(slot_input)
            result.clinical_slot_result = {
                "filled_slots": slot_result.filled_slots,
                "missing_slots": slot_result.missing_slots,
                "essential_filled": slot_result.essential_filled,
                "essential_missing": slot_result.essential_missing,
                "slot_coverage": slot_result.slot_coverage,
                "safety_flag": slot_result.safety_flag,
                "extracted_slots": slot_result.extracted_slots,
            }
            # Update final slots with ClinicalSlot extraction
            result.final_slots = filled_slots  # dialogue-extracted
            result.clinical_slot_coverage = slot_result.slot_coverage
            logger.info(
                "ClinicalSlot: coverage=%.0f%% filled=%d missing=%d safety=%s",
                slot_result.slot_coverage * 100,
                len(slot_result.filled_slots),
                len(slot_result.missing_slots),
                slot_result.safety_flag,
            )
        except Exception as e:
            result.errors.append(f"ClinicalSlot extraction error: {e}")
            logger.error("ClinicalSlot failed: %s", e)

    result.final_slots = filled_slots
    result.ended_at = datetime.now().isoformat()

    logger.info(
        "=== Simulation End: %s | turns=%d | crisis=%s | ctrs=%d | slots=%d ===",
        result.persona_id, result.total_turns, result.crisis_triggered,
        result.final_ctrs_level, len(result.final_slots),
    )

    return result


def save_result(result: SimulationResult, output_dir: Path) -> Path:
    """Save simulation result as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{result.persona_id}_{ts}.json"
    path = output_dir / filename
    path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Result saved: %s", path)
    return path
