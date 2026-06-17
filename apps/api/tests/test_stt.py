"""Unit tests for STT audio validation (no DB). FR-033."""

from __future__ import annotations

import pytest

from src.core.config import Settings
from src.services.stt import STTError, validate_audio

_SETTINGS = Settings()


def _wav(payload: bytes = b"\x00" * 32) -> bytes:
    return b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + payload


def _ogg(payload: bytes = b"\x00" * 32) -> bytes:
    return b"OggS" + payload


def test_valid_opus_passes() -> None:
    validate_audio(_ogg(), "opus", settings=_SETTINGS)


def test_valid_wav_passes() -> None:
    validate_audio(_wav(), "pcm16", settings=_SETTINGS)


def test_empty_rejected() -> None:
    with pytest.raises(STTError) as exc:
        validate_audio(b"", "opus", settings=_SETTINGS)
    assert exc.value.code == "INVALID_AUDIO"
    assert exc.value.http_status == 400


def test_too_large_rejected() -> None:
    big = _ogg(b"\x00" * (_SETTINGS.audio_max_bytes + 1))
    with pytest.raises(STTError) as exc:
        validate_audio(big, "opus", settings=_SETTINGS)
    assert exc.value.code == "AUDIO_TOO_LARGE"
    assert exc.value.http_status == 413


def test_wrong_magic_opus_rejected() -> None:
    with pytest.raises(STTError) as exc:
        validate_audio(b"NOTOGG" + b"\x00" * 20, "opus", settings=_SETTINGS)
    assert exc.value.code == "INVALID_AUDIO"


def test_wrong_magic_wav_rejected() -> None:
    # RIFF present but WAVE tag missing.
    bad = b"RIFF" + b"\x00\x00\x00\x00" + b"AVI " + b"\x00" * 20
    with pytest.raises(STTError) as exc:
        validate_audio(bad, "pcm16", settings=_SETTINGS)
    assert exc.value.code == "INVALID_AUDIO"


def test_unknown_encoding_rejected() -> None:
    with pytest.raises(STTError) as exc:
        validate_audio(_ogg(), "mp3", settings=_SETTINGS)
    assert exc.value.code == "INVALID_AUDIO"
