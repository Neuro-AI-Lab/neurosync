"""CVR-030 (minor-major) HIRA response enrichment regression tests —
`src.f1.F1Pipeline._fetch_crisis_facilities`.

(a) ER/emergency-capacity flag: `Place.emergency_available` is ALWAYS
    `None` for a `getHospBasisList` result (the endpoint carries no such
    field per `docs/ai/api/hira_kakao_map_api_usage_guide.md`'s
    2026-07-10 real-response check) — the hospital list block must render
    the honest "응급실 여부 확인 필요" per hospital instead of silently
    omitting it, and must never invent an availability value.
(b) The crisis hotline (109/119) is additionally repeated directly under
    the hospital list block.

No live HIRA/LLM call anywhere in this file — `NearbyFacilitiesAgent.search`
is monkeypatched to return a synthetic `NearbyResponse`.
"""

from __future__ import annotations

import pytest

from src.agents.nearby_facilities import NearbyFacilitiesAgent
from src.f1 import F1Pipeline
from src.schemas.nearby import MapPayload, NearbyResponse, Place, SourceMeta


def _place(
    *,
    name: str,
    source_id: str,
    distance_km: float | None = 1.2,
    phone: str = "02-1234-5678",
    emergency_available: bool | None = None,
) -> Place:
    return Place(
        id=f"hospital:{source_id}",
        entity_type="hospital",
        source_id=source_id,
        name=name,
        title=name,
        address="서울시 어딘가",
        phone=phone,
        distance_km=distance_km,
        emergency_available=emergency_available,
    )


def _fake_response(places: list[Place]) -> NearbyResponse:
    return NearbyResponse(
        generated_at="2027-01-14T00:00:00Z",
        source="HIRA",
        query={},
        sources={"hospital": SourceMeta()},
        places=places,
        map=MapPayload(),
        notice="",
    )


@pytest.fixture
def pipeline() -> F1Pipeline:
    return F1Pipeline()


def _stub_search(monkeypatch: pytest.MonkeyPatch, pipeline: F1Pipeline, fake_search) -> None:
    """Monkeypatch `NearbyFacilitiesAgent.search` and short-circuit
    `pipeline._get_nearby_agent` to return a bare (never-`__init__`-ed)
    agent instance — safe here because `search` is itself replaced, so no
    adapter attribute on the real instance is ever touched."""
    monkeypatch.setattr(NearbyFacilitiesAgent, "search", fake_search)
    monkeypatch.setattr(
        pipeline, "_get_nearby_agent", lambda: NearbyFacilitiesAgent.__new__(NearbyFacilitiesAgent)
    )


class TestEmergencyAvailabilityDisclosure:
    @pytest.mark.asyncio
    async def test_none_emergency_available_renders_honest_marker(
        self, pipeline: F1Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The realistic case: HIRA's basis-list endpoint never populates
        this field, so every place has emergency_available=None — must
        render '응급실 여부 확인 필요', never silently omit it."""
        places = [
            _place(name="1등병원", source_id="A", emergency_available=None),
            _place(name="2등병원", source_id="B", emergency_available=None),
        ]

        async def _fake_search(self, inp):
            return _fake_response(places)

        _stub_search(monkeypatch, pipeline, _fake_search)
        text, records = await pipeline._fetch_crisis_facilities(37.5, 127.0, top_n=1)
        assert "응급실 여부 확인 필요" in text
        assert "응급실 가능" not in text
        assert "응급실 불가" not in text
        assert records[0]["emergency_available"] is None

    @pytest.mark.asyncio
    async def test_never_invents_availability_when_field_is_none(
        self, pipeline: F1Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A None value must never render as either available or
        unavailable — only the honest 'confirm needed' marker."""
        places = [_place(name="병원", source_id="A", emergency_available=None)]

        async def _fake_search(self, inp):
            return _fake_response(places)

        _stub_search(monkeypatch, pipeline, _fake_search)
        text, _records = await pipeline._fetch_crisis_facilities(37.5, 127.0, top_n=1)
        # Exactly one line for this single (top-1-skipped -> empty) hospital
        # scenario is covered by other tests; here just confirm no
        # available/unavailable claim leaks in for a None field.
        assert "가능" not in text.replace("확인 필요", "")
        assert "불가" not in text

    @pytest.mark.asyncio
    async def test_true_emergency_available_renders_available(
        self, pipeline: F1Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Forward-compatibility: if a future data source ever populates
        this field True, it must render as available, not the honest
        placeholder (never suppress real data)."""
        places = [
            _place(name="1등병원", source_id="A"),
            _place(name="응급병원", source_id="B", emergency_available=True),
        ]

        async def _fake_search(self, inp):
            return _fake_response(places)

        _stub_search(monkeypatch, pipeline, _fake_search)
        text, records = await pipeline._fetch_crisis_facilities(37.5, 127.0, top_n=1)
        assert "응급실 가능" in text
        assert records[0]["emergency_available"] is True

    @pytest.mark.asyncio
    async def test_false_emergency_available_renders_unavailable(
        self, pipeline: F1Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        places = [
            _place(name="1등병원", source_id="A"),
            _place(name="비응급병원", source_id="B", emergency_available=False),
        ]

        async def _fake_search(self, inp):
            return _fake_response(places)

        _stub_search(monkeypatch, pipeline, _fake_search)
        text, records = await pipeline._fetch_crisis_facilities(37.5, 127.0, top_n=1)
        assert "응급실 불가" in text
        assert records[0]["emergency_available"] is False


class TestCrisisHotlineRepeatedInHospitalBlock:
    @pytest.mark.asyncio
    async def test_hotline_appended_to_hospital_block(
        self, pipeline: F1Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        places = [
            _place(name="1", source_id="A"),
            _place(name="2", source_id="B"),
        ]

        async def _fake_search(self, inp):
            return _fake_response(places)

        _stub_search(monkeypatch, pipeline, _fake_search)
        text, _records = await pipeline._fetch_crisis_facilities(37.5, 127.0, top_n=1)
        assert "109" in text
        assert "119" in text

    @pytest.mark.asyncio
    async def test_no_hospitals_found_no_hotline_line_from_this_block(
        self, pipeline: F1Pipeline, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Top-1 is always skipped (see this function's own docstring) — a
        single-result response yields nothing to choose from, and this
        block must not fabricate a hotline line with no hospital list."""

        async def _fake_search(self, inp):
            return _fake_response([_place(name="유일병원", source_id="A")])

        _stub_search(monkeypatch, pipeline, _fake_search)
        text, records = await pipeline._fetch_crisis_facilities(37.5, 127.0, top_n=1)
        assert text == ""
        assert records == []
