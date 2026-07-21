"""Concurrency contract for one service-owned VP artifact namespace."""

from __future__ import annotations

import fcntl
import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import src.services.f5_artifact_store as artifact_store
from src.services.f5_artifact_store import F5ArtifactBundle, persist_f5_artifacts


def _bundle(marker: bytes) -> F5ArtifactBundle:
    return F5ArtifactBundle(
        vp_id="VP-LOCK",
        timestamp="20260102_030405",
        markdown=marker,
        fhir=marker,
        pdf=marker,
    )


def test_vp_namespace_lock_serializes_service_writers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_write_entered = threading.Event()
    release_first_write = threading.Event()
    second_open_started = threading.Event()
    real_open = artifact_store._open_vp_directory
    real_write = artifact_store._write_content
    first_thread_id: int | None = None

    def _tracked_open(root_descriptor: int, vp_id: str) -> int:
        nonlocal first_thread_id
        thread_id = threading.get_ident()
        if first_thread_id is None:
            first_thread_id = thread_id
        elif thread_id != first_thread_id:
            second_open_started.set()
        return real_open(root_descriptor, vp_id)

    def _blocking_write(descriptor: int, content: bytes) -> None:
        if threading.get_ident() == first_thread_id and not first_write_entered.is_set():
            first_write_entered.set()
            assert release_first_write.wait(timeout=5)
        real_write(descriptor, content)

    monkeypatch.setattr(artifact_store, "_open_vp_directory", _tracked_open)
    monkeypatch.setattr(artifact_store, "_write_content", _blocking_write)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(persist_f5_artifacts, tmp_path, _bundle(b"first"))
        assert first_write_entered.wait(timeout=5)

        probe_descriptor = os.open(
            tmp_path / "VP-LOCK",
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
        )
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(probe_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(probe_descriptor)

        second = executor.submit(persist_f5_artifacts, tmp_path, _bundle(b"second"))
        assert second_open_started.wait(timeout=5)
        release_first_write.set()
        first_paths = first.result(timeout=5)
        second_paths = second.result(timeout=5)

    probe_descriptor = os.open(
        tmp_path / "VP-LOCK",
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
    )
    try:
        fcntl.flock(probe_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(probe_descriptor)

    first_pdf = first_paths.get("pdf")
    second_pdf = second_paths.get("pdf")
    assert first_pdf is not None
    assert second_pdf is not None
    first_group = {first_paths["markdown"], first_pdf, first_paths["fhir"]}
    second_group = {second_paths["markdown"], second_pdf, second_paths["fhir"]}
    assert first_group.isdisjoint(second_group)
    assert stat.S_IMODE((tmp_path / "VP-LOCK").stat().st_mode) == 0o700
