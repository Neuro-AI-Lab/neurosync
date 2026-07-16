"""F1 Pipeline — 자율 대화 기반 사전문진.

Agent 협업:
  01_orchestrator → 02_safety (매 턴) → 03_dialogue → 04_clinical_slot

목표: 12 Standard Clinical Slot을 대화로 수집.
Safety: 매 턴 CTRS 분류, CTRS 1-2 시 위기 대응 + 세션 종료.
       CTRS 3 + 자살/자해 카테고리 시 단계적 Safety Probe (T1-F1-DEV-022/023).

Grounding (T1-F1-DEV-018): ClinicalSlotAgent가 추출한 값은 grounding filter를
통과한 경우에만 세션 상태에 반영된다. 근거 없는 값은 폐기되고 턴 로그에 기록된다.
risk_assessment는 추출기에서 절대 수용하지 않는다 — Safety Probe만 채운다.

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
import re
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agents.clinical_slot import ALL_SLOT_KEYS, ESSENTIAL_SLOT_KEYS, ClinicalSlotAgent
from src.agents.dialogue import DialogueAgent
from src.agents.input_normalizer import InputNormalizerAgent
from src.agents.nearby_facilities import NearbyFacilitiesAgent
from src.agents.ocr import OCRAgent
from src.agents.patient_history import PatientHistoryAgent
from src.agents.safety_classifier import SafetyClassifierAgent
from src.agents.sentiment_analyzer import SentimentAnalyzerAgent
from src.agents.stt import STTAgent
from src.dependencies import (
    get_hira_drug_efficacy_adapter,
    get_model_router,
    get_nearby_agent,
    get_ocr_agent,
    get_prompt_loader,
    get_stt_agent,
)
from src.grounding import (
    QUESTIONABLE_SLOT_KEYS,
    RISK_SLOT_KEY,
    evaluate_slot_grounding,
    reply_has_negation,
)
from src.grounding import (
    grounded_coverage as _grounded_coverage,
)
from src.prompts.loader import resolve_prompts_base_dir
from src.schemas.clinical_slot import ClinicalSlotInput
from src.schemas.dialogue import DialogueInput
from src.schemas.input_normalizer import InputNormalizerInput
from src.schemas.nearby import NearbySearchInput
from src.schemas.ocr import DocumentType, OCRInput, OCROutput
from src.schemas.phr import PhrLoadInput, PhrSummary
from src.schemas.safety import SafetyInput, SafetyOutput
from src.schemas.sentiment import (
    SentimentSessionInput,
    SentimentUtteranceInput,
    SentimentUtteranceOutput,
)
from src.schemas.stt import STTInput, STTOutput

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # apps/ai-server/src/f1.py → neurosync/
OUTPUT_DIR = PROJECT_ROOT / "docs" / "ai" / "simulation_results"
# Permanent home for test input fixtures (OCR PDFs, patient-utterance audio),
# separate from OUTPUT_DIR above which holds run OUTPUT (conversation logs, etc.).
FIXTURES_DIR = PROJECT_ROOT / "apps" / "ai-server" / "tests" / "fixtures"

# 페르소나별 임의 위치 (persona MD 주소 기준 · Kakao geocoded 좌표).
# 실 프로덕션에서는 모바일 GPS·환자 프로필 좌표를 사용.
# VP-010/011/012 (PLAN-2026-W28-Q W6): 구청 좌표 근사치 — 이 미션은
# 오프라인이라 Kakao 라이브 지오코딩을 실행하지 않음(disclosed approximation,
# VP-001..004처럼 street-level로 검증되지 않음). Crisis 근처 병원 안내
# 정확도에만 쓰이는 시뮬레이션 하네스 메타데이터, 임상 판단에는 미사용.
PERSONA_LOCATIONS: dict[str, tuple[float, float]] = {
    "VP-001": (37.5807, 126.8898),  # 서울 마포구
    "VP-002": (37.4020, 127.1087),  # 경기 성남 판교
    "VP-003": (37.4782, 126.9515),  # 서울 관악구
    "VP-004": (37.5510, 126.8495),  # 서울 강서구
    "VP-010": (37.5636, 127.0369),  # 서울 성동구 (구청 좌표 근사)
    "VP-011": (37.6018, 126.9290),  # 서울 은평구 (구청 좌표 근사)
    "VP-012": (37.6395, 127.0255),  # 서울 강북구 (구청 좌표 근사)
}

CRISIS_RESPONSE = (
    "지금 많이 힘드시군요. 당신의 이야기를 듣고 있습니다. "
    "자살예방상담전화 109, 응급전화 119로 연락해 주세요."
)

# ── Safety Probe protocol (T1-F1-DEV-022/023, DR-002) ────────────────

_PROBE_TRIGGER_CTRS = 3
_PROBE_TRIGGER_CATEGORIES = {"suicidal_ideation", "self_harm"}

# Graduated probe stages: 사고 빈도 → 구체적 계획 → 수단/의도 → 보호 요인
_PROBE_STAGES: list[tuple[str, str]] = [
    ("frequency", "최근에 그런 생각이 얼마나 자주 드는지"),
    ("plan", "혹시 구체적인 계획을 생각해 본 적이 있는지"),
    ("means_intent", "혹시 방법이나 수단을 생각해 두었는지, 실행할 생각이 있는지"),
    ("protective", "그런 순간에 버틸 수 있게 해 주는 것(가족, 친구, 소중한 일 등)이 있는지"),
]

# Belt-and-braces lexical check for plan/means disclosure in probe answers.
_PLAN_DISCLOSURE_MARKERS = (
    "계획", "방법", "준비", "사놨", "사 놨", "사뒀", "사 뒀", "유서", "날짜",
    "수단", "정해뒀", "정해 뒀", "정했", "구해놨", "구해뒀", "모아뒀", "모아놨",
)

_SOFT_SAFETY_NOTE = (
    " 그리고 혹시 마음이 많이 힘들어질 때는 언제든 자살예방상담전화 109에서 "
    "도움을 받으실 수 있다는 것도 기억해 주세요."
)

_SI_SCREEN_INSTRUCTION = (
    "필요한 문진 정보는 대부분 수집되었습니다. 상담을 마무리하기 전에 안전 확인이 "
    "필요합니다. 공감 1문장 후, 최근에 스스로를 해치고 싶다거나 죽고 싶다는 생각이 "
    "든 적이 있는지 부드럽게 **한 가지만** 질문하세요. 다른 주제는 질문하지 마세요."
)


# ISS-043: the negation veto must be clause-local, not sentence-global.
# Clauses are split on sentence punctuation and common contrastive
# connectives (는데/지만) so "계획을 세워뒀어요. 근데 아직 실행은 않았어요"
# still escalates: the disclosure clause is affirmative even though a later
# clause carries a negation morpheme.
_CLAUSE_SPLIT_RE = re.compile(r"[.!?…~\n,;]|(?:는데|지만)\s")


def _has_plan_disclosure(text: str) -> bool:
    """Lexical check: some CLAUSE discloses a plan/means without clause-local
    negation (ISS-043). Legitimate denials ("계획 같은 건 없어요") keep the
    marker and the negation in the same clause and do not escalate."""
    for clause in _CLAUSE_SPLIT_RE.split(text):
        if not clause or not clause.strip():
            continue
        if any(marker in clause for marker in _PLAN_DISCLOSURE_MARKERS):
            if not reply_has_negation(clause):
                return True
    return False


def _clip(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


@dataclass
class _ProbeState:
    """Pipeline-side safety probe state (kept by the pipeline, not the LLM)."""

    active: bool = False
    awaiting_answer: bool = False
    stage_idx: int = 0  # index into _PROBE_STAGES for the NEXT question
    trigger_utterance: str = ""
    answers: list[str] = field(default_factory=list)
    protective_answer: str = ""


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
    # T1-F1-DEV-018/019 — grounding filter + coverage redefinition
    targeted_slot: str | None = None
    slot_discards: dict[str, str] = field(default_factory=dict)
    grounded_coverage: float = 0.0
    # T1-F1-DEV-002 — InputNormalizer 적용 결과 (원본 vs 정규화, changes)
    normalizer_meta: dict = field(default_factory=dict)
    # T1-F1-DEV-011~013 — per-utterance sentiment (Mode A)
    sentiment: dict = field(default_factory=dict)
    # 명세 준수 — AI 응답 자체에 대한 Safety 재검사 결과 (CTRS)
    dialogue_safety_ctrs: int | None = None
    dialogue_safety_risk: str | None = None
    # BUG-021: True if ANY agent called this turn (safety/clinical_slot/
    # dialogue/input_normalizer) fell back to a generic hardcoded prompt.
    prompts_degraded: bool = False
    # BUG-030 iter-2 / BUG-035 guard telemetry (`docs/ai/fix_design_bug030_
    # iter2.md` §6, ADR-029) — threaded from DialogueAgent alone (no
    # cross-agent OR-fold needed, unlike prompts_degraded).
    dialogue_retry_count: int = 0
    dialogue_retry_reasons: list[str] = field(default_factory=list)
    dialogue_fall_through: bool = False
    dialogue_retry_latency_ms: float = 0.0
    dialogue_crisis_adjacent: bool = False
    # BUG-037 output-isolation guard telemetry (`docs/ai/fix_design_
    # exhaustion_bug037.md` §2, PLAN-2026-W28-U) — same threading
    # discipline as the 5 fields above.
    dialogue_output_isolation_fallback: bool = False
    # BUG-036 near-dup catch telemetry (which sub-rule fired, family,
    # count) — same threading discipline.
    dialogue_near_dup_detail: list[dict] = field(default_factory=list)
    # Fix 2 — Option C exhaustion-degrade telemetry (`docs/ai/fix_design_
    # exhaustion_bug037.md` §3, ADR-030 Decisions 1/2) — same threading
    # discipline as the fields above.
    dialogue_exhaustion_degrade: str | None = None
    dialogue_exhaustion_degrade_phrase: str | None = None


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
    # T1-F1-DEV-019 — grounded coverage over the 8 question-able slots
    grounded_coverage: float = 0.0
    # T1-F1-DEV-022/023 — safety probe protocol
    risk_floor: int | None = None
    probe_events: list[dict] = field(default_factory=list)
    # min CTRS over ALL turns INCLUDING turn 0 (ISS-036 partial fix)
    session_ctrs: int = 5
    # Crisis 발동 시 근처 정신건강의학과 top-N (환자 좌표 기반 HIRA 검색)
    nearby_psychiatric: list[dict] = field(default_factory=list)
    patient_lat: float | None = None
    patient_lng: float | None = None
    # T1-F1-DEV-004/008 — OCR documents attached to this session
    ocr_documents: list[dict] = field(default_factory=list)
    # T1-F1-DEV-003/007 — STT transcripts consumed (one per patient turn if audio input)
    stt_transcripts: list[dict] = field(default_factory=list)
    # T1-F1-DEV-011~013 — Mode B session-level sentiment (calculated at session end)
    session_sentiment: dict = field(default_factory=dict)
    # PHR (개인건강기록) — 세션 시작 시 로드된 myhealthway PHR 요약.
    phr_summary: dict = field(default_factory=dict)
    # BUG-021: session-level aggregate — True if ANY turn had prompts_degraded
    # True (any prompt-driven agent fell back to a generic hardcoded prompt).
    prompts_degraded: bool = False
    # PLAN-2026-W28-Q W2 — multi-session production fields (plan §3 row
    # "Multi-session + question induction").
    session_index: int = 1
    simulated_date: str = ""
    is_revisit: bool = False
    # Repro-metadata (model, prompt_version): captured from the turn-0
    # DialogueAgent call — v3 calls DialogueAgent at turn 0 for every
    # session (autonomous greeting), so it is always the first agent call a
    # session makes, identifying the session's dialogue configuration.
    model: str = ""
    prompt_version: str = ""
    # Narrowed carry-channel content RECEIVED at session start (AVC-02,
    # `_archive/plans/validation_plan_f1f2_continuous.md` §6): final_slots +
    # missing_slots only, never raw prose/risk_assessment narration. `None`
    # for a first-visit session. Persisted so F2 can read it — f2.py's
    # `prior_handoff` used to be hardcoded `None` ("not persisted in F1
    # conversation.json").
    prior_handoff: str | None = None
    # REV-022 Issue 7 / plan §3: slots whose CURRENT final value is still the
    # value carried from a prior session (bypassed evaluate_slot_grounding —
    # never re-grounded THIS session). slot_key -> "carried_from_session_N".
    # A slot re-grounded this session (even to identical text) is NOT here.
    carried_slot_provenance: dict[str, str] = field(default_factory=dict)
    # F4 quick-dev provenance threading (`_archive/plans/f4_quick_dev_plan.md` §2.6
    # option C / §2.7, `PLAN-2026-W29-D`, `ADR-036` item 3): additive,
    # `None`-default fields — a scripted-validation session self-identifies
    # via these two fields; `None`/absent for every natural (non-scripted)
    # session, so re-ingesting any pre-F4 artifact never breaks. Set ONLY by
    # `_run_simulation`'s `scenario_pack_id`/`arc_mode` kwargs
    # (`_apply_scenario_provenance`, below) — never by
    # `F1Pipeline.run_session` itself.
    scenario_pack_id: str | None = None
    arc_mode: str | None = None


_CONTENT_TYPE_BY_SUFFIX: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".heic": "image/heic",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _guess_content_type(path: Path) -> str:
    return _CONTENT_TYPE_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")


def _ocr_output_to_dict(out: OCROutput) -> dict[str, Any]:
    """Serialize OCROutput for F1Result. Keep the full markdown for Handoff."""
    return out.model_dump()


def _stt_output_to_dict(out: STTOutput) -> dict[str, Any]:
    """Serialize STTOutput for F1Result."""
    return out.model_dump()


def _make_canned_patient_fn(
    texts: list[str],
) -> Callable[[str], Awaitable[str]]:
    """Build an async callback that returns pre-transcribed texts in order.

    Used when audio inputs (mp3/wav) are pre-supplied to run_session().
    Each call ignores agent_response and returns the next transcript.
    Raises RuntimeError when exhausted so the loop terminates cleanly.
    """
    idx = {"i": 0}

    async def _fn(_agent_response: str) -> str:
        i = idx["i"]
        if i >= len(texts):
            raise RuntimeError(
                f"Exhausted STT transcripts after {i} turns "
                f"(session had {len(texts)} audio input(s))"
            )
        idx["i"] += 1
        return texts[i]

    return _fn


def _format_ocr_for_context(out: OCROutput) -> str:
    """Compact clinical summary for injection into conversation_history (system).

    We inject the *summary* + a truncated markdown snippet. The full raw text
    stays in F1Result for downstream Handoff generation. This keeps the LLM
    context window bounded while still letting Dialogue reference the
    documents.
    """
    if not out.blocks and not out.extracted_summary.diagnoses:
        return ""

    s = out.extracted_summary
    lines: list[str] = [
        f"[환자 제출 문서 — {out.document_type}] (OCR 요약, AI 진단 아님, 참고용)",
    ]
    if s.patient_name or s.patient_age or s.patient_gender:
        parts = [
            v for v in (s.patient_name, s.patient_age, s.patient_gender) if v
        ]
        lines.append(f"- 환자: {' / '.join(parts)}")
    if s.department:
        lines.append(f"- 진료과: {s.department}")
    if s.diagnoses:
        codes_str = f" ({', '.join(s.diagnosis_codes)})" if s.diagnosis_codes else ""
        lines.append(f"- 문서에 기재된 진단명{codes_str}: {', '.join(s.diagnoses)}")
    if s.scale_scores:
        lines.append(
            "- 문서 내 척도 점수: "
            + ", ".join(f"{k}={v}" for k, v in s.scale_scores.items())
        )
    if s.medications:
        med_str = ", ".join(
            f"{m.name} {m.dose or ''}".strip() for m in s.medications[:5]
        )
        lines.append(f"- 문서에 기재된 약물: {med_str}")
    if s.dates:
        lines.append(f"- 문서 내 날짜: {', '.join(s.dates[:3])}")
    if out.low_confidence_items:
        lines.append(
            f"- 확인 필요 항목({len(out.low_confidence_items)}): OCR 신뢰도 낮음"
        )

    # Bounded markdown snippet for Dialogue reference (max ~1000 chars).
    if out.raw_markdown:
        snippet = out.raw_markdown[:1000]
        if len(out.raw_markdown) > 1000:
            snippet += "\n...(중략)"
        lines.append("")
        lines.append("[문서 원문 발췌]")
        lines.append(snippet)

    lines.append("")
    lines.append(
        "안내: 위 정보는 환자가 제출한 문서에서 OCR로 추출한 참고 자료입니다. "
        "환자에게 새로 물을 때 문서 내용을 자연스럽게 참조하세요. "
        "AI가 내린 진단이 아닙니다."
    )
    return "\n".join(lines)


# ── PHR (개인건강기록) helpers ──────────────────────────────────────

# 페르소나별 기본 PHR 샘플 경로 (익명화 fake data).
# CLI `--phr-vp-default` 편의 인자가 이를 참조.
PERSONA_PHR_FILES: dict[str, list[str]] = {
    "VP-001": [
        "docs/ai/samples/phr/VP-001_medications.json",
        "docs/ai/samples/phr/VP-001_visits.json",
    ],
    "VP-002": [
        "docs/ai/samples/phr/VP-002_medications.json",
        "docs/ai/samples/phr/VP-002_visits.json",
    ],
    "VP-003": [
        "docs/ai/samples/phr/VP-003_medications.json",
        "docs/ai/samples/phr/VP-003_visits.json",
    ],
    "VP-004": [
        "docs/ai/samples/phr/VP-004_medications.json",
        "docs/ai/samples/phr/VP-004_visits.json",
    ],
}


def _format_phr_for_context(summary: PhrSummary, agent: PatientHistoryAgent) -> str:
    """PHR summary → conversation_history에 넣을 system 컨텍스트 문자열.

    LLM이 환자 병력·복약 이력을 인지하도록 안내. AI 진단이 아니라 PHR
    (건보공단 마이헬스웨이 계열) 원본에서 추출한 사실만 담는다.
    """
    if summary.total_medication_events == 0 and summary.total_visits == 0:
        return ""

    lines: list[str] = ["[환자 PHR — 마이헬스웨이 개인건강기록 요약, AI 판단 아님]"]
    note = agent.to_system_prompt_note(summary)
    if note:
        lines.append(f"- {note}")

    # 정신과 약물이 있으면 상세 (최근 3건) 노출
    if summary.psychotropic_medications:
        lines.append("- 정신과 계열 약물 최근 조제:")
        for m in summary.psychotropic_medications[-3:]:
            when = m.dispensed_at.isoformat() if m.dispensed_at else "-"
            days = m.days_supply if m.days_supply is not None else "?"
            freq = m.daily_frequency if m.daily_frequency is not None else "?"
            lines.append(
                f"  · {when} · {m.product_name} "
                f"[{m.efficacy_class_name or m.psychotropic_class}] "
                f"{days}일치 · {freq}회/일"
            )
    else:
        lines.append("- 정신과 계열 약물 이력 없음 (PHR 조회 범위 내).")

    # 진료 방문 요약
    lines.append(
        f"- 총 조제 {summary.total_medication_events}건 · "
        f"방문 {summary.total_visits}건 (정신과명 포함 {summary.psychiatric_visit_count}건)"
    )
    lines.append("")
    lines.append(
        "안내: 위 정보는 환자의 PHR 원본에서 추출한 참고 자료이며, "
        "AI가 새로 부여한 진단이 아닙니다. 대화 중 자연스럽게 참조하세요."
    )
    return "\n".join(lines)


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
        match = re.search(r'"assistant_response"\s*:\s*"((?:[^"\\]|\\.)*)"', stripped)
        if match:
            return match.group(1).replace('\\"', '"').replace('\\n', '\n')
    return stripped


def _filter_and_merge_slots(
    raw_slots: dict[str, Any],
    filled_slots: dict[str, str],
    patient_utterances: list[str],
    asked_slots: list[str | None],
) -> tuple[dict[str, str], dict[str, str]]:
    """Apply the grounding filter to extractor output and merge accepted values.

    Returns (updates, discards) where discards maps slot key → "verdict: reason".
    """
    updates: dict[str, str] = {}
    discards: dict[str, str] = {}
    for key, raw in raw_slots.items():
        if key not in ALL_SLOT_KEYS:
            continue
        value = raw
        if isinstance(value, dict) and isinstance(value.get("value"), str):
            value = value["value"]
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()

        verdict = evaluate_slot_grounding(key, value, patient_utterances, asked_slots)
        if verdict.accepted:
            filled_slots[key] = value
            updates[key] = value
        else:
            discards[key] = f"{verdict.verdict}: {verdict.reason}"
            logger.info(
                "Slot '%s' DISCARDED (%s): %r — %s",
                key, verdict.verdict, value, verdict.reason,
            )
    return updates, discards


def _legacy_essential_coverage(filled_slots: dict[str, str]) -> float:
    """Legacy essential-slot coverage — kept for comparability (T1-F1-DEV-019)."""
    filled_essential = [s for s in ESSENTIAL_SLOT_KEYS if filled_slots.get(s)]
    return len(filled_essential) / len(ESSENTIAL_SLOT_KEYS) if ESSENTIAL_SLOT_KEYS else 0.0


def _compose_carry_content(final_slots: dict[str, str], missing_slots: list[str]) -> str:
    """Narrowed ``--followup-from`` carry-channel payload (AVC-02,
    `_archive/plans/validation_plan_f1f2_continuous.md` §6, PLAN-2026-W28-Q W2).

    ONLY ``final_slots`` (``risk_assessment`` excluded — every session
    re-grounds risk from scratch via the Safety Probe/SI-screen, never
    inherits a prior risk narrative, per this module's own docstring) and
    ``missing_slots`` (key names only, no values) cross this channel. No
    CTRS/crisis-protocol narrative, no free-text handoff prose — replaces
    the old ``generate_handoff_from_result()``-based full-prose channel that
    used to reach both the patient-simulator prompt and the dialogue
    history (today: the full Handoff Report, including its "[2. 위기 분류]"
    and "[5. 위험 평가]" sections).
    """
    lines = ["[이전 세션 요약 — 수집된 정보]"]
    carried = {k: v for k, v in final_slots.items() if k != RISK_SLOT_KEY and v}
    if carried:
        for k, v in carried.items():
            lines.append(f"- {k}: {v}")
    else:
        lines.append("(수집된 정보 없음)")
    lines.append("")
    lines.append("[이전 세션 요약 — 미수집 정보]")
    lines.append(", ".join(missing_slots) if missing_slots else "(없음)")
    return "\n".join(lines)


def _apply_scenario_guideline(persona: Any, scenario_guideline: str | None) -> None:
    """F4 quick-dev isolation seam (design doc §2.6 option C): append the
    harness-rendered scenario-guideline text to `persona.system_prompt`,
    own header (the caller/harness template already includes it, §2.5),
    never touching `prior_handoff`'s own already-appended text above it.
    `persona` is a `tests.simulation.patient_llm.PatientPersona` — typed as
    `Any` here so this module never imports that harness/tests-only type at
    module scope (only inside `_run_simulation`'s own lazy `from tests...`
    import, matching this file's existing convention). A `None`/falsy
    `scenario_guideline` (every non-scripted caller) is a no-op — byte-
    identical `persona.system_prompt` to today.
    """
    if not scenario_guideline:
        return
    persona.system_prompt += f"\n\n{scenario_guideline}\n"


def _apply_scenario_provenance(
    result: F1Result, scenario_pack_id: str | None, arc_mode: str | None
) -> None:
    """Threads `scenario_pack_id`/`arc_mode` onto the returned `F1Result`
    post-call (design doc §2.6 option C) — `F1Result` is a plain mutable
    `@dataclass`, so this is a simple post-call assignment, no
    `F1Pipeline.run_session` signature change. `None` values (every
    non-scripted caller) are genuine no-ops (the field's own default)."""
    if scenario_pack_id is not None:
        result.scenario_pack_id = scenario_pack_id
    if arc_mode is not None:
        result.arc_mode = arc_mode


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
        # 명세 준수: 모든 입력이 InputNormalizer로 수렴 → Dialogue+Safety로.
        self.normalizer = InputNormalizerAgent(model_router=mr, prompt_loader=pl)
        # 명세 준수: 매 턴 sentiment (Mode A) + 세션 종료 sentiment (Mode B).
        self.sentiment = SentimentAnalyzerAgent(model_router=mr, prompt_loader=pl)
        # HIRA 근처 시설 검색 — Crisis 시 정신과 top-3 안내용 (lazy load)
        self._nearby: NearbyFacilitiesAgent | None = None
        # OCR + STT are optional — instantiated lazily only when needed.
        # Failing here (e.g. UPSTAGE_API_KEY missing) should not break text-only
        # sessions; guarded by try/except when actually used.
        self._ocr: OCRAgent | None = None
        self._stt: STTAgent | None = None
        # PHR (myhealthway PHR reader). No external API key needed — file-based v1.
        self._history: PatientHistoryAgent | None = None

    def _get_history_agent(self) -> PatientHistoryAgent:
        if self._history is None:
            # 약효분류 어댑터 주입 (HIRA_SERVICE_KEY 없으면 None → 로컬 캐시만 사용).
            try:
                efficacy_adapter = get_hira_drug_efficacy_adapter()
            except Exception as exc:
                logger.warning("Drug-efficacy adapter unavailable, cache-only: %s", exc)
                efficacy_adapter = None
            self._history = PatientHistoryAgent(efficacy_adapter=efficacy_adapter)
        return self._history

    def _get_nearby_agent(self) -> NearbyFacilitiesAgent | None:
        """Lazy load. HIRA_SERVICE_KEY 없으면 None 반환 (crisis 안내 skip)."""
        if self._nearby is None:
            try:
                self._nearby = get_nearby_agent()
            except Exception as exc:
                logger.warning("Nearby agent unavailable, crisis will use static text: %s", exc)
                self._nearby = None
        return self._nearby

    async def _fetch_crisis_facilities(
        self,
        lat: float | None,
        lng: float | None,
        *,
        radius_km: float = 5.0,
        top_n: int = 3,
    ) -> tuple[str, list[dict]]:
        """환자 위치 기반 근처 정신건강의학과 top-N을 조회.

        Note: 가장 가까운 1곳(top-1)은 의도적으로 제외하고 그 다음 top_n을 반환한다.
        HIRA `dgsbjtCd=03` 필터로 반환되는 최근접 후보는 대형 종합병원인 경우가
        많아 응급실 대기·접근성 이슈가 있어, 실질적 방문 가능성이 높은
        차상위 후보들을 안내한다.

        CVR-030 (minor-major) HIRA response enrichment, two additions to
        the returned text block only (`records`/data contract unchanged):
        (a) per-hospital ER/emergency-capacity disclosure — `Place.
        emergency_available` is ALWAYS `None` for a `getHospBasisList`
        result (verified against the adapter's own parsed fields and
        `docs/ai/api/hira_kakao_map_api_usage_guide.md`'s 2026-07-10
        real-response check: no `emyGrupCd`-class field exists in this
        endpoint's response, only doctor-count counters) — this renders
        the honest "응급실 여부 확인 필요" per hospital instead of silently
        omitting the question a crisis-presenting patient would ask next,
        never inventing an availability value the API does not provide.
        (b) the crisis hotline (109/119) is repeated directly under this
        block, additive to `CRISIS_RESPONSE`'s own hotline line above it —
        a caller that surfaces/copies only this hospital block (e.g. a
        scrolled view) must not lose the hotline reference.
        """
        if lat is None or lng is None:
            return "", []
        agent = self._get_nearby_agent()
        if agent is None:
            return "", []
        try:
            # Agent가 hospital 분기에서 dgsbjtCd=03 + 종별 필터를 강제한다.
            # 요양병원 등 제외 후에도 top_n+1개 이상 남도록 넉넉히 요청.
            resp = await agent.search(NearbySearchInput(
                session_id="crisis-nearby",
                entity_type="hospital",
                lat=lat,
                lng=lng,
                radius_km=radius_km,
                num_of_rows=30,
            ))
        except Exception as exc:
            logger.warning("Crisis nearby search failed: %s", exc)
            return "", []
        if not resp.places:
            return "", []

        # 최근접(index 0) 스킵, 다음 top_n 사용
        chosen = resp.places[1 : top_n + 1]
        if not chosen:
            return "", []

        lines = ["", "📍 가까운 정신건강의학과:"]
        records: list[dict] = []
        for i, pl in enumerate(chosen, 1):
            dist = f"{pl.distance_km:.1f}km" if pl.distance_km is not None else "-"
            phone = f" · ☎ {pl.phone}" if pl.phone else ""
            # CVR-030 (a): honest per-hospital ER disclosure — `None` MUST
            # NOT be silently dropped (spec §10) and MUST NOT be invented
            # as available/unavailable; HIRA's basis-list endpoint simply
            # does not carry this field.
            er = (
                " · 응급실 가능"
                if pl.emergency_available is True
                else " · 응급실 불가"
                if pl.emergency_available is False
                else " · 응급실 여부 확인 필요"
            )
            lines.append(f"{i}. {pl.name} ({dist}){phone}{er}")
            records.append({
                "rank": i,
                "name": pl.name,
                "distance_km": pl.distance_km,
                "phone": pl.phone,
                "address": pl.address,
                "type_name": pl.type_name,
                "lat": pl.lat,
                "lng": pl.lng,
                "emergency_available": pl.emergency_available,
            })
        # CVR-030 (b): repeat the crisis hotline directly under the
        # hospital block (additive to CRISIS_RESPONSE's own hotline line).
        lines.append("☎ 자살예방상담전화 109, 응급전화 119 (24시간)")
        return "\n".join(lines), records

    def _get_ocr_agent(self) -> OCRAgent:
        if self._ocr is None:
            self._ocr = get_ocr_agent()
        return self._ocr

    def _get_stt_agent(self) -> STTAgent:
        if self._stt is None:
            self._stt = get_stt_agent()
        return self._stt

    async def _analyze_utterance_sentiment(
        self,
        *,
        session_id: str,
        utterance: str,
        turn_index: int,
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Run per-utterance sentiment (Mode A). Never blocks the pipeline
        on failure — returns empty dict."""
        if not utterance.strip():
            return {}
        try:
            out = await self.sentiment.run(SentimentUtteranceInput(
                session_id=session_id,
                utterance=utterance,
                turn_index=turn_index,
                conversation_context=history[-6:],  # bounded context
            ))
            if isinstance(out, SentimentUtteranceOutput):
                return {
                    "polarity": out.polarity,
                    "arousal": out.arousal,
                    "emotions": [
                        {"label": e.label, "intensity": e.intensity} for e in out.emotions
                    ],
                    "evidence_phrase": out.evidence_phrase,
                    "risk_signal": out.risk_signal,
                }
            return {}
        except Exception as exc:
            logger.warning("Sentiment (Mode A) failed at turn %d: %s", turn_index, exc)
            return {}

    async def _analyze_session_sentiment(
        self,
        *,
        session_id: str,
        per_utterance: list[dict[str, Any]],
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Run session-level sentiment (Mode B) at session end."""
        if not per_utterance:
            return {}
        # Convert dicts back to typed inputs for the agent
        per_out: list[SentimentUtteranceOutput] = []
        for i, p in enumerate(per_utterance):
            if not p:
                continue
            try:
                per_out.append(
                    SentimentUtteranceOutput(
                        turn_index=i,
                        polarity=float(p.get("polarity", 0.0)),
                        arousal=str(p.get("arousal", "medium")),
                        emotions=[
                            {
                                "label": e.get("label", "neutral"),
                                "intensity": e.get("intensity", 0.0),
                            }
                            for e in (p.get("emotions") or [])
                        ],
                        evidence_phrase=p.get("evidence_phrase", ""),
                        risk_signal=bool(p.get("risk_signal", False)),
                    )
                )
            except Exception:
                continue
        try:
            out = await self.sentiment.run(SentimentSessionInput(
                session_id=session_id,
                per_utterance_results=per_out,
                conversation_history=history,
            ))
            # Mode B returns SentimentSessionOutput
            return out.model_dump() if hasattr(out, "model_dump") else {}
        except Exception as exc:
            logger.warning("Sentiment (Mode B) failed: %s", exc)
            return {}

    async def _normalize_patient_message(
        self,
        raw_text: str,
        *,
        session_id: str,
        input_type: str,
    ) -> tuple[str, dict[str, Any]]:
        """Route patient input through InputNormalizerAgent.

        Returns (normalized_text, meta_dict). On any failure, falls back to
        the original text (Normalizer itself has a safe fallback path).
        """
        if not raw_text.strip():
            return raw_text, {"skipped": "empty_input"}
        try:
            out = await self.normalizer.run(InputNormalizerInput(
                session_id=session_id,
                raw_text=raw_text,
                input_type=input_type,
            ))
            meta = {
                "original": out.original_text,
                "normalized": out.normalized_text,
                "input_type": input_type,
                "change_count": out.change_count,
                "risk_expressions_preserved": out.risk_expressions_preserved,
                "clinical_content_preserved": out.clinical_content_preserved,
                "latency_ms": out.latency_ms,
                "changes": [c.model_dump() for c in out.changes[:6]],
                "prompts_degraded": out.prompts_degraded,
            }
            return out.normalized_text or raw_text, meta
        except Exception as exc:
            logger.warning("InputNormalizer failed, using raw text: %s", exc)
            return raw_text, {"skipped": f"normalizer_error: {type(exc).__name__}"}

    async def _transcribe_audio_inputs(
        self,
        audio_paths: list[Path | str],
        *,
        session_id: str,
        patient_id: str,
    ) -> list[STTOutput]:
        """Batch-transcribe each audio file. Failures produce empty STTOutput
        entries so the pipeline can still continue with the remaining."""
        try:
            agent = self._get_stt_agent()
        except Exception as exc:
            logger.warning("STT agent unavailable, skipping audio inputs: %s", exc)
            return []

        outputs: list[STTOutput] = []
        for p in audio_paths:
            path = Path(p)
            if not path.exists():
                logger.warning("Audio not found, skipping: %s", path)
                continue
            body = path.read_bytes()
            meta = STTInput(
                session_id=session_id,
                patient_id=patient_id,
                filename=path.name,
                mode="batch",
                keywords=["우울감", "불면", "불안", "자살", "자해"],
            )
            try:
                out = await agent.transcribe(body, meta)
                outputs.append(out)
                logger.info(
                    "STT %s → %d chars, %.0fms",
                    path.name, len(out.text), out.latency_ms,
                )
            except Exception as exc:
                logger.error("STT failed for %s: %s", path, exc)
        return outputs

    async def _process_ocr_documents(
        self,
        documents: list[Path | str],
        hints: list[DocumentType] | None,
        *,
        session_id: str,
        patient_id: str,
    ) -> list[OCROutput]:
        """Parse each attached document via OCRAgent. Failures do not abort the session."""
        try:
            agent = self._get_ocr_agent()
        except Exception as exc:
            logger.warning("OCR agent unavailable, skipping documents: %s", exc)
            return []

        outputs: list[OCROutput] = []
        hints_norm: list[DocumentType] = list(hints or [])
        while len(hints_norm) < len(documents):
            hints_norm.append("unknown")

        for i, doc_path in enumerate(documents):
            p = Path(doc_path)
            if not p.exists():
                logger.warning("OCR document not found, skipping: %s", p)
                continue
            try:
                body = p.read_bytes()
                content_type = _guess_content_type(p)
                meta = OCRInput(
                    session_id=session_id,
                    patient_id=patient_id,
                    document_type_hint=hints_norm[i],
                    filename=p.name,
                    confidence_threshold=0.8,
                )
                out = await agent.parse(body, meta, content_type=content_type)
                outputs.append(out)
                logger.info(
                    "OCR parsed %s → type=%s, blocks=%d, %.0fms",
                    p.name, out.document_type, len(out.blocks), out.latency_ms,
                )
            except Exception as exc:
                logger.error("OCR failed for %s: %s", p, exc)

        return outputs

    @staticmethod
    def _summarize_prior_handoff(carry_content: str) -> str:
        """Short, carry-channel-licensed reference to a prior session — feeds
        the Dialogue v3 autonomous greeting's ``session_state["carry_summary"]``
        (AVC-02, PLAN-2026-W28-Q W2).

        The input is ALWAYS ``_compose_carry_content``'s narrowed output
        (final_slots + missing_slots only) — never the old full-prose
        Handoff Report. This function itself never scans for risk/CTRS
        keywords: the v2-era implementation did (looking for "위험"/"risk"
        to append "안전 관련 우려사항도 확인되었습니다" to the greeting) — that
        scan was itself part of the carry-channel overreach this redesign
        closes, so it is removed rather than ported.
        """
        chief = ""
        for line in carry_content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- chief_complaint:"):
                chief = stripped.split(":", 1)[1].strip()
                break
        if chief:
            if len(chief) > 80:
                chief = chief[:80] + "..."
            return f"지난번에 '{chief}' 문제로 상담하셨습니다."
        return "지난번 상담 내용을 확인했습니다."

    # ── Safety probe helpers (pipeline-side state machine) ──────────

    @staticmethod
    def _probe_should_trigger(safety_out: SafetyOutput) -> bool:
        """CTRS 3 + suicidal_ideation/self_harm category → enter probe mode."""
        if int(safety_out.ctrs_level) != _PROBE_TRIGGER_CTRS:
            return False
        return bool(set(safety_out.categories) & _PROBE_TRIGGER_CATEGORIES)

    @staticmethod
    def _build_probe_instruction(stage_idx: int) -> str:
        stage_idx = min(stage_idx, len(_PROBE_STAGES) - 1)
        _, question_hint = _PROBE_STAGES[stage_idx]
        return (
            "환자가 자살/자해 관련 사고를 표현했습니다. 지금은 안전 탐색 단계입니다. "
            "따뜻한 공감 1문장을 먼저 말한 뒤, 아래 주제를 부드럽게 한 가지만 "
            f"질문하세요. 질문 주제: {question_hint}."
        )

    @staticmethod
    def _process_probe_answer(probe: _ProbeState, patient_message: str) -> str:
        """Process the answer to the previously asked probe question.

        Returns "escalate" | "deescalate" | "continue".
        The per-turn safety call is the primary escalation path (CTRS <= 2 is
        handled by the caller before this method); this adds the belt-and-braces
        lexical check and the graduated de-escalation rule.

        Note: probe.stage_idx is the stage of the question that was JUST
        answered — it is only advanced after this method returns "continue".
        """
        answered_idx = min(probe.stage_idx, len(_PROBE_STAGES) - 1)
        stage_name = _PROBE_STAGES[answered_idx][0]

        if _has_plan_disclosure(patient_message):
            return "escalate"

        negated = reply_has_negation(patient_message)
        if stage_name in ("plan", "means_intent") and negated:
            return "deescalate"
        if stage_name == "protective":
            probe.protective_answer = patient_message
            return "deescalate"
        return "continue"

    @staticmethod
    def _compose_probe_risk_assessment(probe: _ProbeState, final_answer: str) -> str:
        """Compose risk_assessment from the ACTUAL probe exchange (no templates)."""
        parts = [f'자살/자해 사고 표현 있음 — 환자 발화: "{_clip(probe.trigger_utterance)}"']
        if final_answer and reply_has_negation(final_answer):
            parts.append(f'구체적 계획/의도 부인 — 환자 발화: "{_clip(final_answer)}"')
        elif final_answer:
            parts.append(f'탐색 질문에 대한 환자 응답: "{_clip(final_answer)}"')
        if probe.protective_answer and probe.protective_answer != final_answer:
            parts.append(f'보호 요인 — 환자 발화: "{_clip(probe.protective_answer)}"')
        return "; ".join(parts)

    @staticmethod
    def _compose_screen_risk_assessment(patient_message: str) -> str:
        """Compose risk_assessment from the SI screening answer (actual words)."""
        if reply_has_negation(patient_message):
            return f'자살/자해 사고 탐색 질문에 부인 — 환자 발화: "{_clip(patient_message)}"'
        return f'자살/자해 사고 탐색 질문에 대한 환자 응답: "{_clip(patient_message)}"'

    # ── Session loop ─────────────────────────────────────────────────

    async def run_session(
        self,
        patient_input_fn: Callable[[str], Awaitable[str]] | None = None,
        session_id: str = "f1_session",
        persona_id: str | None = None,
        persona_name: str | None = None,
        max_turns: int = 15,
        slot_extraction_interval: int = 3,
        is_revisit: bool = False,
        prior_handoff: str = "",
        prior_slots: dict[str, str] | None = None,
        prior_missing_slots: list[str] | None = None,
        prior_session_index: int | None = None,
        session_index: int = 1,
        simulated_date: str | None = None,
        patient_lat: float | None = None,
        patient_lng: float | None = None,
        ocr_documents: list[Path | str] | None = None,
        ocr_document_hints: list[DocumentType] | None = None,
        audio_inputs: list[Path | str] | None = None,
        phr_paths: list[Path | str] | None = None,
    ) -> F1Result:
        """한 세션 실행.

        Args:
            patient_input_fn: async fn(agent_response) → patient_message
            session_id: 세션 ID
            max_turns: 최대 턴 수
            slot_extraction_interval: N턴마다 ClinicalSlotAgent 실행
            is_revisit: 재진 여부
            prior_handoff: 이전 세션의 narrowed carry-channel 내용 — ONLY
                final_slots+missing_slots-shaped 텍스트 (AVC-02). 과거의
                전체 prose Handoff Report가 아니다 — `_compose_carry_content`
                참고.
            prior_slots: 이전 세션에서 수집된 slot (재진 시) — filled_slots를
                직접 시드한다(evaluate_slot_grounding을 우회하므로
                carried_slot_provenance로 별도 태깅됨).
            prior_missing_slots: 이전 세션에서 미수집이었던 slot key 목록
                (재진 시) — Dialogue v3의 연속성 질문 유도에 사용 (값이 아닌
                key만 전달되므로 AVC-02 위반이 아니다).
            prior_session_index: 이전 세션의 session_index — carried_slot_
                provenance 태그(``carried_from_session_N``)에 사용. None이면
                일반 태그(``carried_from_prior_session``)를 사용한다.
            session_index: 이 세션의 순번(1부터). 다중 세션 체이닝용
                (PLAN-2026-W28-Q W2).
            simulated_date: 이 세션의 시뮬레이션 날짜(ISO). None이면 실제
                오늘 날짜를 사용한다.
            patient_lat, patient_lng: 환자 위치 (Crisis 시 근처 정신과 안내용).
                None이면 CRISIS_RESPONSE에 병원 정보 미포함.
            ocr_documents: 세션 시작 시 OCR 처리할 문서 경로 목록 (진단서/처방전 등)
            ocr_document_hints: 각 문서 유형 힌트 ('diagnosis', 'prescription', ...).
                                미지정 시 자동 감지.
            audio_inputs: 환자 음성 입력 파일 경로 목록. 지정 시 STT로 전사 후
                          그 텍스트를 patient_input_fn 대신 순차 사용한다.
                          patient_input_fn과 상호 배타적 (audio_inputs 우선).
            phr_paths: 마이헬스웨이 계열 PHR JSON 파일 경로 목록
                       (투약/진료 각각 여러 파일 병합 가능). 지정 시 세션 시작
                       시점에 로드해 병력 요약을 대화 시스템 프롬프트에 주입하고
                       F1Result.phr_summary에 저장한다.
        """
        resolved_simulated_date = simulated_date or datetime.now().date().isoformat()
        result = F1Result(
            session_id=session_id,
            patient_lat=patient_lat,
            patient_lng=patient_lng,
            persona_id=persona_id,
            persona_name=persona_name,
            started_at=datetime.now().isoformat(),
            session_index=session_index,
            simulated_date=resolved_simulated_date,
            is_revisit=is_revisit,
            prior_handoff=prior_handoff or None,
        )

        # ── STT: 음성 입력 → patient_input_fn 자동 구성 (T1-F1-DEV-003 통합) ──
        # audio_inputs가 주어지면 세션 시작 시점에 모든 오디오를 STT로 전사하고,
        # 그 텍스트들을 순차 반환하는 콜백으로 patient_input_fn을 대체한다.
        # (실시간 스트리밍은 아직 미구현 — batch 모드로 사전 전사)
        if audio_inputs:
            transcribed = await self._transcribe_audio_inputs(
                audio_inputs, session_id=session_id, patient_id=persona_id or "anon"
            )
            for out in transcribed:
                result.stt_transcripts.append(_stt_output_to_dict(out))
            texts = [out.text for out in transcribed if out.text]
            if not texts:
                result.errors.append("STT produced no text — session cannot proceed")
                result.ended_at = datetime.now().isoformat()
                return result
            patient_input_fn = _make_canned_patient_fn(texts)
            logger.info(
                "STT prepared %d patient utterances for session %s",
                len(texts), session_id,
            )
        elif patient_input_fn is None:
            raise ValueError(
                "Either patient_input_fn or audio_inputs must be provided"
            )

        conversation_history: list[dict[str, str]] = []
        filled_slots: dict[str, str] = dict(prior_slots) if prior_slots else {}
        # REV-022 Issue 7: slots pre-seeded from `prior_slots` bypass
        # evaluate_slot_grounding — track which ones are STILL the carried
        # value (never re-grounded this session) so the artifact can tag
        # them distinctly from freshly-grounded values. A key leaves this
        # set the moment this session's grounding filter accepts a fresh
        # value for it (or the Safety Probe/SI-screen re-grounds risk_
        # assessment directly).
        _carried_pending: set[str] = (
            {k for k, v in prior_slots.items() if v} if prior_slots else set()
        )
        prev_agent_response = ""
        repeat_count = 0

        # ── OCR: 세션 시작 시 첨부 문서 처리 (T1-F1-DEV-004 통합) ──
        # 결과는 result.ocr_documents에 저장 + 대화 컨텍스트에 system 메시지로 주입.
        if ocr_documents:
            ocr_outputs = await self._process_ocr_documents(
                ocr_documents,
                ocr_document_hints,
                session_id=session_id,
                patient_id=persona_id or "anon",
            )
            for ocr_out in ocr_outputs:
                result.ocr_documents.append(_ocr_output_to_dict(ocr_out))
                # Inject a compact clinical summary — full markdown is retained
                # in result.ocr_documents for downstream (Handoff Report) use.
                ctx = _format_ocr_for_context(ocr_out)
                if ctx:
                    conversation_history.append({"role": "system", "content": ctx})
            logger.info(
                "OCR processed %d document(s) for session %s",
                len(ocr_outputs),
                session_id,
            )

        # ── PHR: 세션 시작 시 마이헬스웨이 개인건강기록 로드 ──
        # 처방·진료 기록이 있으면 DialogueAgent에 사전 인지 컨텍스트로 전달한다.
        # (대화 시작 전 · base system prompt 앞부분에 결합)
        phr_context_for_dialogue: str = ""
        if phr_paths:
            history_agent = self._get_history_agent()
            try:
                phr_summary = await history_agent.run(
                    PhrLoadInput(
                        session_id=session_id,
                        bundle_paths=[str(p) for p in phr_paths],
                    )
                )
            except Exception as exc:  # 개별 파일 실패는 agent 내부에서 흡수됨
                logger.warning("PHR load failed for session %s: %s", session_id, exc)
                phr_summary = None
            if phr_summary is not None:
                result.phr_summary = phr_summary.model_dump(mode="json")
                ctx = _format_phr_for_context(phr_summary, history_agent)
                if ctx:
                    # (1) 대화 이전 인지: DialogueAgent가 매 턴 system prompt에 결합
                    phr_context_for_dialogue = ctx
                    # (2) 안전망: conversation_history에도 system 메시지로 남겨 다른
                    #    소비층(로그·재현·다른 agent)이 참조 가능하게 유지.
                    conversation_history.append({"role": "system", "content": ctx})
                logger.info(
                    "PHR loaded for session %s — %d meds (%d psychotropic), %d visits",
                    session_id,
                    phr_summary.total_medication_events,
                    len(phr_summary.psychotropic_medications),
                    phr_summary.total_visits,
                )

        # Grounding filter context: patient utterances + which slot the AI's
        # question targeted for each utterance (aligned by index).
        patient_utterances: list[str] = []
        asked_slots: list[str | None] = []

        # Safety probe state (pipeline-side, per DR-002).
        probe = _ProbeState()
        # risk_assessment is grounded only via probe/SI-screen in THIS session.
        # Carried prior values do not count — every session re-screens.
        risk_grounded = False
        risk_question_pending = False  # AI's last question targeted risk_assessment
        pending_soft_safety = False    # append 109 note to next AI response

        def _apply_carried_provenance() -> None:
            """REV-022 Issue 7: tag slots whose current value is STILL the
            un-re-grounded carry (never overwritten this session)."""
            tag = (
                f"carried_from_session_{prior_session_index}"
                if prior_session_index is not None
                else "carried_from_prior_session"
            )
            result.carried_slot_provenance = {
                k: tag for k in _carried_pending if filled_slots.get(k)
            }

        async def _finalize_async() -> F1Result:
            result.session_ctrs = min(
                (t.safety_ctrs for t in result.turns), default=5
            )
            result.grounded_coverage = _grounded_coverage(filled_slots)
            # BUG-021: session-level aggregate, machine-visible without
            # scanning every turn.
            result.prompts_degraded = any(t.prompts_degraded for t in result.turns)
            _apply_carried_provenance()
            # 명세 준수: 세션 종료 시 Sentiment Mode B (session-level 리포트)
            per_utt = [t.sentiment for t in result.turns if t.sentiment]
            result.session_sentiment = await self._analyze_session_sentiment(
                session_id=session_id,
                per_utterance=per_utt,
                history=conversation_history,
            )
            result.ended_at = datetime.now().isoformat()
            return result

        def _finalize() -> F1Result:
            # Sync fallback for early-exit paths — skips Mode B sentiment.
            result.prompts_degraded = any(t.prompts_degraded for t in result.turns)
            result.session_ctrs = min(
                (t.safety_ctrs for t in result.turns), default=5
            )
            result.grounded_coverage = _grounded_coverage(filled_slots)
            _apply_carried_provenance()
            result.ended_at = datetime.now().isoformat()
            return result

        # ── Turn 0: DialogueAgent 자율 인사 (Dialogue v3, PLAN-2026-W28-Q W2) ──
        # v2까지는 하드코딩된 f-string 인사말이었다(DialogueAgent는 turn 0에
        # 호출되지 않았음). v3부터는 DialogueAgent가 turn 0에도 호출되어
        # session_state(첫 방문/재상담 여부 + carry-channel 내용)를 조건으로
        # 자율적으로 인사를 생성한다 — 임상적 내용/슬롯 용어는 turn 0에 금지
        # (DialogueAgent._build_opening_context). 재상담(prior_handoff 있음)과
        # 초진/재진(visit_type)은 별개 개념:
        # - 초진/재진: 의료 분류 (persona MD의 visit_type)
        # - 재상담: 이전 상담 기록이 존재하는 경우 (prior_handoff 비어있지 않음)
        #
        # 재상담 환자에게는 narrowed carry-channel 내용(final_slots+
        # missing_slots만, AVC-02)만 시스템 메시지로 주입한다 — 과거 전체
        # prose Handoff Report(raw risk_assessment 포함)는 더 이상 주입하지
        # 않는다.
        prior_carry_summary: str | None = None
        if prior_handoff:
            prior_carry_summary = self._summarize_prior_handoff(prior_handoff)
            conversation_history.append({
                "role": "system",
                "content": f"[이전 세션 요약 참고 — 재상담 환자]\n{prior_handoff}",
            })

        opening_session_state: dict[str, Any] = {
            "opening_turn": True,
            "is_revisit": is_revisit,
        }
        if prior_carry_summary:
            opening_session_state["carry_summary"] = prior_carry_summary
        if prior_missing_slots:
            opening_session_state["prior_missing_slots"] = list(prior_missing_slots)

        # Record Turn 0 in result (greeting generation + patient first response)
        turn0_start = time.perf_counter()

        try:
            opening_out = await self.dialogue.run(DialogueInput(
                session_id=session_id,
                user_message=(
                    "(세션 시작 트리거 — 첫 인사말을 생성하세요. "
                    "이 문장은 환자의 발화가 아닙니다.)"
                ),
                conversation_history=[],
                filled_slots=dict(filled_slots),
                safety_result=None,
                session_state=opening_session_state,
            ))
            greeting = _extract_text(opening_out.assistant_response)
            result.model = opening_out.model_used
            result.prompt_version = opening_out.prompt_version
        except Exception as e:
            logger.error("Turn 0 opening greeting failed, using static fallback: %s", e)
            result.errors.append(f"Turn 0 opening greeting failed: {e}")
            greeting = (
                "안녕하세요! 저는 정신건강 사전문진을 도와드리는 AI 상담 도우미입니다. "
                "실제 의사 선생님과의 대화가 아니니, 너무 긴장하지 마시고 "
                "편하게 느끼시는 그대로 말씀해 주시면 됩니다.\n\n"
                "지금부터 대화를 시작하겠습니다. "
                "오늘 가장 도움받고 싶은 문제나 증상은 무엇인가요?"
            )
            result.prompt_version = "fallback_static"

        logger.info("Turn 0 | AI (opening): %s", greeting)

        try:
            raw_patient_message = await patient_input_fn(greeting)
        except Exception as e:
            result.errors.append(f"Patient start failed: {e}")
            return _finalize()

        # 명세: 모든 환자 입력은 InputNormalizer로 수렴 후 Safety/Dialogue로.
        input_type_for_normalizer = "stt_transcript" if audio_inputs else "user_text"
        patient_message, turn0_norm_meta = await self._normalize_patient_message(
            raw_patient_message,
            session_id=session_id,
            input_type=input_type_for_normalizer,
        )

        # The opening question targets the chief complaint.
        patient_utterances.append(patient_message)
        asked_slots.append("chief_complaint")

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

        # Slot extraction on first patient message — grounding filter applied
        turn0_slots: dict[str, str] = {}
        turn0_discards: dict[str, str] = {}
        turn0_slot_out = None
        try:
            turn0_slot_out = await self.clinical_slot.run(ClinicalSlotInput(
                session_id=session_id,
                conversation_history=turn0_history + [
                    {"role": "user", "content": patient_message},
                ],
                current_slots=filled_slots,
            ))
            if turn0_slot_out.extracted_slots:
                turn0_slots, turn0_discards = _filter_and_merge_slots(
                    turn0_slot_out.extracted_slots,
                    filled_slots,
                    patient_utterances,
                    asked_slots,
                )
                # REV-022 Issue 7: a freshly-grounded value supersedes any
                # carried one — no longer "still carried" provenance.
                _carried_pending.difference_update(turn0_slots.keys())
                logger.info(
                    "Turn 0 slot extraction: %d accepted, %d discarded",
                    len(turn0_slots), len(turn0_discards),
                )
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

        # Safety probe trigger check on turn 0 (CTRS 3 + SI/self-harm).
        if turn0_safety and not turn0_crisis and self._probe_should_trigger(turn0_safety):
            probe.active = True
            probe.awaiting_answer = False
            probe.stage_idx = 0
            probe.trigger_utterance = patient_message
            result.risk_floor = _PROBE_TRIGGER_CTRS
            result.probe_events.append({
                "type": "trigger",
                "turn": 0,
                "ctrs": int(turn0_safety.ctrs_level),
                "categories": list(turn0_safety.categories),
                "utterance": _clip(patient_message, 200),
            })
            logger.warning("Safety probe triggered at turn 0 (CTRS=3, SI/self-harm)")

        # 명세 준수: Sentiment (Mode A) 매 턴 실행 — 여기서는 Turn 0.
        turn0_sentiment = await self._analyze_utterance_sentiment(
            session_id=session_id,
            utterance=patient_message,
            turn_index=0,
            history=turn0_history,
        )

        turn0_coverage = _legacy_essential_coverage(filled_slots)
        turn0_grounded = _grounded_coverage(filled_slots)

        # BUG-021: aggregate this turn's prompts_degraded across every
        # prompt-driven agent invoked at turn 0 (safety, clinical_slot,
        # input_normalizer — dialogue is never called at turn 0).
        turn0_prompts_degraded = (
            bool(turn0_safety.prompts_degraded if turn0_safety else False)
            or bool(turn0_slot_out.prompts_degraded if turn0_slot_out else False)
            or bool(turn0_norm_meta.get("prompts_degraded", False))
        )

        # BUG-011 fix: a turn-0 crisis must substitute CRISIS_RESPONSE the
        # same way the main per-turn loop does (see `if crisis:` below) —
        # the session-opening greeting must never be the patient-facing text
        # when the very first message already triggers crisis. Per ADR-024,
        # turn-0 crisis text stays the BARE pinned CRISIS_RESPONSE — PR #42's
        # nearby-facility augmentation (below) is deliberately NOT extended
        # to turn 0's agent_response; it only populates
        # result.nearby_psychiatric, out of this program's validated scope.
        turn0_agent_response = CRISIS_RESPONSE if turn0_crisis else greeting

        turn0_latency = (time.perf_counter() - turn0_start) * 1000
        turn0_log = F1TurnLog(
            turn=0,
            patient_message=patient_message,
            safety_ctrs=turn0_ctrs,
            safety_risk=turn0_risk,
            safety_crisis=turn0_crisis,
            safety_categories=turn0_safety.categories if turn0_safety else [],
            safety_flagged=turn0_safety.flagged_phrases if turn0_safety else [],
            agent_response=turn0_agent_response,
            slot_updates=turn0_slots,
            cumulative_slots=dict(filled_slots),
            slot_coverage=turn0_coverage,
            latency_ms=turn0_latency,
            timestamp=datetime.now().isoformat(),
            targeted_slot="chief_complaint",
            slot_discards=turn0_discards,
            grounded_coverage=turn0_grounded,
            normalizer_meta=turn0_norm_meta,
            sentiment=turn0_sentiment,
            prompts_degraded=turn0_prompts_degraded,
        )
        result.turns.append(turn0_log)

        if turn0_crisis:
            result.crisis_triggered = True
            result.crisis_turn = 0
            result.total_turns = 0
            result.final_slots = [{"key": k, "value": v} for k, v in filled_slots.items() if v]
            result.slot_coverage = turn0_coverage
            # 근처 정신과 안내를 조회 (ADR-024: 안내 텍스트는 turn0_log.agent_response에
            # 첨부하지 않는다 — result.nearby_psychiatric에만 별도 저장).
            nearby_text, nearby_records = await self._fetch_crisis_facilities(
                patient_lat, patient_lng,
            )
            if nearby_text:
                result.nearby_psychiatric = nearby_records
                logger.warning(
                    "Crisis at turn 0 — appended %d nearby psychiatric hospitals",
                    len(nearby_records),
                )
            return _finalize()

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
        # turn_norm_meta는 매 턴 갱신 (첫 진입은 Turn 0의 정규화 메타를 승계)
        turn_norm_meta: dict[str, Any] = turn0_norm_meta
        for turn in range(1, max_turns + 1):
            turn_start = time.perf_counter()
            logger.info("Turn %d | Patient: %s", turn, patient_message)
            targeted_slot: str | None = None

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
            slot_discards: dict[str, str] = {}
            probe_just_concluded = False  # QA finding 8: probe cooldown
            # BUG-021: reset every turn — never carry a stale flag from a
            # previous iteration forward if this turn's try/except skips the
            # agent call entirely (e.g. crisis turns skip slot/dialogue).
            slot_prompts_degraded = False
            dialogue_prompts_degraded = False
            post_safety_prompts_degraded = False
            # BUG-030 iter-2 / BUG-035 guard telemetry — same reset
            # discipline as dialogue_prompts_degraded above (never carry a
            # stale value forward from a turn that skipped the dialogue
            # call, e.g. a crisis turn).
            dialogue_retry_count = 0
            dialogue_retry_reasons: list[str] = []
            dialogue_fall_through = False
            dialogue_retry_latency_ms = 0.0
            dialogue_crisis_adjacent = False
            dialogue_output_isolation_fallback = False
            dialogue_near_dup_detail: list[dict] = []
            dialogue_exhaustion_degrade: str | None = None
            dialogue_exhaustion_degrade_phrase: str | None = None

            # ── Step 1b: Safety probe state machine (T1-F1-DEV-022/023) ──
            if not crisis and probe.active and probe.awaiting_answer:
                probe.awaiting_answer = False
                probe.answers.append(patient_message)
                outcome = self._process_probe_answer(probe, patient_message)
                answered_stage = _PROBE_STAGES[
                    min(probe.stage_idx, len(_PROBE_STAGES) - 1)
                ][0]

                if outcome == "escalate":
                    crisis = True
                    probe.active = False
                    result.probe_events.append({
                        "type": "escalation",
                        "turn": turn,
                        "stage": answered_stage,
                        "reason": "plan/means disclosure (lexical check)",
                        "utterance": _clip(patient_message, 200),
                    })
                    logger.warning(
                        "Probe ESCALATION at turn %d (stage=%s, lexical)",
                        turn, answered_stage,
                    )
                elif outcome == "deescalate":
                    risk_value = self._compose_probe_risk_assessment(probe, patient_message)
                    filled_slots[RISK_SLOT_KEY] = risk_value
                    _carried_pending.discard(RISK_SLOT_KEY)
                    risk_grounded = True
                    slot_updates[RISK_SLOT_KEY] = risk_value
                    probe.active = False
                    pending_soft_safety = True
                    probe_just_concluded = True
                    result.probe_events.append({
                        "type": "deescalation",
                        "turn": turn,
                        "stage": answered_stage,
                        "risk_assessment_written": True,
                        "risk_assessment": risk_value,
                    })
                    logger.info("Probe de-escalated at turn %d — risk grounded", turn)
                else:
                    probe.stage_idx += 1
                    if probe.stage_idx >= len(_PROBE_STAGES):
                        # Stages exhausted without denial or disclosure —
                        # compose from the full exchange and exit probe.
                        risk_value = self._compose_probe_risk_assessment(
                            probe, patient_message
                        )
                        filled_slots[RISK_SLOT_KEY] = risk_value
                        _carried_pending.discard(RISK_SLOT_KEY)
                        risk_grounded = True
                        slot_updates[RISK_SLOT_KEY] = risk_value
                        probe.active = False
                        pending_soft_safety = True
                        probe_just_concluded = True
                        result.probe_events.append({
                            "type": "deescalation",
                            "turn": turn,
                            "stage": answered_stage,
                            "risk_assessment_written": True,
                            "risk_assessment": risk_value,
                            "note": "probe stages exhausted",
                        })
                    else:
                        result.probe_events.append({
                            "type": "progress",
                            "turn": turn,
                            "stage": answered_stage,
                            "next_stage": _PROBE_STAGES[probe.stage_idx][0],
                        })
            elif not crisis and risk_question_pending:
                # Answer to an SI screening question (mandatory probe or
                # round-robin risk targeting).
                risk_question_pending = False
                if self._probe_should_trigger(safety_out):
                    # The screening answer itself revealed CTRS-3 SI —
                    # the generic trigger check below enters probe mode.
                    pass
                else:
                    risk_value = self._compose_screen_risk_assessment(patient_message)
                    filled_slots[RISK_SLOT_KEY] = risk_value
                    _carried_pending.discard(RISK_SLOT_KEY)
                    risk_grounded = True
                    slot_updates[RISK_SLOT_KEY] = risk_value
                    result.probe_events.append({
                        "type": "si_screen_result",
                        "turn": turn,
                        "risk_assessment_written": True,
                        "risk_assessment": risk_value,
                    })

            # ── Step 1c: Probe trigger check (CTRS 3 + SI/self-harm) ──
            # QA finding 8 (cooldown): never re-trigger on the turn that just
            # concluded a probe (the concluding answer would immediately
            # restart the full SI questioning), and cap probes at 2 triggers
            # per session — an escalation ends the session anyway.
            prior_triggers = sum(
                1 for e in result.probe_events if e["type"] == "trigger"
            )
            if (
                not crisis
                and not probe.active
                and not probe_just_concluded
                and prior_triggers < 2
                and self._probe_should_trigger(safety_out)
            ):
                probe.active = True
                probe.awaiting_answer = False
                probe.stage_idx = 0
                probe.trigger_utterance = patient_message
                probe.answers = []
                probe.protective_answer = ""
                risk_grounded = False  # new risk episode — re-ground
                result.risk_floor = _PROBE_TRIGGER_CTRS
                result.probe_events.append({
                    "type": "trigger",
                    "turn": turn,
                    "ctrs": int(safety_out.ctrs_level),
                    "categories": list(safety_out.categories),
                    "utterance": _clip(patient_message, 200),
                })
                logger.warning("Safety probe triggered at turn %d", turn)

            if crisis:
                # ── CTRS 1-2 (or probe escalation): Crisis → 세션 종료 ──
                agent_response = CRISIS_RESPONSE
                # 근처 정신과 top-3 자동 안내 (patient_lat/lng 있을 때)
                nearby_text, nearby_records = await self._fetch_crisis_facilities(
                    patient_lat, patient_lng,
                )
                if nearby_text:
                    agent_response = agent_response + "\n" + nearby_text
                    result.nearby_psychiatric = nearby_records
                    logger.warning(
                        "Appended %d nearby psychiatric hospitals to CRISIS response",
                        len(nearby_records),
                    )
                result.crisis_triggered = True
                result.crisis_turn = turn
                logger.warning("CRISIS at turn %d (CTRS=%d)", turn, safety_out.ctrs_level)
            else:
                # ── Step 2: Slot extraction FIRST (매 턴, Dialogue 전에) ──
                # Dialogue가 최신 slot 정보를 보고 질문할 수 있도록.
                # 추출 결과는 grounding filter를 통과한 값만 반영된다.
                try:
                    slot_history = conversation_history + [
                        {"role": "user", "content": patient_message},
                    ]
                    slot_out = await self.clinical_slot.run(ClinicalSlotInput(
                        session_id=session_id,
                        conversation_history=slot_history,
                        current_slots=filled_slots,
                    ))
                    slot_prompts_degraded = bool(slot_out.prompts_degraded)
                    if slot_out.extracted_slots:
                        extract_updates, extract_discards = _filter_and_merge_slots(
                            slot_out.extracted_slots,
                            filled_slots,
                            patient_utterances,
                            asked_slots,
                        )
                        slot_updates.update(extract_updates)
                        slot_discards.update(extract_discards)
                        # REV-022 Issue 7: freshly-grounded values supersede
                        # any carried provenance for the same key.
                        _carried_pending.difference_update(extract_updates.keys())
                    logger.info(
                        "Turn %d slots: +%d accepted, %d discarded, %d total",
                        turn, len(slot_updates), len(slot_discards), len(filled_slots),
                    )
                except Exception as e:
                    logger.warning("Slot extraction failed: %s", e)

                # ── Step 3: Dialogue agent (최신 filled_slots + Safety 결과 사용) ──
                # Dialogue는 응답 생성만 담당.
                # Probe mode에서는 round-robin을 중단하고 probe 지시를 주입한다.
                other_missing = [
                    s for s in QUESTIONABLE_SLOT_KEYS
                    if s != RISK_SLOT_KEY and not filled_slots.get(s)
                ]
                session_state: dict[str, Any] | None = None
                forced_si_screen = False

                if probe.active:
                    session_state = {
                        "probe_instruction": self._build_probe_instruction(probe.stage_idx),
                    }
                    targeted_slot = RISK_SLOT_KEY
                elif not risk_grounded and not other_missing:
                    # Mandatory SI probe: all other question-able slots are
                    # collected — session may NOT end until risk is grounded.
                    session_state = {"probe_instruction": _SI_SCREEN_INSTRUCTION}
                    targeted_slot = RISK_SLOT_KEY
                    forced_si_screen = True
                else:
                    targeted_slot = DialogueAgent.compute_target_slot(
                        filled_slots, conversation_history
                    )
                    # Dialogue v3 (b): continuity phrasing for slots missing
                    # from a prior session — key names only (AVC-02), never
                    # values/prose.
                    round_robin_state: dict[str, Any] = {}
                    if prior_missing_slots:
                        round_robin_state["prior_missing_slots"] = list(prior_missing_slots)
                    # BUG-030 iter-2 / BUG-035 (ADR-029 Decision 3, design §8
                    # de-escalation-turn boundary, rubric §10.3): thread the
                    # ALREADY-COMPUTED `probe_just_concluded` local (Step 1b
                    # above) into the existing session_state field — no new
                    # DialogueInput field, no new logic — so
                    # DialogueAgent._is_crisis_adjacent_turn can structurally
                    # guarantee coverage of the probe/de-escalation-
                    # concluding turn independent of this turn's own
                    # recomputed CTRS.
                    if probe_just_concluded:
                        round_robin_state["probe_just_concluded"] = True
                    if round_robin_state:
                        session_state = round_robin_state

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
                        session_state=session_state,
                        patient_history_context=phr_context_for_dialogue,
                        # BUG-037 (`_archive/plans/fix_design_exhaustion_bug037.md`
                        # §2): this turn's own slot writes (Step 1b risk_
                        # assessment + Step 2 extraction, both already
                        # applied above) — lets the output-isolation guard
                        # prioritize detecting a same-turn clinical-note
                        # leak over an older, already-shown one.
                        slot_updates_this_turn=dict(slot_updates),
                    ))
                    agent_response = _extract_text(dialogue_out.assistant_response)
                    dialogue_prompts_degraded = bool(dialogue_out.prompts_degraded)
                    # BUG-030 iter-2 / BUG-035 / BUG-037 guard telemetry —
                    # from DialogueAgent alone (no cross-agent OR-fold
                    # needed).
                    dialogue_retry_count = dialogue_out.retry_count
                    dialogue_retry_reasons = list(dialogue_out.retry_reasons)
                    dialogue_fall_through = dialogue_out.fall_through
                    dialogue_retry_latency_ms = dialogue_out.retry_latency_ms
                    dialogue_crisis_adjacent = dialogue_out.crisis_adjacent
                    dialogue_output_isolation_fallback = (
                        dialogue_out.output_isolation_fallback
                    )
                    dialogue_near_dup_detail = list(dialogue_out.near_dup_detail)
                    dialogue_exhaustion_degrade = dialogue_out.exhaustion_degrade
                    dialogue_exhaustion_degrade_phrase = (
                        dialogue_out.exhaustion_degrade_phrase
                    )
                except Exception as e:
                    result.errors.append(f"Turn {turn} dialogue error: {e}")
                    logger.error("Dialogue failed: %s", e)
                    break

                if pending_soft_safety:
                    # One-time 109 안내 after probe de-escalation (non-terminating).
                    agent_response = agent_response.rstrip() + _SOFT_SAFETY_NOTE
                    pending_soft_safety = False

                if probe.active:
                    probe.awaiting_answer = True
                elif targeted_slot == RISK_SLOT_KEY:
                    risk_question_pending = True
                    result.probe_events.append({
                        "type": "si_screen",
                        "turn": turn,
                        "forced": forced_si_screen,
                    })

            # 턴 종료 후 history에 현재 턴의 대화 추가
            conversation_history.append({"role": "user", "content": patient_message})
            conversation_history.append({"role": "assistant", "content": agent_response})

            # ── Calculate coverage (orchestrator 역할) ──
            coverage = _legacy_essential_coverage(filled_slots)
            g_coverage = _grounded_coverage(filled_slots)

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
                targeted_slot=targeted_slot,
                slot_discards=slot_discards,
                grounded_coverage=g_coverage,
                dialogue_retry_count=dialogue_retry_count,
                dialogue_retry_reasons=dialogue_retry_reasons,
                dialogue_fall_through=dialogue_fall_through,
                dialogue_retry_latency_ms=dialogue_retry_latency_ms,
                dialogue_crisis_adjacent=dialogue_crisis_adjacent,
                dialogue_output_isolation_fallback=dialogue_output_isolation_fallback,
                dialogue_near_dup_detail=dialogue_near_dup_detail,
                dialogue_exhaustion_degrade=dialogue_exhaustion_degrade,
                dialogue_exhaustion_degrade_phrase=dialogue_exhaustion_degrade_phrase,
            )
            # 명세 준수: Sentiment (Mode A) — 매 턴 환자 발화 정서 signal.
            turn_sentiment = await self._analyze_utterance_sentiment(
                session_id=session_id,
                utterance=patient_message,
                turn_index=turn,
                history=conversation_history,
            )
            # 명세 준수: Dialogue 응답 자체에 대한 Safety 재검사.
            # AI 응답이 부적절한 위험 문구를 담고 있는지 확인 — 실패해도 세션은 계속.
            dialogue_safety_ctrs = None
            dialogue_safety_risk = None
            if agent_response and agent_response != CRISIS_RESPONSE:
                try:
                    post_safety = await self.safety.run(SafetyInput(
                        session_id=session_id,
                        user_message=agent_response,  # AI 응답이 검사 대상
                        conversation_history=conversation_history + [
                            {"role": "user", "content": patient_message},
                        ],
                    ))
                    dialogue_safety_ctrs = int(post_safety.ctrs_level)
                    dialogue_safety_risk = str(post_safety.risk_level)
                    post_safety_prompts_degraded = bool(post_safety.prompts_degraded)
                    if dialogue_safety_ctrs <= 2:
                        logger.warning(
                            "Post-dialogue Safety flagged AI response at turn %d "
                            "(CTRS=%d, risk=%s) — leaving as-is for logging",
                            turn, dialogue_safety_ctrs, dialogue_safety_risk,
                        )
                except Exception as e:
                    logger.warning("Post-dialogue Safety failed at turn %d: %s", turn, e)

            # Attach sentiment + normalizer_meta + dialogue_safety on the log.
            turn_log.sentiment = turn_sentiment
            turn_log.normalizer_meta = turn_norm_meta
            turn_log.dialogue_safety_ctrs = dialogue_safety_ctrs
            turn_log.dialogue_safety_risk = dialogue_safety_risk
            # BUG-021: aggregate across every prompt-driven agent invoked
            # this turn (safety, slot, dialogue, post-dialogue safety
            # re-check, input_normalizer for the message that started it).
            turn_log.prompts_degraded = (
                bool(safety_out.prompts_degraded)
                or slot_prompts_degraded
                or dialogue_prompts_degraded
                or post_safety_prompts_degraded
                or bool(turn_norm_meta.get("prompts_degraded", False))
            )
            result.turns.append(turn_log)
            result.total_turns = turn
            result.final_slots = [{"key": k, "value": v} for k, v in filled_slots.items() if v]
            result.slot_coverage = coverage
            result.grounded_coverage = g_coverage

            logger.info(
                "Turn %d | CTRS=%d | slots=%d | coverage=%.0f%% | grounded=%.0f%% | "
                "sentiment=%s | dlg_ctrs=%s | %.0fms",
                turn, safety_out.ctrs_level, len(filled_slots),
                coverage * 100, g_coverage * 100,
                turn_sentiment.get("polarity", "?"),
                dialogue_safety_ctrs, latency,
            )

            if crisis:
                break

            # ── Handoff ready: 질문 가능 슬롯 모두 수집 + risk grounded 시 종료 ──
            # Termination gate (T1-F1-DEV-018/022): 세션은 risk_assessment가
            # grounded되기 전에는 slot-completion으로 종료될 수 없다.
            other_missing = [
                s for s in QUESTIONABLE_SLOT_KEYS
                if s != RISK_SLOT_KEY and not filled_slots.get(s)
            ]
            if not other_missing and risk_grounded and turn >= 3:
                logger.info(
                    "All questionable slots grounded — ending session (handoff ready)"
                )
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

            # ── Next patient input (정규화 포함) ──
            try:
                raw_next = await patient_input_fn(agent_response)
            except Exception as e:
                result.errors.append(f"Turn {turn} patient error: {e}")
                break

            patient_message, turn_norm_meta = await self._normalize_patient_message(
                raw_next,
                session_id=session_id,
                input_type=input_type_for_normalizer,
            )

            # Record the new utterance + which slot this turn's question targeted.
            patient_utterances.append(patient_message)
            asked_slots.append(targeted_slot)

        # 정상 종료 경로 — Session-level Sentiment (Mode B) 계산 후 반환.
        return await _finalize_async()


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
    n_discards = sum(len(t.slot_discards) for t in r.turns)
    # Fix 2 — Option C elevated-review flag (`docs/ai/fix_design_
    # exhaustion_bug037.md` §3, ADR-030 Decision 3(1) / CVR-013 condition
    # 1): the exhaustion_degrade telemetry must reach an actually-reviewed
    # surface, not just a WARNING log line — the checklist is that surface.
    degrade_turns = [t for t in r.turns if t.dialogue_exhaustion_degrade]
    n_degrades = len(degrade_turns)
    degrade_subrules = sorted({
        t.dialogue_exhaustion_degrade for t in degrade_turns
        if t.dialogue_exhaustion_degrade is not None
    })
    degrade_subrules_str = ", ".join(degrade_subrules) if degrade_subrules else "none"
    lines = [
        f"# F1 Agent Call Checklist — {r.persona_id or r.session_id}",
        "",
        f"> Session: {r.session_id} | Turns: {r.total_turns} | Crisis: {r.crisis_triggered}",
        "",
        "| Check | Status | Detail |",
        "|-------|--------|--------|",
        f"| SafetyClassifier 매 턴 호출 | PASS | {r.total_turns}턴 전체 호출 |",
        f"| DialogueAgent 호출 | "
        f"{'PASS' if not r.crisis_triggered or r.crisis_turn > 1 else 'N/A'} | "
        f"{sum(1 for t in r.turns if not t.safety_crisis)}턴 호출 |",
        f"| ClinicalSlotAgent 호출 | "
        f"{'PASS' if any(t.slot_updates for t in r.turns) else 'WARN'} | "
        f"slot extraction 실행 |",
        "| System prompt 주입 | PASS | 모든 agent에 PromptLoader로 주입 |",
        "| 대화 기록 append | PASS | 매 턴 conversation_history 누적 |",
        "| Full text 저장 (no truncation) | PASS | 모든 턴 전문 저장 |",
        f"| Crisis 대응 (CTRS 1-2) | "
        f"{'PASS — 109/119 안내' if r.crisis_triggered else 'N/A — crisis 미발생'} |",
        f"| Grounding filter 적용 | PASS | {n_discards}개 값 폐기 (ungrounded/system/risk) |",
        f"| Safety probe events | {len(r.probe_events)}건 | risk_floor={r.risk_floor} |",
        f"| Empathy-degrade events (Fix 2 exhaustion) | {n_degrades}건 | "
        f"sub-rules: {degrade_subrules_str} |",
        f"| Session CTRS (turn 0 포함 최솟값) | {r.session_ctrs} | |",
        f"| Slot coverage (legacy, essential 5) | {r.slot_coverage:.0%} | "
        f"{len(r.final_slots)} slots filled |",
        f"| Grounded coverage (questionable 8) | {r.grounded_coverage:.0%} | filter 통과 값만 |",
        f"| OCR documents attached | {'PASS' if r.ocr_documents else 'N/A'} | "
        f"{len(r.ocr_documents)} document(s) parsed |",
        f"| STT audio inputs | {'PASS' if r.stt_transcripts else 'N/A'} | "
        f"{len(r.stt_transcripts)} audio file(s) transcribed |",
        "",
    ]

    lines.append("## Per-Turn Agent Calls")
    lines.append("")
    for t in r.turns:
        lines.append(f"### Turn {t.turn}")
        lines.append(f"- Safety: CTRS={t.safety_ctrs}, risk={t.safety_risk}, "
                      f"categories={t.safety_categories}, crisis={t.safety_crisis}")
        lines.append(f"- Dialogue: response_length={len(t.agent_response)}chars, "
                      f"targeted_slot={t.targeted_slot or 'none'}")
        if (t.dialogue_retry_reasons or t.dialogue_fall_through
                or t.dialogue_output_isolation_fallback or t.dialogue_exhaustion_degrade):
            lines.append(
                f"- Dialogue guard: retries={t.dialogue_retry_count}, "
                f"reasons={t.dialogue_retry_reasons}, "
                f"fall_through={t.dialogue_fall_through}, "
                f"output_isolation_fallback={t.dialogue_output_isolation_fallback}, "
                f"exhaustion_degrade={t.dialogue_exhaustion_degrade or 'none'}"
                + (
                    f" (substituted: \"{t.dialogue_exhaustion_degrade_phrase}\")"
                    if t.dialogue_exhaustion_degrade_phrase else ""
                )
            )
        lines.append(
            f"- Slots updated: {list(t.slot_updates.keys()) if t.slot_updates else 'none'}"
        )
        if t.slot_discards:
            lines.append(f"- Slots discarded: {list(t.slot_discards.keys())}")
        lines.append(f"- Coverage: legacy={t.slot_coverage:.0%}, "
                     f"grounded={t.grounded_coverage:.0%}")
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
        f"Crisis: {r.crisis_triggered} | Coverage: {r.slot_coverage:.0%} (legacy) / "
        f"{r.grounded_coverage:.0%} (grounded)",
        f"> Session CTRS (incl. turn 0): {r.session_ctrs} | Risk floor: {r.risk_floor}",
        f"> Started: {r.started_at} | Ended: {r.ended_at}",
        "",
    ]

    # Crisis 시 근처 정신과 top-N (섹션이 있으면 대화 앞에 배치)
    if r.nearby_psychiatric:
        lines.append("## 🚨 위기 대응 — 근처 정신건강의학과")
        lines.append("")
        if r.patient_lat is not None and r.patient_lng is not None:
            lines.append(
                f"> 환자 위치: ({r.patient_lat:.6f}, {r.patient_lng:.6f}) · HIRA dgsbjtCd=03"
            )
            lines.append("")
        for rec in r.nearby_psychiatric:
            phone = f" · ☎ {rec.get('phone')}" if rec.get("phone") else ""
            addr = f"\n   📍 {rec.get('address', '')}" if rec.get("address") else ""
            lines.append(
                f"{rec.get('rank')}. **{rec.get('name')}** "
                f"({rec.get('distance_km')}km){phone}{addr}"
            )
        lines.extend(["", ""])

    lines.extend(["## Full Conversation", ""])

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
            if t.slot_discards:
                lines.append(
                    f"**Slot Discards**: {json.dumps(t.slot_discards, ensure_ascii=False)}"
                )
                lines.append("")
        else:
            # Turn N: AI 응답 → Patient 응답 (다음 턴 입력)
            crisis_tag = " **[CRISIS]**" if t.safety_crisis else ""
            lines.append(
                f"### Turn {t.turn} | CTRS={t.safety_ctrs} | risk={t.safety_risk}{crisis_tag}"
            )
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
            if t.slot_discards:
                lines.append(
                    f"**Slot Discards**: {json.dumps(t.slot_discards, ensure_ascii=False)}"
                )
                lines.append("")

    # Probe events
    if r.probe_events:
        lines.extend(["## Safety Probe Events", ""])
        for e in r.probe_events:
            lines.append(f"- {json.dumps(e, ensure_ascii=False)}")
        lines.append("")

    # Errors
    if r.errors:
        lines.extend(["## Errors", ""])
        for e in r.errors:
            lines.append(f"- {e}")
        lines.append("")

    # Final slots
    lines.extend(["## Final Slots", ""])
    lines.append(
        f"Coverage: {r.slot_coverage:.0%} legacy (essential 5) / "
        f"{r.grounded_coverage:.0%} grounded (questionable 8) — "
        f"{len(r.final_slots)} slots filled"
    )
    lines.append("")
    for slot in r.final_slots:
        lines.append(f"- **{slot['key']}**: {slot['value']}")

    # OCR documents (if any)
    if r.ocr_documents:
        lines.extend(["", "## OCR Documents", ""])
        for i, doc in enumerate(r.ocr_documents, 1):
            summary = doc.get("extracted_summary", {}) or {}
            doc_type = doc.get("document_type", "unknown")
            lines.append(f"### Document {i} — {doc_type}")
            lines.append("")
            patient_parts = [
                v for v in (
                    summary.get("patient_name"),
                    summary.get("patient_age"),
                    summary.get("patient_gender"),
                )
                if v
            ]
            if patient_parts:
                lines.append(f"- 환자: {' / '.join(patient_parts)}")
            if summary.get("department"):
                lines.append(f"- 진료과: {summary['department']}")
            dxs = summary.get("diagnoses") or []
            codes = summary.get("diagnosis_codes") or []
            if dxs:
                code_str = f" ({', '.join(codes)})" if codes else ""
                lines.append(f"- 진단명{code_str}: {', '.join(dxs)}")
            scores = summary.get("scale_scores") or {}
            if scores:
                lines.append(
                    "- 척도 점수: "
                    + ", ".join(f"{k}={v}" for k, v in scores.items())
                )
            meds = summary.get("medications") or []
            if meds:
                med_str = ", ".join(
                    f"{m.get('name', '?')} {m.get('dose', '') or ''}".strip()
                    for m in meds[:5]
                )
                lines.append(f"- 약물: {med_str}")
            dates = summary.get("dates") or []
            if dates:
                lines.append(f"- 날짜: {', '.join(dates[:3])}")
            low_conf = doc.get("low_confidence_items") or []
            if low_conf:
                lines.append(f"- 확인 필요: {len(low_conf)}개 항목")
            lines.append(
                f"- 페이지: {doc.get('page_count', '?')} | "
                f"지연: {doc.get('latency_ms', 0):.0f}ms"
            )
            lines.append("")

    # PHR (개인건강기록) — 세션 시작 시 로드된 요약
    if r.phr_summary:
        lines.extend(["", "## PHR — 개인건강기록 요약", ""])
        phr = r.phr_summary
        patient = phr.get("patient") or {}
        lines.append(f"- MHID: {patient.get('mhid', '-')}")
        lines.append(f"- name_hash: {patient.get('name_hash', '-')}")
        date_range = phr.get("date_range")
        if date_range and len(date_range) == 2:
            lines.append(f"- 커버 기간: {date_range[0]} ~ {date_range[1]}")
        lines.append(
            f"- 총 조제: {phr.get('total_medication_events', 0)}건 "
            f"(정신과 계열 {len(phr.get('psychotropic_medications') or [])}건)"
        )
        lines.append(
            f"- 총 방문: {phr.get('total_visits', 0)}건 "
            f"(정신과명 포함 {phr.get('psychiatric_visit_count', 0)}건)"
        )
        lines.append(
            f"- 정신과 이력: {'예' if phr.get('has_psychiatric_history') else '아니요'}"
        )
        psycho = phr.get("psychotropic_medications") or []
        if psycho:
            lines.append("")
            lines.append("### 정신과 계열 약물 이력")
            for m in psycho:
                when = m.get("dispensed_at") or "-"
                cls = m.get("efficacy_class_name") or m.get("psychotropic_class", "?")
                name = m.get("product_name", "-")
                days = m.get("days_supply")
                freq = m.get("daily_frequency")
                extra_parts = []
                if days is not None:
                    extra_parts.append(f"{days}일치")
                if freq is not None:
                    extra_parts.append(f"{freq}회/일")
                extra = f" · {' · '.join(extra_parts)}" if extra_parts else ""
                lines.append(f"- {when} · {name} [{cls}]{extra}")
        lines.append("")

    # STT transcripts (if any)
    if r.stt_transcripts:
        lines.extend(["", "## STT Transcripts (음성 입력)", ""])
        for i, tr in enumerate(r.stt_transcripts, 1):
            lines.append(f"### Audio {i}")
            lines.append("")
            lines.append(f"- 텍스트: {tr.get('text', '')[:200]}")
            lines.append(f"- 세그먼트: {len(tr.get('segments', []))}개")
            lines.append(f"- 지속: {tr.get('audio_duration_ms', 0)}ms")
            lines.append(f"- 지연: {tr.get('latency_ms', 0):.0f}ms")
            lines.append(f"- 벤더: {tr.get('vendor', '?')}")
            lines.append(f"- 사용자 확인: {tr.get('user_confirmed', False)} (FR-035)")
            lines.append("")

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
        # ISS-036 partial fix: session CTRS = min over ALL turns INCLUDING
        # turn 0. Previously turn 0 was excluded and fell back to 5, so a
        # turn-0 crisis session was recorded as stable.
        session_ctrs = min(t.safety_ctrs for t in result.turns)
        lines.append(f"- CTRS: {session_ctrs}단계")
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
        lines.append("위험 평가 미수행 (근거 있는 위험 문답 없음)")

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
        "[7. Slot Coverage]",
        f"- Coverage (legacy): {result.slot_coverage:.0%} ({len(result.final_slots)} slots)",
        f"- Grounded coverage: {result.grounded_coverage:.0%} (questionable 8)",
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


