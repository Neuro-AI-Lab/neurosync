"""Smoke tests for the 5 new 10-session scenario packs (VP-002/004/010/011/012)
wired into `scenario_pack.py`'s `_SCENARIO_PACKS` registry — F1-F5
total-validation cohort completion. Pure/offline — no LLM/DB call anywhere in
this file. Mirrors the shape checks in `test_scenario_pack.py` (which covers
the pre-existing 11-session VP-001/003 packs) but scoped to the 10-session
packs and the full 7-VP registry enumeration.
"""

from __future__ import annotations

import re

import pytest

from tests.simulation.scenario_pack import (
    _SCENARIO_PACKS,
    VP_002_TREATMENT_RESPONSE_SETBACK,
    VP_004_FLUCTUATING_PANIC_RECURRENCE,
    VP_010_STABLE_MINIMIZING_SLOW_DISCLOSURE,
    VP_011_SOMATIC_PERSISTENT_LATE_MOOD_DISCLOSURE,
    VP_012_AUD_ESCALATION_CONTEMPLATION,
    get_scenario_pack,
    render_scenario_guideline,
)

# CVR-027: instrument names/scores are measurement contamination when they leak
# into the rendered simulator guideline (the patient LLM should never be
# steered by a scale name or a score, only qualitative state language).
_SCALE_NAME_LEAK_PATTERN = re.compile(r"PHQ-9|GAD-7|AUDIT-C|점수")

_NEW_PACKS = {
    "VP-002": VP_002_TREATMENT_RESPONSE_SETBACK,
    "VP-004": VP_004_FLUCTUATING_PANIC_RECURRENCE,
    "VP-010": VP_010_STABLE_MINIMIZING_SLOW_DISCLOSURE,
    "VP-011": VP_011_SOMATIC_PERSISTENT_LATE_MOOD_DISCLOSURE,
    "VP-012": VP_012_AUD_ESCALATION_CONTEMPLATION,
}


class TestNewPackShape:
    @pytest.mark.parametrize("persona_id", sorted(_NEW_PACKS))
    def test_pack_has_10_sessions(self, persona_id: str) -> None:
        assert len(_NEW_PACKS[persona_id]) == 10

    @pytest.mark.parametrize("persona_id", sorted(_NEW_PACKS))
    def test_session_indices_are_1_through_10_in_order(self, persona_id: str) -> None:
        pack = _NEW_PACKS[persona_id]
        assert [s.session_index for s in pack] == list(range(1, 11))

    @pytest.mark.parametrize("persona_id", sorted(_NEW_PACKS))
    def test_day_offsets_are_strictly_increasing_within_6_months(self, persona_id: str) -> None:
        pack = _NEW_PACKS[persona_id]
        offsets = [s.day_offset for s in pack]
        assert offsets == sorted(offsets)
        assert len(set(offsets)) == len(offsets)
        assert offsets[0] == 0
        assert offsets[-1] <= 183  # ~6 months ceiling

    @pytest.mark.parametrize("persona_id", sorted(_NEW_PACKS))
    def test_scenario_pack_id_unique_and_well_formed(self, persona_id: str) -> None:
        pack = _NEW_PACKS[persona_id]
        ids = [s.scenario_pack_id for s in pack]
        assert len(set(ids)) == len(ids)
        for s in pack:
            assert s.scenario_pack_id == f"{persona_id}_{s.arc_mode}_s{s.session_index:02d}"

    @pytest.mark.parametrize("persona_id", sorted(_NEW_PACKS))
    def test_every_session_has_non_empty_content(self, persona_id: str) -> None:
        for s in _NEW_PACKS[persona_id]:
            assert s.state_descriptor_ko.strip()
            assert s.reveal_guidance_ko.strip()
            if s.session_index > 1:
                assert s.inter_session_events_ko

    @pytest.mark.parametrize("persona_id", sorted(_NEW_PACKS))
    def test_get_scenario_pack_returns_correct_pack(self, persona_id: str) -> None:
        assert get_scenario_pack(persona_id) is _NEW_PACKS[persona_id]

    @pytest.mark.parametrize("persona_id", sorted(_NEW_PACKS))
    def test_symptom_targets_field_itself_never_renders(self, persona_id: str) -> None:
        """`symptom_targets` is design-intent metadata only — the template has no
        placeholder for it. This checks only the field key, not scale-name labels
        that may separately appear inside free-text state descriptors (a content
        question for CVR/critic review, not a rendering-isolation bug)."""
        pack = _NEW_PACKS[persona_id]
        for i, session in enumerate(pack, start=1):
            rendered = render_scenario_guideline(session, len(pack), f"2026-01-{i:02d}")
            assert "symptom_targets" not in rendered


class TestNoScaleNameLeakIntoRenderedGuideline:
    """CVR-027 (major): free-text `state_descriptor_ko`/`inter_session_events_ko`/
    `reveal_guidance_ko` must never embed a literal instrument name or score —
    that IS rendered into the injected simulator guideline (unlike
    `symptom_targets`, which never renders; see
    `test_symptom_targets_field_itself_never_renders` above) and would leak
    ground-truth severity into the patient-simulator prompt. Covers the full
    7-VP registry, not just the 5 new packs, since the invariant is general."""

    @pytest.mark.parametrize("persona_id", sorted(_SCENARIO_PACKS))
    def test_rendered_guideline_has_no_scale_name_or_score_leak(self, persona_id: str) -> None:
        pack = _SCENARIO_PACKS[persona_id]
        for i, session in enumerate(pack, start=1):
            rendered = render_scenario_guideline(session, len(pack), f"2026-01-{i:02d}")
            match = _SCALE_NAME_LEAK_PATTERN.search(rendered)
            assert match is None, (
                f"{persona_id} session {i}: scale-name/score leak {match!r} in "
                f"rendered guideline"
            )


class TestRegistryEnumeratesAllSevenVPs:
    """Dry-list only — confirms the multi-session harness can enumerate all
    7 VPs (VP-001/003 pre-existing + 5 new) via `_SCENARIO_PACKS`. No live
    session/LLM run happens here."""

    def test_registry_contains_exactly_the_expected_7_vps(self) -> None:
        assert set(_SCENARIO_PACKS) == {
            "VP-001", "VP-002", "VP-003", "VP-004",
            "VP-010", "VP-011", "VP-012",
        }

    @pytest.mark.parametrize(
        "persona_id", ["VP-001", "VP-002", "VP-003", "VP-004", "VP-010", "VP-011", "VP-012"]
    )
    def test_each_vp_resolves_via_get_scenario_pack(self, persona_id: str) -> None:
        pack = get_scenario_pack(persona_id)
        assert len(pack) in (10, 11)
        assert pack[0].session_index == 1
