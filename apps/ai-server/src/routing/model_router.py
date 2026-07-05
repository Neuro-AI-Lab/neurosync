"""Model router — selects adapter/model per agent based on registry + fallback policy."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from src.adapters.base import VendorAdapter
from src.routing.fallback_policy import FallbackPolicy
from src.schemas.common import ModelSelection, RiskLevel

logger = logging.getLogger(__name__)

_TIER_ORDER = ("primary", "secondary", "fallback")


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR_NAME} placeholders with environment variable values."""

    def _replacer(match: re.Match[str]) -> str:
        var = match.group(1)
        return os.environ.get(var, match.group(0))

    return re.sub(r"\$\{(\w+)}", _replacer, value)


class ModelRouter:
    """Routes agent requests to the appropriate LLM adapter/model.

    Loads agent_model_registry.yaml and provides:
    - ``select_model()`` — pick the best adapter for an agent
    - ``get_fallback()`` — pick the next tier after a failure
    - ``get_adapter()`` — retrieve the adapter instance
    """

    def __init__(self, registry_path: str | Path) -> None:
        self._registry_path = Path(registry_path)
        self._registry: dict[str, Any] = {}
        self._adapters: dict[str, VendorAdapter] = {}
        self._fallback_policy = FallbackPolicy()
        self._load_registry()

    def _load_registry(self) -> None:
        if not self._registry_path.exists():
            raise FileNotFoundError(f"Registry not found: {self._registry_path}")
        with open(self._registry_path) as f:
            raw = yaml.safe_load(f)
        self._registry = raw.get("agents", {})
        logger.info("Loaded model registry with %d agents", len(self._registry))

    def register_adapters(self, adapters: dict[str, VendorAdapter]) -> None:
        """Register adapter instances by name (e.g. {'solar-pro3': SolarPro3Adapter(...)})."""
        self._adapters.update(adapters)
        logger.info("Registered adapters: %s", list(self._adapters.keys()))

    def get_adapter(self, adapter_name: str) -> VendorAdapter:
        """Retrieve a registered adapter by name."""
        if adapter_name not in self._adapters:
            raise KeyError(
                f"Adapter '{adapter_name}' not registered. "
                f"Available: {list(self._adapters.keys())}"
            )
        return self._adapters[adapter_name]

    def select_model(
        self,
        agent_name: str,
        task_name: str | None = None,
        risk_level: RiskLevel = RiskLevel.none,
        require_json: bool = False,
    ) -> ModelSelection:
        """Select the best model for *agent_name*.

        For fixed agents, returns the single configured adapter.
        For benchmarked agents, returns the highest available tier,
        skipping adapters with open circuit breakers.
        """
        agent_cfg = self._registry.get(agent_name)
        if agent_cfg is None:
            raise KeyError(f"Agent '{agent_name}' not found in registry")

        strategy = agent_cfg.get("strategy", "benchmarked")

        if strategy == "offline":
            raise ValueError(f"Agent '{agent_name}' is offline and cannot be routed")

        if strategy == "fixed":
            return ModelSelection(
                adapter_name=agent_cfg["adapter"],
                model_id=_resolve_env_vars(agent_cfg.get("model", "")),
                tier="fixed",
                supports_json_schema=agent_cfg.get("supports_json_schema", False),
                supports_json_object=agent_cfg.get("supports_json_object", False),
            )

        # Benchmarked: iterate tiers, skip circuit-open adapters
        for tier in _TIER_ORDER:
            tier_cfg = agent_cfg.get(tier)
            if tier_cfg is None:
                continue

            adapter_name = tier_cfg["adapter"]
            if self._fallback_policy.is_circuit_open(adapter_name):
                logger.info(
                    "Skipping %s (tier=%s) for %s — circuit open",
                    adapter_name,
                    tier,
                    agent_name,
                )
                continue

            # If caller requires JSON and adapter doesn't support any form, skip
            if require_json:
                has_json = tier_cfg.get("supports_json_schema", False) or tier_cfg.get(
                    "supports_json_object", False
                )
                if not has_json:
                    # ak-llm: no native JSON — but we can still use prompt-only,
                    # so only skip if there's a better option below
                    # Actually, still return it as fallback — chat_json handles repair
                    pass

            return ModelSelection(
                adapter_name=adapter_name,
                model_id=_resolve_env_vars(tier_cfg.get("model", "")),
                tier=tier,
                supports_json_schema=tier_cfg.get("supports_json_schema", False),
                supports_json_object=tier_cfg.get("supports_json_object", False),
            )

        raise RuntimeError(
            f"No available adapter for agent '{agent_name}' — all circuits open"
        )

    def get_fallback(
        self,
        agent_name: str,
        failed_adapter: str,
        reason: str,
    ) -> ModelSelection | None:
        """Return the next-tier adapter after *failed_adapter*, or None if exhausted.

        Also notifies the fallback policy about the failure.
        """
        agent_cfg = self._registry.get(agent_name)
        if agent_cfg is None or agent_cfg.get("strategy") != "benchmarked":
            return None

        # Find which tier the failed adapter was in
        failed_tier_idx = -1
        for idx, tier in enumerate(_TIER_ORDER):
            tier_cfg = agent_cfg.get(tier)
            if tier_cfg and tier_cfg["adapter"] == failed_adapter:
                failed_tier_idx = idx
                break

        if failed_tier_idx == -1:
            logger.warning(
                "Failed adapter '%s' not found in registry for agent '%s'",
                failed_adapter,
                agent_name,
            )
            return None

        # Try subsequent tiers
        for idx in range(failed_tier_idx + 1, len(_TIER_ORDER)):
            tier = _TIER_ORDER[idx]
            tier_cfg = agent_cfg.get(tier)
            if tier_cfg is None:
                continue

            adapter_name = tier_cfg["adapter"]
            if self._fallback_policy.is_circuit_open(adapter_name):
                continue

            logger.info(
                "Falling back %s: %s → %s (tier=%s, reason=%s)",
                agent_name,
                failed_adapter,
                adapter_name,
                tier,
                reason,
            )
            return ModelSelection(
                adapter_name=adapter_name,
                model_id=_resolve_env_vars(tier_cfg.get("model", "")),
                tier=tier,
                supports_json_schema=tier_cfg.get("supports_json_schema", False),
                supports_json_object=tier_cfg.get("supports_json_object", False),
            )

        logger.warning("No fallback available for %s after %s", agent_name, failed_adapter)
        return None

    def record_success(self, adapter_name: str) -> None:
        """Notify the fallback policy of a successful call."""
        self._fallback_policy.record_success(adapter_name)

    def record_failure(self, adapter_name: str, exc: Exception) -> bool:
        """Notify the fallback policy of a failure. Returns True if should_fallback."""
        return self._fallback_policy.should_fallback(adapter_name, exc)