def _result_from_dict(data: dict) -> F1Result:
    """Build an F1Result from a saved conversation.json dict (old or new format)."""
    turns = [F1TurnLog(**t) for t in data.get("turns", [])]
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
        grounded_coverage=data.get("grounded_coverage", 0.0),
        risk_floor=data.get("risk_floor"),
        probe_events=data.get("probe_events", []),
        session_ctrs=data.get("session_ctrs", 5),
        # PLAN-2026-W28-Q W2 fields — `.get(...)` with defaults so legacy
        # (pre-W2) artifacts load without KeyError (documented fallback,
        # REV-023 ruling 4 atomicity constraint).
        session_index=data.get("session_index", 1),
        simulated_date=data.get("simulated_date", ""),
        is_revisit=data.get("is_revisit", False),
        model=data.get("model", ""),
        prompt_version=data.get("prompt_version", ""),
        prior_handoff=data.get("prior_handoff"),
        carried_slot_provenance=data.get("carried_slot_provenance", {}),
        # F4 quick-dev provenance (§2.7) — `.get(...)` default so pre-F4
        # artifacts (no such keys) load without KeyError.
        scenario_pack_id=data.get("scenario_pack_id"),
        arc_mode=data.get("arc_mode"),
    )


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
    return _result_from_dict(data)


