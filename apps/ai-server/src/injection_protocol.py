"""injection_protocol.py — STT/OCR arbitrary-turn injection composer.

PLAN-2026-W28-Q W3 (`docs/ai/validation_plan_f1f2_continuous.md` §3
"STT/OCR arbitrary-turn injection" row, §5 AVC-15 cross-cutting check,
§6 AVC-15). Part of the EXTERNAL verification-protocol layer
(`continuous_test.py` lineage), not production code — invariant 1
(plan §2): zero test-only hook, import, flag, or parameter enters
`src/f1.py` or `src/f2.py`. The standing AVC-03 grep (persona/harness
references inside `src/agents|schemas|routes`) stays clean; this module
imports FROM production (`src.dependencies.get_stt_agent`/`get_ocr_agent`,
the SAME factories `f1.py` itself uses) — never the other direction.

## What this module does

`F1Pipeline.run_session(patient_input_fn=...)` is f1.py's existing PUBLIC
per-turn seam: an async callback `(agent_response: str) -> patient_message:
str`, called once per patient turn (turn 0's response to the autonomous
greeting, then once per turn 1..max_turns). Real chat sessions expose this
same shape indirectly via `/ai/stt/transcribe` and `/ai/ocr/parse` — a real
client already lets a patient answer by voice (STT'd) or by uploading a
document (OCR'd) that becomes their turn's message.

`compose_injected_patient_input_fn()` wraps an existing base
`patient_input_fn` (e.g. the live `PatientLLM.respond` `f1._run_simulation`
already builds) with a per-scenario **injection schedule** — a turn index
-> modality (`"stt"` | `"ocr"`) -> fixture-file mapping. On a scheduled
turn, instead of delegating to the base function, the composed function
invokes the SAME production agents f1.py itself uses
(`src.dependencies.get_stt_agent()` / `get_ocr_agent()`) against the
fixture file and returns the REAL vendor-transcribed/parsed text as that
turn's patient message — mirroring what a real client's STT/OCR call would
hand back. Every other (non-scheduled) turn is untouched — delegates to
`base_fn` unchanged.

## Modality provenance (AVC-15)

Every injected turn is recorded as a `ModalityProvenanceEvent` (turn index,
modality, fixture path, source id, char count, latency, vendor). Because an
injected turn's text enters `f1.py`'s dialogue exactly like real speech
would (the same `patient_input_fn` seam, the same `InputNormalizer` pass),
F2 will legitimately tag any evidence citing it `source_type="utterance"` —
NOT `"ocr_document"`. That is CORRECT behavior for this injection mode, not
a provenance loss: the `ocr_document` `EvidenceSourceType` value (W1,
`docs/ai/validation_plan_f1f2_continuous.md` §3 row 1) is reserved for
F1's SEPARATE, pre-existing `ocr_documents=` session-start document-
attachment parameter (`f1.py: F1Pipeline.run_session(ocr_documents=...)`),
which this module does NOT touch or replace.

To keep the injected turn's TRUE origin auditable despite that (AVC-15's
"F1/F2 artifact JSON field presence" evidence requirement), this module
writes a HARNESS-ONLY sidecar file next to F1's own `conversation.json`
(`write_provenance_sidecar`, same sibling-file pattern as
`continuous_test.py`'s per-VP session ledger — never read by production
code) and provides `verify_provenance_against_conversation()` to prove the
injected text reached the artifact unmutated (compared against
`normalizer_meta.original`, the pre-normalization echo InputNormalizer
already persists — comparing against the post-normalization
`patient_message` would flag every legitimate correction as a false
mismatch).

Separately, `build_ocr_texts_from_f1_ocr_documents()` +
`audit_ocr_document_evidence()` complete the OTHER, W1-anticipated
`ocr_texts` path: `src.eval.f2_grounding.check_evidence` /
`audit_domain_candidates` have accepted an `ocr_texts: Mapping[str, str]`
kwarg since W1, but "no caller wires real OCR content into this run yet"
(`tests/test_evidence_source_type_ocr.py` module docstring). This module is
that caller — but only as a HARNESS-SIDE, read-only, second-purpose audit
over an EXISTING `domain_inference.json` artifact (reuses the plan §5
run-reuse discipline: zero additional model calls, never treated as
inflating a primary metric's sample size). `f2.py`'s own `_run()` call site
is untouched and keeps passing its own default `ocr_texts={}` — no
production behavior change for non-injected runs.

## SC-6/SC-10 standalone readiness (plan §10, fixtures not yet delivered —
## SKIPPED-awaiting-user-material)

Both cells need only a schedule entry naming the delivered fixture path —
zero code change once the fixtures land:

  SC-6 (OCR-contradicts-speech): 2 scanned-image PDFs (prescription/
  dispensing record, VP-004, naming Escitalopram 20mg or Alprazolam 0.25mg
  PRN + a dispensing/refill date; plan §10 fixture (i)) at any path.
  Schedule one `InjectionCue(modality="ocr", fixture_path=<pdf>,
  turn_index=<N>, label="VP-004_prescription")` at a turn during VP-004's
  medication-adherence discussion; the resulting OCR-derived text
  (`raw_markdown`, first-person register per plan §10) becomes that turn's
  patient message. The "contradiction" against VP-004's own earlier spoken
  non-adherence claim is a downstream clinical-validator/critic read of the
  transcript — this module only delivers the OCR text into the turn.

  SC-10 (OCR document carrying risk-lexicon content): 2 scanned-image PDFs
  (referral/discharge summary, embedded first-person patient quote, 1-2
  risk-lexicon stem families from the established 20-stem-family taxonomy
  (37 literal entries; REV-024 corrected the earlier "15-stem" undercount);
  plan §10 fixture (ii)). Schedule one `InjectionCue(modality="ocr", ...)` at
  any turn; downstream AVC-01/VAL-010 audits then check the injected risk
  content is still caught by F2's EXISTING risk-lexicon evidence filter
  (`src.eval.f2_grounding._RISK_PHRASES`) exactly as spoken risk content
  already is.

`validate_schedule()` below lets both cells be dry-run-checked (fixture
existence, turn-index/modality sanity) with ZERO vendor/model calls, so a
schedule authored today already works the moment fixtures arrive.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from src.dependencies import get_ocr_agent, get_stt_agent
from src.schemas.ocr import OCRInput
from src.schemas.stt import STTInput

logger = logging.getLogger(__name__)

PatientInputFn = Callable[[str], Awaitable[str]]
Modality = Literal["stt", "ocr"]

_DEFAULT_STT_KEYWORDS = ["우울감", "불면", "불안", "자살", "자해"]

_CONTENT_TYPE_BY_SUFFIX: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def _guess_content_type(path: Path) -> str:
    return _CONTENT_TYPE_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")


# ── Injection schedule ──────────────────────────────────────────────────


@dataclass(frozen=True)
class InjectionCue:
    """One scheduled arbitrary-turn injection.

    `turn_index` matches f1.py's own turn numbering exactly: 0 = the
    patient's response to the autonomous turn-0 greeting (the FIRST call
    `patient_input_fn` ever receives), 1..N = the per-turn loop. This is a
    call-ordinal counter internal to the composed function, not a lookup
    into any already-existing conversation state.
    """

    turn_index: int
    modality: Modality
    fixture_path: Path
    label: str = ""

    def __post_init__(self) -> None:
        if self.turn_index < 0:
            raise ValueError(f"turn_index must be >= 0, got {self.turn_index}")
        if self.modality not in ("stt", "ocr"):
            raise ValueError(f"modality must be 'stt' or 'ocr', got {self.modality!r}")
        if not isinstance(self.fixture_path, Path):
            object.__setattr__(self, "fixture_path", Path(self.fixture_path))

    @property
    def resolved_label(self) -> str:
        return self.label or self.fixture_path.stem


def load_schedule_from_json(path: Path) -> list[InjectionCue]:
    """Load a per-scenario injection schedule: a JSON list of
    ``{"turn_index": int, "modality": "stt"|"ocr", "fixture_path": str,
    "label": str (optional)}`` objects."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"schedule file must contain a JSON list, got {type(raw).__name__}")
    return [
        InjectionCue(
            turn_index=int(entry["turn_index"]),
            modality=entry["modality"],
            fixture_path=Path(entry["fixture_path"]),
            label=entry.get("label", ""),
        )
        for entry in raw
    ]


