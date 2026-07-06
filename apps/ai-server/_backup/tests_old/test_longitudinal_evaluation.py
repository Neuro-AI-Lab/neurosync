"""Longitudinal State Analysis Evaluation — Real VP Clinical Data.

Runs TemporalSummaryAgent with actual VP-002 and VP-004 persona data
from docs/ai/personas/ and validates every domain direction against
the persona specifications.

VP-002 (이준호): PHQ-9 12→7, GAD-7 6→5, CTRS 4→5 → overall improved
VP-004 (최하은): PHQ-9 14→21, GAD-7 10→16, CTRS 4→3 → overall worsened

Also tests:
- VP-001/VP-003 (first visits) → all unknown
- Contradiction detection (VP-002 improved then worsened)
- 3-visit longitudinal sequence (VP-004 trajectory)
- Sentiment polarity tracking across visits
- Handoff report accuracy: do temporal results match persona expectations?
"""

from __future__ import annotations

import pytest

from src.agents.temporal_summary import TemporalSummaryAgent, SCALE_THRESHOLD
from src.schemas.temporal import DomainDirection, TemporalSummaryInput


# ═══════════════════════════════════════════════════════════════════════
# VP-002: 이준호 (35M, mild revisit, IMPROVING)
# Source: docs/ai/personas/VP-002_revisit_mild.md
# Prior (초진 6주 전): PHQ-9=12, GAD-7=6, CTRS=4
# Current (재진):       PHQ-9=7,  GAD-7=5, CTRS=5
# ═══════════════════════════════════════════════════════════════════════


class TestVP002LongitudinalImproving:
    """VP-002 이준호: 6-week follow-up after Escitalopram 10mg initiation."""

    @pytest.fixture
    def agent(self):
        return TemporalSummaryAgent()

    @pytest.fixture
    def vp002_input(self):
        return TemporalSummaryInput(
            session_id="VP-002-eval",
            patient_id="이준호",
            is_first_visit=False,
            current_scales={"PHQ-9": 7, "GAD-7": 5},
            prior_scales={"PHQ-9": 12, "GAD-7": 6},
            current_ctrs=5,
            prior_ctrs=4,
            current_sentiment_polarity=0.2,   # improved mood
            prior_sentiment_polarity=-0.4,     # prior depressed mood
            current_date="2026-06-25",
            prior_date="2026-05-06",
        )

    @pytest.mark.asyncio
    async def test_overall_direction_improved(self, agent, vp002_input):
        """VP-002 overall direction must be 'improved'."""
        result = await agent.run(vp002_input)
        assert result.overall_direction == DomainDirection.improved

    @pytest.mark.asyncio
    async def test_phq9_improved(self, agent, vp002_input):
        """PHQ-9: 12→7 (delta=-5, meets threshold) → improved."""
        result = await agent.run(vp002_input)
        phq = next(t for t in result.domain_trends if t.domain == "PHQ-9")
        assert phq.direction == DomainDirection.improved
        assert phq.previous_value == 12
        assert phq.current_value == 7
        assert phq.delta == -5
        assert abs(phq.delta) >= SCALE_THRESHOLD

    @pytest.mark.asyncio
    async def test_gad7_unchanged(self, agent, vp002_input):
        """GAD-7: 6→5 (delta=-1, below threshold) → unchanged.
        Per persona: 'Improved (-1)' but clinically sub-threshold."""
        result = await agent.run(vp002_input)
        gad = next(t for t in result.domain_trends if t.domain == "GAD-7")
        assert gad.direction == DomainDirection.unchanged
        assert gad.delta == -1
        # Note: Persona says "improved" but our threshold=5 correctly classifies as unchanged
        # GAD-7 delta of 1 is NOT clinically significant

    @pytest.mark.asyncio
    async def test_ctrs_improved(self, agent, vp002_input):
        """CTRS: 4→5 (number increased = risk decreased) → improved."""
        result = await agent.run(vp002_input)
        ctrs = next(t for t in result.domain_trends if t.domain == "CTRS")
        assert ctrs.direction == DomainDirection.improved
        assert ctrs.previous_value == 4
        assert ctrs.current_value == 5

    @pytest.mark.asyncio
    async def test_sentiment_improved(self, agent, vp002_input):
        """Sentiment: -0.4→0.2 (delta=+0.6, >0.3) → improved."""
        result = await agent.run(vp002_input)
        assert result.sentiment_trend.direction == DomainDirection.improved
        assert result.sentiment_trend.previous_polarity == -0.4
        assert result.sentiment_trend.current_polarity == 0.2

    @pytest.mark.asyncio
    async def test_plot_data_two_visits(self, agent, vp002_input):
        """Plot data should include 2 time points with correct dates."""
        result = await agent.run(vp002_input)
        assert len(result.plot_data) == 2
        assert result.plot_data[0].date == "2026-05-06"
        assert result.plot_data[0].phq9 == 12
        assert result.plot_data[1].date == "2026-06-25"
        assert result.plot_data[1].phq9 == 7

    @pytest.mark.asyncio
    async def test_not_first_visit(self, agent, vp002_input):
        result = await agent.run(vp002_input)
        assert result.is_first_visit is False

    @pytest.mark.asyncio
    async def test_evidence_strings(self, agent, vp002_input):
        """Each trend should have human-readable evidence."""
        result = await agent.run(vp002_input)
        for trend in result.domain_trends:
            assert len(trend.evidence) >= 1
            assert any("→" in e for e in trend.evidence)


