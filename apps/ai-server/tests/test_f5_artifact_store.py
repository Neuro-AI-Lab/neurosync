"""Security and collision contracts for persisted F5 artifact groups."""

from __future__ import annotations

import hashlib
import logging
import os
import stat
import uuid
from pathlib import Path

import pytest

import src.services.f5_artifact_store as artifact_store
import src.services.f5_report as f5_report
from src.schemas.handoff_report import HandoffReportOutput
from src.services.f5_artifact_store import F5ArtifactPaths
from src.services.f5_report import save_f5_result
from tests.test_f5_report import _minimal_report

_STAMP = "20260102_030405"
_TOKEN_A = "a" * 32


class _FixedInstant:
    def strftime(self, _format: str) -> str:
        return _STAMP


class _ClinicalSentinelError(RuntimeError):
    """Deterministic clinical-content failure for privacy assertions."""


class _FixedDateTime:
    @classmethod
    def now(cls) -> _FixedInstant:
        return _FixedInstant()


class _UuidSequence:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = iter(tokens)
        self.calls = 0

    def __call__(self) -> uuid.UUID:
        self.calls += 1
        return uuid.UUID(hex=next(self._tokens))


class _ConstantUuid:
    def __init__(self, token: str) -> None:
        self._value = uuid.UUID(hex=token)
        self.calls = 0

    def __call__(self) -> uuid.UUID:
        self.calls += 1
        return self._value


class _UuidApi:
    def __init__(self, factory: _UuidSequence | _ConstantUuid) -> None:
        self._factory = factory

    def uuid4(self) -> uuid.UUID:
        return self._factory()


def _freeze_names(
    monkeypatch: pytest.MonkeyPatch, uuid_factory: _UuidSequence | _ConstantUuid
) -> None:
    monkeypatch.setattr(f5_report, "datetime", _FixedDateTime)
    monkeypatch.setattr(artifact_store, "uuid", _UuidApi(uuid_factory))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _all_paths(paths: F5ArtifactPaths) -> tuple[Path, ...]:
    pdf = paths.get("pdf")
    if pdf is None:
        return paths["markdown"], paths["fhir"]
    return paths["markdown"], pdf, paths["fhir"]


def _artifact_name(vp_id: str, token: str, suffix: str) -> str:
    return f"{vp_id}_{_STAMP}_{token}_{suffix}"


