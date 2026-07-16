"""Tests for `tests/simulation/scenario_pack.py` — F4 quick-dev scenario
packs (`_archive/plans/f4_quick_dev_plan.md` §2.3/§2.4/§2.5, `PLAN-2026-W29-D`,
`ADR-036`). Pure/offline — no LLM/DB call anywhere in this file.
"""

from __future__ import annotations

import pytest

from tests.simulation.scenario_pack import (
    VP_001_IMPROVEMENT_PLATEAU,
    VP_003_RELAPSE_AFTER_PARTIAL_IMPROVEMENT,
    get_scenario_pack,
    render_scenario_guideline,
)

_ALL_PACKS = {
    "VP-001": VP_001_IMPROVEMENT_PLATEAU,
    "VP-003": VP_003_RELAPSE_AFTER_PARTIAL_IMPROVEMENT,
}


class TestPackShape:
    @pytest.mark.parametrize("persona_id", sorted(_ALL_PACKS))
    def test_pack_has_11_sessions(self, persona_id: str) -> None:
        assert len(_ALL_PACKS[persona_id]) == 11

    @pytest.mark.parametrize("persona_id", sorted(_ALL_PACKS))
    def test_session_indices_are_1_through_11_in_order(self, persona_id: str) -> None:
        pack = _ALL_PACKS[persona_id]
        assert [s.session_index for s in pack] == list(range(1, 12))

    @pytest.mark.parametrize("persona_id", sorted(_ALL_PACKS))
    def test_day_offsets_are_strictly_increasing_within_6_months(self, persona_id: str) -> None:
        pack = _ALL_PACKS[persona_id]
        offsets = [s.day_offset for s in pack]
        assert offsets == sorted(offsets)
        assert len(set(offsets)) == len(offsets)
        assert offsets[0] == 0
        assert offsets[-1] <= 183  # ~6 months ceiling

    @pytest.mark.parametrize("persona_id", sorted(_ALL_PACKS))
    def test_scenario_pack_id_unique_and_well_formed(self, persona_id: str) -> None:
        pack = _ALL_PACKS[persona_id]
        ids = [s.scenario_pack_id for s in pack]
        assert len(set(ids)) == len(ids)
        for s in pack:
            assert s.scenario_pack_id == f"{persona_id}_{s.arc_mode}_s{s.session_index:02d}"

    def test_get_scenario_pack_returns_correct_pack(self) -> None:
        assert get_scenario_pack("VP-001") is VP_001_IMPROVEMENT_PLATEAU
        assert get_scenario_pack("VP-003") is VP_003_RELAPSE_AFTER_PARTIAL_IMPROVEMENT

    def test_get_scenario_pack_unknown_persona_raises(self) -> None:
        with pytest.raises(KeyError):
            get_scenario_pack("VP-999")

    @pytest.mark.parametrize("persona_id", sorted(_ALL_PACKS))
    def test_every_session_has_non_empty_content(self, persona_id: str) -> None:
        for s in _ALL_PACKS[persona_id]:
            assert s.state_descriptor_ko.strip()
            assert s.reveal_guidance_ko.strip()
            # inter_session_events_ko may legitimately be empty only for S1 (intake).
            if s.session_index > 1:
                assert s.inter_session_events_ko


class TestSymptomTargetsNeverRenderedIntoInjectedText:
    """Numeric symptom targets are DESIGN-INTENT metadata only — the
    template has no placeholder for `symptom_targets`. Checked at the
    SOURCE level (not fuzzy output substring matching, which would
    false-positive on legitimate Korean range notation like "5~6시간" that
    happens to share characters with a target string like "~6") — the true
    guarantee is that `render_scenario_guideline` never reads the field at
    all.
    """

    def test_render_function_source_never_references_symptom_targets(self) -> None:
        import inspect

        from tests.simulation import scenario_pack as scenario_pack_module

        source = inspect.getsource(scenario_pack_module.render_scenario_guideline)
        assert "symptom_targets" not in source

    @pytest.mark.parametrize("persona_id", sorted(_ALL_PACKS))
    def test_scale_name_label_never_surfaces_in_rendered_text(self, persona_id: str) -> None:
        pack = _ALL_PACKS[persona_id]
        for i, session in enumerate(pack, start=1):
            rendered = render_scenario_guideline(session, len(pack), f"2026-01-{i:02d}")
            assert "symptom_targets" not in rendered
            assert "PHQ-9" not in rendered
            assert "CTRS" not in rendered


