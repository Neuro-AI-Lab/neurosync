"""BUG-009 repro: the production `OrchestratorAgent._CRISIS_MESSAGES` still
emit the superseded "1393" suicide-prevention hotline number and never
mention "109", while every other crisis-response surface in this codebase
(the validated `f1.py` pipeline the safety matrix / SM-* scenarios run
against, and `evidence_verifier.py`'s own report audit) has already
standardized on "109" as the current number.

Discovered incidentally during the ADR-011 SM-08a/b spot-gate (qa was asked
to verify SM-08b's `crisis_response_contains_any: ["109", "119"]` expectation
against "the crisis-response source in f1.py/safety code" and flag it as a
BUG if the real hotlines differ). SM-08b's own expectation is correct against
`f1.py.CRISIS_RESPONSE` (`src/f1.py:60-63`, contains both "109" and "119") --
that scenario is not affected. But grepping "safety code" more broadly turned
up a second, inconsistent crisis-message surface:

  - `src/f1.py:60-63` (`CRISIS_RESPONSE`, the validated F1 pipeline path
    exercised by every SM-* scenario): "...자살예방상담전화 109, 응급전화
    119로 연락해 주세요."
  - `src/f1.py:84-87` (`_SOFT_SAFETY_NOTE`, post-probe de-escalation note):
    "...자살예방상담전화 109에서..."
  - `src/agents/evidence_verifier.py:315-332` (`_check_ctrs_action_alignment`,
    audits handoff report section 11): expects CTRS-2 reports to contain
    `109|119|긴급|위기상담` and CTRS-3 reports to contain
    `정신건강의학과|109|위기` -- i.e. the project's own report-quality gate
    treats "109" as the current standard, with no "1393" branch at all.
  - `src/agents/orchestrator.py:58-69` (`_CRISIS_MESSAGES`, consumed live at
    `orchestrator.py:584` in the actual production turn-handling path --
    NOT exercised by f1.py or by any SM-* scenario, per REV-002 issue #8's
    already-flagged f1.py-vs-production parity gap): both the EMERGENCY
    (CTRS 1) and HIGH_RISK (CTRS 2) messages say "자살예방상담전화 1393"
    and never say "109" at all.

This is a real, live, production-path inconsistency (not a scenario-file
defect) -- it does not affect SM-08a/SM-08b's own validity, since those
scenarios exercise `f1.py`, not `orchestrator.py`. Filed as BUG-009, not a
reason to fail the SM-08a/b gate.
"""

from __future__ import annotations

from src.agents.orchestrator import _CRISIS_MESSAGES
from src.f1 import CRISIS_RESPONSE
from src.schemas.orchestrator import CTRSLevel

# The project's own current-standard hotline number, per f1.py (the
# validated pipeline every SM-* safety-matrix scenario runs against) and
# evidence_verifier.py's own report-audit regexes (both branches expect
# "109", neither expects "1393").
_CURRENT_HOTLINE = "109"
_DEPRECATED_HOTLINE = "1393"


def test_f1_crisis_response_uses_current_hotline() -> None:
    """Sanity check: the validated pipeline's own crisis text is what
    SM-08b's `crisis_response_contains_any: ["109", "119"]` expectation
    assumes. If this ever fails, SM-08b's expectation (not just BUG-009)
    needs re-adjudication."""
    assert _CURRENT_HOTLINE in CRISIS_RESPONSE
    assert "119" in CRISIS_RESPONSE


def test_orchestrator_emergency_message_missing_current_hotline() -> None:
    """BUG-009: the production CTRS-1 (EMERGENCY) crisis message still only
    references the deprecated "1393" number and omits "109" entirely."""
    msg = _CRISIS_MESSAGES[CTRSLevel.EMERGENCY]
    assert _DEPRECATED_HOTLINE in msg, (
        "expected the pre-fix state (deprecated number present) -- if this "
        "fails, BUG-009's EMERGENCY message may already be fixed"
    )
    assert _CURRENT_HOTLINE not in msg, (
        "BUG-009 appears fixed for the EMERGENCY message: '109' is now "
        "present. Update error.md and this test accordingly."
    )


def test_orchestrator_high_risk_message_missing_current_hotline() -> None:
    """BUG-009: the production CTRS-2 (HIGH_RISK) crisis message -- the
    exact severity band SM-08b (ADR-010 rule 5) targets -- also only
    references "1393", never "109", unlike f1.py's CRISIS_RESPONSE for the
    same severity band."""
    msg = _CRISIS_MESSAGES[CTRSLevel.HIGH_RISK]
    assert _DEPRECATED_HOTLINE in msg, (
        "expected the pre-fix state (deprecated number present) -- if this "
        "fails, BUG-009's HIGH_RISK message may already be fixed"
    )
    assert _CURRENT_HOTLINE not in msg, (
        "BUG-009 appears fixed for the HIGH_RISK message: '109' is now "
        "present. Update error.md and this test accordingly."
    )
