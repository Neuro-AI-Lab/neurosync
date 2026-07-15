"""BUG-024 fix verification: `tests/smoke_stt_skt.py`'s results-save step
must create its own per-VP output directory on demand.

`tests/smoke_stt_skt.py` is a standalone manual devtool (0 pytest collection
hits, confirmed — `grep -n "def test_\\|class Test" tests/smoke_stt_skt.py`),
invoked directly by a developer against live SKT STT credentials, so this
repro cannot (and per BUG-024's own charter should not) drive `main()`
end-to-end. It instead verifies, at the source level, that the fix — a
`vp_dir.mkdir(parents=True, exist_ok=True)` call immediately before the
results `write_text` — is actually present (not merely proposed), and
separately replicates the exact BUG-024 step-4 repro command through the
FIXED save pattern to prove it no longer raises `FileNotFoundError` against
a genuinely non-pre-existing directory (the post-`f478719`-archive-move
condition BUG-024 describes).
"""

from __future__ import annotations

import re
from pathlib import Path

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "smoke_stt_skt.py"
)


def test_mkdir_precedes_results_write_in_source() -> None:
    """Source-level regression: `vp_dir.mkdir(parents=True, exist_ok=True)`
    must appear before the `out.write_text(...)` results save (BUG-024's
    proposed fix, mirroring `f1.py`'s own `save_f1_result` convention)."""
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    mkdir_match = re.search(r"vp_dir\.mkdir\(parents=True,\s*exist_ok=True\)", source)
    write_match = re.search(r"out\s*=\s*vp_dir\s*/.*stt_smoke_results\.json", source)
    assert mkdir_match is not None, "vp_dir.mkdir(parents=True, exist_ok=True) not found"
    assert write_match is not None, "results out= assignment not found"
    assert mkdir_match.start() < write_match.start(), (
        "mkdir must precede the results save path construction/write"
    )


def test_fixed_save_pattern_succeeds_against_nonexistent_dir(tmp_path) -> None:
    """Functional replication of BUG-024's own step-4 repro, through the
    FIXED pattern — a genuinely non-pre-existing `vp_dir` (the post-archive
    condition) no longer raises FileNotFoundError once `mkdir` runs first."""
    sim_root = tmp_path / "simulation_results"  # deliberately does not exist
    vp_dir = sim_root / "VP-001"
    assert not vp_dir.exists()

    vp_dir.mkdir(parents=True, exist_ok=True)
    out = vp_dir / "VP-001_stt_smoke_results.json"
    out.write_text("[]", encoding="utf-8")

    assert out.exists()
    assert out.read_text(encoding="utf-8") == "[]"
