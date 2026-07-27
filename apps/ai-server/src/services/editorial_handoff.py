"""Editorial handoff PDF renderer — integrates the `docs/ai/handoff_template`
editorial report into the F5 pipeline as an official secondary output.

F5 already emits `<prefix>_handoff.{md,pdf,fhir.json}` (reportlab). This module
turns those same artifacts into the editorial (HTML → Chrome print) PDF:

    F5 artifacts (temporal.json + handoff.md, on disk)
       → build_report_json.py   (report JSON, fixed data contract)
       → make_charts.py         (FIG.01/02/03 via trend_plotter)
       → Chrome --headless --print-to-pdf (index.html?p=<vp>)
       → <prefix>_handoff_editorial.pdf

It is DEPENDENCY-TOLERANT: if Chrome, matplotlib, or the template dir is
unavailable (e.g. a headless production box without a browser), it logs a
warning and returns None — never raises, so F5 save never breaks.
"""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_CHROME_NAMES = ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser")


def _repo_root() -> Path:
    # .../neurosync/apps/ai-server/src/services/editorial_handoff.py → neurosync
    return Path(__file__).resolve().parents[4]


def _template_dir() -> Path:
    return _repo_root() / "docs" / "ai" / "handoff_template"


def _find_chrome() -> str | None:
    for name in _CHROME_NAMES:
        p = shutil.which(name)
        if p:
            return p
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port: int, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def render_editorial_handoff(vp_id: str, out_pdf: Path) -> Path | None:
    """Render the editorial handoff PDF for ``vp_id`` to ``out_pdf``.

    Reads the latest on-disk F1–F5 artifacts (via the template's
    build_report_json), renders charts, and prints the HTML template to PDF.
    Returns ``out_pdf`` on success, or ``None`` if any dependency is missing
    (logged, never raised)."""
    tpl = _template_dir()
    if not (tpl / "index.html").exists():
        logger.warning("editorial handoff skipped: template not found at %s", tpl)
        return None
    chrome = _find_chrome()
    if not chrome:
        logger.warning("editorial handoff skipped: no Chrome/Chromium on PATH")
        return None

    py = sys.executable
    try:
        # 1) F5/F4 artifacts → report JSON (fixed data contract)
        subprocess.run([py, "scripts/build_report_json.py", vp_id],
                       cwd=tpl, check=True, capture_output=True, timeout=90)
        report_json = tpl / "data" / f"report-{vp_id}.json"
        if not report_json.exists():
            logger.warning("editorial handoff skipped: %s not produced", report_json.name)
            return None
        # 2) charts via trend_plotter
        subprocess.run([py, "scripts/make_charts.py", f"data/report-{vp_id}.json"],
                       cwd=tpl, check=True, capture_output=True, timeout=180)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", b"")
        logger.warning("editorial handoff skipped: build/charts failed: %s | %s",
                       exc, (detail[-400:].decode("utf-8", "replace") if detail else ""))
        return None

    # 3) serve template + Chrome print-to-pdf
    port = _free_port()
    server = subprocess.Popen(
        [py, "-m", "http.server", str(port)], cwd=tpl,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _wait_port(port):
            logger.warning("editorial handoff skipped: local http server did not start")
            return None
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
             "--no-pdf-header-footer", "--virtual-time-budget=12000",
             f"--print-to-pdf={out_pdf}", f"http://127.0.0.1:{port}/index.html?p={vp_id}"],
            check=True, capture_output=True, timeout=90)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning("editorial handoff skipped: Chrome render failed: %s", exc)
        return None
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    if out_pdf.exists() and out_pdf.stat().st_size > 0:
        logger.info("editorial handoff PDF written: %s", out_pdf)
        return out_pdf
    logger.warning("editorial handoff skipped: output PDF empty/missing")
    return None
