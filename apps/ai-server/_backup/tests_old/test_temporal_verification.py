"""T1-F4-VER-001/002/004: Temporal summary verification with VP scenarios."""
import pytest
from src.agents.temporal_summary import TemporalSummaryAgent
from src.schemas.temporal import TemporalSummaryInput, DomainDirection

agent = TemporalSummaryAgent()

class TestVP002Improvement:
    """T1-F4-VER-001: VP-002 revisit mild — improvement expected."""
    @pytest.mark.asyncio
    async def test_vp002_phq9_improved(self):
        inp = TemporalSummaryInput(
            session_id="vp002", patient_id="VP-002", is_first_visit=False,
            current_scales={"PHQ-9": 4, "GAD-7": 2},
            prior_scales={"PHQ-9": 12, "GAD-7": 6},
            current_ctrs=5, prior_ctrs=4,
            current_date="2026-06-24", prior_date="2026-05-10",
        )
        result = await agent.run(inp)
        phq = next(t for t in result.domain_trends if t.domain == "PHQ-9")
        assert phq.direction == DomainDirection.improved
        assert phq.delta == -8

    @pytest.mark.asyncio
    async def test_vp002_ctrs_improved(self):
        inp = TemporalSummaryInput(
            session_id="vp002", patient_id="VP-002", is_first_visit=False,
            current_ctrs=5, prior_ctrs=4)
        result = await agent.run(inp)
        ctrs = next(t for t in result.domain_trends if t.domain == "CTRS")
        assert ctrs.direction == DomainDirection.improved

    @pytest.mark.asyncio
    async def test_vp002_plot_data(self):
        inp = TemporalSummaryInput(
            session_id="vp002", patient_id="VP-002", is_first_visit=False,
            current_scales={"PHQ-9": 4}, prior_scales={"PHQ-9": 12},
            current_date="2026-06-24", prior_date="2026-05-10")
        result = await agent.run(inp)
        assert len(result.plot_data) == 2
        assert result.plot_data[0].date == "2026-05-10"
        assert result.plot_data[1].date == "2026-06-24"


class TestVP004Worsening:
    """T1-F4-VER-002: VP-004 revisit severe — worsening expected."""
    @pytest.mark.asyncio
    async def test_vp004_phq9_worsened(self):
        inp = TemporalSummaryInput(
            session_id="vp004", patient_id="VP-004", is_first_visit=False,
            current_scales={"PHQ-9": 21, "GAD-7": 16},
            prior_scales={"PHQ-9": 14, "GAD-7": 10},
            current_ctrs=3, prior_ctrs=4)
        result = await agent.run(inp)
        phq = next(t for t in result.domain_trends if t.domain == "PHQ-9")
        assert phq.direction == DomainDirection.worsened
        assert phq.delta == 7

    @pytest.mark.asyncio
    async def test_vp004_gad7_worsened(self):
        inp = TemporalSummaryInput(
            session_id="vp004", patient_id="VP-004", is_first_visit=False,
            current_scales={"GAD-7": 16}, prior_scales={"GAD-7": 10})
        result = await agent.run(inp)
        gad = next(t for t in result.domain_trends if t.domain == "GAD-7")
        assert gad.direction == DomainDirection.worsened
        assert gad.delta == 6

    @pytest.mark.asyncio
    async def test_vp004_ctrs_worsened(self):
        inp = TemporalSummaryInput(
            session_id="vp004", patient_id="VP-004", is_first_visit=False,
            current_ctrs=3, prior_ctrs=4)
        result = await agent.run(inp)
        ctrs = next(t for t in result.domain_trends if t.domain == "CTRS")
        assert ctrs.direction == DomainDirection.worsened

    @pytest.mark.asyncio
    async def test_vp004_overall_worsened(self):
        inp = TemporalSummaryInput(
            session_id="vp004", patient_id="VP-004", is_first_visit=False,
            current_scales={"PHQ-9": 21, "GAD-7": 16},
            prior_scales={"PHQ-9": 14, "GAD-7": 10},
            current_ctrs=3, prior_ctrs=4)
        result = await agent.run(inp)
        assert result.overall_direction == DomainDirection.worsened


class TestContradictionDetection:
    """T1-F4-VER-004: Detect direction reversal (prior improved → current worsened)."""
    @pytest.mark.asyncio
    async def test_reversal_detected(self):
        # Scenario: patient was improving (PHQ-9 20→12) but now worsened (12→18)
        inp = TemporalSummaryInput(
            session_id="reversal", patient_id="test", is_first_visit=False,
            current_scales={"PHQ-9": 18},
            prior_scales={"PHQ-9": 12},
            current_ctrs=3, prior_ctrs=4)
        result = await agent.run(inp)
        phq = next(t for t in result.domain_trends if t.domain == "PHQ-9")
        assert phq.direction == DomainDirection.worsened
        assert phq.delta == 6
        ctrs = next(t for t in result.domain_trends if t.domain == "CTRS")
        assert ctrs.direction == DomainDirection.worsened

    @pytest.mark.asyncio
    async def test_mixed_directions(self):
        # PHQ-9 improved but GAD-7 worsened → overall worsened (worsened takes priority)
        inp = TemporalSummaryInput(
            session_id="mixed", patient_id="test", is_first_visit=False,
            current_scales={"PHQ-9": 5, "GAD-7": 18},
            prior_scales={"PHQ-9": 15, "GAD-7": 8})
        result = await agent.run(inp)
        assert result.overall_direction == DomainDirection.worsened
