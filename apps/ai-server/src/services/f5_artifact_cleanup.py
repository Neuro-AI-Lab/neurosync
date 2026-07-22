from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, override

type ArtifactKey = Literal["markdown", "pdf", "fhir"]


@dataclass(frozen=True, slots=True)
class ArtifactCleanupError(OSError):
    failure_count: int

    @override
    def __str__(self) -> str:
        return f"F5 artifact cleanup failed: failure_count={self.failure_count}"


@dataclass(frozen=True, slots=True)
class ReservedArtifact:
    key: ArtifactKey
    name: str
    content: bytes
    descriptor: int


def _unlink_first_pass(vp_descriptor: int, reserved: list[ReservedArtifact]) -> list[str]:
    retry_names: list[str] = []
    for artifact in reserved:
        try:
            os.unlink(artifact.name, dir_fd=vp_descriptor)
        except FileNotFoundError:
            pass
        except OSError:
            retry_names.append(artifact.name)
    return retry_names


def _retry_unlinks(vp_descriptor: int, names: list[str]) -> int:
    failure_count = 0
    for name in names:
        try:
            os.unlink(name, dir_fd=vp_descriptor)
        except FileNotFoundError:
            pass
        except OSError:
            failure_count += 1
    return failure_count


def _close_all(reserved: list[ReservedArtifact]) -> int:
    failure_count = 0
    for artifact in reserved:
        try:
            os.close(artifact.descriptor)
        except OSError:
            failure_count += 1
    return failure_count


def discard_reserved(vp_descriptor: int, reserved: list[ReservedArtifact]) -> None:
    retry_names = _unlink_first_pass(vp_descriptor, reserved)
    failure_count = _close_all(reserved)
    failure_count += _retry_unlinks(vp_descriptor, retry_names)
    if failure_count:
        raise ArtifactCleanupError(failure_count) from None


def close_completed(vp_descriptor: int, reserved: list[ReservedArtifact]) -> None:
    failure_count = _close_all(reserved)
    if not failure_count:
        return
    retry_names = _unlink_first_pass(vp_descriptor, reserved)
    failure_count += _retry_unlinks(vp_descriptor, retry_names)
    raise ArtifactCleanupError(failure_count) from None


def discard_after_primary(
    vp_descriptor: int,
    reserved: list[ReservedArtifact],
    primary: BaseException,
) -> None:
    try:
        discard_reserved(vp_descriptor, reserved)
    except ArtifactCleanupError as cleanup_error:
        primary.add_note(
            f"F5 artifact cleanup failed: failure_count={cleanup_error.failure_count}"
        )
