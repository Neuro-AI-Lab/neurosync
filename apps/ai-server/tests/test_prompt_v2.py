"""T1-F1-DEV-017: clinical_slot prompt v2 (anti-echo) validation.

The 2026-07-03 incident: v1's realistic example values were echoed verbatim
into slot values. v2 must contain NO plausible clinical strings, only
unmistakably synthetic placeholders.

PLAN-2026-W28 C1 (prompt_redesign_v3.md §2.3): the ClinicalSlotAgent now
requests v3, not v2 — the runtime-behavior assertions that used to live here
("agent requests v2 and reports v2") are superseded by TestV3PromptFile /
TestAgentRequestsV3 in tests/test_prompt_v3.py, which assert the same
contract against the current version. This file keeps only the *static*
v2-file content checks below, which remain true regardless of which version
is currently loaded (v2 stays on disk for rollback per versioning policy).
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "docs" / "ai" / "prompts"
_V1_PATH = _PROMPTS_DIR / "clinical_slot" / "v1.system.md"
_V2_PATH = _PROMPTS_DIR / "clinical_slot" / "v2.system.md"

# Realistic example strings from v1 that were echoed into the 07-03 run.
_V1_REALISTIC_STRINGS = [
    "정신과 진료 경험 없음",
    "진단받은 신체 질환 없음",
    "자살/자해 사고 명시적 부인",
    "잠을 못 자고, 불안감이 심하다",
    "주 1-2회 맥주 1캔",
    "어머니와 주 2회 통화",
    "말투 차분, 피로감 관찰됨",
    "직장 스트레스가 계기",
]

_REQUIRED_RULES = [
    "묻고 답하지 않은 슬롯은 반드시 null",
    "예시/템플릿 문구를 출력하지 않는다",
    "risk_assessment",
    "추론",
]


class TestV2PromptFile:
    def test_v1_kept_per_versioning_policy(self):
        assert _V1_PATH.exists(), "v1 must be kept (versioning policy)"

    def test_v2_exists(self):
        assert _V2_PATH.exists()

    def test_v2_contains_no_realistic_clinical_strings(self):
        content = _V2_PATH.read_text(encoding="utf-8")
        for s in _V1_REALISTIC_STRINGS:
            assert s not in content, f"v2 must not contain plausible value: {s!r}"

    def test_v2_uses_synthetic_placeholders(self):
        content = _V2_PATH.read_text(encoding="utf-8")
        assert "<환자가 실제로 말한" in content

    def test_v2_contains_required_rules(self):
        content = _V2_PATH.read_text(encoding="utf-8")
        for rule in _REQUIRED_RULES:
            assert rule in content, f"v2 missing rule text: {rule!r}"

    def test_v2_keeps_all_12_keys(self):
        from src.agents.clinical_slot import ALL_SLOT_KEYS
        content = _V2_PATH.read_text(encoding="utf-8")
        for key in ALL_SLOT_KEYS:
            assert key in content, f"v2 missing slot key: {key}"

    def test_v2_risk_never_inferred_rule(self):
        content = _V2_PATH.read_text(encoding="utf-8")
        assert "risk_assessment는 절대 추론하지 않는다" in content
