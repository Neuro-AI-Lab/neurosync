"""Handoff Generator agent — produces structured Markdown handoff reports."""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel

from src.adapters.base import ChatMessage, LLMAdapter
from src.agents.base import AgentInput, BaseAgent
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.common import CTRS_TO_RISK, CTRSLevel, EvidencePacket, EvidenceSource, RiskLevel
from src.schemas.handoff import HandoffInput, HandoffOutput, SlotData

logger = logging.getLogger(__name__)

_PROMPT_AGENT_NAME = "handoff_generator"
# BUG-050 / EXP-029 / CVR-040: v4 (addition-only over v2, prompt file at
# prompts/handoff_generator/v4.system.md) adds a "citation strictness" block
# targeting the observed run()-path failure modes: missing [ev_*] citations
# in sections 3/7/11, fabricated [ev_risk_*] IDs with no real risk event,
# orphan/dangling evidence-registry mismatches in section 12, and
# out-of-range evidence IDs (citing e.g. ev_msg_013 when only 12 packets were
# provided). CVR-040 (cleared-with-conditions) required two further
# additions before pin: gray-zone guidance (search packets by content before
# retreating to "미수집") and an explicit packet-range rule with a worked
# example — both applied. Live in-process repro against the real B5 fixture
# (monkeypatched _PROMPT_VERSION, non-destructive) reached 5/6 EvidenceVerifier
# `passed` verdicts (>= the 4/6 pin threshold); the 1 regenerate was a
# legitimate warning-budget case (3 sections under-cited in one sample), not
# a fabrication/orphan-registry failure — consistent with the production
# 3-attempt regenerate loop's design. v2 (prompt_redesign_v3.md §2.4) removes
# the dead ctrs_level output instruction and placeholder-izes all example
# values.
#
# EXP-030 cluster D1 / CVR-039 finding 3: v4.1 (addition-only over v4, prompt
# file at prompts/handoff_generator/v4.1.system.md) adds a "denial format
# preservation" block targeting a further generation-time loss mode: slot
# values already containing the citation-embedded denial form (e.g.
# `없음(환자 부인: '...')`, produced upstream by clinical_slot v5/BUG-050/
# BUG-049) were present in raw slot logs (CVR-039 finding 3, VP-010 fixture)
# but the rendered B1/B2/B3 handoff reports never preserved that form in
# sections 5/7 — it was silently collapsed to a generic summary. v4.1 does
# not touch v4's existing citation-strictness rules; it adds one further
# rule requiring verbatim-or-meaning-preserving retention of that quoted
# denial in sections 5/7 (and elsewhere the form appears in slot values).
#
# EXP-030 pin-fix wave / CVR-042 finding 2: v4.2 (addition-only over v4.1,
# prompt file at prompts/handoff_generator/v4.2.system.md) adds a
# "risk_assessment denial/screen nuance preservation" block, designed
# COHERENTLY with ADR-044 (orchestrator.py's backstop-vs-risk-grounding
# gate): v4.1's "denial format preservation" rule names section 5 as a
# target but risk_assessment never actually produces the literal
# `없음(환자 부인: '...')` trigger it detects (`clinical_slot/v5.system.md:
# 85-89`, CVR-037 condition 1 hard-excludes risk_assessment from that
# encoding) — only `src/safety_probe.py`'s own compose functions populate
# that slot, in a DIFFERENT quoted format. Now that ADR-044 makes the
# mandatory SI screen/probe actually ground risk_assessment on the
# production route (previously near-never grounded there), section 5 will
# genuinely carry that format's content — v4.2 gives it its own explicit,
# non-literal-trigger preservation rule (and an explicit disclaimer that
# v4.1's rule does not cover it), instead of leaving it silently unhandled
# and mistakenly assumed "already covered". v4.1's own body (including its
# denial-format-preservation rule) is unchanged.
#
# BUG-069 / PLAN-2026-W30-BUG069 (2026-07-23): v4.3 (addition-only over v4.2,
# prompt file at prompts/handoff_generator/v4.3.system.md) adds a "metadata
# citation discipline" block and a "first-visit longitudinal trend
# prohibition" block, closing a distinct diagnosis-level gap the v4/v4.1/v4.2
# citation-strictness rules never covered: sections 1/2 (patient demographics,
# session timestamps) request fields — gender, age range, session start/end
# time — that `HandoffInput`/`_build_user_content` below NEVER actually
# serialize (confirmed by reading this module and `schemas/handoff.py`; no
# gender/age/timestamp field exists anywhere in the handoff pipeline). The
# generator was fabricating plausible-looking values for structurally-absent
# input, and section 1's identifier field was echoing the prompt's own
# "(예: ...)" worked-example text verbatim as if it were a real value.
# Separately, section 9's pre-existing first-visit instruction had no worked
# example (same "rule without an example is unreliable" pattern as BUG-048/
# 049/050) and was observed violated live (a first-visit session's section 9
# asserted a fabricated prior PHQ-9/CTRS/sleep baseline and a directional
# "악화" trend — EXP-031 `logs_rerun/S14_clinician_get_report_bugfix.json`).
# v4.3 does not touch v4.2's existing citation-strictness/denial-preservation/
# risk_assessment rules; `_build_user_content` below is ALSO changed (paired
# fix) to emit an explicit "## 환자 메타데이터" block with literal "기록
# 없음"/"미수집" placeholders for gender/age/timestamps — since apps/api's
# `HandoffRequest` never threads real patient.gender/session-timing values
# into this schema either (a separate, deferred apps/api-side gap — this
# in-scope fix only makes the CURRENT absence explicit and copyable instead
# of leaving blank space the model fills by invention), the safe fallback
# ("기록 없음") is the correct grounded rendering today regardless of that
# upstream gap. `evidence_verifier.py` gets a paired mechanical check
# (metadata-grounding + first-visit-trend-prohibition) so this is not a
# prompt-only defense — BUG-049 lineage dual-defense.
#
# BUG-070 / PLAN-2026-W30-BUG069 (2026-07-23, qa live re-verification of
# v4.3): v4.4 (addition-only over v4.3, prompt file at
# prompts/handoff_generator/v4.4.system.md) closes a residual leak of the
# SAME defect class v4.3 fixed for sections 1/2, now observed in section 6
# (구조화 척도 결과): `ScaleScore` (`schemas/handoff.py`) carries only
# `scale_name`/`total_score`/`severity` — no administration timestamp, no
# per-item positive-symptom list — yet section 6's template literally shows
# `<시행 일시>`/`<주요 양성 문항>` placeholder cells, and v4.3's "메타데이터
# 인용 규율" only worked-examples sections 1/2, so the model was not reliably
# generalizing the "cite-or-미수집" discipline to other sections' structurally
# absent sub-fields — it echoed the literal `<...>` template tokens into the
# final report instead (live evidence: `experiments/EXP-031/logs_bug069/
# resp_session1_*.json`/`resp_session2_*.json`, both first-visit and
# returning-patient sessions; `ai_server_stdout.log` shows the EXISTING
# `evidence_verifier._check_metadata_grounding`'s `<...>`-leak detector
# correctly firing `metadata_template_artifact` and forcing regenerate on
# EVERY one of 3 attempts, but the generator never converges to a clean
# output within the budget — a fail-open exhaustion, not a missed detection).
# v4.4 adds one generalized "템플릿 placeholder 전 섹션 스윕" section (with a
# §6 worked example) making explicit that the v4.3 discipline applies to ANY
# section/sub-field, not just 1/2. Paired fix: `_build_user_content` below now
# emits an explicit, literal "시행 일시: 미수집" / "주요 양성 문항: 미수집"
# note per administered scale — the same "give the model real grounded text
# to copy instead of blank space to invent from" strategy v4.3 already used
# for gender/age/timestamps — so the generator has a concrete answer instead
# of an unresolved template slot. `evidence_verifier.py`'s existing
# `<...>`-leak check (`_TEMPLATE_PLACEHOLDER_ARTIFACT_RE`, added in the v4.3/
# BUG-069 fix) already scans the WHOLE report body, not just sections 1/2, so
# no verifier code change was needed for detection — only the generator side
# needed fixing to make attempts actually converge.
#
# BUG-070 residual regression / PLAN-2026-W30-BUG069 (2026-07-23, qa live
# re-verification of v4.4): v4.5 (addition-only over v4.4, prompt file at
# prompts/handoff_generator/v4.5.system.md) closes a NEW defect the v4.4 fix
# itself introduced: v4.4's "작성 후 자체 점검" item 5 instructed the model to
# re-verify no literal `<...>` template token leaked into the report — the
# model followed this literally but then appended a self-check RESULT
# SUMMARY after section 12 (e.g. "**점검 완료**: ... `` `<...>` `` 형태의
# placeholder 문자열 없음"), and that summary sentence itself quotes the
# literal `<...>` token (to assert its absence), which matches
# `evidence_verifier.py`'s existing whole-report `_TEMPLATE_PLACEHOLDER_
# ARTIFACT_RE` — a false positive that forces `metadata_template_artifact`
# regenerate on every attempt (live evidence: `experiments/EXP-031/
# logs_bug069/resp_session1_v44_13722fd0.json`, `resp_session3_v44_new.json`,
# both exhausting 3/3 attempts per `ai_server_stdout_v44.log`). v4.5 adds one
# "자체 점검 결과 비노출 규율" section making explicit that the self-check is
# a silent internal step never reflected in output — the report must end at
# section 12's table, no meta-commentary after it, and no literal `<...>`
# reproduction even when describing its absence. No verifier code change:
# the false positive was the generator creating new detectable text, not a
# verifier over-fire on legitimate content — `_TEMPLATE_PLACEHOLDER_
# ARTIFACT_RE` continues to catch real data-cell leaks (e.g. section 6)
# unchanged. `_build_user_content` is unaffected (this is an output-shape
# defect, not an input-grounding gap).
#
# UNCHANGED by the v4/v4.1/v4.2/v4.3/v4.4/v4.5 additions: `_NARRATIVE_PROMPT_
# VERSION` (v3, `generate_narrative()`'s narrow A8-only role) is a separate
# pin and is not affected by this run()-path change.
_PROMPT_VERSION = "v4.5"

