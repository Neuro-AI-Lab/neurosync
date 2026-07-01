"""Issue #23: STT audio must be encrypted at rest, not written as plaintext.

DB-free: exercises store_audio() directly against a temp directory.
"""

from __future__ import annotations

import uuid

from src.core.config import Settings
from src.core.encryption import decrypt_bytes
from src.services.stt import store_audio


def test_store_audio_encrypts_at_rest(tmp_path) -> None:
    settings = Settings(audio_storage_dir=str(tmp_path))
    recording_id = uuid.uuid4()
    # A realistic Ogg/Opus payload prefix + body.
    plaintext = b"OggS" + bytes(range(256)) * 8

    path = store_audio(
        plaintext, recording_id=recording_id, encoding="opus", settings=settings
    )

    with open(path, "rb") as fh:
        on_disk = fh.read()

    # The raw plaintext audio must NOT be present on disk.
    assert on_disk != plaintext, "audio stored as PLAINTEXT on disk — not encrypted at rest"

    # And it must round-trip back to the original via the app encryption key + AAD.
    aad = f"audio_recordings.file:{recording_id}".encode()
    assert decrypt_bytes(on_disk, aad=aad, settings=settings) == plaintext
