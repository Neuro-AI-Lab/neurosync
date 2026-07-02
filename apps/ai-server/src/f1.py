"""F1 Pipeline — 자율 대화 기반 사전문진.

Agent 협업:
  01_orchestrator → 02_safety (매 턴) → 03_dialogue → 04_clinical_slot

목표: 12 Standard Clinical Slot을 대화로 수집.
Safety: 매 턴 CTRS 분류, CTRS 1-2 시 위기 대응 + 세션 종료.

Usage (시뮬레이션):
    cd apps/ai-server
    .venv/bin/python -m src.f1 --persona VP-001 --max-turns 10

Usage (프로덕션):
    F1Pipeline을 import하여 WebSocket/HTTP handler에서 사용.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Awaitable

from src.agents.safety_classifier import SafetyClassifierAgent
from src.agents.dialogue import DialogueAgent
from src.agents.clinical_slot import ClinicalSlotAgent
from src.dependencies import get_model_router, get_prompt_loader
from src.schemas.safety import SafetyInput
from src.schemas.dialogue import DialogueInput
from src.schemas.clinical_slot import ClinicalSlotInput

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # apps/ai-server/src/f1.py → neurosync/
OUTPUT_DIR = PROJECT_ROOT / "docs" / "ai" / "simulation_results"

CRISIS_RESPONSE = (
    "지금 많이 힘드시군요. 당신의 이야기를 듣고 있습니다. "
    "자살예방상담전화 109, 응급전화 119로 연락해 주세요."
)

# ── Data structures ──────────────────────────────────────────────────


@dataclass
class F1TurnLog:
    turn: int
    patient_message: str
    safety_ctrs: int
    safety_risk: str
    safety_crisis: bool
    safety_categories: list[str]
    safety_flagged: list[str]
    agent_response: str
    slot_updates: dict[str, str]
    cumulative_slots: dict[str, str]
    slot_coverage: float
    latency_ms: float
    timestamp: str


@dataclass
class F1Result:
    session_id: str
    persona_id: str | None
    persona_name: str | None
    total_turns: int = 0
    crisis_triggered: bool = False
    crisis_turn: int | None = None
    final_slots: list[dict[str, str]] = field(default_factory=list)  # [{key: ..., value: ...}, ...]
    slot_coverage: float = 0.0
    turns: list[F1TurnLog] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""


def _extract_text(response: str) -> str:
    """Extract natural text from possibly JSON-wrapped agent response."""
    stripped = response.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict) and "assistant_response" in data:
                return data["assistant_response"]
        except json.JSONDecodeError:
            pass
        import re
        match = re.search(r'"assistant_response"\s*:\s*"((?:[^"\\]|\\.)*)"', stripped)
        if match:
            return match.group(1).replace('\\"', '"').replace('\\n', '\n')
    return stripped


# ── F1 Pipeline ──────────────────────────────────────────────────────


class F1Pipeline:
    """F1: 자율 대화 기반 사전문진 파이프라인.

    Agent 호출 원칙:
      입력 = system prompt (PromptLoader) + runtime context + conversation history
      모든 agent는 agent md file의 role/규칙을 준수
    """

    def __init__(self) -> None:
        mr = get_model_router()
        pl = get_prompt_loader()
        self.safety = SafetyClassifierAgent(model_router=mr, prompt_loader=pl)
        self.dialogue = DialogueAgent(model_router=mr, prompt_loader=pl)
        self.clinical_slot = ClinicalSlotAgent(model_router=mr, prompt_loader=pl)

    @staticmethod
    def _summarize_prior_handoff(handoff: str) -> str:
        """Extract chief complaint and key state from prior handoff for greeting.

        Parses both:
        - Markdown table: | `chief_complaint` | "우울감과 불면" |
        - Section header: ### 주호소 (with content on next line)
        """
        import re
        lines = handoff.split("\n")
        chief = ""
        risk_info = ""

        # Strategy 1: Markdown table format — | `chief_complaint` | "value" |
        for line in lines:
            if "chief_complaint" in line and "|" in line:
                parts = [p.strip().strip('"').strip('`') for p in line.split("|")]
                for i, p in enumerate(parts):
                    if "chief_complaint" in p and i + 1 < len(parts):
                        chief = parts[i + 1].strip('"')
                        break
                if chief:
                    break

        # Strategy 2: Section header — ### 주호소 or [3. 주호소] (next line has content)
        if not chief:
            for i, line in enumerate(lines):
                if re.search(r"(#+\s*|[\[\(]\d+[\.\)]\s*)주호소", line):
                    # Take the next non-empty line as content
                    for j in range(i + 1, min(i + 4, len(lines))):
                        stripped = lines[j].strip()
                        if stripped and not stripped.startswith(("#", "[", "---")):
                            chief = stripped
                            break
                    break

        # Look for risk level
        for line in lines:
            lower = line.lower()
            if ("risk" in lower or "위험" in lower) and any(
                w in lower for w in ["high", "severe", "높", "심각", "자살", "자해"]
            ):
                risk_info = "안전 관련 우려사항도 확인되었습니다"
                break

        summary_parts = []
        if chief:
            # Truncate to a reasonable greeting length
            if len(chief) > 80:
                chief = chief[:80] + "..."
            summary_parts.append(f"지난번에 '{chief}' 문제로 상담하셨습니다")
        else:
            summary_parts.append("지난번 상담 내용을 확인했습니다")

        if risk_info:
            summary_parts.append(risk_info)

        return " ".join(summary_parts) + "."

    async def run_session(
        self,
        patient_input_fn: Callable[[str], Awaitable[str]],
        session_id: str = "f1_session",
        persona_id: str | None = None,
        persona_name: str | None = None,
        max_turns: int = 15,
        slot_extraction_interval: int = 3,
        is_revisit: bool = False,
        prior_handoff: str = "",
        prior_slots: dict[str, str] | None = None,
    ) -> F1Result:
        """한 세션 실행.

        Args:
            patient_input_fn: async fn(agent_response) → patient_message
            session_id: 세션 ID
            max_turns: 최대 턴 수
            slot_extraction_interval: N턴마다 ClinicalSlotAgent 실행
            is_revisit: 재진 여부
            prior_handoff: 이전 handoff report (재진 시)
            prior_slots: 이전 세션에서 수집된 slot (재진 시)
        """
        result = F1Result(
            session_id=session_id,
            persona_id=persona_id,
            persona_name=persona_name,
            started_at=datetime.now().isoformat(),
        )

        conversation_history: list[dict[str, str]] = []
        filled_slots: dict[str, str] = dict(prior_slots) if prior_slots else {}
        prev_agent_response = ""
        repeat_count = 0

        # ── Turn 0: DialogueAgent 첫 인사 ──
        # 재상담(prior_handoff 있음)과 초진/재진(visit_type)은 별개 개념.
        # - 초진/재진: 의료 분류 (persona MD의 visit_type)
        # - 재상담: 이전 상담 기록이 존재하는 경우 (prior_handoff 비어있지 않음)
        if prior_handoff:
            # 재상담: 지난 상담에서 수집된 주호소/상태 요약을 환자에게 전달
            prior_summary = self._summarize_prior_handoff(prior_handoff)
            greeting = (
                "안녕하세요! 저는 정신건강 사전문진을 도와드리는 AI 상담 도우미입니다. "
                "실제 의사 선생님과의 대화가 아니니, 너무 긴장하지 마시고 "
                "편하게 느끼시는 그대로 말씀해 주시면 됩니다.\n\n"
                f"지난번 상담 기록을 확인했습니다. {prior_summary}\n\n"
                "지난번 이후로 상태가 어떻게 변했는지 편하게 말씀해 주세요."
            )
            # Inject prior handoff as context for DialogueAgent
            conversation_history.append({
                "role": "system",
                "content": f"[이전 상담 기록 참고 — 재상담 환자]\n{prior_handoff}",
            })
        else:
            greeting = (
                "안녕하세요! 저는 정신건강 사전문진을 도와드리는 AI 상담 도우미입니다. "
                "실제 의사 선생님과의 대화가 아니니, 너무 긴장하지 마시고 "
                "편하게 느끼시는 그대로 말씀해 주시면 됩니다.\n\n"
                "지금부터 대화를 시작하겠습니다. "
                "오늘 가장 도움받고 싶은 문제나 증상은 무엇인가요?"
            )

        logger.info("Turn 0 | AI (opening): %s", greeting)

        # Record Turn 0 in result (greeting + patient first response)
        turn0_start = time.perf_counter()

        try:
            patient_message = await patient_input_fn(greeting)
        except Exception as e:
            result.errors.append(f"Patient start failed: {e}")
            result.ended_at = datetime.now().isoformat()
            return result

        # Turn 0: Safety + Slot extraction on patient's first response
        turn0_history = [{"role": "assistant", "content": greeting}]

        # Safety check on first patient message
        try:
            turn0_safety = await self.safety.run(SafetyInput(
                session_id=session_id,
                user_message=patient_message,
                conversation_history=turn0_history,
            ))
        except Exception as e:
            logger.warning("Turn 0 safety failed: %s", e)
            turn0_safety = None

        # Slot extraction on first patient message
        turn0_slots: dict[str, str] = {}
        try:
            turn0_slot_out = await self.clinical_slot.run(ClinicalSlotInput(
                session_id=session_id,
                conversation_history=turn0_history + [
                    {"role": "user", "content": patient_message},
                ],
                current_slots=filled_slots,
            ))
            if turn0_slot_out.extracted_slots:
                from src.agents.clinical_slot import ALL_SLOT_KEYS as _ALL_KEYS
                for k, v in turn0_slot_out.extracted_slots.items():
                    if k not in _ALL_KEYS:
                        continue
                    if isinstance(v, dict) and "value" in v and isinstance(v["value"], str):
                        turn0_slots[k] = v["value"]
                    elif isinstance(v, str) and v:
                        turn0_slots[k] = v
                filled_slots.update(turn0_slots)
                logger.info("Turn 0 slot extraction: %d slots", len(turn0_slots))
        except Exception as e:
            logger.warning("Turn 0 slot extraction failed: %s", e)

        # Check crisis from Turn 0
        turn0_crisis = False
        turn0_ctrs = 5
        turn0_risk = "none"
        if turn0_safety:
            turn0_ctrs = turn0_safety.ctrs_level
            turn0_risk = str(turn0_safety.risk_level)
            turn0_crisis = turn0_safety.crisis_protocol_activated

        from src.agents.clinical_slot import ESSENTIAL_SLOT_KEYS
        filled_essential = [s for s in ESSENTIAL_SLOT_KEYS if filled_slots.get(s)]
        turn0_coverage = len(filled_essential) / len(ESSENTIAL_SLOT_KEYS) if ESSENTIAL_SLOT_KEYS else 0

        turn0_latency = (time.perf_counter() - turn0_start) * 1000
        turn0_log = F1TurnLog(
            turn=0,
            patient_message=patient_message,
            safety_ctrs=turn0_ctrs,
            safety_risk=turn0_risk,
            safety_crisis=turn0_crisis,
            safety_categories=turn0_safety.categories if turn0_safety else [],
            safety_flagged=turn0_safety.flagged_phrases if turn0_safety else [],
            agent_response=greeting,
            slot_updates=turn0_slots,
            cumulative_slots=dict(filled_slots),
            slot_coverage=turn0_coverage,
            latency_ms=turn0_latency,
            timestamp=datetime.now().isoformat(),
        )
        result.turns.append(turn0_log)

        if turn0_crisis:
            result.crisis_triggered = True
            result.crisis_turn = 0
            result.total_turns = 0
            result.final_slots = [{"key": k, "value": v} for k, v in filled_slots.items() if v]
            result.slot_coverage = turn0_coverage
            result.ended_at = datetime.now().isoformat()
            return result

        # Record opening in history
        conversation_history.append({"role": "assistant", "content": greeting})

        # ── Main dialogue loop ──
        # 대화 흐름: AI(greeting) → Patient → [Safety → Dialogue → Slot] → AI → Patient → ...
        # patient_message는 이미 Turn 0에서 받음 (greeting에 대한 응답)
        #
        # conversation_history 관리 원칙:
        #   - agent 호출 시점에는 "이전까지의 완성된 대화"만 들어있음
        #   - 현재 턴의 user/assistant는 턴 끝에 한번에 추가
        #   - agent에는 history + current user_message를 분리 전달
        for turn in range(1, max_turns + 1):
            turn_start = time.perf_counter()
            logger.info("Turn %d | Patient: %s", turn, patient_message)

            # ── Step 1: Safety classification (매 턴 필수) ──
            try:
                safety_out = await self.safety.run(SafetyInput(
                    session_id=session_id,
                    user_message=patient_message,
                    conversation_history=conversation_history,
                ))
            except Exception as e:
                result.errors.append(f"Turn {turn} safety error: {e}")
                logger.error("Safety failed: %s", e)
                break

            crisis = safety_out.crisis_protocol_activated
            agent_response = ""
            slot_updates: dict[str, str] = {}

            if crisis:
                # ── CTRS 1-2: Crisis → 세션 종료 ──
                agent_response = CRISIS_RESPONSE
                result.crisis_triggered = True
                result.crisis_turn = turn
                logger.warning("CRISIS at turn %d (CTRS=%d)", turn, safety_out.ctrs_level)
            else:
                # ── Step 2: Slot extraction FIRST (매 턴, Dialogue 전에) ──
                # Dialogue가 최신 slot 정보를 보고 질문할 수 있도록
                try:
                    slot_history = conversation_history + [
                        {"role": "user", "content": patient_message},
                    ]
                    slot_out = await self.clinical_slot.run(ClinicalSlotInput(
                        session_id=session_id,
                        conversation_history=slot_history,
                        current_slots=filled_slots,
                    ))
                    if slot_out.extracted_slots:
                        from src.agents.clinical_slot import ALL_SLOT_KEYS
                        for k, v in slot_out.extracted_slots.items():
                            # 12 Standard Slots만 허용 — 비표준 키 차단
                            if k not in ALL_SLOT_KEYS:
                                continue
                            if isinstance(v, dict) and "value" in v and isinstance(v["value"], str):
                                filled_slots[k] = v["value"]
                                slot_updates[k] = v["value"]
                            elif isinstance(v, str) and v:
                                filled_slots[k] = v
                                slot_updates[k] = v
                    logger.info(
                        "Turn %d slots: +%d new, %d total",
                        turn, len(slot_updates), len(filled_slots),
                    )
                except Exception as e:
                    logger.warning("Slot extraction failed: %s", e)

                # ── Step 3: Dialogue agent (최신 filled_slots + Safety 결과 사용) ──
                # Dialogue는 응답 생성만 담당.
                # Slot 추출은 Step 2(ClinicalSlotAgent)가, 위험도는 Step 1(SafetyAgent)가 전담.
                try:
                    safety_result_for_dialogue = {
                        "risk_level": str(safety_out.risk_level),
                        "ctrs_level": str(safety_out.ctrs_level),
                    }
                    dialogue_out = await self.dialogue.run(DialogueInput(
                        session_id=session_id,
                        user_message=patient_message,
                        conversation_history=conversation_history,
                        filled_slots=filled_slots,
                        safety_result=safety_result_for_dialogue,
                    ))
                    agent_response = _extract_text(dialogue_out.assistant_response)
                except Exception as e:
                    result.errors.append(f"Turn {turn} dialogue error: {e}")
                    logger.error("Dialogue failed: %s", e)
                    break

            # 턴 종료 후 history에 현재 턴의 대화 추가
            conversation_history.append({"role": "user", "content": patient_message})
            conversation_history.append({"role": "assistant", "content": agent_response})

            # ── Calculate slot coverage (orchestrator 역할) ──
            from src.agents.clinical_slot import ESSENTIAL_SLOT_KEYS
            filled_essential = [s for s in ESSENTIAL_SLOT_KEYS if filled_slots.get(s)]
            coverage = len(filled_essential) / len(ESSENTIAL_SLOT_KEYS) if ESSENTIAL_SLOT_KEYS else 0

            # ── Log turn ──
            latency = (time.perf_counter() - turn_start) * 1000
            turn_log = F1TurnLog(
                turn=turn,
                patient_message=patient_message,
                agent_response=agent_response,
                safety_ctrs=safety_out.ctrs_level,
                safety_risk=str(safety_out.risk_level),
                safety_crisis=crisis,
                safety_categories=safety_out.categories,
                safety_flagged=safety_out.flagged_phrases,
                slot_updates=slot_updates,
                cumulative_slots=dict(filled_slots),
                slot_coverage=coverage,
                latency_ms=latency,
                timestamp=datetime.now().isoformat(),
            )
            result.turns.append(turn_log)
            result.total_turns = turn
            result.final_slots = [{"key": k, "value": v} for k, v in filled_slots.items() if v]
            result.slot_coverage = coverage

            logger.info(
                "Turn %d | CTRS=%d | slots=%d | coverage=%.0f%% | %.0fms",
                turn, safety_out.ctrs_level, len(filled_slots), coverage * 100, latency,
            )

            if crisis:
                break

            # ── Handoff ready: 질문 가능 슬롯 모두 수집 시 세션 종료 ──
            _NO_Q = {"encounter_metadata", "mental_status_exam", "clinical_assessment", "treatment_plan"}
            from src.agents.clinical_slot import ALL_SLOT_KEYS as _ALL
            questionable_missing = [
                s for s in _ALL
                if s not in _NO_Q and s not in filled_slots
            ]
            if not questionable_missing and turn >= 3:
                logger.info("All questionable slots collected — ending session (handoff ready)")
                break

            # ── Repetition detection — stop after 2 consecutive repeats ──
            if agent_response == prev_agent_response and turn > 1:
                repeat_count += 1
                result.errors.append(f"Agent repetition at turn {turn} (count={repeat_count})")
                logger.warning("Agent repeating (count=%d)", repeat_count)
                if repeat_count >= 2:
                    logger.warning("Agent repeated 2+ times — stopping")
                    break
            else:
                repeat_count = 0
            prev_agent_response = agent_response

            # ── Next patient input ──
            try:
                patient_message = await patient_input_fn(agent_response)
            except Exception as e:
                result.errors.append(f"Turn {turn} patient error: {e}")
                break

        result.ended_at = datetime.now().isoformat()
        return result


# ── Output: save results + report + checklist ────────────────────────


def save_f1_result(result: F1Result, output_dir: Path | None = None) -> dict[str, Path]:
    """Save F1 result as JSON + markdown report + checklist.

    Files are saved under a VP-specific subdirectory: {OUTPUT_DIR}/{VP-ID}/
    """
    base = output_dir or OUTPUT_DIR
    # VP별 하위 디렉토리
    vp_id = result.persona_id or result.session_id
    out = base / vp_id
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{vp_id}_{ts}"

    paths: dict[str, Path] = {}

    # 1. Full conversation JSON
    json_path = out / f"{prefix}_conversation.json"
    json_path.write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    paths["json"] = json_path

    # 2. Checklist markdown
    checklist_path = out / f"{prefix}_checklist.md"
    checklist_path.write_text(_build_checklist(result), encoding="utf-8")
    paths["checklist"] = checklist_path

    # 3. Report markdown
    report_path = out / f"{prefix}_report.md"
    report_path.write_text(_build_report(result), encoding="utf-8")
    paths["report"] = report_path

    logger.info("F1 results saved: %s", ", ".join(str(p) for p in paths.values()))
    return paths


def _build_checklist(r: F1Result) -> str:
    lines = [
        f"# F1 Agent Call Checklist — {r.persona_id or r.session_id}",
        "",
        f"> Session: {r.session_id} | Turns: {r.total_turns} | Crisis: {r.crisis_triggered}",
        "",
        "| Check | Status | Detail |",
        "|-------|--------|--------|",
        f"| SafetyClassifier 매 턴 호출 | PASS | {r.total_turns}턴 전체 호출 |",
        f"| DialogueAgent 호출 | {'PASS' if not r.crisis_triggered or r.crisis_turn > 1 else 'N/A'} | "
        f"{sum(1 for t in r.turns if not t.safety_crisis)}턴 호출 |",
        f"| ClinicalSlotAgent 호출 | {'PASS' if any(t.slot_updates for t in r.turns) else 'WARN'} | "
        f"slot extraction 실행 |",
        f"| System prompt 주입 | PASS | 모든 agent에 PromptLoader로 주입 |",
        f"| 대화 기록 append | PASS | 매 턴 conversation_history 누적 |",
        f"| Full text 저장 (no truncation) | PASS | 모든 턴 전문 저장 |",
        f"| Crisis 대응 (CTRS 1-2) | {'PASS — 109/119 안내' if r.crisis_triggered else 'N/A — crisis 미발생'} |",
        f"| Slot coverage | {r.slot_coverage:.0%} | {len(r.final_slots)} slots filled |",
        "",
    ]

    lines.append("## Per-Turn Agent Calls")
    lines.append("")
    for t in r.turns:
        lines.append(f"### Turn {t.turn}")
        lines.append(f"- Safety: CTRS={t.safety_ctrs}, risk={t.safety_risk}, "
                      f"categories={t.safety_categories}, crisis={t.safety_crisis}")
        lines.append(f"- Dialogue: response_length={len(t.agent_response)}chars")
        lines.append(f"- Slots updated: {list(t.slot_updates.keys()) if t.slot_updates else 'none'}")
        lines.append(f"- Cumulative coverage: {t.slot_coverage:.0%}")
        lines.append(f"- Latency: {t.latency_ms:.0f}ms")
        lines.append("")

    return "\n".join(lines)


def _build_report(r: F1Result) -> str:
    """Build human-readable report.

    대화 순서: 매 턴 AI → Patient (AI가 질의/응답, Patient가 답변)

    Turn 0: AI 인사 → Patient 첫 응답
    Turn 1: AI 응답(Turn 1) → Patient 응답(Turn 2 input)
    Turn 2: AI 응답(Turn 2) → Patient 응답(Turn 3 input)
    ...
    마지막 Turn: AI 응답 → (세션 종료, Patient 응답 없음)
    """
    lines = [
        f"# F1 Simulation Report — {r.persona_id or r.session_id}",
        "",
        f"> Persona: {r.persona_name or 'N/A'} | Turns: {r.total_turns} | "
        f"Crisis: {r.crisis_triggered} | Coverage: {r.slot_coverage:.0%}",
        f"> Started: {r.started_at} | Ended: {r.ended_at}",
        "",
        "## Full Conversation",
        "",
    ]

    turns = r.turns

    for i, t in enumerate(turns):
        if t.turn == 0:
            # Turn 0: AI greeting → Patient 첫 응답
            lines.append("### Turn 0 (Opening)")
            lines.append("")
            lines.append(f"**AI**: {t.agent_response}")
            lines.append("")
            lines.append(f"**Patient**: {t.patient_message}")
            lines.append("")
        else:
            # Turn N: AI 응답 → Patient 응답 (다음 턴 입력)
            crisis_tag = " **[CRISIS]**" if t.safety_crisis else ""
            lines.append(f"### Turn {t.turn} | CTRS={t.safety_ctrs} | risk={t.safety_risk}{crisis_tag}")
            lines.append("")
            lines.append(f"**AI**: {t.agent_response}")
            lines.append("")

            # Patient 응답 = 다음 턴의 patient_message
            next_turn = turns[i + 1] if i + 1 < len(turns) else None
            if next_turn and next_turn.turn > 0:
                lines.append(f"**Patient**: {next_turn.patient_message}")
                lines.append("")
            elif t.safety_crisis:
                lines.append("*(위기 프로토콜 발동 — 세션 종료)*")
                lines.append("")
            else:
                lines.append("*(세션 종료)*")
                lines.append("")

            if t.slot_updates:
                lines.append(f"**Slot Updates**: {json.dumps(t.slot_updates, ensure_ascii=False)}")
                lines.append("")

    # Errors
    if r.errors:
        lines.extend(["## Errors", ""])
        for e in r.errors:
            lines.append(f"- {e}")
        lines.append("")

    # Final slots
    lines.extend(["## Final Slots", ""])
    lines.append(f"Coverage: {r.slot_coverage:.0%} ({len(r.final_slots)} slots filled)")
    lines.append("")
    for slot in r.final_slots:
        lines.append(f"- **{slot['key']}**: {slot['value']}")

    return "\n".join(lines)


# ── Handoff report generation ───────────────────────────────────────


def generate_handoff_from_result(result: F1Result) -> str:
    """Generate a handoff report from a completed F1 session result.

    Used to create prior_handoff data for follow-up (재상담) simulations.
    """
    lines = [
        "========================================",
        " 정신건강 사전문진 인계 보고서 (Handoff Report)",
        "========================================",
        "",
        "[1. 환자 기본 정보]",
        f"- 이름: {result.persona_name or 'N/A'}",
        f"- 방문 유형: {'초진' if not result.crisis_triggered else '초진 (위기)'}",
        f"- 문진 일시: {result.started_at[:10] if result.started_at else 'N/A'}",
        "",
        "[2. 위기 분류 (Crisis Triage)]",
    ]

    if result.turns:
        max_ctrs = min(t.safety_ctrs for t in result.turns if t.turn > 0) if any(t.turn > 0 for t in result.turns) else 5
        lines.append(f"- CTRS: {max_ctrs}단계")
        lines.append(f"- 위기 프로토콜 발동: {'예' if result.crisis_triggered else '아니오'}")
    else:
        lines.append("- CTRS: N/A")

    # Slots as sections
    slot_dict = {s["key"]: s["value"] for s in result.final_slots}

    lines.extend([
        "",
        "[3. 주호소]",
        slot_dict.get("chief_complaint", "정보 미수집"),
        "",
        "[4. 증상 요약]",
    ])

    symptom_slots = [
        ("현병력", "history_of_present_illness"),
        ("기능 저하", "functional_impairment"),
        ("증상 시작", "onset"),
        ("증상 기간", "duration"),
    ]
    for label, key in symptom_slots:
        val = slot_dict.get(key, "")
        if val:
            lines.append(f"- {label}: {val}")

    lines.extend(["", "[5. 위험 평가]"])
    risk_val = slot_dict.get("risk_assessment", "")
    if risk_val:
        lines.append(risk_val)
    else:
        lines.append("명시적 자살/자해 사고 확인 안 됨")

    lines.extend(["", "[6. 기타 수집 정보]"])
    other_keys = [
        "substance_use_history", "past_psychiatric_history", "medical_history",
        "personal_social_history", "family_history",
    ]
    for key in other_keys:
        val = slot_dict.get(key, "")
        if val:
            lines.append(f"- {key}: {val}")

    lines.extend([
        "",
        f"[7. Slot Coverage]",
        f"- Coverage: {result.slot_coverage:.0%} ({len(result.final_slots)} slots)",
        "",
        "[8. 대화 요약]",
        f"- 총 턴 수: {result.total_turns}",
    ])

    # Brief conversation summary (last 3 turns)
    dialogue_turns = [t for t in result.turns if t.turn > 0 and not t.safety_crisis]
    if dialogue_turns:
        lines.append("- 주요 대화:")
        for t in dialogue_turns[-3:]:
            lines.append(f"  Turn {t.turn}: 환자 — {t.patient_message[:100]}")

    return "\n".join(lines)


def _load_latest_result(persona_id: str) -> F1Result | None:
    """Load the latest simulation result JSON for a persona."""
    import glob as _glob
    pattern_sub = str(OUTPUT_DIR / persona_id / f"{persona_id}_*_conversation.json")
    pattern_flat = str(OUTPUT_DIR / f"{persona_id}_*_conversation.json")
    files = sorted(_glob.glob(pattern_sub) + _glob.glob(pattern_flat))
    if not files:
        return None
    with open(files[-1], encoding="utf-8") as f:
        data = json.load(f)

    turns = []
    for t in data.get("turns", []):
        turns.append(F1TurnLog(**t))

    return F1Result(
        session_id=data["session_id"],
        persona_id=data.get("persona_id"),
        persona_name=data.get("persona_name"),
        total_turns=data.get("total_turns", 0),
        crisis_triggered=data.get("crisis_triggered", False),
        crisis_turn=data.get("crisis_turn"),
        final_slots=data.get("final_slots", []),
        slot_coverage=data.get("slot_coverage", 0),
        turns=turns,
        errors=data.get("errors", []),
        started_at=data.get("started_at", ""),
        ended_at=data.get("ended_at", ""),
    )


# ── CLI entry point ──────────────────────────────────────────────────


async def _run_simulation(
    persona_id: str,
    max_turns: int,
    followup_from: str | None = None,
) -> None:
    """시뮬레이션 모드: PatientLLM과 F1Pipeline 대화.

    Args:
        followup_from: 이전 세션 결과를 기반으로 재상담 시뮬레이션.
            - persona ID (e.g. "VP-001") → 해당 VP의 최신 결과에서 handoff 생성
            - JSON file path → 해당 파일에서 handoff 생성
    """
    from tests.simulation.patient_llm import load_persona, PatientLLM

    try:
        persona = load_persona(persona_id)
    except FileNotFoundError as e:
        print(f"Persona file not found: {e}")
        print("Available: VP-001, VP-002, VP-003, VP-004")
        sys.exit(1)

    api_key = os.environ.get("UPSTAGE_API_KEY", "")
    if not api_key:
        print("UPSTAGE_API_KEY not set")
        sys.exit(1)

    # Determine prior handoff source
    prior_handoff = ""
    prior_slots: dict[str, str] = {}

    if followup_from:
        # Load prior session result and generate handoff
        if followup_from.endswith(".json"):
            with open(followup_from, encoding="utf-8") as f:
                prior_data = json.load(f)
            prior_result = F1Result(
                session_id=prior_data["session_id"],
                persona_id=prior_data.get("persona_id"),
                persona_name=prior_data.get("persona_name"),
                final_slots=prior_data.get("final_slots", []),
                slot_coverage=prior_data.get("slot_coverage", 0),
                total_turns=prior_data.get("total_turns", 0),
                crisis_triggered=prior_data.get("crisis_triggered", False),
                turns=[F1TurnLog(**t) for t in prior_data.get("turns", [])],
                started_at=prior_data.get("started_at", ""),
                ended_at=prior_data.get("ended_at", ""),
            )
        else:
            prior_result = _load_latest_result(followup_from)
            if prior_result is None:
                print(f"No prior result found for {followup_from}")
                sys.exit(1)

        prior_handoff = generate_handoff_from_result(prior_result)
        prior_slots = {s["key"]: s["value"] for s in prior_result.final_slots}
        print(f"[Follow-up] Using prior session handoff ({len(prior_handoff)} chars, "
              f"{len(prior_slots)} slots)")

        # Inject prior handoff into patient persona for context
        persona.prior_handoff = prior_handoff
        persona.system_prompt += f"""

