"""REV-001 Issue 5 regression tests (critic, `discussion.md`) — explicit
client timeout on all three OpenAI-SDK-shaped LLM adapters.

Before this fix, `AkLlmAdapter`/`SolarPro3Adapter`/`KExaoneAdapter` all
constructed `openai.AsyncOpenAI(...)` with no `timeout=` kwarg, defaulting
to the SDK's 10-minute client timeout — a hung call on the safety-critical
path (e.g. `SafetyClassifierAgent`) could stall a live session for up to 10
minutes before `routing.fallback_policy`'s circuit breaker/fallback ever
engaged. `Settings.llm_client_timeout_s` (default 60s, env-overridable) is
now passed to all three constructors identically.
"""

from __future__ import annotations

from src.adapters.ak_llm import AkLlmAdapter
from src.adapters.k_exaone import KExaoneAdapter
from src.adapters.solar_pro3 import SolarPro3Adapter
from src.config import Settings


class TestLlmClientTimeoutSetting:
    def test_default_is_60_seconds(self) -> None:
        settings = Settings()
        assert settings.llm_client_timeout_s == 60.0

    def test_overridable_via_constructor(self) -> None:
        settings = Settings(llm_client_timeout_s=15.0)
        assert settings.llm_client_timeout_s == 15.0

    def test_overridable_via_env(self, monkeypatch) -> None:
        monkeypatch.setenv("LLM_CLIENT_TIMEOUT_S", "22.5")
        settings = Settings()
        assert settings.llm_client_timeout_s == 22.5


class TestAdapterClientTimeoutWired:
    """Every adapter's `openai.AsyncOpenAI` client carries the configured
    timeout — never the SDK's 10-minute default (600s connect/read/write
    pool `Timeout` object).

    CI-environment discipline (PR #67 CI failure fix): these tests must be
    credential-independent. Keys are injected via monkeypatch.setenv (env
    always wins over .env in pydantic-settings), NEVER via constructor
    kwargs — `skt_a_x_api_key=` as a kwarg is silently ignored because the
    field resolves through validation_alias, which masked this locally
    where .env supplied the value.
    """

    @staticmethod
    def _dummy_keys(monkeypatch) -> None:
        monkeypatch.setenv("SKT_A_X_API_KEY", "test-dummy-key")
        monkeypatch.setenv("UPSTAGE_API_KEY", "test-dummy-key")
        monkeypatch.setenv("LG_K_EXAONE_API_KEY", "test-dummy-key")

    def test_ak_llm_client_has_explicit_timeout(self, monkeypatch) -> None:
        self._dummy_keys(monkeypatch)
        settings = Settings(llm_client_timeout_s=42.0)
        adapter = AkLlmAdapter(settings)
        assert adapter._client.timeout == 42.0

    def test_solar_pro3_client_has_explicit_timeout(self, monkeypatch) -> None:
        self._dummy_keys(monkeypatch)
        settings = Settings(llm_client_timeout_s=42.0)
        adapter = SolarPro3Adapter(settings)
        assert adapter._client.timeout == 42.0

    def test_k_exaone_client_has_explicit_timeout(self, monkeypatch) -> None:
        self._dummy_keys(monkeypatch)
        settings = Settings(llm_client_timeout_s=42.0)
        adapter = KExaoneAdapter(settings)
        assert adapter._client.timeout == 42.0

    def test_all_three_adapters_default_to_the_same_60s(self, monkeypatch) -> None:
        self._dummy_keys(monkeypatch)
        settings = Settings()
        assert AkLlmAdapter(settings)._client.timeout == 60.0
        assert SolarPro3Adapter(settings)._client.timeout == 60.0
        assert KExaoneAdapter(settings)._client.timeout == 60.0

    def test_timeout_is_never_the_sdk_10_minute_default(self, monkeypatch) -> None:
        """The openai SDK's own untouched default is a 600s-family
        `httpx.Timeout` object, not a bare float — asserting our adapters
        carry a plain float instead is itself proof `timeout=` was passed
        explicitly (an unset `timeout` on AsyncOpenAI never resolves to a
        bare float)."""
        self._dummy_keys(monkeypatch)
        settings = Settings()
        assert isinstance(AkLlmAdapter(settings)._client.timeout, float)
