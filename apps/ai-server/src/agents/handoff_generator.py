"""Handoff Generator agent — produces structured Markdown handoff reports."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from src.adapters.base import ChatMessage, LLMAdapter
from src.agents.base import AgentInput, BaseAgent
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.common import EvidencePacket, EvidenceSource, RiskLevel
from src.schemas.handoff import HandoffInput, HandoffOutput, SlotData
from src.services.handoff_risk import RiskEventInput, detect_risk_level, risk_event_text

logger = logging.getLogger(__name__)

_PROMPT_AGENT_NAME = "handoff_generator"
# PLAN-2026-W28 C1 / ADR-007: v2 (prompt_redesign_v3.md §2.4) removes the dead
# ctrs_level output instruction and placeholder-izes all example values.
# UNCHANGED by the F5 A8-narrative addition below: `run()`/`HandoffInput`
# (the live `POST /ai/handoff/generate` route, `routes/handoff.py`) keeps
# loading v2 exactly as before — v2's own 12-section role is not the same
# job as `generate_narrative()`'s narrow A8-only role, so they are pinned
# independently rather than sharing one version constant.
_PROMPT_VERSION = "v2"

# F5 hand-off report Task 2 (`_archive/plans/f5_quick_dev_plan.md` follow-on,
# handoff_generator v3): a SEPARATE pin, used ONLY by `generate_narrative`
# below. v3's prompt (`docs/ai/prompts/handoff_generator/v3.system.md`)
# writes ONLY a brief clinician-facing A8 narrative from F5's own
# already-assembled structured data — it does not replace v2's 12-section
# role, and `run()`/`HandoffInput`/the live route above are untouched.
_NARRATIVE_PROMPT_VERSION = "v3"


def _build_user_content(inp: HandoffInput) -> str:
    """Serialize the handoff input into a structured user message for the LLM."""
    parts: list[str] = []

    # Slots
    parts.append("## 수집된 슬롯 데이터")
    slot_dict = inp.slots.model_dump(exclude_none=True)
    if slot_dict:
        for k, v in slot_dict.items():
            parts.append(f"- **{k}**: {v}")
    else:
        parts.append("- (수집된 슬롯 없음)")

    # Scale scores
    if inp.scale_scores:
        parts.append("\n## 문진 점수")
        for s in inp.scale_scores:
            parts.append(f"- {s.scale_name}: {s.total_score} ({s.severity})")

    # Risk events
    if inp.risk_events:
        parts.append("\n## 위험 이벤트")
        for idx, evt in enumerate(inp.risk_events, 1):
            parts.append(f"- [{idx}] {risk_event_text(evt)}")

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


def _detect_risk_level(risk_events: Sequence[RiskEventInput]) -> RiskLevel:
    return detect_risk_level(risk_events)


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
                content_summary=risk_event_text(evt)[:120],
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