def schedule_to_dicts(schedule: Sequence[InjectionCue]) -> list[dict[str, Any]]:
    return [
        {
            "turn_index": c.turn_index,
            "modality": c.modality,
            "fixture_path": str(c.fixture_path),
            "label": c.resolved_label,
        }
        for c in schedule
    ]


@dataclass(frozen=True)
class ScheduleValidationIssue:
    turn_index: int
    reason: str


def validate_schedule(schedule: Sequence[InjectionCue]) -> list[ScheduleValidationIssue]:
    """Dry-run schedule check — ZERO vendor/model calls. Fixture existence
    + duplicate-turn-index + modality sanity only. Lets an SC-6/SC-10
    schedule be authored and checked before the fixtures physically land
    (module docstring)."""
    issues: list[ScheduleValidationIssue] = []
    seen_turns: set[int] = set()
    for cue in schedule:
        if cue.turn_index in seen_turns:
            issues.append(ScheduleValidationIssue(
                cue.turn_index, "duplicate turn_index in schedule (last one wins silently)",
            ))
        seen_turns.add(cue.turn_index)
        if not cue.fixture_path.exists():
            issues.append(ScheduleValidationIssue(
                cue.turn_index,
                f"fixture not found: {cue.fixture_path} — SKIPPED-awaiting-user-material "
                "until this fixture is delivered (plan §10); do not fabricate one",
            ))
    return issues