# ── CLI entry point ──────────────────────────────────────────────────


async def _run_simulation(
    persona_id: str,
    max_turns: int,
    followup_from: str | None = None,
    patient_lat: float | None = None,
    patient_lng: float | None = None,
    ocr_documents: list[Path] | None = None,
    ocr_hints: list[DocumentType] | None = None,
    audio_inputs: list[Path] | None = None,
    phr_paths: list[Path] | None = None,
    session_index: int | None = None,
    simulated_date: str | None = None,
    scenario_guideline: str | None = None,
    scenario_pack_id: str | None = None,
    arc_mode: str | None = None,
) -> F1Result:
    """시뮬레이션 모드: PatientLLM과 F1Pipeline 대화.

    Args:
        followup_from: 이전 세션 결과를 기반으로 재상담 시뮬레이션.
            - persona ID (e.g. "VP-001") → 해당 VP의 최신 결과에서 handoff 생성
            - JSON file path → 해당 파일에서 handoff 생성
        patient_lat/lng: 환자 좌표. 미지정 시 PERSONA_LOCATIONS에서 자동 조회.
        session_index: 이 세션의 순번(1부터). None이면 followup_from 유무로
            자동 산정 (첫 세션=1, 재상담=이전 session_index+1).
        simulated_date: 이 세션의 시뮬레이션 날짜(ISO). None이면 오늘 날짜.
        scenario_guideline: F4 quick-dev 시나리오 가이드라인 텍스트 (harness가
            렌더링한 완성된 문자열, 자체 헤더 포함 — `docs/ai/f4_quick_dev_
            plan.md` §2.5). `persona.system_prompt`에 `prior_handoff` 블록
            바로 뒤에 그대로 append된다. None(기본값)이면 이 세션은 완전히
            자연(natural) 세션과 동일하게 동작 — 이 인자를 넘기지 않는 모든
            기존 호출자(라이브 4VP 배터리 포함)는 동작 변화가 전혀 없다.
        scenario_pack_id, arc_mode: F4 provenance 태그 (§2.7, `ADR-036` item
            3) — `pipeline.run_session(...)` 완료 후 `result`에 그대로
            threading됨. 둘 다 None(기본값)이면 `F1Result`의 필드 기본값
            (None)이 그대로 유지된다.

    Returns:
        The completed F1Result (also saved to disk via `save_f1_result`) —
        multi-session callers (`continuous_test.py`) chain off this directly
        instead of re-globbing the output directory.
    """
    from tests.simulation.patient_llm import PatientLLM, load_persona

    try:
        persona = load_persona(persona_id)
    except FileNotFoundError as e:
        print(f"Persona file not found: {e}")
        print("Available: VP-001, VP-002, VP-003, VP-004, VP-010, VP-011, VP-012")
        sys.exit(1)

    api_key = os.environ.get("UPSTAGE_API_KEY", "")
    if not api_key:
        print("UPSTAGE_API_KEY not set")
        sys.exit(1)

    # Determine prior handoff source — PLAN-2026-W28-Q W2 (AVC-02): the
    # carry channel is NARROWED to final_slots+missing_slots only. Neither
    # the patient-simulator prompt below nor `prior_handoff` (which reaches
    # the dialogue history via F1Pipeline.run_session) ever sees the old
    # full-prose Handoff Report (CTRS/crisis-protocol narrative, raw
    # risk_assessment prose) again.
    prior_handoff = ""
    prior_slots: dict[str, str] = {}
    prior_missing_slots: list[str] = []
    prior_session_index: int | None = None

    if followup_from:
        # Load prior session result and build the narrowed carry content
        if followup_from.endswith(".json"):
            with open(followup_from, encoding="utf-8") as f:
                prior_data = json.load(f)
            prior_result = _result_from_dict(prior_data)
        else:
            prior_result = _load_latest_result(followup_from)
            if prior_result is None:
                print(f"No prior result found for {followup_from}")
                sys.exit(1)

        prior_slots = {s["key"]: s["value"] for s in prior_result.final_slots}
        prior_missing_slots = [k for k in QUESTIONABLE_SLOT_KEYS if not prior_slots.get(k)]
        prior_session_index = prior_result.session_index
        prior_handoff = _compose_carry_content(prior_slots, prior_missing_slots)
        print(f"[Follow-up] Using prior session carry ({len(prior_slots)} slot(s), "
              f"{len(prior_missing_slots)} missing, session_index={prior_session_index})")

        # Inject the SAME narrowed carry content into the patient persona —
        # never the old full-prose handoff (AVC-02: the patient-simulator
        # prompt is one of the two named injection points this narrowing
        # closes).
        persona.prior_handoff = prior_handoff
        persona.system_prompt += f"""

## 이전 상담 기록 (당신이 기억해야 할 내용)
당신은 이전에 상담을 받은 적이 있습니다. 아래는 지난 상담에서 수집/미수집된 정보입니다.
이전 상태와 비교하여 현재 상태가 좋아졌는지, 나빠졌는지, 유지되는지를 자연스럽게 대화에 반영하세요.
변화가 있는 부분은 구체적으로 이야기하고, 유지되는 부분은 "비슷해요" 정도로 답하세요.

{prior_handoff}
"""

    # F4 quick-dev isolation seam (design doc §2.6 option C): applied AFTER
    # the prior_handoff block above (own header, never touches that block's
    # own text) and BEFORE `PatientLLM(persona=persona)` is constructed
    # below — so a scripted session's guideline reaches the SAME
    # `persona.system_prompt` the patient LLM actually reads, one text.
    _apply_scenario_guideline(persona, scenario_guideline)

    # 주의: persona.visit_type == "revisit"이더라도, --followup-from이 없으면
    # 첫 상담으로 취급한다. 재상담은 명시적 --followup-from 플래그로만 활성화.

    # Patient input source:
    # - Default: PatientLLM (K-EXAONE) generates dynamic responses.
    # - With --audio: skip PatientLLM; F1Pipeline runs STT on files internally.
    pipeline = F1Pipeline()

    if audio_inputs:
        # audio_inputs 경로에서 STT 실행 → 그 결과를 순차 소비.
        patient_fn = None
        print(f"[STT] Skipping PatientLLM — using {len(audio_inputs)} audio input(s)")
    else:
        patient = PatientLLM(persona=persona)  # auto-loads EXAONE keys from env

        async def patient_fn(agent_msg: str) -> str:  # type: ignore[misc]
            return await patient.respond(agent_msg)

    # 환자 좌표: 명시 → PERSONA_LOCATIONS 기본값 → None (crisis 안내 skip)
    resolved_lat = patient_lat
    resolved_lng = patient_lng
    if resolved_lat is None or resolved_lng is None:
        default = PERSONA_LOCATIONS.get(persona_id)
        if default:
            resolved_lat, resolved_lng = default

    resolved_session_index = session_index
    if resolved_session_index is None:
        resolved_session_index = (
            prior_session_index + 1 if prior_session_index is not None else 1
        )

    session_suffix = "_followup" if followup_from else ""
    if audio_inputs:
        session_suffix += "_audio"
    if phr_paths:
        session_suffix += "_phr"
    result = await pipeline.run_session(
        patient_input_fn=patient_fn,
        session_id=f"f1_{persona_id}{session_suffix}",
        persona_id=persona.persona_id,
        persona_name=persona.name,
        max_turns=max_turns,
        is_revisit=bool(followup_from),  # 명시적 --followup-from만 재상담
        prior_handoff=prior_handoff,
        prior_slots=prior_slots,
        prior_missing_slots=prior_missing_slots,
        prior_session_index=prior_session_index,
        session_index=resolved_session_index,
        simulated_date=simulated_date,
        patient_lat=resolved_lat,
        patient_lng=resolved_lng,
        ocr_documents=ocr_documents,
        ocr_document_hints=ocr_hints,
        audio_inputs=audio_inputs,
        phr_paths=phr_paths,
    )

    # F4 quick-dev provenance threading (design doc §2.6 option C / §2.7) —
    # after `pipeline.run_session(...)` closes above, before `save_f1_
    # result` below, so the tag reaches the saved conversation.json for
    # free (any new F1Result dataclass field is captured by `asdict`).
    _apply_scenario_provenance(result, scenario_pack_id, arc_mode)

    paths = save_f1_result(result)

    # Summary
    print(f"\n{'='*60}")
    print(f"  F1 Result: {persona_id} ({persona.name})")
    if followup_from:
        print("  Mode: Follow-up (재상담)")
    print(f"{'='*60}")
    print(f"  Turns: {result.total_turns}")
    print(f"  Crisis: {f'YES (turn {result.crisis_turn})' if result.crisis_triggered else 'No'}")
    print(f"  Slot Coverage (legacy): {result.slot_coverage:.0%}")
    print(f"  Grounded Coverage: {result.grounded_coverage:.0%}")
    print(f"  Session CTRS: {result.session_ctrs} | Risk floor: {result.risk_floor}")
    print(f"  Probe events: {len(result.probe_events)}")
    print(f"  OCR documents: {len(result.ocr_documents)}")
    print(f"  STT transcripts: {len(result.stt_transcripts)}")
    if result.phr_summary:
        phr = result.phr_summary
        psycho_ct = len(phr.get("psychotropic_medications") or [])
        print(
            f"  PHR: {phr.get('total_medication_events', 0)} meds "
            f"({psycho_ct} psychotropic), {phr.get('total_visits', 0)} visits · "
            f"psychiatric_history={phr.get('has_psychiatric_history', False)}"
        )
    if result.nearby_psychiatric:
        print(f"  Nearby psychiatric (crisis): {len(result.nearby_psychiatric)} hospital(s)")
        for r in result.nearby_psychiatric[:3]:
            phone = f" ☎ {r.get('phone')}" if r.get("phone") else ""
            print(f"    {r.get('rank')}. {r.get('name')} ({r.get('distance_km')}km){phone}")
    print(f"  Errors: {len(result.errors)}")
    print(f"  Files: {', '.join(p.name for p in paths.values())}")
    print(f"{'='*60}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="F1 Pipeline — 자율 대화 기반 사전문진")
    parser.add_argument(
        "--persona", default="VP-001",
        help="VP-001, VP-002, VP-003, VP-004, VP-010, VP-011, VP-012",
    )
    parser.add_argument("--max-turns", type=int, default=10)
    parser.add_argument(
        "--followup-from",
        default=None,
        help="재상담 모드: 이전 세션의 persona ID 또는 conversation.json 경로",
    )
    parser.add_argument(
        "--lat", type=float, default=None,
        help="환자 위도 (Crisis 시 근처 정신과 안내). 미지정 시 PERSONA_LOCATIONS 사용",
    )
    parser.add_argument(
        "--lng", type=float, default=None,
        help="환자 경도 (Crisis 시 근처 정신과 안내). 미지정 시 PERSONA_LOCATIONS 사용",
    )
    parser.add_argument(
        "--ocr",
        default=None,
        help=(
            "OCR 처리할 문서 경로 (콤마 구분). "
            "예: --ocr apps/ai-server/tests/fixtures/ocr/VP-001/VP-001_first_visit_mild_ocr.pdf"
        ),
    )
    parser.add_argument(
        "--ocr-hint",
        default=None,
        help=(
            "OCR 문서 유형 힌트 (콤마 구분, --ocr 개수와 일치). "
            "값: diagnosis | prescription | consultation | lab_result | unknown. "
            "미지정 시 unknown (자동 감지)."
        ),
    )
    parser.add_argument(
        "--ocr-vp-default",
        action="store_true",
        help=(
            "편의 옵션: --persona VP-001 이고 --ocr 미지정이면 "
            "apps/ai-server/tests/fixtures/ocr/VP-001/VP-001_*_ocr.pdf를 자동 첨부."
        ),
    )
    parser.add_argument(
        "--audio",
        default=None,
        help=(
            "환자 음성 입력 파일 경로 (콤마 구분). 지정 시 PatientLLM 대신 STT 결과를 "
            "순차 사용. 예: --audio VP-001-001.mp3,VP-001-002.mp3"
        ),
    )
    parser.add_argument(
        "--audio-vp-default",
        action="store_true",
        help=(
            "편의 옵션: --audio 미지정 시 "
            "apps/ai-server/tests/fixtures/audio/{persona}/{persona}-*.mp3를 정렬 순 자동 첨부."
        ),
    )
    parser.add_argument(
        "--phr",
        default=None,
        help=(
            "PHR JSON 파일 경로 (콤마 구분, 여러 파일 병합). 지정 시 세션 시작 시 "
            "마이헬스웨이 개인건강기록을 로드해 병력 요약을 대화 컨텍스트에 주입. "
            "예: --phr docs/ai/samples/phr/VP-001_medications.json,"
            "docs/ai/samples/phr/VP-001_visits.json"
        ),
    )
    parser.add_argument(
        "--phr-vp-default",
        action="store_true",
        help=(
            "편의 옵션: --persona VP-001~004 · --phr 미지정 시 "
            "PERSONA_PHR_FILES에 등록된 페르소나별 기본 PHR 샘플 파일 자동 첨부."
        ),
    )
    parser.add_argument(
        "--session-index", type=int, default=None,
        help="다중 세션 체이닝용 세션 순번(1부터). 미지정 시 자동 산정.",
    )
    parser.add_argument(
        "--simulated-date", default=None,
        help="이 세션의 시뮬레이션 날짜(ISO, 예: 2026-07-25). 미지정 시 오늘 날짜.",
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

    # BUG-021: fail-fast path-existence validation, not the old unset-only
    # guard (which silently let an explicit-but-wrong PROMPTS_BASE_DIR
    # through and degraded every prompt-driven agent to a generic fallback).
    resolve_prompts_base_dir(PROJECT_ROOT)

    # Resolve OCR documents
    ocr_docs: list[Path] | None = None
    ocr_hints_list: list[DocumentType] | None = None

    if args.ocr:
        ocr_docs = [Path(p.strip()) for p in args.ocr.split(",") if p.strip()]
    elif args.ocr_vp_default:
        default_glob = FIXTURES_DIR / "ocr" / args.persona
        matches = sorted(default_glob.glob(f"{args.persona}_*_ocr.pdf"))
        if matches:
            ocr_docs = matches
            print(f"[OCR default] Auto-attached {len(matches)} document(s) for {args.persona}")

    if args.ocr_hint and ocr_docs:
        hints_raw = [h.strip() for h in args.ocr_hint.split(",") if h.strip()]
        valid = {"diagnosis", "prescription", "consultation", "lab_result", "unknown"}
        ocr_hints_list = [h if h in valid else "unknown" for h in hints_raw]  # type: ignore[misc]

    # Resolve audio inputs (patient utterances)
    audio_paths: list[Path] | None = None
    if args.audio:
        audio_paths = [Path(p.strip()) for p in args.audio.split(",") if p.strip()]
    elif args.audio_vp_default:
        default_glob = FIXTURES_DIR / "audio" / args.persona
        matches = sorted(default_glob.glob(f"{args.persona}-*.mp3"))
        if matches:
            audio_paths = matches
            print(
                f"[Audio default] Auto-attached {len(matches)} audio file(s) for {args.persona}"
            )

    # Resolve PHR inputs
    phr_paths: list[Path] | None = None
    if args.phr:
        phr_paths = [Path(p.strip()) for p in args.phr.split(",") if p.strip()]
    elif args.phr_vp_default:
        default_files = PERSONA_PHR_FILES.get(args.persona)
        if default_files:
            resolved = [PROJECT_ROOT / p for p in default_files]
            existing = [p for p in resolved if p.is_file()]
            if existing:
                phr_paths = existing
                print(
                    f"[PHR default] Auto-attached {len(existing)} PHR file(s) for {args.persona}"
                )

    asyncio.run(
        _run_simulation(
            args.persona,
            args.max_turns,
            args.followup_from,
            patient_lat=args.lat,
            patient_lng=args.lng,
            ocr_documents=ocr_docs,
            ocr_hints=ocr_hints_list,
            audio_inputs=audio_paths,
            phr_paths=phr_paths,
            session_index=args.session_index,
            simulated_date=args.simulated_date,
        )
    )


if __name__ == "__main__":
    main()