# ═══════════════════════════════════════════════════════════════════════
# VP-004: 최하은 (31F, severe revisit, WORSENING)
# Source: docs/ai/personas/VP-004_revisit_severe.md
# Prior (초진 2개월 전): PHQ-9=14, GAD-7=10, CTRS=4
# Current (재진):         PHQ-9=21, GAD-7=16, CTRS=3
# ═══════════════════════════════════════════════════════════════════════


class TestVP004LongitudinalWorsening:
    """VP-004 최하은: 2-month follow-up, medication changes, new symptoms."""

    @pytest.fixture
    def agent(self):
        return TemporalSummaryAgent()

    @pytest.fixture
    def vp004_input(self):
        return TemporalSummaryInput(
            session_id="VP-004-eval",
            patient_id="최하은",
            is_first_visit=False,
            current_scales={"PHQ-9": 21, "GAD-7": 16},
            prior_scales={"PHQ-9": 14, "GAD-7": 10},
            current_ctrs=3,
            prior_ctrs=4,
            current_sentiment_polarity=-0.8,   # severe depression
            prior_sentiment_polarity=-0.3,      # moderate depression prior
            current_date="2026-06-25",
            prior_date="2026-04-14",
        )

    @pytest.mark.asyncio
    async def test_overall_direction_worsened(self, agent, vp004_input):
        """VP-004 overall direction must be 'worsened'."""
        result = await agent.run(vp004_input)
        assert result.overall_direction == DomainDirection.worsened

    @pytest.mark.asyncio
    async def test_phq9_worsened(self, agent, vp004_input):
        """PHQ-9: 14→21 (delta=+7, exceeds threshold) → worsened."""
        result = await agent.run(vp004_input)
        phq = next(t for t in result.domain_trends if t.domain == "PHQ-9")
        assert phq.direction == DomainDirection.worsened
        assert phq.previous_value == 14
        assert phq.current_value == 21
        assert phq.delta == 7
        assert phq.delta >= SCALE_THRESHOLD

    @pytest.mark.asyncio
    async def test_gad7_worsened(self, agent, vp004_input):
        """GAD-7: 10→16 (delta=+6, exceeds threshold) → worsened."""
        result = await agent.run(vp004_input)
        gad = next(t for t in result.domain_trends if t.domain == "GAD-7")
        assert gad.direction == DomainDirection.worsened
        assert gad.delta == 6

    @pytest.mark.asyncio
    async def test_ctrs_worsened(self, agent, vp004_input):
        """CTRS: 4→3 (lower number = higher risk) → worsened."""
        result = await agent.run(vp004_input)
        ctrs = next(t for t in result.domain_trends if t.domain == "CTRS")
        assert ctrs.direction == DomainDirection.worsened
        assert ctrs.previous_value == 4
        assert ctrs.current_value == 3

    @pytest.mark.asyncio
    async def test_sentiment_worsened(self, agent, vp004_input):
        """Sentiment: -0.3→-0.8 (delta=-0.5, <-0.3) → worsened."""
        result = await agent.run(vp004_input)
        assert result.sentiment_trend.direction == DomainDirection.worsened

    @pytest.mark.asyncio
    async def test_all_domains_worsened(self, agent, vp004_input):
        """ALL three domains (PHQ-9, GAD-7, CTRS) must be worsened."""
        result = await agent.run(vp004_input)
        for trend in result.domain_trends:
            assert trend.direction == DomainDirection.worsened, (
                f"{trend.domain} expected worsened, got {trend.direction}"
            )

    @pytest.mark.asyncio
    async def test_plot_data_spans_2_months(self, agent, vp004_input):
        result = await agent.run(vp004_input)
        assert len(result.plot_data) == 2
        assert result.plot_data[0].date == "2026-04-14"
        assert result.plot_data[1].date == "2026-06-25"
        assert result.plot_data[0].phq9 == 14
        assert result.plot_data[1].phq9 == 21


# ═══════════════════════════════════════════════════════════════════════
# VP-001/VP-003: First visits → all unknown
# ═══════════════════════════════════════════════════════════════════════