# F5 hand-off report Task 2 (`_archive/plans/f5_quick_dev_plan.md` follow-on,
# handoff_generator v3): a SEPARATE pin, used ONLY by `generate_narrative`
# below. v3's prompt (`apps/ai-server/prompts/handoff_generator/v3.system.md`)
# writes ONLY a brief clinician-facing A8 narrative from F5's own
# already-assembled structured data — it does not replace v2's 12-section
# role, and `run()`/`HandoffInput`/the live route above are untouched.
_NARRATIVE_PROMPT_VERSION = "v3"


def _build_user_content(inp: HandoffInput) -> str:
    """Serialize the handoff input into a structured user message for the LLM."""
    parts: list[str] = []

    # BUG-069 fix: `HandoffInput` has no gender/age/session-timestamp field
    # (confirmed — `schemas/handoff.py` carries none), so sections 1/2's
    # demographic/timing requests were previously backed by nothing at all,
    # inviting fabrication. Emitting an explicit, literal "기록 없음"/
    # "미수집" block gives the model real grounded text to copy instead of
    # blank space it must fill by inventing a value. If a future apps/api
    # enrichment adds these fields to `HandoffInput`, this block should be
    # updated to render the real values instead (out of this fix's scope —
    # apps/api restart required).
    # BUG-069 follow-up (F5 metadata enrichment, 2026-07-25): `HandoffInput`
    # gained optional `patient_gender`/`session_started_at`/
    # `session_ended_at` fields (apps/api's `_build_request` now threads the
    # real `PatientProfile.gender`/`Session.created_at`/`Session.
    # submitted_at` values through). When a value IS present, cite it
    # directly — this is a real input field, not an invention, so the v4.3+
    # "cite-or-기록없음" grounding discipline is satisfied either way. When
    # absent (older caller, field not yet populated, session never
    # submitted), the v4.3 fallback text is UNCHANGED — the fallback exists
    # for exactly that case and must keep working for it. `연령대`/`소요
    # 시간` have no backing field even after this fix (out of this fix's
    # scope — `PatientProfile.birth_year` is a distinct enrichment; a
    # derived duration would need both start AND end present) — those two
    # keep the original fallback text unconditionally.
    parts.append("## 환자 메타데이터")
    if inp.patient_gender:
        parts.append(f"- **성별**: {inp.patient_gender}")
    else:
        parts.append("- **성별**: 기록 없음 (입력에 제공되지 않음)")
    parts.append("- **연령대**: 기록 없음 (입력에 제공되지 않음)")
    if inp.session_started_at:
        parts.append(f"- **사전문진 시작 일시**: {inp.session_started_at}")
    else:
        parts.append("- **사전문진 시작 일시**: 미수집 (입력에 제공되지 않음)")
    if inp.session_ended_at:
        parts.append(f"- **사전문진 종료 일시**: {inp.session_ended_at}")
    else:
        parts.append("- **사전문진 종료 일시**: 미수집 (입력에 제공되지 않음)")
    parts.append("- **소요 시간**: 미수집 (입력에 제공되지 않음)")

    # Slots
    parts.append("\n## 수집된 슬롯 데이터")
    slot_dict = inp.slots.model_dump(exclude_none=True)
    if slot_dict:
        for k, v in slot_dict.items():
            parts.append(f"- **{k}**: {v}")
    else:
        parts.append("- (수집된 슬롯 없음)")

    # Scale scores
    # BUG-070 fix: `ScaleScore` (schemas/handoff.py) carries only
    # scale_name/total_score/severity — no administration timestamp, no
    # per-item positive-symptom list — so section 6's "시행 일시"/"주요 양성
    # 문항" columns were previously backed by nothing at all, inviting the
    # model to echo the template's own literal `<시행 일시>`/`<주요 양성
    # 문항>` placeholder tokens verbatim (BUG-070 live repro). Same strategy
    # as v4.3's gender/age/timestamp fix: give the model explicit, literal
    # "미수집" text to copy per scale instead of blank space to invent from.
    if inp.scale_scores:
        parts.append("\n## 문진 점수")
        for s in inp.scale_scores:
            parts.append(f"- {s.scale_name}: {s.total_score} ({s.severity})")
            parts.append("  - 시행 일시: 미수집 (입력에 제공되지 않음)")
            parts.append("  - 주요 양성 문항: 미수집 (문항별 응답이 입력에 제공되지 않음)")

    # Risk events
    if inp.risk_events:
        parts.append("\n## 위험 이벤트")
        for idx, evt in enumerate(inp.risk_events, 1):
            parts.append(f"- [{idx}] {evt}")

    # OCR documents
    if inp.ocr_documents:
        parts.append("\n## OCR 문서")
        for idx, doc in enumerate(inp.ocr_documents, 1):
            parts.append(f"- [{idx}] {doc}")

    # Conversation history
    if inp.conversation_history:
        parts.append("\n## 대화 내역")
        for turn in inp.conversation_history:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            parts.append(f"**{role}**: {content}")

    # Prior handoff
    if inp.prior_handoff:
        parts.append("\n## 이전 Handoff Report")
        parts.append(inp.prior_handoff)
    elif inp.is_first_visit:
        parts.append("\n## 방문 유형: 초진")

    return "\n".join(parts)


