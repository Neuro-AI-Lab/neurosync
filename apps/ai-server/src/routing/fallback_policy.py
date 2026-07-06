"""Fallback decision logic — determines when and how to fall back."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import openai

logger = logging.getLogger(__name__)

# ── Error classification ───────────────────────────────────────────────

_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def is_transient(exc: Exception) -> bool:
    """Return True if the error is likely transient and worth retrying/falling back."""
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIStatusError) and exc.status_code in _TRANSIENT_STATUS_CODES:
        return True
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    return False


def is_permanent(exc: Exception) -> bool:
    """Return True if the error should NOT trigger fallback (bad request, auth, etc.)."""
    if isinstance(exc, openai.AuthenticationError):
        return True
    if isinstance(exc, openai.APIStatusError) and exc.status_code in {400, 401, 403, 404, 422}:
        return True
    return False


# ── Backoff calculator ─────────────────────────────────────────────────

_BACKOFF_BASE_S = 1.0
_BACKOFF_MAX_S = 30.0


def backoff_seconds(attempt: int, base: float = _BACKOFF_BASE_S) -> float:
    """Exponential backoff with cap: base * 2^attempt, max 30s."""
    return min(base * (2**attempt), _BACKOFF_MAX_S)


# ── Fallback policy ───────────────────────────────────────────────────


@dataclass
class FailureRecord:
    """Tracks recent failures for a single adapter."""

    adapter_name: str
    failure_count: int = 0
    last_failure_ts: float = 0.0
    consecutive_failures: int = 0
    circuit_open_until: float = 0.0


@dataclass
class FallbackPolicy:
    """Decides whether to fall back and tracks adapter health.

    Simple circuit-breaker: after ``threshold`` consecutive failures within
    ``window_s`` seconds, the adapter is "open" (skipped) for ``cooldown_s``.
    """

    threshold: int = 3
    window_s: float = 60.0
    cooldown_s: float = 30.0
    _records: dict[str, FailureRecord] = field(default_factory=dict)

    def _get_record(self, adapter_name: str) -> FailureRecord:
        if adapter_name not in self._records:
            self._records[adapter_name] = FailureRecord(adapter_name=adapter_name)
        return self._records[adapter_name]

    def should_fallback(self, adapter_name: str, exc: Exception) -> bool:
        """Return True if we should fall back to the next tier.

        - Permanent errors → always fall back (no point retrying)
        - Transient errors → fall back if circuit is open or threshold exceeded
        """
        if is_permanent(exc):
            logger.warning(
                "Permanent error on %s (%s) — falling back immediately",
                adapter_name,
                type(exc).__name__,
            )
            return True

        if not is_transient(exc):
            # Unknown error type — fall back to be safe
            return True

        record = self._get_record(adapter_name)
        now = time.monotonic()

        # Reset if outside window
        if now - record.last_failure_ts > self.window_s:
            record.consecutive_failures = 0

        record.failure_count += 1
        record.consecutive_failures += 1
        record.last_failure_ts = now

        if record.consecutive_failures >= self.threshold:
            record.circuit_open_until = now + self.cooldown_s
            logger.warning(
                "Circuit opened for %s after %d consecutive failures (cooldown %.0fs)",
                adapter_name,
                record.consecutive_failures,
                self.cooldown_s,
            )
            return True

        return True  # For transient errors, always prefer fallback over waiting

    def is_circuit_open(self, adapter_name: str) -> bool:
        """Check if the adapter's circuit breaker is open (should be skipped)."""
        record = self._get_record(adapter_name)
        if record.circuit_open_until == 0.0:
            return False
        now = time.monotonic()
        if now >= record.circuit_open_until:
            # Cooldown expired — half-open, allow one attempt
            record.circuit_open_until = 0.0
            record.consecutive_failures = 0
            return False
        return True

    def record_success(self, adapter_name: str) -> None:
        """Reset failure counters after a successful call."""
        record = self._get_record(adapter_name)
        record.consecutive_failures = 0
        record.circuit_open_until = 0.0

    def get_backoff(self, adapter_name: str) -> float:
        """Return suggested backoff in seconds based on failure count."""
        record = self._get_record(adapter_name)
        return backoff_seconds(record.consecutive_failures)