# ── Modality provenance (AVC-15) ────────────────────────────────────────


@dataclass(frozen=True)
class ModalityProvenanceEvent:
    """One injected turn's provenance record — full extracted text is kept
    (needed by `build_ocr_texts_from_provenance`/grounding audits); callers
    reporting this externally should use `text_preview`/`char_count` only,
    never dump `text` verbatim (clinical-content discipline)."""

    turn_index: int
    modality: Modality
    fixture_path: str
    label: str
    source_id: str
    vendor: str
    char_count: int
    latency_ms: float
    extracted_at: str
    text: str
    text_preview: str = ""

    def to_dict(self, *, include_full_text: bool = True) -> dict[str, Any]:
        d = asdict(self)
        if not include_full_text:
            d.pop("text", None)
        return d


def _stt_source_id(cue: InjectionCue) -> str:
    return f"stt:{cue.resolved_label}"


def _ocr_source_id(cue: InjectionCue) -> str:
    return f"ocr:{cue.resolved_label}"


async def _run_stt_cue(
    cue: InjectionCue,
    *,
    session_id: str,
    patient_id: str,
    get_stt_agent_fn: Callable[[], Any],
) -> tuple[str, ModalityProvenanceEvent]:
    agent = get_stt_agent_fn()
    audio_bytes = cue.fixture_path.read_bytes()
    meta = STTInput(
        session_id=session_id,
        patient_id=patient_id,
        filename=cue.fixture_path.name,
        mode="batch",
        keywords=list(_DEFAULT_STT_KEYWORDS),
    )
    started = time.perf_counter()
    out = await agent.transcribe(audio_bytes, meta)
    latency_ms = (time.perf_counter() - started) * 1000
    text = out.text or ""
    event = ModalityProvenanceEvent(
        turn_index=cue.turn_index,
        modality="stt",
        fixture_path=str(cue.fixture_path),
        label=cue.resolved_label,
        source_id=_stt_source_id(cue),
        vendor=getattr(out, "vendor", "skt-ak-stt"),
        char_count=len(text),
        latency_ms=latency_ms,
        extracted_at=datetime.now().isoformat(),
        text=text,
        text_preview=text[:10],
    )
    return text, event


async def _run_ocr_cue(
    cue: InjectionCue,
    *,
    session_id: str,
    patient_id: str,
    get_ocr_agent_fn: Callable[[], Any],
    ocr_text_field: Literal["raw_markdown", "raw_text"],
    max_ocr_chars: int,
) -> tuple[str, ModalityProvenanceEvent]:
    agent = get_ocr_agent_fn()
    doc_bytes = cue.fixture_path.read_bytes()
    meta = OCRInput(
        session_id=session_id,
        patient_id=patient_id,
        document_type_hint="unknown",
        filename=cue.fixture_path.name,
    )
    content_type = _guess_content_type(cue.fixture_path)
    started = time.perf_counter()
    out = await agent.parse(doc_bytes, meta, content_type=content_type)
    latency_ms = (time.perf_counter() - started) * 1000
    text = getattr(out, ocr_text_field, "") or out.raw_text or out.raw_markdown or ""
    text = text[:max_ocr_chars]
    event = ModalityProvenanceEvent(
        turn_index=cue.turn_index,
        modality="ocr",
        fixture_path=str(cue.fixture_path),
        label=cue.resolved_label,
        source_id=_ocr_source_id(cue),
        vendor=getattr(out, "ocr_vendor", "upstage_solar_document_parse"),
        char_count=len(text),
        latency_ms=latency_ms,
        extracted_at=datetime.now().isoformat(),
        text=text,
        text_preview=text[:10],
    )
    return text, event


