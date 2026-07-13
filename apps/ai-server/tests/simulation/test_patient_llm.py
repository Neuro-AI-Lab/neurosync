"""`tests.simulation.patient_llm.load_persona` — ID-glob vs. explicit-path seam.

`docs/ai/validation_plan_f1f2_continuous.md` §6 canary design: audit-only
persona copies live under `docs/ai/personas/_canary_audit/`, provably
disjoint from `PERSONAS_DIR.glob(f"{persona_id}_*.md")` (non-recursive), so
the normal ID-glob path never loads them. This seam lets a caller (the
SC-13 protocol runner) load one directly by path. No LLM/network calls —
`load_persona` only reads and parses a local `.md` file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.simulation import patient_llm
from tests.simulation.patient_llm import PatientPersona, load_persona

REPO_ROOT = Path(__file__).resolve().parents[4]
CANARY_AUDIT_DIR = REPO_ROOT / "docs" / "ai" / "personas" / "_canary_audit"

_MINIMAL_PERSONA_MD = """# {persona_id}: 테스트 페르소나 — 테스트환자

## 1. Demographics
- 25세 여성, 테스트용.

## 5. Expected dialogue patterns
- 예시 발화: "테스트 발화입니다."

## 6. Patient LLM simulation prompt

```
당신은 테스트 환자입니다. 항상 1문장으로 짧게 답하세요.
```
"""


def _write_persona(dir_path: Path, filename: str, persona_id: str = "VP-777") -> Path:
    path = dir_path / filename
    path.write_text(_MINIMAL_PERSONA_MD.format(persona_id=persona_id), encoding="utf-8")
    return path


class TestIdModeRegression:
    """ID-glob mode must stay byte-for-byte unchanged — f1.py's own
    `--persona` CLI argument passes a plain VP-NNN id through this seam
    untouched."""

    def test_loads_by_id_via_glob(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_persona(tmp_path, "VP-777_first_visit_mild.md", persona_id="VP-777")
        monkeypatch.setattr(patient_llm, "PERSONAS_DIR", tmp_path)

        persona = load_persona("VP-777")

        assert isinstance(persona, PatientPersona)
        assert persona.persona_id == "VP-777"
        assert persona.severity == "mild"
        assert persona.visit_type == "first_visit"
        assert "테스트 환자" in persona.system_prompt

    def test_unknown_id_fails_loudly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(patient_llm, "PERSONAS_DIR", tmp_path)
        with pytest.raises(FileNotFoundError, match="Persona file not found"):
            load_persona("VP-999")

    def test_real_persona_dir_still_resolves_vp001(self) -> None:
        """Smoke check against the actual repo persona directory — proves
        the glob-mode default path (no monkeypatch) is untouched."""
        persona = load_persona("VP-001")
        assert persona.persona_id == "VP-001"
        assert persona.system_prompt


class TestPathModeSeam:
    """Explicit `.md` path resolution — the new seam."""

    def test_loads_by_explicit_path(self, tmp_path: Path) -> None:
        md_path = _write_persona(tmp_path, "VP-777_first_visit_mild.md", persona_id="VP-777")

        persona = load_persona(str(md_path))

        assert persona.persona_id == "VP-777"
        assert persona.severity == "mild"
        assert persona.visit_type == "first_visit"

    def test_path_mode_disjoint_from_id_glob(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A path-mode load must succeed even when PERSONAS_DIR points
        somewhere that does NOT contain the file — proving path-mode never
        depends on the ID-glob resolution."""
        real_dir = tmp_path / "real_personas"
        real_dir.mkdir()
        empty_dir = tmp_path / "empty_personas"
        empty_dir.mkdir()
        monkeypatch.setattr(patient_llm, "PERSONAS_DIR", empty_dir)

        md_path = _write_persona(real_dir, "VP-777_first_visit_mild.md", persona_id="VP-777")
        persona = load_persona(str(md_path))
        assert persona.persona_id == "VP-777"

        # ID-glob mode for the SAME id still fails against the (deliberately
        # empty) PERSONAS_DIR — proving the two resolution paths are
        # genuinely independent, not one silently falling back to the other.
        with pytest.raises(FileNotFoundError):
            load_persona("VP-777")

    def test_nonexistent_path_fails_loudly(self, tmp_path: Path) -> None:
        missing = tmp_path / "VP-999_does_not_exist.md"
        with pytest.raises(FileNotFoundError, match="Persona file path not found"):
            load_persona(str(missing))

    def test_loads_a_canary_audit_copy(self) -> None:
        """Integration check against the real, already-landed
        `_canary_audit/` copy (`DATASET-006` addendum / `REV-023` ruling
        1a) — proves path-mode loads the exact audit-only file the
        blocked SC-13 runner needs."""
        canary_path = CANARY_AUDIT_DIR / "VP-001_first_visit_mild.md"
        if not canary_path.is_file():
            pytest.skip(f"canary audit copy not present at {canary_path}")

        persona = load_persona(str(canary_path))

        assert persona.persona_id == "VP-001"
        assert persona.severity == "mild"
        assert persona.visit_type == "first_visit"
        # Section 6 (system_prompt) must NOT carry section 8's CANARY table —
        # `_extract_section_content` only pulls the Patient LLM simulation
        # prompt block, never the canary-audit-only section appended after it.
        assert "CANARY-VP001" not in persona.system_prompt

    def test_canary_copy_id_matches_normal_id_mode_load(self) -> None:
        """The SAME VP loaded via path-mode (canary copy) vs. ID-mode
        (original) must resolve to the same `persona_id`, so downstream
        session-id/PERSONA_LOCATIONS lookups behave identically."""
        canary_path = CANARY_AUDIT_DIR / "VP-001_first_visit_mild.md"
        if not canary_path.is_file():
            pytest.skip(f"canary audit copy not present at {canary_path}")

        via_path = load_persona(str(canary_path))
        via_id = load_persona("VP-001")
        assert via_path.persona_id == via_id.persona_id == "VP-001"
