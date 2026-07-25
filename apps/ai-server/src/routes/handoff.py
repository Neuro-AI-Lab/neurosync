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
from datetime import datetime
from pathlib import Path
from typing import assert_never

from contracts.handoff import HandoffRequest, HandoffResponse
from contracts.longitudinal import HandoffReportRequest, HandoffReportResponse
from fastapi import APIRouter, Depends, HTTPException

from src import f4, f5
from src.agents.handoff_contract_generator import (
    HandoffContractGenerator,
    HandoffContractValidationError,
    HandoffProviderError,
)
from src.dependencies import get_model_router, get_prompt_loader
from src.prompts.loader import PromptLoader
from src.routing.model_router import ModelRouter
from src.services.f5_pdf_boundary import PdfRendered, PdfRenderFailed, render_pdf
from src.services.f5_report import (
    build_fhir_bundle,
    build_markdown_report,
    build_pdf_report,
    validate_fhir_bundle,
)
from src.services.handoff_contract_adapter import adapt_handoff_request
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

def get_handoff_agent(
    model_router: ModelRouter = Depends(get_model_router),
    prompt_loader: PromptLoader = Depends(get_prompt_loader),
) -> HandoffContractGenerator:
    return HandoffContractGenerator(model_router=model_router, prompt_loader=prompt_loader)


@router.post("/generate", response_model=HandoffResponse)
async def generate(
    body: HandoffRequest,
    handoff_agent: HandoffContractGenerator = Depends(get_handoff_agent),
) -> HandoffResponse:
    """Generate the shared response contract and reject unverifiable citations."""
    local_input = adapt_handoff_request(body)
    try:
        return await handoff_agent.generate(body, local_input)
    except HandoffContractValidationError as exc:
        logger.warning("Handoff response rejected after validation retries")
        raise HTTPException(status_code=422, detail="Handoff response validation failed") from exc
    except HandoffProviderError as exc:
        logger.error("Handoff response provider failed")
        raise HTTPException(status_code=500, detail="Handoff report generation failed") from exc


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
        generated_at=datetime.now().astimezone().isoformat(),
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
    # The FHIR validator reads externally shaped nested JSON; keep ordinary
    # shape failures behind the same generic, PHI-free HTTP boundary.
    try:
        fhir_violations = validate_fhir_bundle(fhir_bundle)
    except Exception:
        fhir_violations = None
    if fhir_violations is None or fhir_violations:
        violation_count = 1 if fhir_violations is None else len(fhir_violations)
        logger.error(
            "Handoff report FHIR validation failed: violation_count=%d",
            violation_count,
        )
        raise HTTPException(
            status_code=500,
            detail="Handoff report FHIR validation failed",
        ) from None

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
            match render_pdf(build_pdf_report, handoff_report, chart_paths):
                case PdfRendered(content=pdf_bytes):
                    pass
                case PdfRenderFailed():
                    logger.error("Handoff report PDF generation failed: pdf_status=failed")
                    raise HTTPException(
                        status_code=500,
                        detail="Handoff report PDF generation failed",
                    ) from None
                case unreachable:
                    assert_never(unreachable)

        if len(pdf_bytes) > _PDF_SIZE_GUARD_BYTES:
            pdf_omitted_reason = (
                f"PDF is {len(pdf_bytes)} bytes, exceeding the "
                f"{_PDF_SIZE_GUARD_BYTES} byte response size guard — omitted. "
                "report_markdown/fhir_bundle are unaffected."
            )
            logger.warning(
                "Handoff report PDF omitted by response size guard: "
                "pdf_status=omitted bytes=%d limit=%d",
                len(pdf_bytes),
                _PDF_SIZE_GUARD_BYTES,
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