class TestSecureF5OutputPaths:
    @pytest.mark.parametrize(
        "vp_id",
        ["", ".", "..", "nested/vp", r"nested\vp", "/absolute", "a//b"],
    )
    def test_malformed_vp_id_is_rejected(self, tmp_path: Path, vp_id: str) -> None:
        root = tmp_path / "root"
        root.mkdir()

        with pytest.raises((OSError, ValueError)):
            save_f5_result(_minimal_report(), root, vp_id=vp_id)

    def test_absolute_and_traversal_paths_leave_outside_unchanged(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        outside = tmp_path / "outside"
        root.mkdir()
        outside.mkdir()
        sentinel = outside / "sentinel.bin"
        sentinel.write_bytes(b"outside-original")
        before = _digest(sentinel)

        for vp_id in (str(outside), "../outside"):
            with pytest.raises((OSError, ValueError)):
                save_f5_result(_minimal_report(), root, vp_id=vp_id)

        assert _digest(sentinel) == before
        assert set(outside.iterdir()) == {sentinel}

    def test_child_symlink_is_never_followed(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        outside = tmp_path / "outside"
        root.mkdir()
        outside.mkdir()
        sentinel = outside / "sentinel.bin"
        sentinel.write_bytes(b"outside-original")
        (root / "VP-LINK").symlink_to(outside, target_is_directory=True)

        with pytest.raises((OSError, ValueError)):
            save_f5_result(_minimal_report(), root, vp_id="VP-LINK")

        assert set(outside.iterdir()) == {sentinel}
        assert sentinel.read_bytes() == b"outside-original"

    def test_child_file_is_never_replaced(self, tmp_path: Path) -> None:
        root = tmp_path / "root"
        root.mkdir()
        child = root / "VP-FILE"
        child.write_bytes(b"existing-child")

        with pytest.raises((OSError, ValueError)):
            save_f5_result(_minimal_report(), root, vp_id="VP-FILE")

        assert child.read_bytes() == b"existing-child"

    def test_authorized_root_symlink_is_resolved_once(self, tmp_path: Path) -> None:
        authorized = tmp_path / "authorized"
        authorized.mkdir()
        root_link = tmp_path / "root-link"
        root_link.symlink_to(authorized, target_is_directory=True)

        paths = save_f5_result(_minimal_report(), root_link, vp_id="VP-ROOT-LINK")

        assert set(paths) == {"markdown", "pdf", "fhir"}
        assert all(path.resolve().is_relative_to(authorized) for path in _all_paths(paths))

    def test_output_modes_are_owner_read_write_only(self, tmp_path: Path) -> None:
        paths = save_f5_result(_minimal_report(), tmp_path, vp_id="VP-MODE")

        assert {stat.S_IMODE(path.stat().st_mode) for path in _all_paths(paths)} == {0o600}


class TestExclusiveArtifactCreation:
    def test_identical_timestamp_uuid_collision_retries_full_uuid_group(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tokens = _UuidSequence([_TOKEN_A, _TOKEN_A, "b" * 32])
        _freeze_names(monkeypatch, tokens)
        report = _minimal_report()
        first = save_f5_result(report, tmp_path, vp_id="VP-COLLIDE")
        first_paths = _all_paths(first)
        first_hashes = tuple(_digest(path) for path in first_paths)

        second = save_f5_result(report, tmp_path, vp_id="VP-COLLIDE")

        assert set(first_paths).isdisjoint(_all_paths(second))
        assert all(_TOKEN_A in path.name for path in first_paths)
        assert all("b" * 32 in path.name for path in _all_paths(second))
        assert tuple(_digest(path) for path in first_paths) == first_hashes
        assert tokens.calls == 3

    def test_preexisting_final_name_collision_is_preserved_and_partial_reservation_cleaned(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vp_id = "VP-PARTIAL"
        vp_dir = tmp_path / vp_id
        vp_dir.mkdir()
        collision = vp_dir / _artifact_name(vp_id, _TOKEN_A, "handoff_fhir.json")
        collision.write_bytes(b"pre-existing-final")
        tokens = _UuidSequence([_TOKEN_A, "b" * 32])
        _freeze_names(monkeypatch, tokens)

        paths = save_f5_result(_minimal_report(), tmp_path, vp_id=vp_id)

        assert collision.read_bytes() == b"pre-existing-final"
        assert all("b" * 32 in path.name for path in _all_paths(paths))
        assert not (vp_dir / _artifact_name(vp_id, _TOKEN_A, "handoff.md")).exists()
        assert not (vp_dir / _artifact_name(vp_id, _TOKEN_A, "handoff.pdf")).exists()

    def test_collision_retry_is_bounded_at_100_and_preserves_prior_bytes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vp_id = "VP-EXHAUST"
        vp_dir = tmp_path / vp_id
        vp_dir.mkdir()
        collision = vp_dir / _artifact_name(vp_id, _TOKEN_A, "handoff.md")
        collision.write_bytes(b"pre-existing-final")
        token = _ConstantUuid(_TOKEN_A)
        _freeze_names(monkeypatch, token)

        with pytest.raises(FileExistsError):
            save_f5_result(_minimal_report(), tmp_path, vp_id=vp_id)

        assert token.calls == 100
        assert collision.read_bytes() == b"pre-existing-final"
        assert set(vp_dir.iterdir()) == {collision}

    def test_partial_write_failure_removes_only_this_invocations_names(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        vp_id = "VP-WRITE-FAIL"
        vp_dir = tmp_path / vp_id
        vp_dir.mkdir()
        prior = vp_dir / "prior_handoff.pdf"
        prior.write_bytes(b"prior-valid-pdf")
        before = {path.name: path.read_bytes() for path in vp_dir.iterdir()}
        real_write = artifact_store._write_content
        calls = 0

        def _fail_second_write(descriptor: int, content: bytes) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                os.write(descriptor, content[:5])
                raise OSError("simulated partial write")
            real_write(descriptor, content)

        monkeypatch.setattr(artifact_store, "_write_content", _fail_second_write)

        with pytest.raises(OSError, match="simulated partial write"):
            save_f5_result(_minimal_report(), tmp_path, vp_id=vp_id)

        assert {path.name: path.read_bytes() for path in vp_dir.iterdir()} == before

    def test_pdf_failure_log_is_constant_and_prior_pdf_survives(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        first = save_f5_result(_minimal_report(), tmp_path, vp_id="VP-PDF")
        prior_pdf = first.get("pdf")
        assert prior_pdf is not None
        prior_pdf_hash = _digest(prior_pdf)

        def _raise_secret(
            _report: HandoffReportOutput, _chart_paths: dict[str, Path]
        ) -> bytes:
            raise _ClinicalSentinelError("CLINICAL-SECRET-SENTINEL")

        monkeypatch.setattr(f5_report, "build_pdf_report", _raise_secret)
        second = save_f5_result(_minimal_report(), tmp_path, vp_id="VP-PDF")

        assert set(second) == {"markdown", "fhir"}
        assert _digest(prior_pdf) == prior_pdf_hash
        assert "CLINICAL-SECRET-SENTINEL" not in caplog.text
        assert all(record.exc_info is None for record in caplog.records)
        assert "pdf_status=failed" in caplog.text

    def test_success_log_contains_metrics_but_no_identifier_or_artifact_path(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        vp_sentinel = "CLINICAL-VP-SENTINEL"
        root = tmp_path / "CLINICAL-ROOT-SENTINEL"
        root.mkdir()
        caplog.set_level(logging.INFO, logger=f5_report.__name__)

        paths = save_f5_result(_minimal_report(), root, vp_id=vp_sentinel)

        forbidden = [vp_sentinel, root.name, str(root)]
        forbidden.extend(path.name for path in _all_paths(paths))
        forbidden.extend(str(path) for path in _all_paths(paths))
        assert all(value not in caplog.text for value in forbidden)
        assert "artifact_count=3" in caplog.text
        assert "pdf_status=saved" in caplog.text
        assert "markdown_bytes=" in caplog.text
        assert "fhir_bytes=" in caplog.text
        assert "pdf_bytes=" in caplog.text

    @pytest.mark.parametrize("failure_type", [KeyboardInterrupt, SystemExit])
    def test_persistence_pdf_boundary_propagates_system_exceptions(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        failure_type: type[KeyboardInterrupt] | type[SystemExit],
    ) -> None:
        def _raise_system_exception(
            _report: HandoffReportOutput, _chart_paths: dict[str, Path]
        ) -> bytes:
            raise failure_type

        monkeypatch.setattr(f5_report, "build_pdf_report", _raise_system_exception)

        with pytest.raises(failure_type):
            save_f5_result(_minimal_report(), tmp_path)
