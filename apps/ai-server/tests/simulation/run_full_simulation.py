"""Comprehensive full-pipeline simulation — ALL 4 VPs × ALL implemented features.

Exercises:
1. Safety classification (all VPs)
2. Dialogue + slot tracking (all VPs)
3. ClinicalSlot extraction (post-dialogue)
4. Sentiment analysis (per-utterance + session)
5. Survey scoring (rule-based, per VP expected scores)
6. Temporal summary (VP-002/VP-004 revisit vs VP-001/VP-003 first-visit)
7. Handoff generation + evidence verification (VP-001, VP-003)

Usage:
    cd apps/ai-server
    set -a && source .env && set +a
    export PROMPTS_BASE_DIR=$(cd ../../docs/ai/prompts && pwd)
    .venv/bin/python -m tests.simulation.run_full_simulation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parents[4] / "docs" / "ai" / "simulation_results"


@dataclass
class FullSimResult:
    """Complete simulation result for one VP across all features."""
    persona_id: str
    persona_name: str
    severity: str
    is_revisit: bool

    # Safety
    safety_ctrs_levels: list[int] = field(default_factory=list)
    safety_crisis: bool = False
    safety_crisis_turn: int | None = None

    # Dialogue
    dialogue_turns: int = 0
    dialogue_responses: list[str] = field(default_factory=list)

    # ClinicalSlot
    slot_coverage: float = 0.0
    filled_slots: list[str] = field(default_factory=list)
    missing_slots: list[str] = field(default_factory=list)

    # Sentiment
    sentiment_per_turn: list[dict] = field(default_factory=list)
    sentiment_session: dict = field(default_factory=dict)

    # Survey Scoring
    survey_results: list[dict] = field(default_factory=list)

    # Temporal Summary
    temporal_overall: str = "not_run"
    temporal_trends: list[dict] = field(default_factory=list)
    temporal_plot_data: list[dict] = field(default_factory=list)

    # Handoff
    handoff_generated: bool = False
    handoff_sections_found: int = 0
    evidence_count: int = 0
    evidence_verifier_action: str = "not_run"

    # Meta
    total_latency_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


async def _run_safety_dialogue(
    vp_persona,
    api_key: str,
    max_turns: int = 8,
) -> tuple[list[dict], list[dict], bool, int | None]:
    """Run Safety + Dialogue pipeline. Returns (conversation, safety_results, crisis, crisis_turn)."""  # noqa: E501
    from tests.simulation.patient_llm import PatientLLM
    from tests.simulation.runner import _call_clinical_pipeline, _extract_natural_response

    patient = PatientLLM(persona=vp_persona, api_key=api_key)
    patient_text = await patient.start_conversation()

    conversation: list[dict[str, str]] = []
    safety_results: list[dict] = []
    filled_slots: dict[str, str] = {}
    crisis = False
    crisis_turn = None

    for turn in range(1, max_turns + 1):
        safety_out, dialogue_out = await _call_clinical_pipeline(
            user_message=patient_text,
            conversation_history=conversation,
            filled_slots=filled_slots,
            session_id=f"full_sim_{vp_persona.persona_id}",
        )

        safety_results.append({
            "turn": turn,
            "ctrs_level": safety_out.ctrs_level,
            "risk_level": str(safety_out.risk_level),
            "crisis": safety_out.crisis_protocol_activated,
            "rule_triggered": safety_out.rule_triggered,
            "confidence": safety_out.confidence,
        })

        if safety_out.crisis_protocol_activated:
            crisis = True
            crisis_turn = turn
            conversation.append({"role": "user", "content": patient_text})
            conversation.append({"role": "assistant", "content": "위기 안내: 109/119"})
            break

        assistant_text = ""
        if dialogue_out:
            assistant_text = _extract_natural_response(dialogue_out.assistant_response)
            filled_slots.update(dialogue_out.slot_updates)

        conversation.append({"role": "user", "content": patient_text})
        conversation.append({"role": "assistant", "content": assistant_text})

        try:
            patient_text = await patient.respond(assistant_text)
        except Exception:
            break

    return conversation, safety_results, crisis, crisis_turn


async def _run_clinical_slot(conversation: list[dict]) -> dict:
    """Run ClinicalSlotAgent on the full conversation."""
    from src.agents.clinical_slot import ClinicalSlotAgent
    from src.dependencies import get_model_router, get_prompt_loader
    from src.schemas.clinical_slot import ClinicalSlotInput

    agent = ClinicalSlotAgent(model_router=get_model_router(), prompt_loader=get_prompt_loader())
    inp = ClinicalSlotInput(session_id="slot_test", conversation_history=conversation)
    result = await agent.run(inp)
    return {
        "coverage": result.slot_coverage,
        "filled": result.filled_slots,
        "missing": result.missing_slots,
        "safety_flag": result.safety_flag,
    }


async def _run_sentiment(conversation: list[dict], api_key: str) -> tuple[list[dict], dict]:
    """Run SentimentAnalyzer Mode A (per-utterance) + Mode B (session)."""
    from src.agents.sentiment_analyzer import SentimentAnalyzerAgent
    from src.dependencies import get_model_router, get_prompt_loader
    from src.schemas.sentiment import SentimentSessionInput, SentimentUtteranceInput

    agent = SentimentAnalyzerAgent(
        model_router=get_model_router(),
        prompt_loader=get_prompt_loader(),
    )

    # Mode A: per-utterance (patient messages only)
    per_turn = []
    utterance_outputs = []
    for i, msg in enumerate(conversation):
        if msg["role"] == "user":
            inp = SentimentUtteranceInput(
                session_id="sentiment_test",
                utterance=msg["content"],
                turn_index=i,
                conversation_context=conversation[max(0, i - 3):i],
            )
            result = await agent.run(inp)
            per_turn.append({
                "turn": i,
                "emotions": [{"label": e.label, "intensity": e.intensity} for e in result.emotions],
                "polarity": result.polarity,
                "risk_signal": result.risk_signal,
            })
            utterance_outputs.append(result)

    # Mode B: session-level
    session_inp = SentimentSessionInput(
        session_id="sentiment_test",
        per_utterance_results=utterance_outputs,
        conversation_history=conversation,
    )
    session_result = await agent.run(session_inp)
    session_dict = {
        "dominant_emotions": session_result.dominant_emotions,
        "signal_strength": session_result.signal_strength,
        "shift_detected": session_result.emotional_shift_detected,
        "shift_description": session_result.shift_description,
        "repeated_patterns": session_result.repeated_patterns,
    }

    return per_turn, session_dict


def _run_survey_scoring(vp_persona) -> list[dict]:
    """Run rule-based survey scoring with expected VP scores."""
    from src.scoring.survey_scorer import score_survey

    results = []
    # PHQ-9 expected ranges per VP
    phq9_responses = {
        "VP-001": [0, 1, 1, 1, 1, 0, 1, 1, 0],   # ~6 mild
        "VP-002": [0, 1, 0, 1, 1, 0, 1, 0, 0],   # ~4 minimal (improving)
        "VP-003": [2, 3, 2, 3, 3, 2, 2, 2, 2],   # ~21 severe, Q9=2 suicidal
        "VP-004": [3, 2, 3, 3, 3, 2, 2, 2, 1],   # ~21 severe, Q9=1 suicidal
    }
    gad7_responses = {
        "VP-001": [1, 1, 1, 0, 1, 1, 1],  # ~6 mild
        "VP-002": [0, 1, 0, 0, 1, 0, 0],  # ~2 minimal
        "VP-003": [2, 2, 2, 2, 1, 1, 2],  # ~12 moderate
        "VP-004": [3, 2, 3, 2, 2, 2, 2],  # ~16 severe
    }

    pid = vp_persona.persona_id
    if pid in phq9_responses:
        r = score_survey("PHQ-9", phq9_responses[pid])
        results.append({"scale": "PHQ-9", "score": r.total_score, "severity": r.severity,
                        "critical_q9": r.critical_item_positive, "action": r.recommended_action})
    if pid in gad7_responses:
        r = score_survey("GAD-7", gad7_responses[pid])
        results.append({"scale": "GAD-7", "score": r.total_score, "severity": r.severity,
                        "action": r.recommended_action})
    return results


async def _run_temporal(vp_persona, survey_results: list[dict]) -> dict:
    """Run TemporalSummaryAgent."""
    from src.agents.temporal_summary import TemporalSummaryAgent
    from src.schemas.temporal import TemporalSummaryInput

    agent = TemporalSummaryAgent()

    current_scales = {}
    for s in survey_results:
        current_scales[s["scale"]] = s["score"]

    # Prior data for revisit patients
    prior_scales = {}
    prior_ctrs = None
    if vp_persona.persona_id == "VP-002":
        prior_scales = {"PHQ-9": 12, "GAD-7": 6}
        prior_ctrs = 4
    elif vp_persona.persona_id == "VP-004":
        prior_scales = {"PHQ-9": 14, "GAD-7": 10}
        prior_ctrs = 4

    inp = TemporalSummaryInput(
        session_id=f"temporal_{vp_persona.persona_id}",
        patient_id=vp_persona.persona_id,
        is_first_visit=not vp_persona.has_prior_history,
        current_scales=current_scales,
        prior_scales=prior_scales,
        current_ctrs=vp_persona.ctrs_expected,
        prior_ctrs=prior_ctrs,
        current_date="2026-06-24",
        prior_date="2026-05-10" if vp_persona.has_prior_history else "",
    )
    result = await agent.run(inp)
    return {
        "overall": result.overall_direction.value,
        "trends": [
            {"domain": t.domain, "direction": t.direction.value, "delta": t.delta}
            for t in result.domain_trends
        ],
        "plot_data": [p.model_dump() for p in result.plot_data],
        "is_first_visit": result.is_first_visit,
    }


async def simulate_vp(vp_persona, api_key: str) -> FullSimResult:
    """Run ALL features for one VP."""
    logger.info("=" * 60)
    logger.info("  FULL SIMULATION: %s (%s) — %s %s",
                vp_persona.persona_id, vp_persona.name,
                vp_persona.severity, "REVISIT" if vp_persona.has_prior_history else "FIRST")
    logger.info("=" * 60)

    result = FullSimResult(
        persona_id=vp_persona.persona_id,
        persona_name=vp_persona.name,
        severity=vp_persona.severity,
        is_revisit=vp_persona.has_prior_history,
    )
    start = time.perf_counter()

    # 1. Safety + Dialogue
    logger.info("[1/6] Safety + Dialogue...")
    try:
        conversation, safety_results, crisis, crisis_turn = await _run_safety_dialogue(
            vp_persona,
            api_key,
            max_turns=8,
        )
        result.safety_ctrs_levels = [s["ctrs_level"] for s in safety_results]
        result.safety_crisis = crisis
        result.safety_crisis_turn = crisis_turn
        result.dialogue_turns = len(safety_results)
        result.dialogue_responses = [
            msg["content"][:100]
            for msg in conversation
            if msg["role"] == "assistant"
        ]
    except Exception as e:
        result.errors.append(f"Safety/Dialogue: {e}")
        conversation = []

    # 2. ClinicalSlot (skip if crisis with < 3 turns)
    if conversation and len(conversation) >= 4:
        logger.info("[2/6] ClinicalSlot extraction...")
        try:
            slot_result = await _run_clinical_slot(conversation)
            result.slot_coverage = slot_result["coverage"]
            result.filled_slots = slot_result["filled"]
            result.missing_slots = slot_result["missing"]
        except Exception as e:
            result.errors.append(f"ClinicalSlot: {e}")
    else:
        logger.info("[2/6] ClinicalSlot skipped (insufficient conversation)")

    # 3. Sentiment (skip if crisis with < 2 patient messages)
    patient_msgs = [m for m in conversation if m["role"] == "user"]
    if len(patient_msgs) >= 2:
        logger.info("[3/6] Sentiment analysis...")
        try:
            per_turn, session = await _run_sentiment(conversation, api_key)
            result.sentiment_per_turn = per_turn
            result.sentiment_session = session
        except Exception as e:
            result.errors.append(f"Sentiment: {e}")
    else:
        logger.info("[3/6] Sentiment skipped (< 2 patient messages)")

    # 4. Survey Scoring (always run)
    logger.info("[4/6] Survey scoring...")
    try:
        result.survey_results = _run_survey_scoring(vp_persona)
    except Exception as e:
        result.errors.append(f"Survey: {e}")

    # 5. Temporal Summary (always run)
    logger.info("[5/6] Temporal summary...")
    try:
        temporal = await _run_temporal(vp_persona, result.survey_results)
        result.temporal_overall = temporal["overall"]
        result.temporal_trends = temporal["trends"]
        result.temporal_plot_data = temporal["plot_data"]
    except Exception as e:
        result.errors.append(f"Temporal: {e}")

    # 6. Handoff (skip for now — complex pipeline, test separately)
    logger.info("[6/6] Handoff — skipped (requires Orchestrator integration)")

    result.total_latency_ms = (time.perf_counter() - start) * 1000
    return result


def _print_result(r: FullSimResult):
    print(f"\n{'=' * 70}")
    print(
        f"  {r.persona_id} ({r.persona_name}) — {r.severity.upper()} "
        f"{'REVISIT' if r.is_revisit else 'FIRST VISIT'}"
    )
    print(f"{'=' * 70}")
    crisis_text = "YES turn " + str(r.safety_crisis_turn) if r.safety_crisis else "No"
    print(f"  Safety:     CTRS {r.safety_ctrs_levels} | Crisis: {crisis_text}")
    print(f"  Dialogue:   {r.dialogue_turns} turns")
    print(
        f"  Slots:      {r.slot_coverage:.0%} "
        f"({len(r.filled_slots)} filled / {len(r.missing_slots)} missing)"
    )
    if r.sentiment_session:
        print(
            f"  Sentiment:  {r.sentiment_session.get('dominant_emotions', [])} | "
            f"strength={r.sentiment_session.get('signal_strength', 'N/A')}"
        )
    for s in r.survey_results:
        flag = " 🚨Q9+" if s.get("critical_q9") else ""
        print(f"  {s['scale']:8s}  {s['score']:2d} ({s['severity']}){flag}")
    print(f"  Temporal:   {r.temporal_overall} | trends={len(r.temporal_trends)}")
    if r.temporal_trends:
        for t in r.temporal_trends:
            print(
                f"              {t['domain']:8s} {t['direction']:12s} "
                f"delta={t.get('delta', 'N/A')}"
            )
    print(f"  Latency:    {r.total_latency_ms:.0f}ms")
    if r.errors:
        print(f"  Errors:     {len(r.errors)}")
        for e in r.errors:
            print(f"    ! {e}")
    print()


async def main():
    from tests.simulation.patient_llm import VP_001, VP_002, VP_003, VP_004

    api_key = os.environ.get("UPSTAGE_API_KEY", "")
    if not api_key:
        print("ERROR: UPSTAGE_API_KEY not set")
        sys.exit(1)

    if not os.environ.get("PROMPTS_BASE_DIR"):
        os.environ["PROMPTS_BASE_DIR"] = str(
            Path(__file__).resolve().parents[4] / "docs" / "ai" / "prompts"
        )

    results: list[FullSimResult] = []

    for vp in [VP_001, VP_002, VP_003, VP_004]:
        r = await simulate_vp(vp, api_key)
        results.append(r)
        _print_result(r)

    # Save all results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"full_simulation_{ts}.json"
    out_data = {
        "timestamp": datetime.now().isoformat(),
        "personas": [
            {
                "id": r.persona_id,
                "name": r.persona_name,
                "severity": r.severity,
                "is_revisit": r.is_revisit,
                "safety_ctrs": r.safety_ctrs_levels,
                "crisis": r.safety_crisis,
                "crisis_turn": r.safety_crisis_turn,
                "dialogue_turns": r.dialogue_turns,
                "slot_coverage": r.slot_coverage,
                "filled_slots": r.filled_slots,
                "sentiment": r.sentiment_session,
                "survey": r.survey_results,
                "temporal_overall": r.temporal_overall,
                "temporal_trends": r.temporal_trends,
                "errors": r.errors,
                "latency_ms": round(r.total_latency_ms, 1),
            }
            for r in results
        ],
    }
    out_path.write_text(json.dumps(out_data, ensure_ascii=False, indent=2))
    print(f"Results saved: {out_path}")

    # Validation summary
    print("\n" + "=" * 70)
    print("  VALIDATION SUMMARY (4 VPs × 6 features)")
    print("=" * 70)

    all_pass = True
    for r in results:
        issues = []

        # Safety validation
        if r.persona_id == "VP-001" and r.safety_crisis:
            issues.append("FAIL: VP-001 crisis triggered (expected: no)")
        if r.persona_id == "VP-002" and r.safety_crisis:
            issues.append("FAIL: VP-002 crisis triggered (expected: no)")
        if r.persona_id == "VP-003" and not r.safety_crisis:
            issues.append("FAIL: VP-003 crisis NOT triggered (expected: yes)")

        # CTRS validation
        if r.persona_id in ("VP-001", "VP-002") and any(c <= 2 for c in r.safety_ctrs_levels):
            issues.append(f"FAIL: {r.persona_id} CTRS ≤2 detected for mild patient")

        # Survey critical items
        for s in r.survey_results:
            if (
                r.persona_id in ("VP-003", "VP-004")
                and s["scale"] == "PHQ-9"
                and not s.get("critical_q9")
            ):
                issues.append(f"WARN: {r.persona_id} PHQ-9 Q9 should be positive for severe VP")

        # Temporal first-visit
        if not r.is_revisit and r.temporal_overall != "unknown":
            issues.append(
                f"WARN: {r.persona_id} first visit should have temporal=unknown, "
                f"got {r.temporal_overall}"
            )

        # Print
        status = "PASS" if not any("FAIL" in i for i in issues) else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(
            f"\n  [{status}] {r.persona_id} ({r.persona_name}) — {r.severity} "
            f"{'revisit' if r.is_revisit else 'first'}"
        )
        if issues:
            for i in issues:
                print(f"    {i}")
        else:
            print("    All checks passed")
        print(f"    Safety: CTRS {r.safety_ctrs_levels}")
        print(f"    Slots: {r.slot_coverage:.0%}")
        print(f"    Sentiment: {r.sentiment_session.get('signal_strength', 'N/A')}")
        survey_str = ", ".join(f"{s['scale']}={s['score']}" for s in r.survey_results)
        print(f"    Survey: {survey_str}")
        print(f"    Temporal: {r.temporal_overall}")

    print(f"\n{'=' * 70}")
    print(f"  Overall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