class TestFirstVisitAllUnknown:
    """First-visit patients must return all 'unknown' — no comparison baseline."""

    @pytest.mark.asyncio
    async def test_vp001_first_visit(self):
        agent = TemporalSummaryAgent()
        inp = TemporalSummaryInput(
            session_id="VP-001-eval", patient_id="김서연",
            is_first_visit=True,
        )
        result = await agent.run(inp)
        assert result.overall_direction == DomainDirection.unknown
        assert result.is_first_visit is True
        assert len(result.domain_trends) == 0

    @pytest.mark.asyncio
    async def test_vp003_first_visit(self):
        agent = TemporalSummaryAgent()
        inp = TemporalSummaryInput(
            session_id="VP-003-eval", patient_id="박민수",
            is_first_visit=True,
        )
        result = await agent.run(inp)
        assert result.overall_direction == DomainDirection.unknown


# ═══════════════════════════════════════════════════════════════════════
# Advanced: Contradiction detection & 3-visit sequence
# ═══════════════════════════════════════════════════════════════════════


class TestContradictionAndMultiVisit:
    """Test direction reversal detection and 3-visit longitudinal tracking."""

    @pytest.mark.asyncio
    async def test_vp002_then_relapse(self):
        """VP-002 improved at visit 2, but what if visit 3 shows worsening?
        Simulate: Visit 2 (PHQ-9=7) → Visit 3 (PHQ-9=15) → worsened."""
        agent = TemporalSummaryAgent()
        inp = TemporalSummaryInput(
            session_id="VP-002-relapse",
            is_first_visit=False,
            current_scales={"PHQ-9": 15, "GAD-7": 12},
            prior_scales={"PHQ-9": 7, "GAD-7": 5},
            current_ctrs=3,
            prior_ctrs=5,
            current_date="2026-08-01",
            prior_date="2026-06-25",
        )
        result = await agent.run(inp)
        assert result.overall_direction == DomainDirection.worsened
        phq = next(t for t in result.domain_trends if t.domain == "PHQ-9")
        assert phq.direction == DomainDirection.worsened
        assert phq.delta == 8  # 7→15

    @pytest.mark.asyncio
    async def test_vp004_3visit_trajectory(self):
        """VP-004 trajectory: Visit 1→2 worsened, Visit 2→3 even worse.
        Visit 1: PHQ-9=14, GAD-7=10 (2026-04-14)
        Visit 2: PHQ-9=21, GAD-7=16 (2026-06-25)
        Visit 3: PHQ-9=24, GAD-7=18 (simulated 2026-08-01)"""
        agent = TemporalSummaryAgent()

        # Visit 2→3 comparison
        inp = TemporalSummaryInput(
            session_id="VP-004-v3",
            is_first_visit=False,
            current_scales={"PHQ-9": 24, "GAD-7": 18},
            prior_scales={"PHQ-9": 21, "GAD-7": 16},
            current_ctrs=2,  # escalated to high risk
            prior_ctrs=3,
            current_sentiment_polarity=-0.95,
            prior_sentiment_polarity=-0.8,
            current_date="2026-08-01",
            prior_date="2026-06-25",
        )
        result = await agent.run(inp)

        # PHQ-9: +3 (below threshold) → unchanged despite worsening
        phq = next(t for t in result.domain_trends if t.domain == "PHQ-9")
        assert phq.direction == DomainDirection.unchanged  # delta=3 < threshold=5
        assert phq.delta == 3

        # GAD-7: +2 → unchanged
        gad = next(t for t in result.domain_trends if t.domain == "GAD-7")
        assert gad.direction == DomainDirection.unchanged

        # CTRS: 3→2 → worsened (inverted scale)
        ctrs = next(t for t in result.domain_trends if t.domain == "CTRS")
        assert ctrs.direction == DomainDirection.worsened

        # Overall: CTRS worsened takes priority
        assert result.overall_direction == DomainDirection.worsened

    @pytest.mark.asyncio
    async def test_partial_data_comparison(self):
        """Only PHQ-9 available, no GAD-7 → PHQ-9 drives overall direction."""
        agent = TemporalSummaryAgent()
        inp = TemporalSummaryInput(
            session_id="partial",
            is_first_visit=False,
            current_scales={"PHQ-9": 20},
            prior_scales={"PHQ-9": 8},
            # No GAD-7, no CTRS, no sentiment
        )
        result = await agent.run(inp)
        assert result.overall_direction == DomainDirection.worsened

    @pytest.mark.asyncio
    async def test_one_improved_two_unchanged(self):
        """PHQ-9 improved, GAD-7 unchanged, CTRS unchanged → overall improved
        (all improved check: only 1 improved, 2 unchanged → should be unchanged)."""
        agent = TemporalSummaryAgent()
        inp = TemporalSummaryInput(
            session_id="mixed-mild",
            is_first_visit=False,
            current_scales={"PHQ-9": 5, "GAD-7": 8},
            prior_scales={"PHQ-9": 12, "GAD-7": 10},
            current_ctrs=4, prior_ctrs=4,
        )
        result = await agent.run(inp)
        # PHQ-9: -7 → improved, GAD-7: -2 → unchanged, CTRS: 4→4 → unchanged
        # Not ALL improved → unchanged
        assert result.overall_direction == DomainDirection.unchanged
