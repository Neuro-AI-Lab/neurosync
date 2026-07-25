"""Structured official-contract handoff generation with citation validation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Final, override

from contracts.handoff import Citation, HandoffRequest, HandoffResponse, SleepAppetiteActivity
from pydantic import BaseModel, ConfigDict, ValidationError

from src.adapters.base import ChatMessage, LLMAdapter
from src.prompts.loader import PromptLoader
from src.routing.fallback_policy import AdapterHealthFailure
from src.routing.model_router import ModelRouter
from src.schemas.common import ModelSelection
from src.schemas.handoff import HandoffInput
from src.services.handoff_claim_guard import handoff_claims_are_valid

_AGENT_NAME: Final = "handoff_generator"
_PROMPT_VERSION: Final = "v4"
_MAX_RETRIES: Final = 2


@dataclass(frozen=True, slots=True)
class HandoffContractValidationError(AdapterHealthFailure):
    """The provider response was not valid official handoff JSON."""

    @override
    def __str__(self) -> str:
        return "handoff response failed contract validation"


@dataclass(frozen=True, slots=True)
class HandoffProviderError(AdapterHealthFailure):
    """The configured provider could not produce a response."""

    @override
    def __str__(self) -> str:
        return "handoff provider failed"


class _SleepAppetiteActivityDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sleep: str | None
    appetite: str | None
    activity: str | None


class _HandoffDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chief_complaint: str
    present_illness: str
    symptoms: list[str]
    onset: str | None
    recent_changes: str | None
    triggers: list[str]
    sleep_appetite_activity: _SleepAppetiteActivityDraft
    psych_history: str | None
    medications: str | None
    documents_summary: list[str]
    clinician_attention: list[str]
    evidence: list[Citation]


def _validate_citations(draft: _HandoffDraft, request: HandoffRequest) -> None:
    if not handoff_claims_are_valid(draft, request):
        raise HandoffContractValidationError()


def _to_response(draft: _HandoffDraft, latency_ms: int) -> HandoffResponse:
    return HandoffResponse(
        chief_complaint=draft.chief_complaint,
        present_illness=draft.present_illness,
        symptoms=draft.symptoms,
        onset=draft.onset,
        recent_changes=draft.recent_changes,
        triggers=draft.triggers,
        sleep_appetite_activity=SleepAppetiteActivity(
            sleep=draft.sleep_appetite_activity.sleep,
            appetite=draft.sleep_appetite_activity.appetite,
            activity=draft.sleep_appetite_activity.activity,
        ),
        psych_history=draft.psych_history,
        medications=draft.medications,
        documents_summary=draft.documents_summary,
        clinician_attention=draft.clinician_attention,
        evidence=draft.evidence,
        latency_ms=latency_ms,
    )


class HandoffContractGenerator:
    """Generate an official HandoffResponse while retaining local run() elsewhere."""

    def __init__(self, model_router: ModelRouter, prompt_loader: PromptLoader) -> None:
        self._router = model_router
        self._prompt_loader = prompt_loader

    async def _request_json(
        self,
        selection: ModelSelection,
        local_input: HandoffInput,
    ) -> str:
        if selection.supports_json_schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "handoff_response",
                    "strict": True,
                    "schema": _HandoffDraft.model_json_schema(),
                },
            }
        elif selection.supports_json_object:
            response_format = {"type": "json_object"}
        else:
            response_format = None
        messages = [
            ChatMessage(
                role="system",
                content=self._prompt_loader.load_system_prompt(_AGENT_NAME, _PROMPT_VERSION),
            ),
            ChatMessage(role="user", content=local_input.model_dump_json(exclude_none=True)),
        ]
        content: str | None = None
        provider_failed = False
        # Provider boundary: discard arbitrary Exception content; BaseException propagates.
        try:
            adapter = self._router.get_adapter(selection.adapter_name)
            if isinstance(adapter, LLMAdapter):
                response = await adapter.chat_timed(
                    messages,
                    model=selection.model_id,
                    temperature=0.2,
                    max_tokens=4096,
                    response_format=response_format,
                )
                content = response.content
            else:
                provider_failed = True
        except Exception:
            provider_failed = True
        if provider_failed or content is None:
            raise HandoffProviderError() from None
        return content

    def _select_model(self) -> ModelSelection:
        selection: ModelSelection | None = None
        provider_failed = False
        # Router boundary: discard arbitrary Exception content; BaseException propagates.
        try:
            selection = self._router.select_model(_AGENT_NAME, require_json=True)
        except Exception:
            provider_failed = True
        if provider_failed or selection is None:
            raise HandoffProviderError() from None
        return selection

    async def generate(
        self,
        request: HandoffRequest,
        local_input: HandoffInput,
    ) -> HandoffResponse:
        """Try three configured tiers and return the first grounded response."""
        started = time.perf_counter()
        selection = self._select_model()
        for attempt in range(1 + _MAX_RETRIES):
            try:
                content = await self._request_json(selection, local_input)
                draft = _HandoffDraft.model_validate_json(content)
                _validate_citations(draft, request)
                elapsed_ms = max(0, round((time.perf_counter() - started) * 1000))
                response = _to_response(draft, elapsed_ms)
            except (ValidationError, HandoffContractValidationError):
                failure: HandoffContractValidationError | HandoffProviderError = (
                    HandoffContractValidationError()
                )
            except HandoffProviderError as exc:
                failure = exc
            else:
                self._router.record_success(selection.adapter_name)
                return response

            _ = self._router.record_failure(selection.adapter_name, failure)
            if attempt == _MAX_RETRIES:
                raise failure
            fallback = self._router.get_fallback(
                _AGENT_NAME,
                selection.adapter_name,
                "handoff attempt failed",
            )
            if fallback is None:
                raise failure
            selection = fallback
        raise HandoffContractValidationError()
