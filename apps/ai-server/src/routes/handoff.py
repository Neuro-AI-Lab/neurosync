"""POST /ai/handoff/generate — Handoff report generation endpoint (LLM-backed
narrative, pre-existing).

POST /ai/handoff/report — stateless F4+F5 hand-off report assembly
(`docs/ai/deployment_integration_plan.md` R1). A THIN wrapper over
`src.f4.analyze_longitudinal_series` + `src.f5.assemble_handoff_report`
(both pure, deterministic, zero-LLM) plus `src.services.f5_report`'s
markdown/PDF/FHIR exporters — no engine or exporter logic changes here or in
`src.services.stateless_longitudinal`, which only converts the request
payload into their harness-input dataclasses, mirroring
`src/continuous_test.py`'s own file-backed assembly. Distinct from
`/generate` above (an LLM-narrated report from raw messages) — `/report`
never calls an LLM by default (`narrative_enabled=False` unless the caller
supplies an ALREADY-GENERATED `narrative_text`, `src.f5`'s own A8 contract).
"""

from __future__ import annotations

import base64
import logging
import tempfile
import uuid
from pathlib import Path

from contracts.longitudinal import HandoffReportRequest, HandoffReportResponse
from fastapi import APIRouter, Depends, HTTPException

from src import f4, f5
from src.agents.evidence_verifier import (
    EvidenceVerifierAgent,
    EvidenceVerifierInput,
    VerifierAction,
)
from src.agents.handoff_generator import HandoffGeneratorAgent
from src.dependencies import get_model_router, get_prompt_loader
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.schemas.handoff import HandoffInput, HandoffOutput
from src.services.f5_report import build_fhir_bundle, build_markdown_report, build_pdf_report
from src.services.stateless_longitudinal import (
    build_all_sessions,
    build_domain_inference_snapshot,
    build_f3_administration,
    build_series_input,
    build_session_snapshot,
    generate_charts_in_memory,
    sorted_sessions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/handoff", tags=["handoff"])

# ~10MB response size guard (`docs/ai/deployment_integration_plan.md` R1) —
# base64 inflates bytes by ~4/3, so this caps the PRE-encode PDF byte size.
_PDF_SIZE_GUARD_BYTES = 10 * 1024 * 1024

_MAX_REGENERATE_ATTEMPTS = 2


def _get_handoff_agent(
    model_router: ModelRouter = Depends(get_model_router),
    prompt_loader: PromptLoader = Depends(get_prompt_loader),
) -> HandoffGeneratorAgent:
    return HandoffGeneratorAgent(model_router=model_router, prompt_loader=prompt_loader)


def _get_verifier_agent() -> EvidenceVerifierAgent:
    return EvidenceVerifierAgent()


@router.post("/generate", response_model=HandoffOutput)
async def generate(
    body: HandoffInput,
    handoff_agent: HandoffGeneratorAgent = Depends(_get_handoff_agent),
    verifier: EvidenceVerifierAgent = Depends(_get_verifier_agent),
) -> HandoffOutput:
    """Generate a handoff report, then verify evidence integrity.

    If the verifier says ``regenerate``, the report is regenerated up to
    ``_MAX_REGENERATE_ATTEMPTS`` times. If it says ``reject``, a 422 is returned.
    """
    if not body.request_id:
        body.request_id = str(uuid.uuid4())

    logger.info(
        "Handoff generate request_id=%s session_id=%s",
        body.request_id,
        body.session_id,
    )

    last_result: HandoffOutput | None = None

    for attempt in range(1 + _MAX_REGENERATE_ATTEMPTS):
        try:
            result = await handoff_agent.run(body)
        except Exception as exc:
            logger.error("Handoff generation failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=500, detail="Handoff report generation failed"
            ) from exc

        last_result = result

        # Verify
        # BUG-069 fix: `is_first_visit`/`has_scale_scores`/`has_ocr_documents`/
        # `prior_handoff_present` were previously never threaded through from
        # `body` here — the verifier's section-completeness and (new)
        # first-visit-trend checks silently ran against their Pydantic
        # defaults (`is_first_visit=True`, the rest `False`) regardless of
        # the REAL request.
        #
        # BUG-069 follow-up (F5 metadata enrichment, 2026-07-25):
        # `patient_gender`/`session_started_at`/`session_ended_at` are now
        # threaded through too — `HandoffInput` gained these optional fields
        # (apps/api's `_build_request` populates them from `PatientProfile.
        # gender`/`Session.created_at`/`Session.submitted_at` when
        # available). Passing them here upgrades the verifier's metadata
        # check from "any specific-looking assertion is fabricated" (the
        # `None` case, unchanged for callers that don't supply these) to a
        # real mismatch comparison, per `EvidenceVerifierInput`'s own
        # docstring.
        verifier_input = EvidenceVerifierInput(
            session_id=body.session_id,
            request_id=body.request_id,
            report_markdown=result.report_markdown,
            evidence_packets=result.evidence_packets,
            is_first_visit=body.is_first_visit,
            has_scale_scores=bool(body.scale_scores),
            has_ocr_documents=bool(body.ocr_documents),
            prior_handoff_present=bool(body.prior_handoff),
            patient_gender=body.patient_gender,
            session_started_at=body.session_started_at,
            session_ended_at=body.session_ended_at,
        )

        try:
            verification = await verifier.run(verifier_input)
        except Exception as exc:
            logger.warning("Evidence verification failed, returning unverified: %s", exc)
            break

        if verification.action == VerifierAction.passed:
            logger.info(
                "Handoff verified (attempt %d): latency=%.0fms",
                attempt + 1,
                result.latency_ms,
            )
            return result

        if verification.action == VerifierAction.reject:
            logger.warning(
                "Handoff REJECTED: %d issues — %s",
                len(verification.issues),
                [i.description for i in verification.issues],
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Handoff report rejected by evidence verifier",
                    "issues": [i.model_dump() for i in verification.issues],
                },
            )

        # regenerate
        logger.info(
            "Handoff needs regeneration (attempt %d/%d): %d issues",
            attempt + 1,
            1 + _MAX_REGENERATE_ATTEMPTS,
            len(verification.issues),
        )

    # Exhausted regeneration attempts — return the last result with a warning
    if last_result:
        last_result.requires_human_review = True
        last_result.reason_summary += " [WARNING: verification issues remain after regeneration]"
        return last_result

    raise HTTPException(status_code=500, detail="Handoff generation failed unexpectedly")