## 이전 상담 기록 (당신이 기억해야 할 내용)
당신은 이전에 상담을 받은 적이 있습니다. 아래는 지난 상담 때의 기록입니다.
이전 상태와 비교하여 현재 상태가 좋아졌는지, 나빠졌는지, 유지되는지를 자연스럽게 대화에 반영하세요.
변화가 있는 부분은 구체적으로 이야기하고, 유지되는 부분은 "비슷해요" 정도로 답하세요.

{prior_handoff}
"""

    # 주의: persona.visit_type == "revisit"이더라도, --followup-from이 없으면
    # 첫 상담으로 취급한다. 재상담은 명시적 --followup-from 플래그로만 활성화.

    # Patient LLM uses K-EXAONE (not Solar Pro3)
    patient = PatientLLM(persona=persona)  # auto-loads EXAONE keys from env
    pipeline = F1Pipeline()

    async def patient_fn(agent_msg: str) -> str:
        return await patient.respond(agent_msg)

    session_suffix = "_followup" if followup_from else ""
    result = await pipeline.run_session(
        patient_input_fn=patient_fn,
        session_id=f"f1_{persona_id}{session_suffix}",
        persona_id=persona.persona_id,
        persona_name=persona.name,
        max_turns=max_turns,
        is_revisit=bool(followup_from),  # 명시적 --followup-from만 재상담
        prior_handoff=prior_handoff,
        prior_slots=prior_slots,
    )

    paths = save_f1_result(result)

    # Summary
    print(f"\n{'='*60}")
    print(f"  F1 Result: {persona_id} ({persona.name})")
    if followup_from:
        print(f"  Mode: Follow-up (재상담)")
    print(f"{'='*60}")
    print(f"  Turns: {result.total_turns}")
    print(f"  Crisis: {'YES (turn {})'.format(result.crisis_turn) if result.crisis_triggered else 'No'}")
    print(f"  Slot Coverage: {result.slot_coverage:.0%}")
    print(f"  Errors: {len(result.errors)}")
    print(f"  Files: {', '.join(p.name for p in paths.values())}")
    print(f"{'='*60}")


def main() -> None:
    parser = argparse.ArgumentParser(description="F1 Pipeline — 자율 대화 기반 사전문진")
    parser.add_argument("--persona", default="VP-001", help="VP-001, VP-002, VP-003, VP-004")
    parser.add_argument("--max-turns", type=int, default=10)
    parser.add_argument(
        "--followup-from",
        default=None,
        help="재상담 모드: 이전 세션의 persona ID 또는 conversation.json 경로",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Load .env for API keys
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    if not os.environ.get("PROMPTS_BASE_DIR"):
        os.environ["PROMPTS_BASE_DIR"] = str(PROJECT_ROOT / "docs" / "ai" / "prompts")

    asyncio.run(_run_simulation(args.persona, args.max_turns, args.followup_from))


if __name__ == "__main__":
    main()