def compose_injected_patient_input_fn(
    base_fn: PatientInputFn,
    schedule: Sequence[InjectionCue],
    *,
    session_id: str,
    patient_id: str,
    get_stt_agent_fn: Callable[[], Any] = get_stt_agent,
    get_ocr_agent_fn: Callable[[], Any] = get_ocr_agent,
    ocr_text_field: Literal["raw_markdown", "raw_text"] = "raw_markdown",
    max_ocr_chars: int = 2000,
) -> tuple[PatientInputFn, list[ModalityProvenanceEvent]]:
    """Wrap `base_fn` with `schedule` — the composed callable is a drop-in
    `patient_input_fn` for `F1Pipeline.run_session(patient_input_fn=...)`.

    Returns `(composed_fn, events)`. `events` is the SAME list object the
    composed function appends to as it runs — inspect it after the session
    completes (mirrors `continuous_test.py`'s own mutable-context-object
    pattern for `ChainContext`).

    Raises `FileNotFoundError` from within the composed call if a scheduled
    fixture is missing — never fabricates or silently skips a scheduled
    injection (per-project no-silent-failure discipline).
    """
    cues_by_turn = {c.turn_index: c for c in schedule}
    events: list[ModalityProvenanceEvent] = []
    counter = {"turn": 0}

    async def _composed(agent_response: str) -> str:
        turn_index = counter["turn"]
        counter["turn"] += 1
        cue = cues_by_turn.get(turn_index)
        if cue is None:
            return await base_fn(agent_response)

        if not cue.fixture_path.exists():
            raise FileNotFoundError(
                f"injection_protocol: scheduled {cue.modality} fixture missing for turn "
                f"{turn_index}: {cue.fixture_path} — SKIPPED-awaiting-user-material until "
                "this fixture is delivered (plan §10); do not fabricate a fixture."
            )

        if cue.modality == "stt":
            text, event = await _run_stt_cue(
                cue, session_id=session_id, patient_id=patient_id,
                get_stt_agent_fn=get_stt_agent_fn,
            )
        else:  # "ocr" — validated by InjectionCue.__post_init__
            text, event = await _run_ocr_cue(
                cue, session_id=session_id, patient_id=patient_id,
                get_ocr_agent_fn=get_ocr_agent_fn,
                ocr_text_field=ocr_text_field, max_ocr_chars=max_ocr_chars,
            )

        events.append(event)
        logger.info(
            "injection_protocol.turn_injected — turn=%d modality=%s source_id=%s chars=%d "
            "latency_ms=%.0f",
            turn_index, cue.modality, event.source_id, event.char_count, event.latency_ms,
        )
        return text

    return _composed, events


# ── Sidecar artifact — harness-only, never read by production code ─────


def write_provenance_sidecar(
    conversation_json_path: Path,
    events: Sequence[ModalityProvenanceEvent],
    *,
    persona_id: str | None = None,
) -> Path:
    """Write `<VP>_<ts>_modality_provenance.json` next to F1's own
    `conversation.json` — same sibling-file, harness-only pattern as
    `continuous_test.py`'s per-VP session ledger. Production code
    (`f1.py`/`f2.py`) never reads this file."""
    stem = conversation_json_path.stem
    if stem.endswith("_conversation"):
        stem = stem[: -len("_conversation")]
    sidecar_path = conversation_json_path.with_name(f"{stem}_modality_provenance.json")
    payload = {
        "schema_version": 1,
        "conversation_path": str(conversation_json_path),
        "persona_id": persona_id,
        "events": [e.to_dict() for e in events],
        "written_at": datetime.now().isoformat(),
    }
    sidecar_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return sidecar_path


def verify_provenance_against_conversation(
    conversation_json: Mapping[str, Any],
    events: Sequence[ModalityProvenanceEvent],
) -> list[str]:
    """Cross-check each provenance event's recorded text against the SAME
    turn's RAW (pre-normalization) input in the F1 artifact — proves the
    injected text reached the pipeline unmutated end-to-end (AVC-15's
    "F1/F2 artifact JSON field presence" evidence). Compares against
    `normalizer_meta.original` (InputNormalizer's own pre-normalization
    echo), NOT `patient_message` (post-normalization — a legitimate
    correction would show as a false mismatch there).

    Returns a list of human-readable mismatch descriptions; empty = fully
    consistent.
    """
    turns_by_index = {t.get("turn"): t for t in (conversation_json.get("turns") or [])}
    mismatches: list[str] = []
    for ev in events:
        turn = turns_by_index.get(ev.turn_index)
        if turn is None:
            mismatches.append(
                f"turn {ev.turn_index}: no matching turn found in conversation.json"
            )
            continue
        norm_meta = turn.get("normalizer_meta") or {}
        raw_at_turn = norm_meta.get("original")
        if raw_at_turn is None:
            raw_at_turn = turn.get("patient_message")
        if raw_at_turn != ev.text:
            mismatches.append(
                f"turn {ev.turn_index}: recorded raw input does not match the "
                f"{ev.modality} injection's extracted text (source_id={ev.source_id})"
            )
    return mismatches


