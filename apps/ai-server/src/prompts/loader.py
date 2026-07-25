"""Prompt template loader — reads system prompts and JSON schemas from disk."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def resolve_prompts_base_dir(project_root: str | Path) -> Path:
    """Resolve ``PROMPTS_BASE_DIR`` for a CLI entry point, failing fast (BUG-021).

    Replaces the old unset-only guard (``if not os.environ.get(...)``) shared
    by ``f1.py``/``f2.py``/``safety_matrix.py``/``continuous_test.py``, which
    only ever corrected a *missing* value — an explicit-but-wrong value (e.g.
    a repo-root-relative ``.env`` value read from a cwd that isn't the repo
    root) silently passed through, and every prompt-driven agent then
    degraded to its generic hardcoded fallback prompt with no hard failure.

    ADR-041 T4 addendum: prompts moved from repo-root ``docs/ai/prompts/`` to
    the deploy unit, ``apps/ai-server/prompts/``.

    Resolution order:
      1. Unset -> default to ``{project_root}/apps/ai-server/prompts``.
      2. Set and resolves (as given — absolute, or relative to the current
         working directory) to an existing directory -> used as-is.
      3. Set but does not resolve from the cwd -> re-anchored against
         *project_root* (recovers the documented failure mode: a repo-root-
         relative ``.env`` value read while cwd is ``apps/ai-server`` or a
         worktree copy).
      4. Still does not resolve -> ``RuntimeError`` — no caller may fall
         through to a silently degraded run.

    On success, ``os.environ["PROMPTS_BASE_DIR"]`` is rewritten to the
    resolved absolute path so every later ``Settings()``/``PromptLoader``
    construction in this process sees the corrected value.

    Raises:
        RuntimeError: If no candidate resolves to an existing directory.
    """
    root = Path(project_root)
    raw = os.environ.get("PROMPTS_BASE_DIR")
    attempted: list[Path] = []
    default_dir = root / "apps" / "ai-server" / "prompts"

    if raw:
        candidate = Path(raw)
        attempted.append(candidate.resolve())
        if not candidate.is_dir():
            candidate = root / raw
            attempted.append(candidate.resolve())
    else:
        candidate = default_dir
        attempted.append(candidate.resolve())

    if not candidate.is_dir():
        tried = " or ".join(str(p) for p in attempted)
        raise RuntimeError(
            f"PROMPTS_BASE_DIR does not resolve to an existing directory "
            f"(tried: {tried}). Every prompt-driven agent would otherwise "
            "silently fall back to a generic hardcoded prompt with no hard "
            "failure (BUG-021) — fix PROMPTS_BASE_DIR in .env, or unset it "
            f"to use the default ({default_dir})."
        )

    resolved = candidate.resolve()
    os.environ["PROMPTS_BASE_DIR"] = str(resolved)
    return resolved


class PromptLoader:
    """Loads prompt templates from the filesystem.

    Directory layout expected::

        {base_dir}/{agent_name}/{version}.system.md
        {base_dir}/{agent_name}/{version}.schema.json   (optional)
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)

    def load_system_prompt(self, agent_name: str, version: str = "v1") -> str:
        """Read the system prompt markdown for *agent_name* at *version*.

        Returns:
            The raw markdown content.

        Raises:
            FileNotFoundError: If the prompt file does not exist.
        """
        path = self._base_dir / agent_name / f"{version}.system.md"
        if not path.exists():
            raise FileNotFoundError(
                f"System prompt not found: {path} "
                f"(base_dir={self._base_dir}, agent={agent_name}, version={version})"
            )
        content = path.read_text(encoding="utf-8")
        logger.debug("Loaded system prompt %s/%s (%d chars)", agent_name, version, len(content))
        return content

    def load_schema(self, agent_name: str, version: str = "v1") -> dict[str, Any] | None:
        """Read an optional JSON schema for *agent_name* at *version*.

        Returns:
            Parsed JSON dict, or None if the file does not exist.
        """
        path = self._base_dir / agent_name / f"{version}.schema.json"
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8")
        schema = json.loads(content)
        logger.debug("Loaded schema %s/%s", agent_name, version)
        return schema

    def prompt_exists(self, agent_name: str, version: str = "v1") -> bool:
        """Check whether a system prompt exists without loading it."""
        path = self._base_dir / agent_name / f"{version}.system.md"
        return path.exists()
