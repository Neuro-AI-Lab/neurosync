"""Regression test for BUG-067 (fixed this pass, EXP-031 live re-verification).

Pre-fix: `services/chat.py::_extract_slots`'s `conversation_history` builder
sent the raw, unmapped `role='ai'` to `/ai/slots/extract` — the SAME defect
BUG-064 fixed at the `respond` call site, but never applied here. From the
2nd extraction call onward (any conversation with a prior assistant turn),
Upstage 400'd (`"role" value 'ai' must be one of
['system','assistant','user','tool']`), and `_extract_slots` silently fell
back to the caller's existing (near-empty) slots. `Session.clinical_slots`
never accumulated past the first turn's fields no matter how long the
conversation ran — starving BUG-066's `_build_request`/`_build_slots` (the
structured evidence base for F5 handoff generation).

Fix (this pass): the role map is factored into one shared seam
(`_to_llm_role`/`_to_llm_history`, `services/chat.py`) used by BOTH
`_extract_slots` and `respond`, so a third sibling call site can't drift
again."""

from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace

import pytest


def test_to_llm_role_maps_ai_to_assistant_and_passes_through_others():
    from src.services.chat import _to_llm_role

    assert _to_llm_role("ai") == "assistant"
    assert _to_llm_role("user") == "user"
    assert _to_llm_role("system") == "system"


def test_to_llm_history_never_emits_raw_role_ai():
    from src.services.chat import _to_llm_history

    context = [
        SimpleNamespace(role="user", content="잠을 잘 못 자고..."),
        SimpleNamespace(role="ai", content="언제부터 그러셨나요?"),
        SimpleNamespace(role="user", content="식욕도 없고..."),
    ]
    history = _to_llm_history(context)
    assert all(entry["role"] != "ai" for entry in history), (
        f"raw role='ai' leaked into outbound conversation_history: {history!r}"
    )
    assert [entry["role"] for entry in history] == ["user", "assistant", "user"]


def test_extract_slots_source_uses_shared_seam_map():
    """`_extract_slots`'s conversation_history builder must route through
    the shared `_to_llm_history` helper, not build its own unmapped
    `{"role": m.role, ...}` list (BUG-067's exact defect)."""
    from src.services.chat import _extract_slots

    source = inspect.getsource(_extract_slots)
    assert "_to_llm_history(context)" in source, (
        "_extract_slots no longer routes its outbound conversation_history "
        "through the shared _to_llm_history seam-map — BUG-067 regression "
        "risk (unmapped role='ai' 400s at Upstage from the 2nd extraction "
        "call onward)"
    )
    assert '"role": m.role' not in source, (
        "_extract_slots appears to build conversation_history with a raw, "
        "unmapped role again — BUG-067 regression"
    )


@pytest.mark.asyncio
async def test_extract_slots_calls_ai_client_with_mapped_roles(monkeypatch):
    """End-to-end (ai_client-mocked) check: whatever `_extract_slots` sends
    over the wire to `ai_client.slots_extract` never contains a raw
    `role='ai'` entry, even though the stored context does."""
    from src.services.chat import _extract_slots

    captured: dict = {}

    class _FakeAIClient:
        async def slots_extract(self, payload):
            captured["conversation_history"] = payload.conversation_history
            return SimpleNamespace(extracted_slots={"chief_complaint": "수면 곤란"})

    context = [
        SimpleNamespace(role="user", content="잠을 잘 못 자고..."),
        SimpleNamespace(role="ai", content="언제부터 그러셨나요?"),
        SimpleNamespace(role="user", content="식욕도 없고..."),
    ]

    result = await _extract_slots(
        ai_client=_FakeAIClient(),
        session_id=uuid.uuid4(),
        context=context,
        current={},
    )

    sent_history = captured["conversation_history"]
    assert all(entry["role"] != "ai" for entry in sent_history), (
        f"_extract_slots sent an unmapped role='ai' entry to ai-server: {sent_history!r}"
    )
    assert result["chief_complaint"] == "수면 곤란"
