"""`src.run_injected_session` — protocol runner: F1Pipeline + injection schedule.

`docs/ai/validation_plan_f1f2_continuous.md` §3 STT/OCR row + §6 canary
design (SC-13/SC-15 execution vehicle). Deterministic, mocked-LLM coverage
only: `tests.f1_testkit`'s stub `F1Pipeline` + an injected stub base
`patient_input_fn` — zero vendor/model calls, zero live credentials.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.injection_protocol import InjectionCue
from src.run_injected_session import _persona_id_for_lookup, run_injected_session
from tests.f1_testkit import make_pipeline

_PERSONA_MD = """# VP-901: 테스트 페르소나 — 테스트환자

## 1. Demographics
- 30세, 테스트용.

## 5. Expected dialogue patterns
- 예시 발화: "테스트입니다."

## 6. Patient LLM simulation prompt

```
당신은 테스트 환자입니다. 1문장으로 짧게 답하세요.
```
"""


@pytest.fixture
def persona_path(tmp_path: Path) -> Path:
    p = tmp_path / "VP-901_first_visit_mild.md"
    p.write_text(_PERSONA_MD, encoding="utf-8")
    return p


async def _filler_base_fn(_agent_response: str) -> str:
    """Harmless non-scheduled-turn responder — never a real PatientLLM/
    vendor call."""
    return "필러 발화입니다."


class TestPersonaIdForLookup:
    def test_plain_id_passes_through(self) -> None:
        assert _persona_id_for_lookup("VP-001") == "VP-001"

    def test_path_mode_derives_leading_token(self) -> None:
        path = "docs/ai/personas/_canary_audit/VP-001_first_visit_mild.md"
        assert _persona_id_for_lookup(path) == "VP-001"


class TestRunInjectedSession:
    @pytest.mark.asyncio
    async def test_text_cue_reaches_pipeline_as_patient_input_verbatim(
        self, tmp_path: Path, persona_path: Path
    ) -> None:
        pipeline = make_pipeline()
        schedule = [
            InjectionCue(turn_index=0, modality="text", text="CANARY-TEST-ECHO-PROBE-XYZ"),
        ]

        result, _paths, _sidecar_path, events = await run_injected_session(
            persona_source=str(persona_path),
            schedule=schedule,
            max_turns=1,
            out_dir=tmp_path,
            pipeline=pipeline,
            base_patient_fn=_filler_base_fn,
        )

        assert result.persona_id == "VP-901"
        assert result.turns[0].patient_message == "CANARY-TEST-ECHO-PROBE-XYZ"
        assert len(events) == 1
        assert events[0].modality == "text"
        assert events[0].text == "CANARY-TEST-ECHO-PROBE-XYZ"

    @pytest.mark.asyncio
    async def test_artifacts_carry_the_modality_provenance_sidecar(
        self, tmp_path: Path, persona_path: Path
    ) -> None:
        pipeline = make_pipeline()
        schedule = [InjectionCue(turn_index=0, modality="text", text="에코 테스트 발화")]

        result, paths, sidecar_path, events = await run_injected_session(
            persona_source=str(persona_path),
            schedule=schedule,
            max_turns=1,
            out_dir=tmp_path,
            pipeline=pipeline,
            base_patient_fn=_filler_base_fn,
        )

        # Same artifact shape as f1.py's own CLI (save_f1_result).
        assert set(paths.keys()) == {"json", "checklist", "report"}
        for p in paths.values():
            assert p.exists()

        assert sidecar_path.exists()
        assert sidecar_path.name.endswith("_modality_provenance.json")
        assert sidecar_path.parent == paths["json"].parent

        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert payload["persona_id"] == result.persona_id == "VP-901"
        assert payload["conversation_path"] == str(paths["json"])
        assert len(payload["events"]) == 1
        assert payload["events"][0]["modality"] == "text"
        assert payload["events"][0]["source_id"] == events[0].source_id

    @pytest.mark.asyncio
    async def test_invalid_schedule_raises_before_any_pipeline_call(
        self, tmp_path: Path, persona_path: Path
    ) -> None:
        pipeline = make_pipeline()
        schedule = [
            InjectionCue(turn_index=0, modality="ocr", fixture_path=tmp_path / "missing.pdf"),
        ]

        with pytest.raises(ValueError, match="schedule failed validation"):
            await run_injected_session(
                persona_source=str(persona_path),
                schedule=schedule,
                max_turns=1,
                out_dir=tmp_path,
                pipeline=pipeline,
                base_patient_fn=_filler_base_fn,
            )
