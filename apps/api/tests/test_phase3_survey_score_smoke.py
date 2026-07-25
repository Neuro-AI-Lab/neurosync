"""PRD §4/§7 Phase 3 criterion 2 smoke — REV-010 issue 1 remediation.

REV-010 (critic, 2026-07-22, blocking) found that the only pre-existing test
touching `score_with_ai` (`test_questionnaire_scoring_ai.py`, "PR#74 M4",
Phase-0-era) exercises the AI-success (non-fallback) path for **PHQ9 only**;
GAD-7 and PHQ-4 had zero AI-success coverage and AUDIT-C had only a
deliberate-fallback test. The PRD's own named verification method for
criterion 2 (`docs/ai/integration_prd_f1f3_hospital.md:155,157`) is:

    "4종 문진(PHQ9/GAD7/AUDITC/PHQ4) 각 1건씩 실제 응답 세트로 스코어링
    스모크" + "로그에 local fallback 카운트 0 확인"

This file adds that missing coverage directly against `score_with_ai`
(`src/services/questionnaire.py`) — no `apps/api/tests/conftest.py` fixture
and no DB are needed, since `score_with_ai` takes its `AIClient` as a plain
argument. This sidesteps BUG-058 (broken `client` fixture) entirely rather
than working around it.

Non-tautology design (the previous test `test_uses_ai_server_result_when_available`
was flagged as weak because its AI-mocked value could coincide with what local
scoring would independently produce for the same input): every scale's fixture
below is deliberately constructed so the mocked ai-server result is one a
correct local fallback computation of the *same input* could never produce —
either the `total_score`/`severity` diverge from `severity_for()`'s own cutoff
math, or (mirroring the PRD's named PHQ-9 item9 SI-flag / AUDIT-C Korean-cutoff
specifics) `critical_item_positive=True` is asserted on non-PHQ9 scales, which
`critical_item_positive()` can structurally never return (it hard-codes
`False` unless `qtype == "PHQ9"`) — so a passing assertion is only possible if
the ai-server branch, not the local-fallback branch, actually executed.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import pytest
from contracts.survey import SurveyScoreResponse

from src.services.ai_client import AIClientError
from src.services.questionnaire import critical_item_positive, score_questionnaire, score_with_ai

# ── BUG-052/058 hard constraint: force-empty, never unset, all live keys ──
for _key in (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "UPSTAGE_API_KEY",
    "HIRA_API_KEY",
    "KAKAO_API_KEY",
    "NS_RAG_API_KEY",
    "SKT_A_X_API_KEY",
):
    os.environ[_key] = ""


@pytest.fixture(autouse=True)
def _forbid_live_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defense-in-depth: this suite never touches `httpx` directly (the mock
    ai-server is a plain fake object satisfying `AIClient`'s duck-typed
    `survey_score` method), but guard the real transport anyway in case a
    future edit routes through the real `AIClient`."""
    import httpx

    _real_post = httpx.AsyncClient.post

    async def _guarded_post(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> Any:
        transport = getattr(self, "_transport", None)
        if isinstance(transport, httpx.ASGITransport | httpx.MockTransport):
            return await _real_post(self, *args, **kwargs)
        raise AssertionError(
            "live HTTP call attempted — this suite must only use the "
            "mock-ai-server fake client, never a live AIClient transport"
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _guarded_post)


class _MockAIServer:
    """Stands in for `AIClient` at the exact boundary `score_with_ai` calls —
    equivalent to a mocked `/ai/survey/score` response, no network."""

    def __init__(self, result: SurveyScoreResponse) -> None:
        self._result = result
        self.calls: list[Any] = []

    async def survey_score(self, payload: Any) -> SurveyScoreResponse:
        self.calls.append(payload)
        return self._result


# One real response set + one non-tautological ai-server mock per scale type.
# `answers` are chosen so `score_questionnaire()`'s own local math would land
# on a materially different (total, severity) than the mocked ai-server value,
# and (for non-PHQ9) with `critical_item_positive` a local fallback could
# structurally never produce.
CASES: dict[str, dict[str, Any]] = {
    "PHQ9": {
        # sum=9 -> local "mild" (5..9 band); item9=0 -> local critical False.
        "answers": [1, 1, 1, 1, 1, 1, 1, 1, 0],
        "ai_total": 27,
        "ai_severity": "severe",
        "ai_critical": True,  # PRD-named: PHQ-9 item9 SI flag
    },
    "GAD7": {
        # sum=7 -> local "mild" (5..9 band).
        "answers": [1, 1, 1, 1, 1, 1, 1],
        "ai_total": 21,
        "ai_severity": "severe",
        "ai_critical": True,  # local fallback can never set this (qtype != PHQ9)
    },
    "AUDITC": {
        # sum=3 -> local "minimal" (<=3 band, approximate — PRD-named: Korean
        # cutoff is ai-server's single source of truth per questionnaire.py docstring).
        "answers": [1, 1, 1],
        "ai_total": 12,
        "ai_severity": "severe",
        "ai_critical": True,
    },
    "PHQ4": {
        # sum=4 -> local "mild" (3..5 band).
        "answers": [1, 1, 1, 1],
        "ai_total": 12,
        "ai_severity": "severe",
        "ai_critical": True,
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize("qtype", ["PHQ9", "GAD7", "AUDITC", "PHQ4"])
async def test_score_with_ai_uses_canonical_ai_result_not_local_fallback(
    qtype: str, caplog: pytest.LogCaptureFixture
) -> None:
    case = CASES[qtype]
    answers = case["answers"]

    # sanity: confirm the mocked ai-server value genuinely diverges from what
    # local scoring of the SAME input would independently compute — otherwise
    # the assertion below would be tautological (could pass via either branch).
    local_total, local_severity = score_questionnaire(qtype, answers)
    local_critical = critical_item_positive(qtype, answers)
    assert (local_total, local_severity) != (case["ai_total"], case["ai_severity"]), (
        f"{qtype}: fixture is tautological — local and mocked-ai values coincide"
    )
    if qtype != "PHQ9":
        assert local_critical is False, (
            f"{qtype}: local fallback critical must be False for the "
            "non-tautology guarantee to hold"
        )
    assert case["ai_critical"] != local_critical or (local_total, local_severity) != (
        case["ai_total"],
        case["ai_severity"],
    )

    mock_server = _MockAIServer(
        SurveyScoreResponse(
            scale_name=qtype,
            total_score=case["ai_total"],
            max_score=case["ai_total"],
            severity=case["ai_severity"],
            critical_item_positive=case["ai_critical"],
        )
    )

    with caplog.at_level(logging.WARNING, logger="src.services.questionnaire"):
        total, severity, critical = await score_with_ai(
            qtype,
            answers,
            ai_client=mock_server,
            session_id=uuid.uuid4(),
            patient_sex="unknown",
        )

    # 1) the mocked ai-server was actually invoked exactly once.
    assert len(mock_server.calls) == 1

    # 2) the returned triple is the AI value, not the local one — this is the
    # PRD's "200 canonical scoring" bar, made non-tautological by construction
    # above (the two branches cannot agree on this input).
    assert (total, severity, critical) == (
        case["ai_total"],
        case["ai_severity"],
        case["ai_critical"],
    )

    # 3) "local fallback count 0" — the exact PRD-named log signal
    # (`questionnaire.py:165-166`, "survey scoring fell back to local
    # cutoffs") never fired.
    fallback_records = [
        r for r in caplog.records if "fell back to local cutoffs" in r.getMessage()
    ]
    assert fallback_records == [], (
        f"{qtype}: local-fallback log fired even though the mock ai-server "
        f"succeeded: {[r.getMessage() for r in fallback_records]}"
    )


@pytest.mark.asyncio
async def test_score_with_ai_still_falls_back_on_genuine_ai_failure() -> None:
    """Negative control for the smoke above: confirms the fallback log DOES
    fire (and IS the mechanism the positive cases prove absent) when the
    ai-server genuinely fails — guards against the positive assertions above
    passing merely because the log filter is broken/always empty."""

    class _FailingServer:
        async def survey_score(self, payload: Any) -> SurveyScoreResponse:
            raise AIClientError("mock ai-server outage")

    caplog_logger = logging.getLogger("src.services.questionnaire")
    caplog_logger.propagate = True

    handler = logging.Handler()
    records: list[logging.LogRecord] = []
    handler.emit = records.append  # type: ignore[assignment]
    caplog_logger.addHandler(handler)
    try:
        total, severity, critical = await score_with_ai(
            "PHQ9",
            [1] * 9,
            ai_client=_FailingServer(),
            session_id=uuid.uuid4(),
        )
    finally:
        caplog_logger.removeHandler(handler)

    fallback_records = [r for r in records if "fell back to local cutoffs" in r.getMessage()]
    assert len(fallback_records) == 1
    # PHQ9 [1]*9 -> local total=9 "mild", item9=1>0 -> critical True.
    assert (total, severity, critical) == (9, "mild", True)
