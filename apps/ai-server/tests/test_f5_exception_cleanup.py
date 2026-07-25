from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

import src.services.f5_artifact_cleanup as artifact_cleanup
import src.services.f5_artifact_store as artifact_store
from src.services.f5_artifact_cleanup import ArtifactCleanupError, ReservedArtifact


def _reserved_group(vp_dir: Path) -> tuple[int, list[ReservedArtifact]]:
    vp_descriptor = os.open(vp_dir, os.O_RDONLY | os.O_DIRECTORY)
    names = ("first.md", "second.pdf", "third.json")
    descriptors = [
        os.open(vp_dir / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        for name in names
    ]
    reserved = [
        ReservedArtifact(key, name, b"payload", descriptor)
        for key, name, descriptor in zip(
            ("markdown", "pdf", "fhir"), names, descriptors, strict=True
        )
    ]
    return vp_descriptor, reserved


def test_failed_unlink_is_retried_after_every_descriptor_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vp_dir = tmp_path / "VP-CLEANUP"
    vp_dir.mkdir()
    vp_descriptor, reserved = _reserved_group(vp_dir)
    real_unlink = os.unlink
    real_close = os.close
    events: list[tuple[str, str | int]] = []
    failed_once = False

    def _transient_unlink(name: str, *, dir_fd: int) -> None:
        nonlocal failed_once
        events.append(("unlink", name))
        if name == "first.md" and not failed_once:
            failed_once = True
            raise OSError("private unlink sentinel")
        real_unlink(name, dir_fd=dir_fd)

    def _tracked_close(descriptor: int) -> None:
        events.append(("close", descriptor))
        real_close(descriptor)

    monkeypatch.setattr(os, "unlink", _transient_unlink)
    monkeypatch.setattr(os, "close", _tracked_close)
    try:
        artifact_cleanup.discard_reserved(vp_descriptor, reserved)
    finally:
        real_close(vp_descriptor)

    retry_index = max(
        index for index, event in enumerate(events) if event == ("unlink", "first.md")
    )
    close_indexes = [index for index, event in enumerate(events) if event[0] == "close"]
    assert close_indexes and max(close_indexes) < retry_index
    assert list(vp_dir.iterdir()) == []


def test_cleanup_attempts_all_resources_and_raises_content_free_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vp_dir = tmp_path / "CLINICAL-PATH-SENTINEL"
    vp_dir.mkdir()
    vp_descriptor, reserved = _reserved_group(vp_dir)
    real_close = os.close
    calls: list[int] = []

    def _close_then_fail_first(descriptor: int) -> None:
        calls.append(descriptor)
        real_close(descriptor)
        if len(calls) == 1:
            raise OSError("CLINICAL-CLOSE-SENTINEL")

    monkeypatch.setattr(os, "close", _close_then_fail_first)
    try:
        with pytest.raises(ArtifactCleanupError) as raised:
            artifact_cleanup.discard_reserved(vp_descriptor, reserved)
    finally:
        real_close(vp_descriptor)

    assert len(calls) == len(reserved)
    assert list(vp_dir.iterdir()) == []
    assert str(raised.value) == "F5 artifact cleanup failed: failure_count=1"
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None


def test_primary_write_failure_is_preserved_with_count_only_cleanup_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = artifact_store.F5ArtifactBundle(
        vp_id="VP-PRIMARY",
        timestamp="20260722_120000",
        markdown=b"md",
        pdf=b"pdf",
        fhir=b"fhir",
    )
    primary = OSError("CLINICAL-WRITE-SENTINEL")
    real_close = os.close
    failed_close = False

    def _fail_write(_descriptor: int, _content: memoryview) -> int:
        raise primary

    def _close_then_fail_once(descriptor: int) -> None:
        nonlocal failed_close
        real_close(descriptor)
        if not failed_close:
            failed_close = True
            raise OSError("CLINICAL-CLOSE-SENTINEL")

    monkeypatch.setattr(os, "write", _fail_write)
    monkeypatch.setattr(os, "close", _close_then_fail_once)

    with pytest.raises(OSError) as raised:
        _ = artifact_store.persist_f5_artifacts(tmp_path, bundle)

    assert raised.value is primary
    assert raised.value.__notes__ == ["F5 artifact cleanup failed: failure_count=1"]
    assert list((tmp_path / bundle.vp_id).iterdir()) == []


def test_success_path_close_failure_removes_group_and_raises_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = artifact_store.F5ArtifactBundle(
        vp_id="VP-CLOSE",
        timestamp="20260722_120000",
        markdown=b"md",
        pdf=b"pdf",
        fhir=b"fhir",
    )
    real_close = os.close
    real_unlink = os.unlink
    failed_regular_close = False
    failed_unlink = False

    def _close_then_fail_regular_file(descriptor: int) -> None:
        nonlocal failed_regular_close
        is_regular = os.path.isfile(f"/dev/fd/{descriptor}")
        real_close(descriptor)
        if is_regular and not failed_regular_close:
            failed_regular_close = True
            raise OSError("CLINICAL-CLOSE-SENTINEL")

    def _fail_first_unlink_once(name: str, *, dir_fd: int) -> None:
        nonlocal failed_unlink
        if not failed_unlink:
            failed_unlink = True
            raise OSError("CLINICAL-UNLINK-SENTINEL")
        real_unlink(name, dir_fd=dir_fd)

    monkeypatch.setattr(os, "close", _close_then_fail_regular_file)
    monkeypatch.setattr(os, "unlink", _fail_first_unlink_once)

    with pytest.raises(ArtifactCleanupError) as raised:
        _ = artifact_store.persist_f5_artifacts(tmp_path, bundle)

    assert raised.value.failure_count == 1
    assert list((tmp_path / bundle.vp_id).iterdir()) == []


def test_write_base_exception_propagates_after_owned_files_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = artifact_store.F5ArtifactBundle(
        vp_id="VP-BASE",
        timestamp="20260722_120000",
        markdown=b"md",
        pdf=None,
        fhir=b"fhir",
    )

    def _interrupt(_descriptor: int, _content: memoryview) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "write", _interrupt)

    with pytest.raises(KeyboardInterrupt):
        _ = artifact_store.persist_f5_artifacts(tmp_path, bundle)

    assert list((tmp_path / bundle.vp_id).iterdir()) == []


