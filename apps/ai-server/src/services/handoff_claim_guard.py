"""Pure extractive-grounding checks for official handoff claims."""

from __future__ import annotations

import re
from typing import Final, Protocol

from contracts.handoff import Citation, HandoffRequest

_DIRECT_DIAGNOSIS_PATTERNS: Final = (
    re.compile(
        r"(?:우울증|조현병|불안장애)\s*(?:입니다|이다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\S+(?:으)?로\s*(?:판단|진단)(?:합니다|됩니다|내립니다)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:진단|확진)(?:을)?\s*(?:합니다|내립니다|됩니다)", re.IGNORECASE),
    re.compile(r"\b(?:patient|you)\s+(?:has|have)\s+\w+", re.IGNORECASE),
    re.compile(r"\bdiagnose\s+(?:the\s+)?patient\b", re.IGNORECASE),
    re.compile(r"\b(?:the\s+)?diagnosis\s+(?:is|:)\s*\w+", re.IGNORECASE),
)
_DIRECT_TREATMENT_PATTERNS: Final = (
    re.compile(
        r"(?:복용|투약|투여|처방)(?:을)?\s*(?:하세요|하십시오|해야\s*합니다|권고합니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:시작|중단|증량|감량|변경)(?:을)?\s*(?:하세요|하십시오|해야\s*합니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:prescribe|start taking|stop taking|increase|decrease)\b",
        re.IGNORECASE,
    ),
)


class SleepAppetiteActivityClaims(Protocol):
    """Nested extractive claim fields consumed by the guard."""

    sleep: str | None
    appetite: str | None
    activity: str | None


class HandoffClaims(Protocol):
    """Structural claim view shared by the provider draft and guard."""

    chief_complaint: str
    present_illness: str
    symptoms: list[str]
    onset: str | None
    recent_changes: str | None
    triggers: list[str]
    @property
    def sleep_appetite_activity(self) -> SleepAppetiteActivityClaims: ...
    psych_history: str | None
    medications: str | None
    documents_summary: list[str]
    clinician_attention: list[str]
    evidence: list[Citation]


def _populated_targets(claims: HandoffClaims) -> dict[str, str]:
    targets = {
        field: value
        for field, value in (
            ("chief_complaint", claims.chief_complaint),
            ("present_illness", claims.present_illness),
            ("onset", claims.onset),
            ("recent_changes", claims.recent_changes),
            ("psych_history", claims.psych_history),
            ("medications", claims.medications),
            ("sleep_appetite_activity.sleep", claims.sleep_appetite_activity.sleep),
            ("sleep_appetite_activity.appetite", claims.sleep_appetite_activity.appetite),
            ("sleep_appetite_activity.activity", claims.sleep_appetite_activity.activity),
        )
        if value is not None and value.strip()
    }
    for field, values in (
        ("symptoms", claims.symptoms),
        ("triggers", claims.triggers),
        ("clinician_attention", claims.clinician_attention),
    ):
        targets.update(
            {f"{field}[{index}]": value for index, value in enumerate(values) if value.strip()}
        )
    return targets


def _contains_direct_clinical_assertion(value: str) -> bool:
    return any(
        pattern.search(value) is not None
        for pattern in (*_DIRECT_DIAGNOSIS_PATTERNS, *_DIRECT_TREATMENT_PATTERNS)
    )


def handoff_claims_are_valid(claims: HandoffClaims, request: HandoffRequest) -> bool:
    """Require one exact user-message span for every populated claim target."""
    if claims.documents_summary:
        return False

    targets = _populated_targets(claims)
    if any(_contains_direct_clinical_assertion(value) for value in targets.values()):
        return False
    if len(claims.evidence) != len(targets):
        return False

    messages: dict[str, tuple[str, str]] = {}
    for message in request.messages:
        source_id = str(message.message_id)
        if source_id in messages:
            return False
        messages[source_id] = (message.role, message.content)

    cited_targets: set[str] = set()
    for citation in claims.evidence:
        source = messages.get(str(citation.source_message_id))
        claim = targets.get(citation.field)
        if source is None or claim is None or citation.field in cited_targets:
            return False
        role, content = source
        if (
            role != "user"
            or len(citation.quote.strip()) < 2
            or citation.quote not in content
            or claim != citation.quote
        ):
            return False
        cited_targets.add(citation.field)
    return cited_targets == targets.keys()
