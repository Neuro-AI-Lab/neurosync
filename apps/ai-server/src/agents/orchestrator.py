"""Orchestrator agent — rule-based state machine for the Task 1 pipeline.

Manages the full pre-consultation flow:
  input_received → safety_gate → context_retrieval → dialogue_loop
  → slot_extraction → handoff_generation → evidence_verification → handoff_delivery

CTRS 1-2 at any point → crisis_flow (immediate).
All routing decisions are rule-based — no LLM call in this agent.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.agents.base import BaseAgent
from src.agents.clinical_slot import ALL_SLOT_KEYS, ESSENTIAL_SLOT_KEYS, ClinicalSlotAgent
from src.agents.evidence_verifier import (
    EvidenceVerifierAgent,
    EvidenceVerifierInput,
    VerifierAction,
)
from src.agents.handoff_generator import HandoffGeneratorAgent
from src.agents.safety_classifier import SafetyClassifierAgent
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.clinical_slot import ClinicalSlotInput
from src.schemas.common import CTRSLevel, RiskLevel
from src.schemas.handoff import HandoffInput, ScaleScore, SlotData
from src.schemas.orchestrator import (
    OrchestratorInput,
    OrchestratorTurnResult,
    SafetyStatus,
    SessionStage,
    SessionState,
    StageRecord,
)
from src.schemas.safety import SafetyInput
from src.scoring.survey_scorer import ScoreResult, score_survey

logger = logging.getLogger(__name__)

# Slot coverage threshold to exit dialogue loop
_SLOT_COVERAGE_THRESHOLD = 0.7

# Maximum dialogue turns before forcing slot extraction
_MAX_DIALOGUE_TURNS = 20

# Crisis CTRS levels
_CRISIS_CTRS = {CTRSLevel.EMERGENCY, CTRSLevel.HIGH_RISK}

# Maximum handoff regeneration attempts
_MAX_HANDOFF_REGEN = 2

# Crisis response messages per CTRS level
_CRISIS_MESSAGES: dict[CTRSLevel, str] = {
    CTRSLevel.EMERGENCY: (
        "지금 많이 위급한 상황이시군요. 즉시 119 또는 112에 연락해 주세요. "
        "자살예방상담전화 109도 24시간 운영되고 있습니다. "
        "당신의 안전이 가장 중요합니다."
    ),
    CTRSLevel.HIGH_RISK: (
        "지금 많이 힘드시군요. 당신의 이야기를 듣고 있습니다. "
        "혼자 감당하지 않으셔도 됩니다. "
        "자살예방상담전화 109, 정신건강위기상담전화 1577-0199로 연락해 주세요."
    ),
}

# Essential slot list for coverage tracking
_ESSENTIAL_SLOTS = ESSENTIAL_SLOT_KEYS


class OrchestratorAgent(BaseAgent):
    """Rule-based state machine orchestrating the clinical pipeline."""

    def __init__(
        self,
        model_router: ModelRouter,
        prompt_loader: PromptLoader,
    ) -> None:
        self._model_router = model_router
        self._prompt_loader = prompt_loader
        # Sub-agents are created lazily
        self._safety_agent: SafetyClassifierAgent | None = None
        self._slot_agent: ClinicalSlotAgent | None = None
        self._handoff_agent: HandoffGeneratorAgent | None = None
        self._verifier_agent: EvidenceVerifierAgent | None = None

    @property
    def agent_name(self) -> str:
        return "orchestrator"

    def _get_safety_agent(self) -> SafetyClassifierAgent:
        if self._safety_agent is None:
            self._safety_agent = SafetyClassifierAgent(
                model_router=self._model_router,
                prompt_loader=self._prompt_loader,
            )
        return self._safety_agent

    def _get_slot_agent(self) -> ClinicalSlotAgent:
        if self._slot_agent is None:
            self._slot_agent = ClinicalSlotAgent(
                model_router=self._model_router,
                prompt_loader=self._prompt_loader,
            )
        return self._slot_agent

    def _get_handoff_agent(self) -> HandoffGeneratorAgent:
        if self._handoff_agent is None:
            self._handoff_agent = HandoffGeneratorAgent(
                model_router=self._model_router,
                prompt_loader=self._prompt_loader,
            )
        return self._handoff_agent

    def _get_verifier_agent(self) -> EvidenceVerifierAgent:
        if self._verifier_agent is None:
            self._verifier_agent = EvidenceVerifierAgent()
        return self._verifier_agent

    # ── Public API ──────────────────────────────────────────────────

    async def run(self, inp: Any, **kwargs: Any) -> OrchestratorTurnResult:
        """Execute one orchestrator turn.

        Accepts OrchestratorInput directly (not AgentInput) because the
        orchestrator is the top-level coordinator, not a leaf agent.
        """
        if not isinstance(inp, OrchestratorInput):
            raise TypeError(f"Expected OrchestratorInput, got {type(inp).__name__}")
        return await self.process_turn(inp)

    async def process_turn(self, inp: OrchestratorInput) -> OrchestratorTurnResult:
        """Process a single patient turn through the state machine.

        For the dialogue phase, each call handles one turn (safety → dialogue).
        When slot coverage reaches threshold or max turns, transitions to
        slot_extraction → handoff pipeline automatically.
        """
        # Initialize or restore session state
        state = inp.session_state or SessionState(
            session_id=inp.session_id,
            patient_id=inp.patient_id,
        )

        try:
            result = await self._execute_pipeline(inp, state)
        except Exception as exc:
            logger.error("Orchestrator pipeline error: %s", exc, exc_info=True)
            state.current_stage = SessionStage.error
            state.error_log.append(f"{datetime.now().isoformat()}: {exc}")
            result = OrchestratorTurnResult(
                session_id=state.session_id,
                current_stage=SessionStage.error,
                session_state=state,
                stage_history=state.stage_history,
                error=str(exc),
            )

        return result

    # ── Pipeline execution ──────────────────────────────────────────

    async def _execute_pipeline(
        self, inp: OrchestratorInput, state: SessionState
    ) -> OrchestratorTurnResult:
        """Run stages sequentially until we need to wait for next user input."""

        # Stage 1: Input received
        state.current_stage = SessionStage.input_received
        self._record_stage(state, SessionStage.input_received, "orchestrator", "pass")

        # Stage 2: Safety gate (mandatory, every turn)
        safety_result = await self._run_safety_gate(inp, state)

        if state.current_stage == SessionStage.crisis_flow:
            return self._build_crisis_result(state, safety_result)

        # Stage 3: Context retrieval (first turn only, or when needed)
        if state.turn_count == 0:
            await self._run_context_retrieval(state)

        # Stage 4: Dialogue loop — return response and wait for next input
        state.current_stage = SessionStage.dialogue_loop
        state.turn_count += 1

        # Add user message to conversation history
        if inp.raw_input:
            state.conversation_history.append({
                "role": "user",
                "content": inp.raw_input,
            })

        # Check if we should exit dialogue and move to slot extraction
        if self._should_extract_slots(state):
            return await self._run_post_dialogue_pipeline(state)

        # Still in dialogue — return turn result for caller to generate response
        self._record_stage(state, SessionStage.dialogue_loop, "03_dialogue", "continue")
        self._update_slot_coverage(state)

        return OrchestratorTurnResult(
            session_id=state.session_id,
            current_stage=SessionStage.dialogue_loop,
            safety_status=state.safety_status,
            slot_coverage=state.slot_coverage,
            session_state=state,
            stage_history=state.stage_history,
        )

    # ── Safety gate ─────────────────────────────────────────────────

    async def _run_safety_gate(
        self, inp: OrchestratorInput, state: SessionState
    ) -> Any:
        """Run SafetyClassifier on the current input. Returns SafetyOutput."""
        state.current_stage = SessionStage.safety_gate

        safety_agent = self._get_safety_agent()
        safety_input = SafetyInput(
            session_id=state.session_id,
            user_message=inp.raw_input,
            conversation_history=state.conversation_history,
        )

        try:
            result = await safety_agent.run(safety_input)
        except Exception as exc:
            # Safety failure → assume CTRS 2 (safe-side default)
            logger.error("Safety gate failed: %s — assuming CTRS 2", exc)
            state.safety_status = SafetyStatus(
                ctrs_level=CTRSLevel.HIGH_RISK,
                risk_level=RiskLevel.high,
                crisis_triggered=True,
                last_checked_at=datetime.now(),
            )
            state.current_stage = SessionStage.crisis_flow
            state.error_log.append(f"Safety gate timeout/failure: {exc}")
            self._record_stage(state, SessionStage.safety_gate, "02_safety_classifier", "fail")
            return None

        # Update safety status
        state.safety_status = SafetyStatus(
            ctrs_level=result.ctrs_level,
            risk_level=result.risk_level,
            crisis_triggered=result.crisis_protocol_activated,
            last_checked_at=datetime.now(),
        )

        # Check for crisis
        if result.ctrs_level in _CRISIS_CTRS:
            state.current_stage = SessionStage.crisis_flow
            self._record_stage(
                state, SessionStage.safety_gate, "02_safety_classifier",
                "crisis", f"CTRS {int(result.ctrs_level)}"
            )
        else:
            self._record_stage(
                state, SessionStage.safety_gate, "02_safety_classifier",
                "pass", f"CTRS {int(result.ctrs_level)}"
            )

        return result

    # ── Context retrieval ───────────────────────────────────────────

    async def _run_context_retrieval(self, state: SessionState) -> None:
        """Retrieve prior context (temporal data, prior handoffs).

        Currently a placeholder — TemporalRetriever (Agent 08) is not yet
        implemented.  When it is, this will call it and merge results into
        state.
        """
        state.current_stage = SessionStage.context_retrieval

        # TODO: Call TemporalRetrieverAgent when available (ISS-010 / F2-DEV-001)
        # For first-visit patients, this is a no-op anyway.
        if state.is_first_visit:
            self._record_stage(
                state, SessionStage.context_retrieval, "08_temporal_retriever",
                "skip", "first visit — no prior context"
            )
        else:
            self._record_stage(
                state, SessionStage.context_retrieval, "08_temporal_retriever",
                "skip", "retriever not implemented"
            )

    # ── Slot coverage check ─────────────────────────────────────────

    def _should_extract_slots(self, state: SessionState) -> bool:
        """Decide whether to exit dialogue and proceed to slot extraction."""
        self._update_slot_coverage(state)

        if state.slot_coverage >= _SLOT_COVERAGE_THRESHOLD:
            logger.info(
                "Slot coverage %.2f >= %.2f — moving to extraction",
                state.slot_coverage, _SLOT_COVERAGE_THRESHOLD,
            )
            return True

        if state.turn_count >= _MAX_DIALOGUE_TURNS:
            logger.info(
                "Max turns %d reached — forcing slot extraction",
                _MAX_DIALOGUE_TURNS,
            )
            return True

        return False

    def _update_slot_coverage(self, state: SessionState) -> None:
        """Recompute slot coverage from current slot_data."""
        filled = [k for k in ALL_SLOT_KEYS if self._slot_is_filled(state.slot_data, k)]
        state.filled_slots = filled
        state.missing_essential_slots = [
            k for k in _ESSENTIAL_SLOTS if k not in filled
        ]
        state.slot_coverage = len(filled) / len(ALL_SLOT_KEYS) if ALL_SLOT_KEYS else 0.0

    @staticmethod
    def _slot_is_filled(slot_data: dict[str, Any], key: str) -> bool:
        """Check if a slot key is present and non-empty in slot_data."""
        parts = key.split(".")
        if len(parts) == 1:
            val = slot_data.get(key)
        else:
            # Nested: e.g. "symptoms.sleep"
            parent = slot_data.get(parts[0], {})
            if isinstance(parent, dict):
                val = parent.get(parts[1])
            else:
                val = None

        if val is None:
            return False
        if isinstance(val, str) and not val.strip():
            return False
        if isinstance(val, dict) and val.get("value") in (None, ""):
            return False
        return True

    # ── Post-dialogue pipeline ──────────────────────────────────────

    async def _run_post_dialogue_pipeline(
        self, state: SessionState
    ) -> OrchestratorTurnResult:
        """Run slot_extraction → handoff_generation → evidence_verification → delivery."""

        # ── Slot extraction ─────────────────────────────────────────
        state.current_stage = SessionStage.slot_extraction
        try:
            slot_agent = self._get_slot_agent()
            slot_input = ClinicalSlotInput(
                session_id=state.session_id,
                conversation_history=state.conversation_history,
                current_slots=state.slot_data,
            )
            slot_result = await slot_agent.run(slot_input)
            # Merge extracted slots into state
            if hasattr(slot_result, "extracted_slots") and slot_result.extracted_slots:
                self.update_slots(state, slot_result.extracted_slots)
            self._update_slot_coverage(state)
            self._record_stage(
                state, SessionStage.slot_extraction, "04_clinical_slot",
                "pass", f"coverage={state.slot_coverage:.2f}"
            )
        except Exception as exc:
            logger.warning("Slot extraction failed: %s — proceeding with existing slots", exc)
            self._record_stage(
                state, SessionStage.slot_extraction, "04_clinical_slot",
                "fail", str(exc)
            )

        # ── Handoff generation + verification loop ──────────────────
        state.current_stage = SessionStage.handoff_generation
        handoff_report = None

        try:
            handoff_agent = self._get_handoff_agent()
            handoff_input = self._build_handoff_input(state)

            for attempt in range(1 + _MAX_HANDOFF_REGEN):
                handoff_result = await handoff_agent.run(handoff_input)
                self._record_stage(
                    state, SessionStage.handoff_generation, "10_handoff_generator",
                    "pass", f"attempt {attempt + 1}"
                )

                # Evidence verification
                state.current_stage = SessionStage.evidence_verification
                verifier = self._get_verifier_agent()
                verifier_input = EvidenceVerifierInput(
                    session_id=state.session_id,
                    report_markdown=handoff_result.report_markdown,
                    evidence_packets=handoff_result.evidence_packets,
                )
                verification = await verifier.run(verifier_input)

                if verification.action == VerifierAction.passed:
                    self._record_stage(
                        state, SessionStage.evidence_verification, "11_evidence_verifier",
                        "pass", f"verified on attempt {attempt + 1}"
                    )
                    handoff_report = {
                        "report_markdown": handoff_result.report_markdown,
                        "evidence_packets": [
                            p.model_dump() for p in handoff_result.evidence_packets
                        ],
                        "missing_slots": handoff_result.missing_slots,
                        "risk_level": str(handoff_result.risk_level),
                        # trend_plot은 58db676에서 제거됨(F1 범위 밖). 계약 유지 위해 키만 남김.
                        "trend_plot_base64": None,
                    }
                    break

                if verification.action == VerifierAction.reject:
                    self._record_stage(
                        state, SessionStage.evidence_verification, "11_evidence_verifier",
                        "fail", f"rejected: {len(verification.issues)} issues"
                    )
                    state.error_log.append(
                        f"Handoff rejected: {[i.description for i in verification.issues]}"
                    )
                    break

                # regenerate
                self._record_stage(
                    state, SessionStage.evidence_verification, "11_evidence_verifier",
                    "regenerate", f"attempt {attempt + 1}/{1 + _MAX_HANDOFF_REGEN}"
                )
                state.current_stage = SessionStage.handoff_generation

        except Exception as exc:
            logger.error("Handoff pipeline failed: %s", exc)
            self._record_stage(
                state, SessionStage.handoff_generation, "10_handoff_generator",
                "fail", str(exc)
            )
            state.error_log.append(f"Handoff pipeline error: {exc}")

        # ── Handoff delivery ────────────────────────────────────────
        state.current_stage = SessionStage.handoff_delivery
        self._record_stage(state, SessionStage.handoff_delivery, "orchestrator", "pass")
        state.current_stage = SessionStage.completed

        return OrchestratorTurnResult(
            session_id=state.session_id,
            current_stage=SessionStage.completed,
            safety_status=state.safety_status,
            slot_coverage=state.slot_coverage,
            handoff_ready=True,
            handoff_report=handoff_report,
            session_state=state,
            stage_history=state.stage_history,
        )

    def _build_handoff_input(self, state: SessionState) -> HandoffInput:
        """Construct HandoffInput from the current session state."""
        slot_data = state.slot_data
        symptoms = (
            slot_data.get("symptoms", {})
            if isinstance(slot_data.get("symptoms"), dict)
            else {}
        )

        # ISS-020: carry collected scale scores + safety/risk events into the
        # handoff so the clinician-facing report never loses PHQ-9/GAD-7 severity
        # or suicide-risk indicators collected during the session.
        scale_scores: list[ScaleScore] = []
        for name, data in state.scale_scores.items():
            if name.startswith("_"):  # skip meta keys (e.g. "_prior" trend data)
                continue
            if isinstance(data, dict) and data.get("total_score") is not None:
                scale_scores.append(
                    ScaleScore(
                        scale_name=name,
                        total_score=int(data["total_score"]),
                        severity=str(data.get("severity", "")),
                    )
                )

        risk_events: list[dict[str, str]] = []
        ss = state.safety_status
        if ss is not None and ss.risk_level != RiskLevel.none:
            risk_events.append(
                {
                    "ctrs_level": str(int(ss.ctrs_level)),
                    "risk_level": ss.risk_level.value,
                    "crisis": str(ss.crisis_triggered),
                }
            )

        return HandoffInput(
            session_id=state.session_id,
            slots=SlotData(
                chief_complaint=slot_data.get("chief_complaint"),
                history_of_present_illness=slot_data.get("history_of_present_illness"),
                onset=slot_data.get("onset"),
                duration=slot_data.get("duration"),
                triggers=slot_data.get("triggers"),
                sleep=symptoms.get("sleep"),
                appetite=symptoms.get("appetite"),
                mood=symptoms.get("mood"),
                anxiety=symptoms.get("anxiety"),
                concentration=symptoms.get("concentration"),
                energy=symptoms.get("energy"),
                functional_impairment=slot_data.get("functional_impairment"),
                medication=slot_data.get("current_medications"),
                past_psychiatric_history=slot_data.get("past_psychiatric_history"),
                risk_factors=slot_data.get("risk_factors"),
                psychosocial_context=slot_data.get("psychosocial_context"),
                substance_use=slot_data.get("substance_use"),
            ),
            conversation_history=state.conversation_history,
            scale_scores=scale_scores,
            risk_events=risk_events,
            is_first_visit=state.is_first_visit,
        )

    # ── Crisis flow ─────────────────────────────────────────────────

    def _build_crisis_result(
        self, state: SessionState, safety_result: Any
    ) -> OrchestratorTurnResult:
        """Build the crisis protocol response."""
        ctrs = state.safety_status.ctrs_level
        message = _CRISIS_MESSAGES.get(ctrs, _CRISIS_MESSAGES[CTRSLevel.HIGH_RISK])

        self._record_stage(
            state, SessionStage.crisis_flow, "orchestrator",
            "crisis", f"CTRS {ctrs.value} — crisis protocol activated"
        )

        return OrchestratorTurnResult(
            session_id=state.session_id,
            current_stage=SessionStage.crisis_flow,
            assistant_response=message,
            safety_status=state.safety_status,
            slot_coverage=state.slot_coverage,
            crisis_triggered=True,
            requires_human_review=True,
            session_state=state,
            stage_history=state.stage_history,
        )

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _record_stage(
        state: SessionState,
        stage: SessionStage,
        agent: str,
        result: str,
        detail: str = "",
    ) -> None:
        """Append a stage transition record to the session history."""
        state.stage_history.append(
            StageRecord(
                stage=stage,
                agent=agent,
                result=result,
                timestamp=datetime.now(),
                detail=detail,
            )
        )

    # ── Convenience: update slots from external call ────────────────

    @staticmethod
    def update_slots(state: SessionState, new_slots: dict[str, Any]) -> None:
        """Merge new slot data into session state (called by route after dialogue)."""
        for key, value in new_slots.items():
            parts = key.split(".")
            if len(parts) == 1:
                state.slot_data[key] = value
            else:
                state.slot_data.setdefault(parts[0], {})[parts[1]] = value

    @staticmethod
    def add_assistant_turn(state: SessionState, response: str) -> None:
        """Record an assistant response in conversation history."""
        state.conversation_history.append({
            "role": "assistant",
            "content": response,
        })

    # ── Survey planner ──────────────────────────────────────────────

    @staticmethod
    def plan_surveys(state: SessionState) -> list[str]:
        """Recommend which clinical scales to administer based on slot data.

        Rules:
        - PHQ-9: always recommended (depression screening standard)
        - GAD-7: if anxiety-related slots are filled or chief_complaint mentions anxiety
        - PHQ-4: if neither PHQ-9 nor GAD-7 scored yet (ultra-brief screener)
        - WHO-5: if mood or energy slots suggest low wellbeing
        - AUDIT-C: if substance_use slot mentions alcohol
        """
        recommended: list[str] = []
        already_scored = set(state.scale_scores.keys())
        slots = state.slot_data

        # PHQ-9 always
        if "PHQ-9" not in already_scored:
            recommended.append("PHQ-9")

        # GAD-7 if anxiety signals present
        symptoms = slots.get("symptoms", {})
        anxiety_signal = (
            isinstance(symptoms, dict) and symptoms.get("anxiety")
        ) or "불안" in str(slots.get("chief_complaint", ""))
        if anxiety_signal and "GAD-7" not in already_scored:
            recommended.append("GAD-7")

        # PHQ-4 as fallback if no PHQ-9 or GAD-7
        if "PHQ-9" not in already_scored and "GAD-7" not in already_scored:
            if "PHQ-4" not in already_scored:
                recommended.append("PHQ-4")

        # WHO-5 if mood/energy concerns
        mood_concern = isinstance(symptoms, dict) and (
            symptoms.get("mood") or symptoms.get("energy")
        )
        if mood_concern and "WHO-5" not in already_scored:
            recommended.append("WHO-5")

        # AUDIT-C if substance use mentions alcohol
        substance = str(slots.get("substance_use", ""))
        if ("알코올" in substance or "술" in substance) and "AUDIT-C" not in already_scored:
            recommended.append("AUDIT-C")

        return recommended

    @staticmethod
    def score_and_check_safety(
        state: SessionState, scale_name: str, responses: list[int],
        patient_sex: str = "unknown",
    ) -> tuple[ScoreResult, bool]:
        """Score a survey and check if it triggers a safety referral.

        Returns:
            (ScoreResult, safety_triggered) — safety_triggered is True if
            the score warrants immediate safety referral (e.g. PHQ-9 Q9 >= 1).
        """
        result = score_survey(scale_name, responses, patient_sex=patient_sex)
        state.scale_scores[scale_name] = {
            "total_score": result.total_score,
            "severity": result.severity,
            "critical_item_positive": result.critical_item_positive,
            "recommended_action": result.recommended_action,
        }

        safety_triggered = result.recommended_action == "safety_referral"
        return result, safety_triggered