def _find_missing_slots(slots: SlotData) -> list[str]:
    """Return names of slots that are None (uncollected)."""
    data = slots.model_dump()
    return [k for k, v in data.items() if v is None]


_RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.none: 0,
    RiskLevel.low: 1,
    RiskLevel.medium: 2,
    RiskLevel.high: 3,
    RiskLevel.critical: 4,
}
_RISK_BY_VALUE: dict[str, RiskLevel] = {r.value: r for r in RiskLevel}


def _event_risk(evt: object) -> RiskLevel:
    """Best-effort severity of a single risk event.

    Prefers an explicit ``risk_level``; otherwise maps ``ctrs_level`` via
    CTRS_TO_RISK; a present-but-unlabelled event keeps the "at least medium"
    floor.
    """
    if not isinstance(evt, dict):
        return RiskLevel.medium
    raw = str(evt.get("risk_level", "")).strip().lower()
    if raw in _RISK_BY_VALUE:
        return _RISK_BY_VALUE[raw]
    ctrs_raw = str(evt.get("ctrs_level", "")).strip()
    if ctrs_raw.isdigit():
        try:
            return CTRS_TO_RISK.get(CTRSLevel(int(ctrs_raw)), RiskLevel.medium)
        except ValueError:
            pass
    return RiskLevel.medium


