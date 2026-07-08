"""BUG-013 repro: `make dev-py`'s ai-server line changes directory into
`apps/ai-server` before launching uvicorn (`Makefile:38`, `cd apps/ai-server &&
uv run uvicorn src.main:app --reload --port 8001`), so the FastAPI process's
cwd is `apps/ai-server`, not the repo root — while `Settings.prompts_base_dir`
defaults to the *relative* path `"docs/ai/prompts"`, documented (both in
`config.py`'s own docstring and in `docs/dev-environment.md` §5.1(b)) as
"repo-root-relative". `PromptLoader`/`Settings.resolve_prompts_dir()` never
anchor this relative path to the project root the way `f1.py`/`f2.py`/
`safety_matrix.py` do for their own `PROMPTS_BASE_DIR` auto-correction
(`f1.py:1341-1342`, `f2.py:473-474`, `safety_matrix.py:270-271`) — the FastAPI
app has no equivalent correction (this asymmetry is itself documented in
`docs/dev-environment.md` §5.1(b), citing the same three script line ranges).

Net effect: a developer who runs `make dev-py` (the exact command
`docs/dev-environment.md` §5.1(a) recommends as the "safer" way to start
ai-server locally, citing `Makefile:35-38`) and leaves `PROMPTS_BASE_DIR`
unset (which the same doc says is "usually fine to leave blank") gets a
`PromptLoader` pointed at `apps/ai-server/docs/ai/prompts` — a directory that
does not exist; the real prompts live at the repo root's `docs/ai/prompts`.
The failure is lazy (`PromptLoader.load_system_prompt` raises
`FileNotFoundError` only when a prompt-dependent endpoint is actually hit),
so the server starts cleanly and the gap is only discovered at request time.

This repro is code-level and deterministic (no live server, no LLM):
1. Confirms the `Makefile` `dev-py` target still `cd`s into `apps/ai-server`
   before invoking uvicorn for the ai-server line (the precondition for the
   bug; also guards against silent re-drift of `docs/dev-environment.md`'s
   `Makefile:35-38` citation, which currently describes this command as
   running "레포 루트에서" / "from the repo root").
2. Confirms `Settings()`'s default `prompts_base_dir`, resolved against a cwd
   of `apps/ai-server` (what `make dev-py` actually produces), does not
   exist, while the same default resolved against the real repo root does.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.config import Settings
from src.f1 import PROJECT_ROOT

MAKEFILE_PATH = PROJECT_ROOT / "Makefile"
AI_SERVER_DIR = PROJECT_ROOT / "apps" / "ai-server"


class TestBug013MakeDevPyCwdBreaksDefaultPromptsBaseDir:
    def test_makefile_dev_py_still_cds_into_ai_server_before_uvicorn(self) -> None:
        """Precondition: `make dev-py`'s ai-server line changes directory
        before running uvicorn, so the process cwd is `apps/ai-server`, not
        the repo root. If this line is ever changed to preserve repo-root
        cwd (e.g. `uv run --project apps/ai-server uvicorn ...` — NOT
        `--directory`, which itself chdirs prior to running the command per
        `uv run --help` and was empirically confirmed to do so during
        BUG-013 QA re-verification, 2026-07-08), this assertion should be
        updated/inverted and `docs/dev-environment.md` §5.1(a)'s "레포
        루트에서" characterization would then be accurate."""
        text = MAKEFILE_PATH.read_text(encoding="utf-8")
        dev_py_block = text.split("dev-py:", 1)[1].split("\ntest:", 1)[0]
        assert "cd apps/ai-server && uv run uvicorn src.main:app" in dev_py_block

    def test_default_prompts_base_dir_does_not_exist_from_ai_server_cwd(self) -> None:
        """Reproduces the bug: resolving the default `prompts_base_dir`
        against the cwd `make dev-py` actually launches ai-server with
        (`apps/ai-server`, per the precondition test above) points at a
        directory that does not exist."""
        settings = Settings()
        assert settings.prompts_base_dir == "docs/ai/prompts"

        cwd = os.getcwd()
        try:
            os.chdir(AI_SERVER_DIR)
            resolved_under_dev_py_cwd = settings.resolve_prompts_dir().resolve()
        finally:
            os.chdir(cwd)

        assert resolved_under_dev_py_cwd == AI_SERVER_DIR / "docs" / "ai" / "prompts"
        assert not resolved_under_dev_py_cwd.exists()

    def test_default_prompts_base_dir_exists_from_repo_root_cwd(self) -> None:
        """Contrast case: the same default *does* resolve correctly if the
        process cwd is the repo root — confirming the defect is specifically
        about `make dev-py`'s cwd, not a broken default path in general."""
        settings = Settings()

        cwd = os.getcwd()
        try:
            os.chdir(PROJECT_ROOT)
            resolved_under_repo_root_cwd = settings.resolve_prompts_dir().resolve()
        finally:
            os.chdir(cwd)

        assert resolved_under_repo_root_cwd == PROJECT_ROOT / "docs" / "ai" / "prompts"
        assert resolved_under_repo_root_cwd.exists()
        assert resolved_under_repo_root_cwd.is_dir()

    def test_project_root_sanity(self) -> None:
        """Sanity check that PROJECT_ROOT (imported from f1.py, reused here
        rather than re-derived) actually points at the repo root and not
        somewhere else — protects the other assertions in this file from a
        silently-wrong shared fixture."""
        assert (PROJECT_ROOT / "Makefile").is_file()
        assert (PROJECT_ROOT / "apps" / "ai-server" / "pyproject.toml").is_file()
        assert Path(PROJECT_ROOT / "docs" / "ai" / "prompts").is_dir()
