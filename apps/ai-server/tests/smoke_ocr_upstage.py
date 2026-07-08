"""Smoke test — Upstage Document Parse API against VP-001~004 진단서 PDFs.

OCR 어댑터/에이전트/라우트 구현 전, 벤더 API 자체가 대상 문서에
정상 동작하는지 기능 검증한다. 결과는 각 PDF 옆에 저장한다.

실행:
    cd apps/ai-server
    .venv/bin/python -m tests.smoke_ocr_upstage
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from src.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
SIMULATION_DIR = REPO_ROOT / "docs" / "ai" / "simulation_results"


def find_pdfs() -> list[Path]:
    return sorted(SIMULATION_DIR.glob("VP-*/VP-*_ocr.pdf"))


def parse_document(pdf_path: Path, settings: Settings) -> dict:
    """Call POST /v1/document-digitization with model=document-parse."""
    url = f"{settings.upstage_base_url.rstrip('/')}/document-digitization"
    headers = {"Authorization": f"Bearer {settings.upstage_api_key}"}

    with pdf_path.open("rb") as fh:
        files = {"document": (pdf_path.name, fh, "application/pdf")}
        data = {
            "model": settings.upstage_document_parse_model
            if hasattr(settings, "upstage_document_parse_model")
            else "document-parse",
            "ocr": "auto",
            "output_formats": '["markdown","text","html"]',
            "coordinates": "true",
            "chart_recognition": "true",
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, headers=headers, files=files, data=data)

    if resp.status_code != 200:
        return {
            "ok": False,
            "status": resp.status_code,
            "error": resp.text[:500],
        }

    body = resp.json()
    return {"ok": True, "body": body}


def summarize(body: dict) -> dict:
    """Extract high-level stats from Document Parse response."""
    content = body.get("content", {})
    elements = body.get("elements", [])
    usage = body.get("usage", {})

    text = content.get("text", "") if isinstance(content, dict) else ""
    md = content.get("markdown", "") if isinstance(content, dict) else ""
    html = content.get("html", "") if isinstance(content, dict) else ""

    categories: dict[str, int] = {}
    for el in elements:
        cat = el.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "pages": usage.get("pages"),
        "num_elements": len(elements),
        "categories": categories,
        "text_chars": len(text),
        "markdown_chars": len(md),
        "html_chars": len(html),
        "text_preview": text[:400],
        "markdown_preview": md[:400],
    }


def main() -> int:
    load_dotenv()
    settings = Settings()

    if not settings.upstage_api_key:
        print("[ERR] UPSTAGE_API_KEY 미설정 — .env 확인", file=sys.stderr)
        return 1

    pdfs = find_pdfs()
    if not pdfs:
        print(f"[ERR] PDF 없음 in {SIMULATION_DIR}", file=sys.stderr)
        return 1

    print(f"=== Upstage Document Parse Smoke Test ===")
    print(f"Base URL: {settings.upstage_base_url}")
    print(f"Model:    document-parse")
    print(f"PDFs:     {len(pdfs)}")
    print()

    overall_ok = True
    for pdf_path in pdfs:
        vp_id = pdf_path.parent.name
        print(f"[{vp_id}] {pdf_path.name}")
        started = time.perf_counter()
        result = parse_document(pdf_path, settings)
        latency_ms = (time.perf_counter() - started) * 1000

        if not result["ok"]:
            print(f"  ✗ FAIL — HTTP {result['status']}")
            print(f"    error: {result['error']}")
            overall_ok = False
            continue

        body = result["body"]
        stats = summarize(body)
        print(f"  ✓ 200 OK — {latency_ms:.0f}ms")
        print(f"    pages:        {stats['pages']}")
        print(f"    elements:     {stats['num_elements']}")
        print(f"    categories:   {stats['categories']}")
        print(f"    text_chars:   {stats['text_chars']}")
        print(f"    md_chars:     {stats['markdown_chars']}")
        print(f"    text preview: {stats['text_preview'][:150].replace(chr(10), ' ')}...")

        # Persist full raw response + summary next to the PDF
        stem = pdf_path.stem
        out_json = pdf_path.parent / f"{stem}_upstage_raw.json"
        out_summary = pdf_path.parent / f"{stem}_upstage_summary.md"

        out_json.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")

        md_report = (
            f"# Upstage Document Parse — {pdf_path.name}\n\n"
            f"- pages: {stats['pages']}\n"
            f"- elements: {stats['num_elements']}\n"
            f"- categories: {stats['categories']}\n"
            f"- latency_ms: {latency_ms:.0f}\n\n"
            f"## Markdown Output\n\n{body.get('content', {}).get('markdown', '')}\n\n"
            f"## Text Output\n\n```\n{body.get('content', {}).get('text', '')}\n```\n"
        )
        out_summary.write_text(md_report, encoding="utf-8")
        print(f"    saved: {out_summary.name}, {out_json.name}")
        print()

    print("=== Summary ===")
    print(f"  {'PASS' if overall_ok else 'FAIL'} — {len(pdfs)} PDFs tested")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
