"""F1 세션에 PHR이 자동 로드·주입되는지 통합 테스트.

CI가 실행. 실 LLM 호출 없이 canned patient 응답만 사용.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.agents.patient_history import PatientHistoryAgent
from src.f1 import PERSONA_PHR_FILES, F1Pipeline, _format_phr_for_context
from src.schemas.phr import PhrLoadInput

REPO_ROOT = Path(__file__).resolve().parents[3]


# ── _format_phr_for_context unit test ────────────────────────────────


def test_format_phr_for_context_negative():
    """정신과 이력 없는 요약 → 컨텍스트에 '이력 없음' 명시."""
    med = REPO_ROOT / "docs" / "ai" / "samples" / "phr" / "VP-001_medications.json"
    vis = REPO_ROOT / "docs" / "ai" / "samples" / "phr" / "VP-001_visits.json"
    if not med.is_file():
        pytest.skip("VP-001 PHR sample missing")

    async def _run():
        agent = PatientHistoryAgent()
        summary = await agent.run(
            PhrLoadInput(session_id="unit", bundle_paths=[str(med), str(vis)])
        )
        return summary, _format_phr_for_context(summary, agent)

    summary, ctx = asyncio.run(_run())
    assert not summary.has_psychiatric_history
    assert ctx  # 방문/조제 있으므로 컨텍스트는 나옴
    assert "정신과 계열 약물 이력 없음" in ctx
    assert "AI가 새로 부여한 진단이 아닙니다" in ctx


def test_format_phr_for_context_positive():
    """정신과 이력 있으면 최근 3건 약물 상세 노출."""
    med = REPO_ROOT / "docs" / "ai" / "samples" / "phr" / "VP-004_medications.json"
    vis = REPO_ROOT / "docs" / "ai" / "samples" / "phr" / "VP-004_visits.json"
    if not med.is_file():
        pytest.skip("VP-004 PHR sample missing")

    async def _run():
        agent = PatientHistoryAgent()
        summary = await agent.run(
            PhrLoadInput(session_id="unit", bundle_paths=[str(med), str(vis)])
        )
        return summary, _format_phr_for_context(summary, agent)

    summary, ctx = asyncio.run(_run())
    assert summary.has_psychiatric_history
    assert "정신과 계열 약물 최근 조제" in ctx
    assert "SSRI" in ctx or "BENZO" in ctx or "ZDRUG" in ctx


# ── PERSONA_PHR_FILES sanity ─────────────────────────────────────────


def test_persona_phr_files_paths_exist():
    """각 페르소나별 기본 PHR 파일 경로가 실제 존재."""
    for vp_id, paths in PERSONA_PHR_FILES.items():
        for rel in paths:
            abs_path = REPO_ROOT / rel
            assert abs_path.is_file(), f"{vp_id} PHR sample missing: {abs_path}"


# ── F1 통합: PHR이 세션에 주입되는지 ─────────────────────────────────


@pytest.mark.parametrize(
    "vp_id,expected_has_history,expected_psycho_count",
    [
        ("VP-001", False, 0),
        ("VP-002", True, 3),   # SSRI × 3
        ("VP-003", True, 1),   # BENZO 응급
        ("VP-004", True, 8),   # SSRI + BENZO + ZDRUG 총 8건
    ],
)
def test_f1_run_session_loads_phr(vp_id, expected_has_history, expected_psycho_count):
    """F1Pipeline.run_session에 phr_paths 넘기면 result.phr_summary 채워짐."""
    files = PERSONA_PHR_FILES.get(vp_id)
    if not files:
        pytest.skip(f"{vp_id} PHR mapping missing")
    resolved = [REPO_ROOT / p for p in files]
    if not all(p.is_file() for p in resolved):
        pytest.skip(f"{vp_id} PHR files missing")

    responses = iter(["최근에 잠이 잘 안 와요.", "네, 그런 것 같아요."])

    async def canned(_):
        return next(responses)

    async def _run():
        pipeline = F1Pipeline()
        return await pipeline.run_session(
            patient_input_fn=canned,
            session_id=f"pytest-phr-{vp_id}",
            persona_id=vp_id,
            persona_name=f"pytest-{vp_id}",
            max_turns=2,
            phr_paths=resolved,
        )

    result = asyncio.run(_run())

    assert result.phr_summary, f"{vp_id}: phr_summary is empty"
    assert result.phr_summary["has_psychiatric_history"] is expected_has_history
    psycho = result.phr_summary["psychotropic_medications"] or []
    assert len(psycho) == expected_psycho_count, (
        f"{vp_id}: psychotropic count={len(psycho)}, expected {expected_psycho_count}"
    )
    # 계약: patient의 name_hash 저장 · 원문 이름은 저장되지 않음
    assert result.phr_summary["patient"]["name_hash"]
    assert result.phr_summary["patient"]["mhid"]


def test_dialogue_input_carries_phr_context():
    """DialogueInput 스키마가 patient_history_context 필드를 가진다 (계약 안전망)."""
    from src.schemas.dialogue import DialogueInput

    di = DialogueInput(
        session_id="unit",
        user_message="테스트",
        patient_history_context="테스트 컨텍스트",
    )
    assert di.patient_history_context == "테스트 컨텍스트"

    di_default = DialogueInput(session_id="unit", user_message="테스트")
    assert di_default.patient_history_context == ""


def test_dialogue_agent_prepends_history_to_system_prompt():
    """DialogueAgent가 patient_history_context를 base system prompt 앞에 결합.

    실제 LLM 호출 없이 messages 구성만 검증하기 위해 adapter를 mock 한다.
    """
    from unittest.mock import AsyncMock, MagicMock

    from src.adapters.base import ChatMessage, LLMAdapter
    from src.agents.dialogue import DialogueAgent
    from src.schemas.dialogue import DialogueInput

    # Fake router/loader
    prompt_loader = MagicMock()
    prompt_loader.load_system_prompt.return_value = "BASE_DIALOGUE_PROMPT"

    fake_adapter = MagicMock(spec=LLMAdapter)
    fake_adapter.chat_timed = AsyncMock()
    fake_response = MagicMock()
    fake_response.content = '{"assistant_response": "네", "reason_summary": "ok"}'
    fake_response.model = "test"
    fake_response.finish_reason = "stop"
    fake_response.latency_ms = 1.0
    fake_response.usage = None
    fake_adapter.chat_timed.return_value = fake_response

    fake_router = MagicMock()
    fake_selection = MagicMock()
    fake_selection.adapter_name = "test-adapter"
    fake_selection.model_id = "test"
    fake_selection.supports_json_schema = False
    fake_selection.supports_json_object = True
    fake_router.select_model.return_value = fake_selection
    fake_router.get_adapter.return_value = fake_adapter

    agent = DialogueAgent(model_router=fake_router, prompt_loader=prompt_loader)

    async def _call():
        return await agent.run(
            DialogueInput(
                session_id="unit",
                user_message="안녕하세요",
                patient_history_context="[PHR] 정신과 SSRI 3개월 이력 있음.",
            )
        )

    asyncio.run(_call())

    # adapter.chat_timed 호출 시 messages 첫 번째 = system prompt
    call_args = fake_adapter.chat_timed.call_args
    messages: list[ChatMessage] = call_args.args[0]
    assert messages[0].role == "system"
    system_content = messages[0].content
    # PHR 컨텍스트가 base prompt보다 먼저 배치돼야 함
    phr_idx = system_content.find("정신과 SSRI 3개월 이력 있음")
    base_idx = system_content.find("BASE_DIALOGUE_PROMPT")
    assert phr_idx >= 0, "patient_history_context가 system prompt에 삽입되지 않음"
    assert base_idx >= 0, "base prompt 누락"
    assert phr_idx < base_idx, "patient_history_context는 base prompt 앞이어야 함"


def test_f1_run_session_without_phr():
    """phr_paths 안 주면 phr_summary는 빈 dict — 기존 flow 회귀 없음."""
    responses = iter(["잠이 잘 안 와요.", "네요."])

    async def canned(_):
        return next(responses)

    async def _run():
        pipeline = F1Pipeline()
        return await pipeline.run_session(
            patient_input_fn=canned,
            session_id="pytest-phr-none",
            persona_id="VP-001",
            persona_name="pytest",
            max_turns=2,
        )

    result = asyncio.run(_run())
    assert result.phr_summary == {}