# ── ocr_texts path (AVC-15 / W1 EvidenceSourceType 'ocr_document') ─────


def build_ocr_texts_from_provenance(
    events: Sequence[ModalityProvenanceEvent],
) -> dict[str, str]:
    """{source_id: full_text} for every OCR-modality provenance event from
    THIS module's per-turn injection — usable as `check_evidence`'s/
    `audit_domain_candidates`'s `ocr_texts` kwarg. See caveat in
    `audit_ocr_document_evidence`: injected-turn OCR text legitimately
    surfaces as `utterance` evidence, not `ocr_document` — this mapping is
    provided for completeness/defense-in-depth, not because it is expected
    to be consumed by F2's `ocr_document` branch for THIS injection mode.
    """
    return {e.source_id: e.text for e in events if e.modality == "ocr"}


def build_ocr_texts_from_f1_ocr_documents(
    ocr_documents: Sequence[Mapping[str, Any]],
    *,
    persona_id: str,
) -> dict[str, str]:
    """{source_id: full_text} sourced from `F1Result.ocr_documents` — the
    SEPARATE, pre-existing, already-production `ocr_documents=`
    session-start attachment parameter (`f1.py`
    `F1Pipeline.run_session(ocr_documents=...)`), unrelated to this
    module's per-turn injection. Naming convention matches
    `tests/test_evidence_source_type_ocr.py`'s fixture convention
    (`"ocr:VP-004_prescription"`): `ocr:<persona_id>_<document_type>_<i>`.
    """
    out: dict[str, str] = {}
    for i, doc in enumerate(ocr_documents):
        doc_type = doc.get("document_type", "unknown")
        text = doc.get("raw_markdown") or doc.get("raw_text") or ""
        if not text:
            continue
        out[f"ocr:{persona_id}_{doc_type}_{i}"] = text
    return out


def audit_ocr_document_evidence(
    domain_inference_artifact: Mapping[str, Any],
    ocr_texts: Mapping[str, str],
) -> list[Any]:
    """AVC-15 harness-side, READ-ONLY, second-purpose audit (plan §5
    run-reuse discipline — zero additional model calls, never treated as
    inflating a primary metric's sample size): re-checks every
    `source_type == "ocr_document"` evidence item already present in an
    EXISTING F2 `domain_inference.json` artifact against REAL parsed OCR
    text, using `src.eval.f2_grounding.check_evidence` (accepts `ocr_texts`
    since W1; this module is simply its first real caller).

    Does NOT change `f2.py`'s own `_run()` — that call site keeps its own
    default `ocr_texts={}` untouched (no production behavior change for
    non-injected runs).

    Expected result for THIS module's per-turn injection mode: EMPTY —
    injected STT/OCR text enters the dialogue as an ordinary `utterance`
    (module docstring), never `ocr_document`. `ocr_document`-tagged
    evidence can only arise from F1's separate `ocr_documents=` path
    (`build_ocr_texts_from_f1_ocr_documents` above). An empty return here
    is a correct, honest result — not a bug or an unimplemented check.
    """
    from src.eval.f2_grounding import check_evidence

    verdicts: list[Any] = []
    for cand in domain_inference_artifact.get("domain_candidates", []) or []:
        for ev in cand.get("evidence", []) or []:
            if ev.get("source_type") != "ocr_document":
                continue
            verdicts.append(check_evidence(
                "ocr_document",
                ev.get("source_id", ""),
                ev.get("quote", ""),
                chunk_texts={},
                utterances={},
                ocr_texts=ocr_texts,
                domain=cand.get("domain", ""),
            ))
    return verdicts


# ── CLI — schedule validation only, ZERO vendor/model calls ────────────


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "injection_protocol — validate an STT/OCR arbitrary-turn injection "
            "schedule (fixture existence + turn-index sanity only; makes NO vendor "
            "or model calls, W7 runs the actual battery)"
        )
    )
    parser.add_argument("--schedule", required=True, help="Path to a schedule JSON file")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    schedule = load_schedule_from_json(Path(args.schedule))
    issues = validate_schedule(schedule)
    print(f"injection_protocol: {len(schedule)} cue(s), {len(issues)} issue(s)")
    for issue in issues:
        print(f"  [turn {issue.turn_index}] {issue.reason}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
