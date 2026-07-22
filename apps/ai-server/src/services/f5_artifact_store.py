"""POSIX-only, descriptor-relative persistence for one F5 artifact group.

The caller-authorized root may itself be a symlink: it is resolved exactly
once before opening. VP children and artifact leaves are always opened relative
to retained directory descriptors with no-follow semantics. Each service-owned
VP namespace is mode 0700 and exclusively locked while names can change.
"""

from __future__ import annotations

import fcntl
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NotRequired, TypedDict, override

from src.services.f5_artifact_cleanup import (
    ArtifactCleanupError,
    ArtifactKey,
    ReservedArtifact,
    close_completed,
    discard_after_primary,
    discard_reserved,
)

_MAX_GROUP_ATTEMPTS: Final = 100
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS: Final = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC


@dataclass(frozen=True, slots=True)
class InvalidVpIdError(ValueError):
    """The requested VP directory is not one safe relative component."""

    @override
    def __str__(self) -> str:
        return "vp_id must be one nonempty relative path component"


@dataclass(frozen=True, slots=True)
class ArtifactCollisionError(FileExistsError):
    """Every bounded artifact-group reservation attempt collided."""

    attempts: int

    @override
    def __str__(self) -> str:
        return "unable to reserve a unique F5 artifact group"


@dataclass(frozen=True, slots=True)
class F5ArtifactBundle:
    """Fully rendered bytes and identity for one atomic-name group."""

    vp_id: str
    timestamp: str
    markdown: bytes
    fhir: bytes
    pdf: bytes | None


class F5ArtifactPaths(TypedDict):
    markdown: Path
    fhir: Path
    pdf: NotRequired[Path]


def _validated_vp_id(raw: str) -> str:
    separators = {"/", "\\", os.sep}
    if os.altsep is not None:
        separators.add(os.altsep)
    if (
        not raw
        or raw in {".", ".."}
        or Path(raw).is_absolute()
        or any(separator in raw for separator in separators)
    ):
        raise InvalidVpIdError
    return raw


def _write_content(descriptor: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(descriptor, remaining)
        remaining = remaining[written:]


def _reserve_group(vp_descriptor: int, bundle: F5ArtifactBundle) -> list[ReservedArtifact]:
    artifacts: list[tuple[ArtifactKey, str, bytes]] = [
        ("markdown", "handoff.md", bundle.markdown),
        ("fhir", "handoff_fhir.json", bundle.fhir),
    ]
    if bundle.pdf is not None:
        artifacts.insert(1, ("pdf", "handoff.pdf", bundle.pdf))
    for _attempt in range(_MAX_GROUP_ATTEMPTS):
        prefix = f"{bundle.vp_id}_{bundle.timestamp}_{uuid.uuid4().hex}"
        reserved: list[ReservedArtifact] = []
        try:
            for key, suffix, content in artifacts:
                name = f"{prefix}_{suffix}"
                descriptor = os.open(name, _FILE_FLAGS, 0o600, dir_fd=vp_descriptor)
                reserved.append(ReservedArtifact(key, name, content, descriptor))
                os.fchmod(descriptor, 0o600)
        except FileExistsError:
            try:
                discard_reserved(vp_descriptor, reserved)
            except ArtifactCleanupError:
                raise
            continue
        except BaseException as primary:
            discard_after_primary(vp_descriptor, reserved, primary)
            raise
        return reserved
    raise ArtifactCollisionError(attempts=_MAX_GROUP_ATTEMPTS)


def _open_vp_directory(root_descriptor: int, vp_id: str) -> int:
    try:
        os.mkdir(vp_id, 0o700, dir_fd=root_descriptor)
    except FileExistsError:
        descriptor = os.open(vp_id, _DIRECTORY_FLAGS, dir_fd=root_descriptor)
    else:
        descriptor = os.open(vp_id, _DIRECTORY_FLAGS, dir_fd=root_descriptor)
    try:
        os.fchmod(descriptor, 0o700)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except OSError:
        os.close(descriptor)
        raise
    return descriptor


def persist_f5_artifacts(root: Path, bundle: F5ArtifactBundle) -> F5ArtifactPaths:
    """Persist one collision-proof group beneath an authorized output root."""
    vp_id = _validated_vp_id(bundle.vp_id)
    root.mkdir(parents=True, exist_ok=True)
    authorized_root = root.resolve(strict=True)
    root_descriptor = os.open(authorized_root, _DIRECTORY_FLAGS)
    try:
        vp_descriptor = _open_vp_directory(root_descriptor, vp_id)
        try:
            reserved = _reserve_group(vp_descriptor, bundle)
            try:
                for artifact in reserved:
                    _write_content(artifact.descriptor, artifact.content)
            except BaseException as primary:
                discard_after_primary(vp_descriptor, reserved, primary)
                raise
            close_completed(vp_descriptor, reserved)
        finally:
            os.close(vp_descriptor)
    finally:
        os.close(root_descriptor)

    output_dir = authorized_root / vp_id
    names = {artifact.key: artifact.name for artifact in reserved}
    paths = F5ArtifactPaths(
        markdown=output_dir / names["markdown"],
        fhir=output_dir / names["fhir"],
    )
    if "pdf" in names:
        paths["pdf"] = output_dir / names["pdf"]
    return paths
