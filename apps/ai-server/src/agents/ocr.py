"""OCR Document agent — Upstage Document Parse → structured blocks + summary.

Contract: docs/ai/agents/07_ocr.md.
Not an LLM agent — the adapter itself does the extraction. This agent adds
domain-specific structuring: block classification, confidence gating, and
clinical summary aggregation (diagnoses, medications, dates, scale scores).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any

from src.adapters.solar_document_parse import SolarDocumentParseAdapter
from src.agents.base import BaseAgent
from src.schemas.ocr import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_VERIFY,
    BoundingBox,
    DocumentType,
    ExtractedSummary,
    LowConfidenceItem,
    Medication,
    OCRBlock,
    OCRInput,
    OCROutput,
)

logger = logging.getLogger(__name__)

_PROMPT_VERSION = "v1"

# ── Document type detection ──────────────────────────────────────────

_TYPE_KEYWORDS: dict[DocumentType, list[str]] = {
    "diagnosis": ["진단서", "임상적 추정", "최종 진단", "한국질병분류번호", "발병연월일"],
    "prescription": ["처방전", "용법", "일수", "1일 투여량", "총투여량", "조제"],
    "consultation": ["상담기록", "상담일지", "회기", "상담 내용"],
    "lab_result": ["검사결과", "검사 결과", "참고범위", "정상범위", "판독"],
}


# ── Clinical field extraction patterns ────────────────────────────────

# KCD-8 / ICD-10 codes: F41.9, F32.9, F51.0, F419 (no dot), etc.
# Korean forms often drop the decimal (F419 == F41.9). Match both.
_ICD_PATTERN = re.compile(r"\b([A-Z]\d{2}\.\d{1,2}|[A-Z]\d{3,4})\b")

# Dates: 2026-07-07 / 2026.07.07 / 2026년 7월 7일 / 26년 7월 7일
_DATE_PATTERNS = [
    re.compile(r"\d{4}[-./]\s?\d{1,2}[-./]\s?\d{1,2}"),
    re.compile(r"\d{4}\s?년\s?\d{1,2}\s?월\s?\d{1,2}\s?일"),
    re.compile(r"\d{2}\s?년\s?\d{1,2}\s?월\s?\d{1,2}\s?일"),
]

# Clinical scale scores: PHQ-9 7점 / GAD-7 8점 / K-MMSE 24점
_SCALE_PATTERN = re.compile(
    r"(PHQ-?9|GAD-?7|PHQ-?4|WHO-?5|AUDIT-?C|K-?MMSE|BDI|BAI)\s*[:：]?\s*(\d{1,2})\s*점?",
    re.IGNORECASE,
)

# Department: "정신건강의학과", "내과", "가정의학과", etc.
_DEPT_PATTERN = re.compile(r"[가-힣]+(?:의학과|건강의학과|건강과|내과|외과|정신과)")

# Medication (very rough — will be refined by future normalization pass)
# Matches "약물명 용량단위 [빈도]"
_MED_DOSAGE_PATTERN = re.compile(
    r"([가-힣A-Za-z][가-힣A-Za-z\s]{1,30})\s+(\d+(?:\.\d+)?\s?(?:mg|g|정|캡슐|ml|㎎))",
    re.IGNORECASE,
)

# Common Korean patient info fields.
# Support both freeform ("성명: 김서연") and table-cell ("| 성명 | 김서연 |") forms.
_NAME_PATTERN = re.compile(
    r"(?:환자\s*)?성명\s*(?:[:：]|\|)\s*([가-힣]{2,4})"
)
_AGE_PATTERN = re.compile(r"(?:만\s*)?(\d{1,3})\s*세")
_GENDER_PATTERN = re.compile(
    r"성별\s*(?:[:：]|\|)\s*(남성|여성|남|여)"
)


class OCRAgent(BaseAgent):
    """Structures Upstage Document Parse output for clinical downstream use."""

    def __init__(self, adapter: SolarDocumentParseAdapter) -> None:
        self._adapter = adapter

    @property
    def agent_name(self) -> str:
        return "ocr_agent"

    async def run(self, inp: Any, **kwargs: Any) -> OCROutput:
        raise NotImplementedError("Use OCRAgent.parse(document_bytes, meta) directly")

    async def parse(
        self,
        document: bytes,
        meta: OCRInput,
        *,
        content_type: str = "application/pdf",
    ) -> OCROutput:
        """Parse a document and return structured clinical extraction."""
        start = time.perf_counter()

        try:
            raw = await self._adapter.parse(
                document,
                filename=meta.filename,
                content_type=content_type,
            )
        except Exception as exc:
            logger.error("OCR adapter failed: %s", exc)
            return self._empty_output(
                meta,
                reason=f"adapter_failure: {type(exc).__name__}",
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        content = raw.get("content", {}) or {}
        elements = raw.get("elements", []) or []
        usage = raw.get("usage", {}) or {}

        raw_text = content.get("text", "") if isinstance(content, dict) else ""
        raw_markdown = content.get("markdown", "") if isinstance(content, dict) else ""

        # 1. Structure elements → OCRBlocks
        blocks = self._structure_blocks(elements, meta.confidence_threshold)

        # 2. Detect document type (unless hinted)
        doc_type = (
            meta.document_type_hint
            if meta.document_type_hint != "unknown"
            else self._detect_document_type(raw_text)
        )

        # 3. Extract clinical summary
        summary = self._build_summary(raw_text, raw_markdown, blocks)

        # 4. Collect low-confidence items per 4-tier gate (spec §Confidence Threshold)
        low_conf: list[LowConfidenceItem] = []
        for b in blocks:
            if b.confidence >= CONFIDENCE_HIGH:
                continue  # ≥ 0.9: clean, no flagging
            if b.confidence >= CONFIDENCE_LOW:
                severity, msg = "info", "정보 신뢰도 다소 낮음"
            elif b.confidence >= CONFIDENCE_VERIFY:
                severity, msg = "verify", "확인 필요"
            else:
                severity, msg = "retry", "OCR 신뢰도 매우 낮음 — 재시도 권장"
            low_conf.append(
                LowConfidenceItem(
                    block_id=b.block_id,
                    field=b.field,
                    value=b.value[:120],
                    confidence=b.confidence,
                    severity=severity,
                    message=msg,
                )
            )

        latency_ms = (time.perf_counter() - start) * 1000

        return OCROutput(
            session_id=meta.session_id,
            patient_id=meta.patient_id,
            document_type=doc_type,
            blocks=blocks,
            extracted_summary=summary,
            low_confidence_items=low_conf,
            raw_markdown=raw_markdown,
            raw_text=raw_text,
            page_count=usage.get("pages", 0) or 0,
            element_count=len(elements),
            timestamp=datetime.now().isoformat(),
            model_used="document-parse",
            prompt_version=_PROMPT_VERSION,
            latency_ms=latency_ms,
            reason_summary=(
                f"parsed {len(elements)} elements → {len(blocks)} blocks, "
                f"{len(low_conf)} flagged (verify/retry: "
                f"{sum(1 for lc in low_conf if lc.severity in ('verify', 'retry'))})"
            ),
        )

    # ── Structuring helpers ─────────────────────────────────────────

    def _structure_blocks(
        self, elements: list[dict[str, Any]], threshold: float
    ) -> list[OCRBlock]:
        """Convert Upstage elements into typed OCRBlocks.

        Upstage does not expose per-element confidence, so we synthesize one:
        - table/heading elements: 0.95
        - paragraph: 0.90
        - unknown/other: 0.70
        - Downgrade to 0.60 when the element category is 'figure' or 'chart'
          (visual, harder to trust).
        """
        blocks: list[OCRBlock] = []
        for i, el in enumerate(elements):
            category = el.get("category", "unknown")
            confidence = _synthesize_confidence(category)
            value = self._extract_element_text(el)
            if not value:
                continue
            bbox = self._extract_bbox(el)

            # 4-tier gate per spec §Confidence Threshold.
            # `threshold` acts as a legacy override for the "needs_verification"
            # boundary but the spec's fixed tiers below still shape output.
            if confidence < CONFIDENCE_VERIFY:
                # Very low confidence — null out value, mark for retry
                out_value = ""
                needs_verify = True
            elif confidence < CONFIDENCE_LOW:
                out_value = value
                needs_verify = True
            else:
                out_value = value
                # Caller-tuned threshold can still flag mid-range values.
                needs_verify = confidence < threshold

            block = OCRBlock(
                block_id=f"blk_{i+1:03d}",
                field=category,  # semantic labeling happens in summary aggregation
                value=out_value,
                confidence=confidence,
                bounding_box=bbox,
                needs_verification=needs_verify,
                source="ocr_extracted",  # spec §핵심 구분 — AI 진단 아님을 강제 표기
                category=category,
            )
            blocks.append(block)
        return blocks

    @staticmethod
    def _extract_element_text(el: dict[str, Any]) -> str:
        content = el.get("content", {})
        if isinstance(content, dict):
            for key in ("markdown", "text", "html"):
                v = content.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        if isinstance(content, str):
            return content.strip()
        return ""

    @staticmethod
    def _extract_bbox(el: dict[str, Any]) -> BoundingBox | None:
        coords = el.get("coordinates")
        if not coords or not isinstance(coords, list) or len(coords) < 2:
            return None
        try:
            xs = [float(p["x"]) for p in coords if isinstance(p, dict) and "x" in p]
            ys = [float(p["y"]) for p in coords if isinstance(p, dict) and "y" in p]
            if not xs or not ys:
                return None
            return BoundingBox(
                x=min(xs),
                y=min(ys),
                width=max(xs) - min(xs),
                height=max(ys) - min(ys),
                page=int(el.get("page", 1)),
            )
        except (KeyError, ValueError, TypeError):
            return None

    # ── Document type detection ────────────────────────────────────

    @staticmethod
    def _detect_document_type(text: str) -> DocumentType:
        scores: dict[DocumentType, int] = {}
        for dtype, keywords in _TYPE_KEYWORDS.items():
            scores[dtype] = sum(1 for kw in keywords if kw in text)
        if not scores or max(scores.values()) == 0:
            return "unknown"
        return max(scores, key=scores.get)  # type: ignore[arg-type]

    # ── Clinical summary aggregation ────────────────────────────────

    def _build_summary(
        self, raw_text: str, raw_markdown: str, blocks: list[OCRBlock]
    ) -> ExtractedSummary:
        summary = ExtractedSummary()

        # ICD/KCD codes
        for m in _ICD_PATTERN.finditer(raw_text):
            code = m.group(1)
            if code not in summary.diagnosis_codes:
                summary.diagnosis_codes.append(code)

        # Diagnoses — heuristic: capture text after "(주상병)" or "(부상병)"
        for match in re.finditer(r"\(([주부]상병)\)\s*([^\n(]+?)(?=[FA-Z]\d{2}|$|\()", raw_text):
            dx = match.group(2).strip()
            # Strip table pipe separators and trailing punctuation
            dx = dx.rstrip("| \t,.;").strip()
            if dx and dx not in summary.diagnoses:
                summary.diagnoses.append(dx)

        # Dates
        for pat in _DATE_PATTERNS:
            for m in pat.finditer(raw_text):
                date_str = m.group(0)
                if date_str not in summary.dates:
                    summary.dates.append(date_str)

        # Clinical scale scores
        for m in _SCALE_PATTERN.finditer(raw_text):
            scale = m.group(1).upper().replace("-", "").replace(" ", "")
            # Normalize (PHQ9 → PHQ-9)
            if scale == "PHQ9":
                scale = "PHQ-9"
            elif scale == "GAD7":
                scale = "GAD-7"
            elif scale == "PHQ4":
                scale = "PHQ-4"
            elif scale == "WHO5":
                scale = "WHO-5"
            elif scale == "AUDITC":
                scale = "AUDIT-C"
            score = int(m.group(2))
            summary.scale_scores[scale] = score

        # Department
        dept_match = _DEPT_PATTERN.search(raw_text)
        if dept_match:
            summary.department = dept_match.group(0)

        # Medications
        seen_meds: set[str] = set()
        for m in _MED_DOSAGE_PATTERN.finditer(raw_text):
            name = m.group(1).strip()
            dose = m.group(2).strip()
            # Filter out common false positives (numeric-heavy)
            if len(name) < 2 or name.isdigit():
                continue
            key = f"{name}|{dose}"
            if key in seen_meds:
                continue
            seen_meds.add(key)
            summary.medications.append(
                Medication(name=name, dose=dose, confidence=0.75)
            )

        # Patient basics
        name_m = _NAME_PATTERN.search(raw_text)
        if name_m:
            summary.patient_name = name_m.group(1)
        age_m = _AGE_PATTERN.search(raw_text)
        if age_m:
            summary.patient_age = f"만 {age_m.group(1)}세"
        gender_m = _GENDER_PATTERN.search(raw_text)
        if gender_m:
            g = gender_m.group(1)
            if g in ("남성", "여성"):
                summary.patient_gender = g
            else:
                summary.patient_gender = "남성" if g == "남" else "여성"

        return summary

    # ── Empty output on adapter failure ─────────────────────────────

    @staticmethod
    def _empty_output(meta: OCRInput, reason: str, latency_ms: float) -> OCROutput:
        return OCROutput(
            session_id=meta.session_id,
            patient_id=meta.patient_id,
            document_type=meta.document_type_hint or "unknown",
            reason_summary=reason,
            latency_ms=latency_ms,
            timestamp=datetime.now().isoformat(),
            prompt_version=_PROMPT_VERSION,
        )


def _synthesize_confidence(category: str) -> float:
    """Map Upstage element category → synthesized confidence.

    Upstage doesn't expose per-element confidence, so we approximate based on
    category difficulty. Downstream code treats < 0.8 as needs_verification.
    """
    high = {"heading1", "heading2", "table", "paragraph", "list"}
    medium = {"caption", "footer", "header"}
    low = {"figure", "chart", "equation"}
    if category in high:
        return 0.92
    if category in medium:
        return 0.82
    if category in low:
        return 0.60
    return 0.70