class TestIsolationInvariant:
    """Design doc §2.5's explicit guard: session i's rendered text NEVER
    contains any OTHER session's own state/events/reveal content — the
    harness only ever injects ONE session's pack text per F1 run."""

    @pytest.mark.parametrize("persona_id", sorted(_ALL_PACKS))
    def test_no_session_text_leaks_into_another_sessions_rendering(self, persona_id: str) -> None:
        pack = _ALL_PACKS[persona_id]
        n = len(pack)
        rendered_by_index = {
            s.session_index: render_scenario_guideline(s, n, f"2026-01-{s.session_index:02d}")
            for s in pack
        }
        for session in pack:
            own_text = rendered_by_index[session.session_index]
            for other in pack:
                if other.session_index == session.session_index:
                    continue
                # A distinctive-enough fragment of the OTHER session's own
                # state descriptor must not appear in THIS session's text.
                # Use a long-enough substring (>=20 chars) to avoid trivial
                # shared-vocabulary false positives (e.g. common particles).
                other_fragment = other.state_descriptor_ko[:24]
                assert other_fragment not in own_text, (
                    f"{persona_id} session {session.session_index}'s guideline leaked "
                    f"session {other.session_index}'s state descriptor"
                )
                for event in other.inter_session_events_ko:
                    event_fragment = event[:24]
                    if not event_fragment.strip():
                        continue
                    assert event_fragment not in own_text, (
                        f"{persona_id} session {session.session_index}'s guideline leaked "
                        f"session {other.session_index}'s inter-session event"
                    )

    def test_render_contains_the_never_know_the_future_guard(self) -> None:
        pack = VP_001_IMPROVEMENT_PLATEAU
        rendered = render_scenario_guideline(pack[0], len(pack), "2026-01-01")
        assert "앞으로 무슨 일이 있을지 알지 못합니다" in rendered

    def test_render_only_includes_this_sessions_own_fields(self) -> None:
        pack = VP_003_RELAPSE_AFTER_PARTIAL_IMPROVEMENT
        session5 = pack[4]
        rendered = render_scenario_guideline(session5, len(pack), "2026-02-05")
        assert session5.state_descriptor_ko in rendered
        assert session5.reveal_guidance_ko in rendered
        for event in session5.inter_session_events_ko:
            assert event in rendered


class TestADR036ContentDispositions:
    """ADR-036 items 5/6 — the exact scripted content dispositions this
    mission licensed."""

    def test_vp001_s1_target_is_mild_baseline_not_moderate_over_triage(self) -> None:
        s1 = VP_001_IMPROVEMENT_PLATEAU[0]
        assert s1.symptom_targets["PHQ-9"] == "~7"

    def test_vp003_gains_system_prompted_brother_referral_event_post_relapse(self) -> None:
        """ADR-036 item 5 / CVR-020 binding condition 1: >=1 event after the
        S6/S7 relapse window depicting a system-crisis-flow-consequence
        (brother-facilitated psychiatric intake contact)."""
        post_relapse_sessions = VP_003_RELAPSE_AFTER_PARTIAL_IMPROVEMENT[7:]  # S8..S11
        found = any(
            "정신과" in event and ("형" in event or "브라더" in event)
            for s in post_relapse_sessions
            for event in s.inter_session_events_ko
        )
        assert found, (
            "no post-relapse event depicts a brother-facilitated psychiatric intake contact"
        )