def _detect_risk_level(risk_events: list[dict[str, str]]) -> RiskLevel:
    """Return the maximum severity across all risk events (none if empty)."""
    if not risk_events:
        return RiskLevel.none
    return max(
        (_event_risk(evt) for evt in risk_events),
        key=lambda r: _RISK_ORDER[r],
    )


class NarrativeGenerationOutput(BaseModel):
    """`generate_narrative`'s own return type — deliberately NOT
    `HandoffOutput` (that type is 12-section/`report_markdown`-shaped, v2's
    own contract). Local to this module — never imports `schemas.
    handoff_report` (F5's schema module), keeping this agent decoupled
    from F5-specific types; the CALLER (`src.services.f5_report.
    build_narrative_input_text` + `src.f5.HandoffReportInput.
    narrative_text`) is responsible for both directions of that
    conversion."""

    text: str
    model_used: str
    prompt_version: str
    latency_ms: float


class HandoffGeneratorAgent(BaseAgent):
    """Generates a structured Markdown handoff report with evidence citations."""

    def __init__(
        self,
        model_router: ModelRouter,
        prompt_loader: PromptLoader,
    ) -> None:
        self._router = model_router
        self._prompt_loader = prompt_loader

    @property
    def agent_name(self) -> str:
        return _PROMPT_AGENT_NAME

    async def run(self, inp: AgentInput, **kwargs: Any) -> HandoffOutput:
        """Generate the handoff report."""
        start = time.perf_counter()

        if not isinstance(inp, HandoffInput):
            raise TypeError(f"Expected HandoffInput, got {type(inp).__name__}")

        # Load system prompt
        system_prompt = self._prompt_loader.load_system_prompt(
            _PROMPT_AGENT_NAME, _PROMPT_VERSION
        )

        # Build user content
        user_content = _build_user_content(inp)

        # Select model
        selection = self._router.select_model(self.agent_name)
        adapter = self._router.get_adapter(selection.adapter_name)
        assert isinstance(adapter, LLMAdapter)

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ]

        try:
            resp = await adapter.chat_timed(
                messages,
                model=selection.model_id,
                temperature=0.2,
                max_tokens=4096,
            )
            self._router.record_success(selection.adapter_name)
            report_markdown = resp.content
            model_used = resp.model

        except Exception as exc:
            logger.error("Handoff generation failed on %s: %s", selection.adapter_name, exc)
            self._router.record_failure(selection.adapter_name, exc)

            # Try fallback
            fallback = self._router.get_fallback(
                self.agent_name, selection.adapter_name, str(exc)
            )
            if fallback is None:
                raise RuntimeError("Handoff generation failed — no fallback available") from exc

            fb_adapter = self._router.get_adapter(fallback.adapter_name)
            assert isinstance(fb_adapter, LLMAdapter)
            resp = await fb_adapter.chat_timed(
                messages,
                model=fallback.model_id,
                temperature=0.2,
                max_tokens=4096,
            )
            self._router.record_success(fallback.adapter_name)
            report_markdown = resp.content
            model_used = resp.model

        # Extract evidence packets from the conversation history
        evidence_packets = _extract_evidence_packets(inp)

        missing_slots = _find_missing_slots(inp.slots)
        risk_level = _detect_risk_level(inp.risk_events)

        latency_ms = (time.perf_counter() - start) * 1000

        return HandoffOutput(
            model_used=model_used,
            prompt_version=_PROMPT_VERSION,
            latency_ms=latency_ms,
            reason_summary="Handoff report generated from collected slots and conversation",
            report_markdown=report_markdown,
            evidence_packets=evidence_packets,
            missing_slots=missing_slots,
            risk_level=risk_level,
            requires_human_review=risk_level != RiskLevel.none or len(missing_slots) > 3,
        )

    async def generate_narrative(self, structured_summary: str) -> NarrativeGenerationOutput:
        """F5 hand-off report Task 2 — generate ONLY the A8 narrative
        section from *structured_summary*, a plain-text summary of F5's
        own A0-A5/A7/B sections (built by `src.services.f5_report.
        build_narrative_input_text`, which the CALLER runs before this
        method — A6 content is never included in that text by design, so
        this method never even receives disease-candidate text to
        potentially echo). Uses the SEPARATE `_NARRATIVE_PROMPT_VERSION =
        "v3"` pin — `run()`'s own `_PROMPT_VERSION = "v2"` and the live
        `POST /ai/handoff/generate` route are entirely unaffected by this
        method's existence.

        `src.f5` itself never calls this method (module docstring's
        zero-LLM invariant) — a CALLER (harness or future live route) is
        responsible for calling this, then passing the returned `.text`
        into `HandoffReportInput.narrative_text` /
        `narrative_enabled=True` so `src.f5.assemble_handoff_report` can
        render (or, per its own defense-in-depth guard, refuse) it.
        """
        start = time.perf_counter()
        system_prompt = self._prompt_loader.load_system_prompt(
            _PROMPT_AGENT_NAME, _NARRATIVE_PROMPT_VERSION
        )
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=structured_summary),
        ]

        selection = self._router.select_model(self.agent_name)
        adapter = self._router.get_adapter(selection.adapter_name)
        assert isinstance(adapter, LLMAdapter)

        try:
            resp = await adapter.chat_timed(
                messages,
                model=selection.model_id,
                temperature=0.2,
                max_tokens=800,
            )
            self._router.record_success(selection.adapter_name)
            text, model_used = resp.content, resp.model
        except Exception as exc:
            logger.error("Narrative generation failed on %s: %s", selection.adapter_name, exc)
            self._router.record_failure(selection.adapter_name, exc)

            fallback = self._router.get_fallback(
                self.agent_name, selection.adapter_name, str(exc)
            )
            if fallback is None:
                raise RuntimeError(
                    "Narrative generation failed — no fallback available"
                ) from exc

            fb_adapter = self._router.get_adapter(fallback.adapter_name)
            assert isinstance(fb_adapter, LLMAdapter)
            resp = await fb_adapter.chat_timed(
                messages,
                model=fallback.model_id,
                temperature=0.2,
                max_tokens=800,
            )
            self._router.record_success(fallback.adapter_name)
            text, model_used = resp.content, resp.model

        latency_ms = (time.perf_counter() - start) * 1000
        return NarrativeGenerationOutput(
            text=text.strip(),
            model_used=model_used,
            prompt_version=_NARRATIVE_PROMPT_VERSION,
            latency_ms=latency_ms,
        )


