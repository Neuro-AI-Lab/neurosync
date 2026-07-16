"""`src.injection_protocol` — STT/OCR arbitrary-turn injection composer.

PLAN-2026-W28-Q W3 (`_archive/plans/validation_plan_f1f2_continuous.md` §3
"STT/OCR arbitrary-turn injection" row, §6 AVC-15). Deterministic,
mocked-adapter coverage only — no vendor/model calls (the live 2-call
composer proof lives in `tests/smoke_injection_composer.py`, run manually,
never part of this suite).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.injection_protocol import (
    InjectionCue,
    ModalityProvenanceEvent,
    ScheduleValidationIssue,
    audit_ocr_document_evidence,
    build_ocr_texts_from_f1_ocr_documents,
    build_ocr_texts_from_provenance,
    compose_injected_patient_input_fn,
    load_schedule_from_json,
    schedule_to_dicts,
    validate_schedule,
    verify_provenance_against_conversation,
    write_provenance_sidecar,
)


def _make_stt_output(text: str) -> MagicMock:
    out = MagicMock()
    out.text = text
    out.vendor = "skt-ak-stt"
    return out


def _make_ocr_output(markdown: str, raw_text: str = "") -> MagicMock:
    out = MagicMock()
    out.raw_markdown = markdown
    out.raw_text = raw_text
    out.ocr_vendor = "upstage_solar_document_parse"
    return out


# ── InjectionCue / schedule ─────────────────────────────────────────────


class TestInjectionCue:
    def test_rejects_negative_turn_index(self) -> None:
        with pytest.raises(ValueError, match="turn_index"):
            InjectionCue(turn_index=-1, modality="stt", fixture_path=Path("x.mp3"))

    def test_rejects_unknown_modality(self) -> None:
        with pytest.raises(ValueError, match="modality"):
            InjectionCue(turn_index=0, modality="video", fixture_path=Path("x.mp4"))  # type: ignore[arg-type]

    def test_coerces_str_fixture_path_to_path(self) -> None:
        cue = InjectionCue(turn_index=1, modality="ocr", fixture_path="doc.pdf")  # type: ignore[arg-type]
        assert isinstance(cue.fixture_path, Path)

    def test_resolved_label_falls_back_to_fixture_stem(self) -> None:
        cue = InjectionCue(turn_index=1, modality="ocr", fixture_path=Path("VP-004_rx.pdf"))
        assert cue.resolved_label == "VP-004_rx"

    def test_resolved_label_prefers_explicit_label(self) -> None:
        cue = InjectionCue(
            turn_index=1, modality="ocr", fixture_path=Path("VP-004_rx.pdf"), label="custom",
        )
        assert cue.resolved_label == "custom"

    def test_stt_cue_without_fixture_path_raises(self) -> None:
        with pytest.raises(ValueError, match="requires `fixture_path`"):
            InjectionCue(turn_index=0, modality="stt", text="should not matter")

    def test_ocr_cue_without_fixture_path_raises(self) -> None:
        with pytest.raises(ValueError, match="requires `fixture_path`"):
            InjectionCue(turn_index=0, modality="ocr")


class TestTextModalityCue:
    """`"text"` modality — literal patient text, no fixture, no vendor call
    (plan §6 SC-15 prompt-echo probes)."""

    def test_text_cue_requires_non_empty_text(self) -> None:
        with pytest.raises(ValueError, match="requires a non-empty `text`"):
            InjectionCue(turn_index=0, modality="text")

    def test_text_cue_does_not_require_fixture_path(self) -> None:
        cue = InjectionCue(turn_index=0, modality="text", text="안녕하세요, 접니다.")
        assert cue.fixture_path is None
        assert cue.text == "안녕하세요, 접니다."

    def test_text_cue_resolved_label_falls_back_to_turn_marker(self) -> None:
        cue = InjectionCue(turn_index=2, modality="text", text="probe text")
        assert cue.resolved_label == "text-turn2"

    def test_text_cue_resolved_label_prefers_explicit_label(self) -> None:
        cue = InjectionCue(
            turn_index=0, modality="text", text="probe text", label="echo-probe",
        )
        assert cue.resolved_label == "echo-probe"


class TestScheduleJsonRoundTrip:
    def test_load_schedule_from_json(self, tmp_path: Path) -> None:
        schedule_path = tmp_path / "schedule.json"
        fixture = tmp_path / "audio.mp3"
        fixture.write_bytes(b"fake")
        schedule_path.write_text(json.dumps([
            {"turn_index": 2, "modality": "stt", "fixture_path": str(fixture), "label": "vp1"},
        ]), encoding="utf-8")

        cues = load_schedule_from_json(schedule_path)
        assert len(cues) == 1
        assert cues[0].turn_index == 2
        assert cues[0].modality == "stt"
        assert cues[0].fixture_path == fixture
        assert cues[0].label == "vp1"

    def test_load_schedule_from_json_rejects_non_list(self, tmp_path: Path) -> None:
        schedule_path = tmp_path / "bad.json"
        schedule_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        with pytest.raises(ValueError, match="JSON list"):
            load_schedule_from_json(schedule_path)

    def test_schedule_to_dicts_round_trips_fields(self, tmp_path: Path) -> None:
        fixture = tmp_path / "doc.pdf"
        fixture.touch()
        cue = InjectionCue(turn_index=0, modality="ocr", fixture_path=fixture)
        dicts = schedule_to_dicts([cue])
        assert dicts == [{
            "turn_index": 0, "modality": "ocr", "fixture_path": str(fixture), "label": "doc",
        }]

    def test_load_schedule_from_json_with_text_modality(self, tmp_path: Path) -> None:
        schedule_path = tmp_path / "schedule.json"
        schedule_path.write_text(json.dumps([
            {"turn_index": 0, "modality": "text", "text": "안녕하세요", "label": "echo"},
        ]), encoding="utf-8")

        cues = load_schedule_from_json(schedule_path)
        assert len(cues) == 1
        assert cues[0].modality == "text"
        assert cues[0].text == "안녕하세요"
        assert cues[0].fixture_path is None
        assert cues[0].label == "echo"

    def test_schedule_to_dicts_includes_text_when_present(self) -> None:
        cue = InjectionCue(turn_index=0, modality="text", text="probe")
        dicts = schedule_to_dicts([cue])
        assert dicts == [{
            "turn_index": 0, "modality": "text", "fixture_path": None,
            "label": "text-turn0", "text": "probe",
        }]


class TestValidateSchedule:
    def test_missing_fixture_is_reported(self, tmp_path: Path) -> None:
        cue = InjectionCue(turn_index=0, modality="stt", fixture_path=tmp_path / "missing.mp3")
        issues = validate_schedule([cue])
        assert len(issues) == 1
        assert isinstance(issues[0], ScheduleValidationIssue)
        assert "SKIPPED-awaiting-user-material" in issues[0].reason

    def test_existing_fixture_is_clean(self, tmp_path: Path) -> None:
        fixture = tmp_path / "present.pdf"
        fixture.touch()
        cue = InjectionCue(turn_index=0, modality="ocr", fixture_path=fixture)
        assert validate_schedule([cue]) == []

    def test_duplicate_turn_index_is_flagged(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.pdf"
        f2 = tmp_path / "b.pdf"
        f1.touch()
        f2.touch()
        cues = [
            InjectionCue(turn_index=3, modality="ocr", fixture_path=f1),
            InjectionCue(turn_index=3, modality="ocr", fixture_path=f2),
        ]
        issues = validate_schedule(cues)
        assert any("duplicate" in i.reason for i in issues)

    def test_text_cue_never_reports_a_missing_fixture(self) -> None:
        cue = InjectionCue(turn_index=0, modality="text", text="probe text")
        assert validate_schedule([cue]) == []

    def test_text_cue_duplicate_turn_index_still_flagged(self) -> None:
        cues = [
            InjectionCue(turn_index=1, modality="text", text="a"),
            InjectionCue(turn_index=1, modality="text", text="b"),
        ]
        issues = validate_schedule(cues)
        assert any("duplicate" in i.reason for i in issues)


# ── Composer ─────────────────────────────────────────────────────────────


class TestComposeInjectedPatientInputFn:
    @pytest.mark.asyncio
    async def test_non_scheduled_turn_delegates_to_base_fn(self) -> None:
        base_fn = AsyncMock(return_value="base response")
        composed, events = compose_injected_patient_input_fn(
            base_fn, schedule=[], session_id="s1", patient_id="VP-001",
        )
        result = await composed("agent said hi")
        assert result == "base response"
        base_fn.assert_awaited_once_with("agent said hi")
        assert events == []

    @pytest.mark.asyncio
    async def test_scheduled_stt_turn_calls_stt_agent_not_base_fn(self, tmp_path: Path) -> None:
        fixture = tmp_path / "VP-001-001.mp3"
        fixture.write_bytes(b"fake-audio")
        base_fn = AsyncMock(return_value="SHOULD NOT BE USED")

        fake_agent = MagicMock()
        fake_agent.transcribe = AsyncMock(return_value=_make_stt_output("전사된 환자 발화"))
        get_stt_agent_fn = MagicMock(return_value=fake_agent)

        cue = InjectionCue(turn_index=0, modality="stt", fixture_path=fixture, label="vp1-t0")
        composed, events = compose_injected_patient_input_fn(
            base_fn, schedule=[cue], session_id="s1", patient_id="VP-001",
            get_stt_agent_fn=get_stt_agent_fn,
        )

        result = await composed("greeting")
        assert result == "전사된 환자 발화"
        base_fn.assert_not_awaited()
        fake_agent.transcribe.assert_awaited_once()
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, ModalityProvenanceEvent)
        assert ev.turn_index == 0
        assert ev.modality == "stt"
        assert ev.source_id == "stt:vp1-t0"
        assert ev.char_count == len("전사된 환자 발화")
        assert ev.text == "전사된 환자 발화"
        assert ev.text_preview == "전사된 환자 발화"[:10]

    @pytest.mark.asyncio
    async def test_scheduled_ocr_turn_calls_ocr_agent(self, tmp_path: Path) -> None:
        fixture = tmp_path / "VP-004_rx.pdf"
        fixture.write_bytes(b"%PDF-fake")
        base_fn = AsyncMock(return_value="SHOULD NOT BE USED")

        fake_agent = MagicMock()
        fake_agent.parse = AsyncMock(
            return_value=_make_ocr_output("에스시탈로프람 20mg 1일 1회 처방")
        )
        get_ocr_agent_fn = MagicMock(return_value=fake_agent)

        cue = InjectionCue(
            turn_index=3, modality="ocr", fixture_path=fixture, label="VP-004_prescription",
        )
        composed, events = compose_injected_patient_input_fn(
            base_fn, schedule=[cue], session_id="s1", patient_id="VP-004",
            get_ocr_agent_fn=get_ocr_agent_fn,
        )

        # turns 0..2 fall through to base_fn; turn 3 is the scheduled cue.
        for _ in range(3):
            await composed("filler agent turn")
        result = await composed("agent turn 3")

        assert result == "에스시탈로프람 20mg 1일 1회 처방"
        assert base_fn.await_count == 3
        fake_agent.parse.assert_awaited_once()
        assert len(events) == 1
        assert events[0].source_id == "ocr:VP-004_prescription"
        assert events[0].modality == "ocr"

    @pytest.mark.asyncio
    async def test_missing_fixture_raises_file_not_found_never_fabricates(
        self, tmp_path: Path
    ) -> None:
        cue = InjectionCue(turn_index=0, modality="ocr", fixture_path=tmp_path / "absent.pdf")
        composed, _events = compose_injected_patient_input_fn(
            AsyncMock(), schedule=[cue], session_id="s1", patient_id="VP-999",
        )
        with pytest.raises(FileNotFoundError, match="SKIPPED-awaiting-user-material"):
            await composed("greeting")

    @pytest.mark.asyncio
    async def test_scheduled_text_turn_returns_literal_no_vendor_call(self) -> None:
        base_fn = AsyncMock(return_value="SHOULD NOT BE USED")
        get_stt_agent_fn = MagicMock(side_effect=AssertionError("STT agent must not be built"))
        get_ocr_agent_fn = MagicMock(side_effect=AssertionError("OCR agent must not be built"))

        cue = InjectionCue(
            turn_index=0, modality="text", text="CANARY-ECHO-PROBE-XYZ", label="echo-probe",
        )
        composed, events = compose_injected_patient_input_fn(
            base_fn, schedule=[cue], session_id="s1", patient_id="VP-001",
            get_stt_agent_fn=get_stt_agent_fn, get_ocr_agent_fn=get_ocr_agent_fn,
        )

        result = await composed("agent turn 0")

        assert result == "CANARY-ECHO-PROBE-XYZ"
        base_fn.assert_not_awaited()
        get_stt_agent_fn.assert_not_called()
        get_ocr_agent_fn.assert_not_called()
        assert len(events) == 1
        ev = events[0]
        assert ev.modality == "text"
        assert ev.source_id == "text:echo-probe"
        assert ev.vendor == "literal"
        assert ev.latency_ms == 0.0
        assert ev.text == "CANARY-ECHO-PROBE-XYZ"
        assert ev.char_count == len("CANARY-ECHO-PROBE-XYZ")

    @pytest.mark.asyncio
    async def test_text_only_schedule_never_constructs_a_vendor_client(self) -> None:
        """A schedule mixing multiple text cues across turns must never
        touch either vendor-agent factory — the composer's default factory
        args are the LIVE production factories, so this proves a real
        vendor client is never constructed for a text-only run."""
        base_fn = AsyncMock(return_value="filler")
        get_stt_agent_fn = MagicMock(side_effect=AssertionError("must not be built"))
        get_ocr_agent_fn = MagicMock(side_effect=AssertionError("must not be built"))

        schedule = [
            InjectionCue(turn_index=0, modality="text", text="첫 발화"),
            InjectionCue(turn_index=2, modality="text", text="세 번째 발화"),
        ]
        composed, events = compose_injected_patient_input_fn(
            base_fn, schedule=schedule, session_id="s1", patient_id="VP-001",
            get_stt_agent_fn=get_stt_agent_fn, get_ocr_agent_fn=get_ocr_agent_fn,
        )

        assert await composed("turn 0") == "첫 발화"
        assert await composed("turn 1 (not scheduled)") == "filler"
        assert await composed("turn 2") == "세 번째 발화"

        get_stt_agent_fn.assert_not_called()
        get_ocr_agent_fn.assert_not_called()
        assert len(events) == 2
        assert base_fn.await_count == 1

    @pytest.mark.asyncio
    async def test_ocr_text_bounded_by_max_ocr_chars(self, tmp_path: Path) -> None:
        fixture = tmp_path / "long.pdf"
        fixture.write_bytes(b"%PDF-fake")
        fake_agent = MagicMock()
        fake_agent.parse = AsyncMock(return_value=_make_ocr_output("가" * 5000))
        get_ocr_agent_fn = MagicMock(return_value=fake_agent)

        cue = InjectionCue(turn_index=0, modality="ocr", fixture_path=fixture)
        composed, events = compose_injected_patient_input_fn(
            AsyncMock(), schedule=[cue], session_id="s1", patient_id="VP-001",
            get_ocr_agent_fn=get_ocr_agent_fn, max_ocr_chars=100,
        )
        result = await composed("greeting")
        assert len(result) == 100
        assert events[0].char_count == 100


# ── Provenance sidecar ───────────────────────────────────────────────────


class TestProvenanceSidecar:
    def test_write_provenance_sidecar_shape_and_naming(self, tmp_path: Path) -> None:
        conv_path = tmp_path / "VP-001_20260711_120000_conversation.json"
        conv_path.write_text("{}", encoding="utf-8")
        ev = ModalityProvenanceEvent(
            turn_index=1, modality="stt", fixture_path="a.mp3", label="l",
            source_id="stt:l", vendor="skt-ak-stt", char_count=3, latency_ms=1.0,
            extracted_at="2026-07-11T00:00:00", text="abc", text_preview="abc",
        )
        sidecar = write_provenance_sidecar(conv_path, [ev], persona_id="VP-001")
        assert sidecar.name == "VP-001_20260711_120000_modality_provenance.json"
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        assert payload["persona_id"] == "VP-001"
        assert payload["conversation_path"] == str(conv_path)
        assert len(payload["events"]) == 1
        assert payload["events"][0]["source_id"] == "stt:l"

    def test_verify_provenance_matches_normalizer_original(self) -> None:
        ev = ModalityProvenanceEvent(
            turn_index=0, modality="stt", fixture_path="a.mp3", label="l",
            source_id="stt:l", vendor="skt-ak-stt", char_count=5, latency_ms=1.0,
            extracted_at="t", text="원본 텍스트", text_preview="원본 텍스트",
        )
        conversation_json = {
            "turns": [
                {"turn": 0, "patient_message": "정규화된 텍스트",
                 "normalizer_meta": {"original": "원본 텍스트", "change_count": 1}},
            ]
        }
        assert verify_provenance_against_conversation(conversation_json, [ev]) == []

    def test_verify_provenance_flags_a_genuine_mismatch(self) -> None:
        ev = ModalityProvenanceEvent(
            turn_index=0, modality="stt", fixture_path="a.mp3", label="l",
            source_id="stt:l", vendor="skt-ak-stt", char_count=5, latency_ms=1.0,
            extracted_at="t", text="원본 텍스트", text_preview="원본 텍스트",
        )
        conversation_json = {
            "turns": [
                {"turn": 0, "patient_message": "전혀 다른 텍스트",
                 "normalizer_meta": {"original": "전혀 다른 원본", "change_count": 0}},
            ]
        }
        mismatches = verify_provenance_against_conversation(conversation_json, [ev])
        assert len(mismatches) == 1
        assert "turn 0" in mismatches[0]

    def test_verify_provenance_missing_turn_is_flagged(self) -> None:
        ev = ModalityProvenanceEvent(
            turn_index=5, modality="ocr", fixture_path="a.pdf", label="l",
            source_id="ocr:l", vendor="upstage_solar_document_parse", char_count=1,
            latency_ms=1.0, extracted_at="t", text="x", text_preview="x",
        )
        mismatches = verify_provenance_against_conversation({"turns": []}, [ev])
        assert len(mismatches) == 1
        assert "no matching turn" in mismatches[0]


# ── ocr_texts / AVC-15 audit ─────────────────────────────────────────────


class TestOcrTextsAndAudit:
    def test_build_ocr_texts_from_provenance_only_includes_ocr_events(self) -> None:
        stt_ev = ModalityProvenanceEvent(
            turn_index=0, modality="stt", fixture_path="a.mp3", label="l1",
            source_id="stt:l1", vendor="skt-ak-stt", char_count=1, latency_ms=1.0,
            extracted_at="t", text="s", text_preview="s",
        )
        ocr_ev = ModalityProvenanceEvent(
            turn_index=1, modality="ocr", fixture_path="a.pdf", label="l2",
            source_id="ocr:l2", vendor="upstage_solar_document_parse", char_count=1,
            latency_ms=1.0, extracted_at="t", text="에스시탈로프람 20mg", text_preview="에스시탈",
        )
        mapping = build_ocr_texts_from_provenance([stt_ev, ocr_ev])
        assert mapping == {"ocr:l2": "에스시탈로프람 20mg"}

    def test_build_ocr_texts_from_f1_ocr_documents(self) -> None:
        docs = [
            {"document_type": "prescription", "raw_markdown": "에스시탈로프람 20mg"},
            {"document_type": "diagnosis", "raw_markdown": "", "raw_text": ""},  # empty, skipped
        ]
        mapping = build_ocr_texts_from_f1_ocr_documents(docs, persona_id="VP-004")
        assert mapping == {"ocr:VP-004_prescription_0": "에스시탈로프람 20mg"}

    def test_audit_ocr_document_evidence_accepts_grounded_quote(self) -> None:
        artifact = {
            "domain_candidates": [
                {
                    "domain": "depression",
                    "evidence": [
                        {
                            "source_type": "ocr_document",
                            "source_id": "ocr:VP-004_prescription",
                            "quote": "에스시탈로프람 20mg",
                        },
                        {
                            "source_type": "utterance",
                            "source_id": "turn_1",
                            "quote": "요즘 잠을 못 자요",
                        },
                    ],
                }
            ]
        }
        ocr_texts = {"ocr:VP-004_prescription": "환자에게 에스시탈로프람 20mg 처방함."}
        verdicts = audit_ocr_document_evidence(artifact, ocr_texts)
        # only the ocr_document evidence item is checked — utterance is skipped.
        assert len(verdicts) == 1
        assert verdicts[0].accepted

    def test_audit_ocr_document_evidence_empty_when_no_ocr_document_evidence(self) -> None:
        artifact = {
            "domain_candidates": [
                {"domain": "anxiety", "evidence": [
                    {"source_type": "utterance", "source_id": "turn_2", "quote": "불안해요"},
                ]},
            ]
        }
        assert audit_ocr_document_evidence(artifact, {}) == []

    def test_audit_ocr_document_evidence_rejects_when_ocr_texts_missing(self) -> None:
        artifact = {
            "domain_candidates": [
                {"domain": "depression", "evidence": [
                    {"source_type": "ocr_document", "source_id": "ocr:missing", "quote": "x"},
                ]},
            ]
        }
        verdicts = audit_ocr_document_evidence(artifact, {})
        assert len(verdicts) == 1
        assert not verdicts[0].accepted
