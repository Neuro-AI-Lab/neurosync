"""Smoke test — SKT A.X STT Batch API on VP-XXX mp3 files.

Exercises the vendor API directly to verify:
  1. Batch pipeline (upload-token → upload → transcript) works end-to-end.
  2. Transcribed text matches the original patient utterances (patient_tts_index).

Usage:
    cd apps/ai-server
    .venv/bin/python -m tests.smoke_stt_skt              # defaults to VP-001
    .venv/bin/python -m tests.smoke_stt_skt --vp VP-002
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
SIM_ROOT = REPO_ROOT / "docs" / "ai" / "simulation_results"
TTS_INDEX = SIM_ROOT / "tts_scripts" / "patient_tts_index.json"

# ── SKT env — the .env uses SKT_A_X_K1, docs expect SKT_A_X_API_KEY ─────
# Accept both.
BASE_URL = "https://awf-gw.adot.ai"


def _get_api_key() -> str:
    for k in ("SKT_A_X_API_KEY", "SKT_A_X_K1"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def _upload(audio_bytes: bytes, api_key: str) -> str:
    """Upload audio → return file_key."""
    size = len(audio_bytes)

    # Step 1: token
    with httpx.Client(timeout=30.0) as client:
        r = client.get(
            f"{BASE_URL}/v1/stt/upload-token",
            params={"fileSize": size},
            headers={"X-API-Key": api_key},
        )
        r.raise_for_status()
        upload_token = r.json()["upload_token"]

    # Step 2: upload
    with httpx.Client(timeout=120.0) as client:
        r = client.put(
            f"{BASE_URL}/v1/stt/upload/{upload_token}",
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/octet-stream",
            },
            content=audio_bytes,
        )
        r.raise_for_status()
        return r.json()["file_key"]


def _transcript(file_key: str, api_key: str, message_id: str) -> dict:
    """Call transcript API → return raw response."""
    body = {
        "message_id": message_id,
        "speech_model": os.environ.get("SKT_A_X_STT_BATCH_MODEL", "A.X_STT_note_batch"),
        "audio_file_key": file_key,
        "keywords": ["우울감", "불면", "불안", "자살", "자해"],
        "agreement_of_data_collection": False,
    }
    with httpx.Client(timeout=180.0) as client:
        r = client.post(
            f"{BASE_URL}/v1/stt/transcript",
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
            json=body,
        )
        r.raise_for_status()
        return r.json()


def _extract_transcript_text(resp: dict) -> str:
    """Concatenate utterances[].text if present, else fall back to text field."""
    if "utterances" in resp and isinstance(resp["utterances"], list):
        return " ".join(u.get("text", "") for u in resp["utterances"]).strip()
    for key in ("text", "transcript"):
        if key in resp:
            return str(resp[key]).strip()
    return json.dumps(resp, ensure_ascii=False)[:300]


# ── Similarity utilities ─────────────────────────────────────────────

_NORMALIZE_RE = re.compile(r"[\s,.!?~…\"'()\[\]-]")


def _normalize(text: str) -> str:
    return _NORMALIZE_RE.sub("", text.replace("​", ""))


def _char_similarity(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na and not nb:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _word_similarity(a: str, b: str) -> float:
    ta = re.findall(r"\S+", a)
    tb = re.findall(r"\S+", b)
    if not ta and not tb:
        return 1.0
    return difflib.SequenceMatcher(None, ta, tb).ratio()


_SAFETY_MARKERS = (
    "죽고", "죽어", "자살", "자해", "살고 싶지", "사라지고 싶",
    "약을 많이 먹", "손목을 그",
)


def _safety_preserved(original: str, hypothesis: str) -> tuple[bool, list[str]]:
    orig_norm = _normalize(original)
    hyp_norm = _normalize(hypothesis)
    lost: list[str] = []
    for marker in _SAFETY_MARKERS:
        m_norm = _normalize(marker)
        if m_norm in orig_norm and m_norm not in hyp_norm:
            lost.append(marker)
    return len(lost) == 0, lost


# ── Main ────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="SKT A.X STT Batch smoke test")
    parser.add_argument("--vp", default="VP-001", help="Persona ID (VP-001~004)")
    args = parser.parse_args()
    vp_id: str = args.vp

    load_dotenv(REPO_ROOT / "apps" / "ai-server" / ".env")
    api_key = _get_api_key()
    if not api_key:
        print("[ERR] SKT API key not found (SKT_A_X_API_KEY or SKT_A_X_K1)", file=sys.stderr)
        return 1

    vp_dir = SIM_ROOT / vp_id

    # Load expected texts from TTS index (if available for this VP)
    expected_by_idx: dict[int, dict] = {}
    if TTS_INDEX.exists():
        idx = json.loads(TTS_INDEX.read_text(encoding="utf-8"))
        persona = idx["personas"].get(vp_id, {})
        utterances = persona.get("utterances", [])
        expected_by_idx = {u["utterance_index"]: u for u in utterances}

    audio_files = sorted(vp_dir.glob(f"{vp_id}-*.mp3"))
    if not audio_files:
        print(f"[ERR] no mp3 files in {vp_dir}", file=sys.stderr)
        return 1

    print(f"=== SKT A.X STT Batch Smoke Test — {vp_id} ===")
    print(f"API base:    {BASE_URL}")
    print(f"Batch model: {os.environ.get('SKT_A_X_STT_BATCH_MODEL', 'A.X_STT_note_batch')}")
    print(f"Audio files: {len(audio_files)}")
    print(f"Expected utterances: {len(expected_by_idx)}")
    print()

    file_re = re.compile(rf"{re.escape(vp_id)}-(\d{{3}})\.mp3")
    vp_slug = vp_id.lower().replace("-", "")

    results = []
    for path in audio_files:
        m = file_re.match(path.name)
        if not m:
            continue
        idx_num = int(m.group(1))
        expected = expected_by_idx.get(idx_num)
        expected_text = expected["full"] if expected else ""

        audio = path.read_bytes()
        message_id = f"{vp_slug}-smoke-{idx_num:03d}"

        print(f"[{path.name}] {len(audio):,} bytes")
        started = time.perf_counter()
        try:
            file_key = _upload(audio, api_key)
            resp = _transcript(file_key, api_key, message_id)
        except httpx.HTTPStatusError as exc:
            print(f"  ✗ HTTP {exc.response.status_code}: {exc.response.text[:300]}")
            continue
        except Exception as exc:
            print(f"  ✗ {type(exc).__name__}: {exc}")
            continue
        latency_ms = (time.perf_counter() - started) * 1000

        hyp = _extract_transcript_text(resp)
        char_sim = _char_similarity(expected_text, hyp)
        word_sim = _word_similarity(expected_text, hyp)
        safety_ok, lost = _safety_preserved(expected_text, hyp)

        print(f"  → transcribed ({latency_ms:.0f}ms)")
        print(f"  expected:  {expected_text[:200]}")
        print(f"  actual:    {hyp[:200]}")
        print(f"  char_sim:  {char_sim:.1%}  |  word_sim: {word_sim:.1%}")
        if not safety_ok:
            print(f"  ⚠️  safety markers lost: {lost}")
        else:
            print(f"  safety:   preserved")
        print()

        results.append({
            "file": path.name,
            "utterance_index": idx_num,
            "expected": expected_text,
            "hypothesis": hyp,
            "char_similarity": char_sim,
            "word_similarity": word_sim,
            "safety_preserved": safety_ok,
            "safety_lost": lost,
            "latency_ms": latency_ms,
            "raw": resp,
        })

    # Save
    out = vp_dir / f"{vp_id}_stt_smoke_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    if results:
        avg_char = sum(r["char_similarity"] for r in results) / len(results)
        avg_word = sum(r["word_similarity"] for r in results) / len(results)
        avg_lat = sum(r["latency_ms"] for r in results) / len(results)
        n_safety_lost = sum(1 for r in results if not r["safety_preserved"])
        print("=== Summary ===")
        print(f"  files:            {len(results)}/{len(audio_files)}")
        print(f"  avg char_sim:     {avg_char:.1%}")
        print(f"  avg word_sim:     {avg_word:.1%}")
        print(f"  avg latency:      {avg_lat:.0f}ms")
        print(f"  safety loss:      {n_safety_lost}/{len(results)}")
        print(f"  saved:            {out.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