def _extract_evidence_packets(inp: HandoffInput) -> list[EvidencePacket]:
    """Build evidence packet list from input data sources."""
    packets: list[EvidencePacket] = []
    counter: dict[str, int] = {}

    def _next_id(prefix: str) -> str:
        counter[prefix] = counter.get(prefix, 0) + 1
        return f"ev_{prefix}_{counter[prefix]:03d}"

    # Messages as evidence
    for turn in inp.conversation_history:
        if turn.get("role") == "user":
            content = turn.get("content", "")
            if content.strip():
                packets.append(
                    EvidencePacket(
                        evidence_id=_next_id("msg"),
                        source_type=EvidenceSource.message,
                        source_ref="환자 발화",
                        content_summary=content[:120],
                    )
                )

    # Scale scores
    for score in inp.scale_scores:
        packets.append(
            EvidencePacket(
                evidence_id=_next_id("scale"),
                source_type=EvidenceSource.scale,
                source_ref=score.scale_name,
                content_summary=f"{score.scale_name}: {score.total_score} ({score.severity})",
            )
        )

    # Risk events
    for evt in inp.risk_events:
        packets.append(
            EvidencePacket(
                evidence_id=_next_id("risk"),
                source_type=EvidenceSource.risk_event,
                source_ref="Safety Agent",
                content_summary=str(evt)[:120],
            )
        )

    # OCR documents
    for doc in inp.ocr_documents:
        packets.append(
            EvidencePacket(
                evidence_id=_next_id("doc"),
                source_type=EvidenceSource.document_block,
                source_ref="OCR 문서",
                content_summary=str(doc)[:120],
            )
        )

    # Prior handoff
    if inp.prior_handoff:
        packets.append(
            EvidencePacket(
                evidence_id=_next_id("prior"),
                source_type=EvidenceSource.prior_handoff,
                source_ref="이전 Handoff Report",
                content_summary=inp.prior_handoff[:120],
            )
        )

    return packets
