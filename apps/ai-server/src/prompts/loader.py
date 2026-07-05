"""Prompt template loader — reads system prompts and JSON schemas from disk."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
