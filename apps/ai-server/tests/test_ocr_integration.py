"""Integration test — OCRAgent + SolarDocumentParseAdapter against VP-001~004.

Runs the full agent chain (adapter → response parsing → clinical summary) and
verifies the extraction meets 07_ocr.md contract.

Run directly (not via pytest, because it hits the real API):
    cd apps/ai-server
    .venv/bin/python -m tests.test_ocr_integration
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.dependencies import get_ocr_agent
from src.schemas.ocr import OCRInput

REPO_ROOT = Path(__file__).resolve().parents[3]
OCR_FIXTURES_DIR = REPO_ROOT / "apps" / "ai-server" / "tests" / "fixtures" / "ocr"


def _pdfs() -> list[Path]:
    return sorted(OCR_FIXTURES_DIR.glob("VP-*/VP-*_ocr.pdf"))


async def _run_one(agent, pdf_path: Path) -> dict:
    vp_id = pdf_path.parent.name
    meta = OCRInput(
        session_id=f"ocr_test_{vp_id}",
        patient_id=f"pt_{vp_id.lower()}",
        document_type_hint="diagnosis",  # These are all diagnosis certificates
        filename=pdf_path.name,
        confidence_threshold=0.8,
    )
    document = pdf_path.read_bytes()
    result = await agent.parse(document, meta)

    return {
        "vp_id": vp_id,
        "file": pdf_path.name,
        "doc_type_detected": result.document_type,
        "blocks": len(result.blocks),
        "low_confidence": len(result.low_confidence_items),
        "pages": result.page_count,
        "elements": result.element_count,
        "latency_ms": result.latency_ms,
        "summary": {
            "diagnoses": result.extracted_summary.diagnoses,
            "diagnosis_codes": result.extracted_summary.diagnosis_codes,
            "medications_count": len(result.extracted_summary.medications),
            "medications_preview": [
                f"{m.name} {m.dose}"
                for m in result.extracted_summary.medications[:3]
            ],
            "department": result.extracted_summary.department,
            "dates": result.extracted_summary.dates[:3],
            "scale_scores": result.extracted_summary.scale_scores,
            "patient_name": result.extracted_summary.patient_name,
            "patient_age": result.extracted_summary.patient_age,
            "patient_gender": result.extracted_summary.patient_gender,
        },
        "raw_md_chars": len(result.raw_markdown),
        "raw_text_chars": len(result.raw_text),
        "block_categories": _count_categories(result.blocks),
        "output": result,
    }


def _count_categories(blocks) -> dict[str, int]:
    counts: dict[str, int] = {}
    for b in blocks:
        counts[b.category] = counts.get(b.category, 0) + 1
    return counts


def _assert_contract(row: dict) -> list[str]:
    """Return list of contract violations (empty if all pass)."""
    violations: list[str] = []
    r = row["output"]

    if r.document_type != "diagnosis":
        violations.append(f"doc_type={r.document_type}, expected diagnosis")

    if len(r.blocks) == 0:
        violations.append("blocks empty")

    if r.raw_text.strip() == "":
        violations.append("raw_text empty")

    if r.page_count <= 0:
        violations.append(f"page_count={r.page_count}")

    # All 4 PDFs are diagnosis certs → should extract at least patient name
    if not r.extracted_summary.patient_name:
        violations.append("patient_name not extracted")

    # ICD codes expected in diagnosis
    if not r.extracted_summary.diagnosis_codes:
        violations.append("no ICD/KCD codes extracted")

    # Every block has valid confidence
    for b in r.blocks:
        if not (0.0 <= b.confidence <= 1.0):
            violations.append(f"block {b.block_id} confidence={b.confidence}")

    # needs_verification consistent with threshold
    for b in r.blocks:
        expected = b.confidence < 0.8
        if b.needs_verification != expected:
            violations.append(f"block {b.block_id} needs_verify mismatch")

    return violations


async def main() -> int:
    load_dotenv()
    agent = get_ocr_agent()
    pdfs = _pdfs()

    if not pdfs:
        print(f"[ERR] no PDFs found in {OCR_FIXTURES_DIR}", file=sys.stderr)
        return 1

    print("=== OCR Agent Integration Test ===")
    print(f"Agent:   {agent.agent_name}")
    print(f"Adapter: {agent._adapter.adapter_name}")
    print(f"PDFs:    {len(pdfs)}")
    print()

    all_pass = True
    rows: list[dict] = []
    for pdf in pdfs:
        try:
            row = await _run_one(agent, pdf)
        except Exception as exc:
            print(f"[{pdf.parent.name}] EXCEPTION: {exc}")
            all_pass = False
            continue

        violations = _assert_contract(row)
        status = "PASS" if not violations else "FAIL"
        if violations:
            all_pass = False

        vp = row["vp_id"]
        s = row["summary"]
        print(f"[{vp}] {status} — {row['latency_ms']:.0f}ms")
        print(f"  doc_type:       {row['doc_type_detected']}")
        print(f"  pages/elements: {row['pages']} / {row['elements']}")
        print(f"  blocks:         {row['blocks']} (categories: {row['block_categories']})")
        print(f"  needs_verify:   {row['low_confidence']}")
        print(f"  patient:        {s['patient_name']} / {s['patient_age']} / {s['patient_gender']}")
        print(f"  department:     {s['department']}")
        print(f"  ICD codes:      {s['diagnosis_codes']}")
        print(f"  diagnoses:      {s['diagnoses']}")
        print(f"  medications:    {s['medications_count']} → {s['medications_preview']}")
        print(f"  scale_scores:   {s['scale_scores']}")
        print(f"  dates:          {s['dates']}")
        if violations:
            print("  VIOLATIONS:")
            for v in violations:
                print(f"    ✗ {v}")

        # Persist agent output for record
        out_path = pdf.parent / f"{pdf.stem}_agent_output.json"
        out_path.write_text(
            json.dumps(row["output"].model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  saved: {out_path.name}")
        print()
        rows.append(row)

    print("=== Summary ===")
    print(f"  {'PASS' if all_pass else 'FAIL'} — {len(rows)}/{len(pdfs)} PDFs")
    if rows:
        total_ms = sum(r["latency_ms"] for r in rows)
        avg = total_ms / len(rows)
        print(f"  avg latency: {avg:.0f}ms  (max {max(r['latency_ms'] for r in rows):.0f}ms)")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