def test_collision_cleanup_failure_aborts_without_overwriting_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = uuid.UUID(hex="a" * 32)
    bundle = artifact_store.F5ArtifactBundle(
        vp_id="VP-COLLISION",
        timestamp="20260722_120000",
        markdown=b"md",
        pdf=b"pdf",
        fhir=b"fhir",
    )
    prefix = f"{bundle.vp_id}_{bundle.timestamp}_{token.hex}"
    vp_dir = tmp_path / bundle.vp_id
    vp_dir.mkdir()
    collision = vp_dir / f"{prefix}_handoff_fhir.json"
    _ = collision.write_bytes(b"existing")
    real_unlink = os.unlink

    def _persistent_markdown_unlink(name: str, *, dir_fd: int) -> None:
        if name.endswith("_handoff.md"):
            raise OSError("CLINICAL-UNLINK-SENTINEL")
        real_unlink(name, dir_fd=dir_fd)

    monkeypatch.setattr(uuid, "uuid4", lambda: token)
    monkeypatch.setattr(os, "unlink", _persistent_markdown_unlink)
    try:
        with pytest.raises(ArtifactCleanupError) as raised:
            _ = artifact_store.persist_f5_artifacts(tmp_path, bundle)
    finally:
        _ = real_unlink(vp_dir / f"{prefix}_handoff.md")

    assert collision.read_bytes() == b"existing"
    assert set(vp_dir.iterdir()) == {collision}
    assert str(raised.value) == "F5 artifact cleanup failed: failure_count=1"
    assert "CLINICAL-UNLINK-SENTINEL" not in str(raised.value)
