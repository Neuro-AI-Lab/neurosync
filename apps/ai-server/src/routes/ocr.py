"""POST /ai/ocr/parse — Document OCR endpoint.

Accepts multipart upload (file + form fields), calls Upstage Document Parse
via OCRAgent, returns structured extraction (blocks + clinical summary).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from src.agents.ocr import OCRAgent
from src.dependencies import get_ocr_agent
from src.schemas.ocr import DocumentType, OCRInput, OCROutput

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/ocr", tags=["ocr"])

# Upstage limits: 50MB max, sync mode 100 pages max
_MAX_FILE_BYTES = 50 * 1024 * 1024
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/bmp",
    "image/tiff",
    "image/heic",
    # Office formats accepted by Upstage
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",  # fall-through for uncommon PDFs
}


@router.post("/parse", response_model=OCROutput)
async def parse_document(
    document: UploadFile = File(..., description="PDF or image file"),
    session_id: str = Form(...),
    patient_id: str = Form(...),
    document_type_hint: DocumentType = Form("unknown"),
    confidence_threshold: float = Form(0.8, ge=0.0, le=1.0),
    request_id: str | None = Form(None),
    agent: OCRAgent = Depends(get_ocr_agent),
) -> OCROutput:
    """Parse a medical document (진단서/처방전/etc.)."""
    if not request_id:
        request_id = str(uuid.uuid4())

    # Content-type gate (be lenient — some browsers send application/octet-stream)
    content_type = document.content_type or "application/octet-stream"
    if content_type not in _ALLOWED_CONTENT_TYPES:
        logger.warning(
            "OCR request %s: unusual content-type %s (filename=%s), proceeding",
            request_id, content_type, document.filename,
        )

    # Read + size check
    body = await document.read()
    if len(body) == 0:
        raise HTTPException(status_code=400, detail="Empty document")
    if len(body) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Document exceeds 50MB limit ({len(body):,} bytes)",
        )

    filename = document.filename or "document.pdf"
    logger.info(
        "OCR parse request_id=%s session_id=%s patient_id=%s file=%s (%d bytes) hint=%s",
        request_id, session_id, patient_id, filename, len(body), document_type_hint,
    )

    meta = OCRInput(
        session_id=session_id,
        request_id=request_id,
        patient_id=patient_id,
        document_type_hint=document_type_hint,
        filename=filename,
        confidence_threshold=confidence_threshold,
    )

    try:
        result = await agent.parse(body, meta, content_type=content_type)
    except Exception as exc:
        logger.error("OCR parse failed request_id=%s: %s", request_id, exc, exc_info=True)
        raise HTTPException(status_code=502, detail="OCR upstream failure") from exc

    logger.info(
        "OCR parse result request_id=%s: type=%s blocks=%d needs_verify=%d latency=%.0fms",
        request_id, result.document_type, len(result.blocks),
        len(result.low_confidence_items), result.latency_ms,
    )
    return result