@router.post("/report", response_model=HandoffReportResponse)
async def report(body: HandoffReportRequest) -> HandoffReportResponse:
    """Stateless F4+F5 hand-off report — `body.sessions` mirrors the
    session-ledger entry shape; F4's longitudinal analysis is ALWAYS
    recomputed internally from `body.sessions` here (never accepted
    pre-computed), so this endpoint and `POST /ai/temporal/analyze` can
    never silently disagree about the same input series. This route never
    reads a ledger file or any other server-side session state (R2).
    """
    if len(body.sessions) < 2:
        raise HTTPException(
            status_code=422,
            detail=(
                "F5's own B-section consumes F4's longitudinal output verbatim, which "
                f"itself requires >=2 sessions (got {len(body.sessions)})"
            ),
        )
    sessions = sorted_sessions(body.sessions)
    header = sessions[-1]

    # BUG-055 fail-loud (Option B, ADR-046 #1): a session that triggered
    # crisis or was flagged for the ADR-044 clinical-escalation backstop
    # MUST carry an explicit `risk_assessment` string on this request — a
    # silently-absent value here is exactly BUG-055's original fail-silent
    # mechanism (the field did not exist at all before this fix). Hard 422,
    # never a quiet None-pass-through. This is an assembly-time contract
    # check only — SafetyClassifier's own live safety path (crisis
    # interception during `/ai/chat/respond`) is entirely unaffected.
    fail_loud_sessions = [
        s.session_index
        for s in sessions
        if (s.crisis_triggered or s.clinical_escalation_required)
        and not (s.risk_assessment and s.risk_assessment.strip())
    ]
    if fail_loud_sessions:
        raise HTTPException(
            status_code=422,
            detail=(
                "BUG-055 fail-loud: session_index "
                f"{fail_loud_sessions} triggered crisis or clinical "
                "escalation but carry no risk_assessment on the wire — the "
                "caller must thread session_state.slot_data.risk_assessment "
                "(ChatResponse.session_state, contract1) into "
                "LongitudinalSessionEntry.risk_assessment for that session "
                "before calling /ai/handoff/report."
            ),
        )

    series_input = build_series_input(body.vp_id, sessions)
    try:
        longitudinal = f4.analyze_longitudinal_series(series_input)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    chart_filenames = f5.ChartFilenames()
    chart_png_bytes: dict[str, bytes] = {}
    if body.include_charts:
        chart_filenames, chart_png_bytes = generate_charts_in_memory(longitudinal)

    all_f3 = tuple(
        sorted(
            (a for a in (build_f3_administration(e) for e in sessions) if a is not None),
            key=lambda a: a.session_index,
        )
    )
    current_f3 = next((a for a in all_f3 if a.session_index == header.session_index), None)

    handoff_input = f5.HandoffReportInput(
        vp_id=body.vp_id,
        session=build_session_snapshot(header),
        current_session_f3=current_f3,
        all_f3_administrations=all_f3,
        domain_inference=build_domain_inference_snapshot(body.domain_inference),
        longitudinal=longitudinal,
        chart_filenames=chart_filenames,
        all_sessions=build_all_sessions(sessions),
        narrative_enabled=body.narrative_enabled,
        narrative_text=body.narrative_text,
    )
    try:
        handoff_report = f5.assemble_handoff_report(handoff_input)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    report_markdown = build_markdown_report(handoff_report)
    fhir_bundle = build_fhir_bundle(handoff_report)

    pdf_base64: str | None = None
    pdf_omitted_reason: str | None = None
    chart_pngs_base64 = {
        key: base64.b64encode(png).decode("ascii") for key, png in chart_png_bytes.items()
    }

    if body.include_pdf:
        chart_paths: dict[str, Path] = {}

        with tempfile.TemporaryDirectory(prefix="ns_handoff_pdf_") as tmp:
            tmp_dir = Path(tmp)
            for key, png in chart_png_bytes.items():
                path = tmp_dir / f"{key}.png"
                path.write_bytes(png)
                chart_paths[key] = path
            try:
                pdf_bytes = build_pdf_report(handoff_report, chart_paths)
            except RuntimeError as exc:
                # Missing/mismatched embedded Korean font asset (ADR-038
                # Decision 1 / BUG-044) — an honest 500, never a silently
                # PDF-less response with no explanation.
                logger.error("Handoff report PDF build failed: %s", exc)
                raise HTTPException(status_code=500, detail=str(exc)) from exc

        if len(pdf_bytes) > _PDF_SIZE_GUARD_BYTES:
            pdf_omitted_reason = (
                f"PDF is {len(pdf_bytes)} bytes, exceeding the "
                f"{_PDF_SIZE_GUARD_BYTES} byte response size guard — omitted. "
                "report_markdown/fhir_bundle are unaffected."
            )
            logger.warning(
                "Handoff report PDF omitted (size guard): vp_id=%s bytes=%d",
                body.vp_id, len(pdf_bytes),
            )
        else:
            pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")

    return HandoffReportResponse(
        vp_id=body.vp_id,
        report_markdown=report_markdown,
        fhir_bundle=fhir_bundle,
        pdf_base64=pdf_base64,
        pdf_omitted_reason=pdf_omitted_reason,
        chart_pngs_base64=chart_pngs_base64,
    )
