"""T1-F4-VER-003 + T1-F4-DEV-003: Temporal direction classification tests."""
import pytest
from src.agents.temporal_summary import TemporalSummaryAgent
from src.schemas.temporal import TemporalSummaryInput, DomainDirection

agent = TemporalSummaryAgent()

class TestFirstVisit:
    @pytest.mark.asyncio
    async def test_first_visit_all_unknown(self):
        inp = TemporalSummaryInput(session_id="t", is_first_visit=True)
        result = await agent.run(inp)
        assert result.overall_direction == DomainDirection.unknown
        assert result.is_first_visit is True
        assert result.domain_trends == []

class TestPHQ9Direction:
    @pytest.mark.asyncio
    async def test_improved(self):
        inp = TemporalSummaryInput(session_id="t", is_first_visit=False,
            current_scales={"PHQ-9": 10}, prior_scales={"PHQ-9": 16})
        result = await agent.run(inp)
        phq = next(t for t in result.domain_trends if t.domain == "PHQ-9")
        assert phq.direction == DomainDirection.improved
        assert phq.delta == -6

    @pytest.mark.asyncio
    async def test_worsened(self):
        inp = TemporalSummaryInput(session_id="t", is_first_visit=False,
            current_scales={"PHQ-9": 15}, prior_scales={"PHQ-9": 8})
        result = await agent.run(inp)
        phq = next(t for t in result.domain_trends if t.domain == "PHQ-9")
        assert phq.direction == DomainDirection.worsened
        assert phq.delta == 7

    @pytest.mark.asyncio
    async def test_unchanged(self):
        inp = TemporalSummaryInput(session_id="t", is_first_visit=False,
            current_scales={"PHQ-9": 12}, prior_scales={"PHQ-9": 8})
        result = await agent.run(inp)
        phq = next(t for t in result.domain_trends if t.domain == "PHQ-9")
        assert phq.direction == DomainDirection.unchanged  # delta 4 < 5

    @pytest.mark.asyncio
    async def test_no_prior(self):
        inp = TemporalSummaryInput(session_id="t", is_first_visit=False,
            current_scales={"PHQ-9": 15}, prior_scales={})
        result = await agent.run(inp)
        phq = next(t for t in result.domain_trends if t.domain == "PHQ-9")
        assert phq.direction == DomainDirection.unknown

class TestCTRSDirection:
    @pytest.mark.asyncio
    async def test_worsened(self):
        """CTRS 5->4 = worsened (lower number = MORE dangerous)"""
        inp = TemporalSummaryInput(session_id="t", is_first_visit=False,
            current_ctrs=4, prior_ctrs=5)
        result = await agent.run(inp)
        ctrs = next(t for t in result.domain_trends if t.domain == "CTRS")
        assert ctrs.direction == DomainDirection.worsened

    @pytest.mark.asyncio
    async def test_improved(self):
        """CTRS 3->4 = improved"""
        inp = TemporalSummaryInput(session_id="t", is_first_visit=False,
            current_ctrs=4, prior_ctrs=3)
        result = await agent.run(inp)
        ctrs = next(t for t in result.domain_trends if t.domain == "CTRS")
        assert ctrs.direction == DomainDirection.improved

    @pytest.mark.asyncio
    async def test_unchanged(self):
        inp = TemporalSummaryInput(session_id="t", is_first_visit=False,
            current_ctrs=4, prior_ctrs=4)
        result = await agent.run(inp)
        ctrs = next(t for t in result.domain_trends if t.domain == "CTRS")
        assert ctrs.direction == DomainDirection.unchanged

class TestOverallDirection:
    @pytest.mark.asyncio
    async def test_worsened_takes_priority(self):
        """If any domain worsened, overall = worsened"""
        inp = TemporalSummaryInput(session_id="t", is_first_visit=False,
            current_scales={"PHQ-9": 10, "GAD-7": 15},
            prior_scales={"PHQ-9": 16, "GAD-7": 8},
            current_ctrs=4, prior_ctrs=4)
        result = await agent.run(inp)
        assert result.overall_direction == DomainDirection.worsened  # GAD-7 worsened

    @pytest.mark.asyncio
    async def test_all_improved(self):
        inp = TemporalSummaryInput(session_id="t", is_first_visit=False,
            current_scales={"PHQ-9": 5, "GAD-7": 3},
            prior_scales={"PHQ-9": 15, "GAD-7": 12},
            current_ctrs=5, prior_ctrs=4)
        result = await agent.run(inp)
        assert result.overall_direction == DomainDirection.improved

class TestPlotData:
    @pytest.mark.asyncio
    async def test_plot_points(self):
        inp = TemporalSummaryInput(session_id="t", is_first_visit=False,
            current_scales={"PHQ-9": 10}, prior_scales={"PHQ-9": 16},
            current_date="2026-06-24", prior_date="2026-05-10",
            current_ctrs=4, prior_ctrs=5)
        result = await agent.run(inp)
        assert len(result.plot_data) == 2
        assert result.plot_data[0].date == "2026-05-10"
        assert result.plot_data[1].date == "2026-06-24"
