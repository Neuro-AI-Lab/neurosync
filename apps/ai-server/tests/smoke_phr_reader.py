"""PHR reader/parser 실 파일 검증 smoke test.

사용:
    cd apps/ai-server
    .venv/bin/python -m tests.smoke_phr_reader
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES_DIR = REPO_ROOT / "docs" / "ai" / "samples" / "phr"

from src.agents.patient_history import PatientHistoryAgent  # noqa: E402

PERSONAS = [
    ("VP-001", "김서연 (28F 초진 경증, 마포)"),
    ("VP-002", "이준호 (35M 재진 경증, 판교)"),
    ("VP-003", "박민수 (42M 초진 중증, 관악)"),
    ("VP-004", "최하은 (29F 재진 중증, 강서)"),
]


EXPECTED = {
    # (has_psy_history, min_meds, min_visits, expected_classes)
    "VP-001": (False, 3, 4, set()),
    "VP-002": (True, 4, 7, {"SSRI"}),
    "VP-003": (True, 3, 6, {"BENZO"}),  # 응급 로라제팜 1건
    "VP-004": (True, 8, 11, {"SSRI", "BENZO", "ZDRUG"}),
}


async def run_one(vp_id: str, name: str) -> dict:
    med_path = SAMPLES_DIR / f"{vp_id}_medications.json"
    vis_path = SAMPLES_DIR / f"{vp_id}_visits.json"
    if not med_path.is_file() or not vis_path.is_file():
        print(f"[{vp_id}] SKIP — sample missing")
        return {"vp_id": vp_id, "skipped": True}

    agent = PatientHistoryAgent()
    bundles = await agent.load_bundles([med_path, vis_path])
    summary = await agent.summarize(bundles)

    classes = sorted({m.psychotropic_class for m in summary.psychotropic_medications})
    print(f"\n=== [{vp_id}] {name} ===")
    print(f"  MHID={summary.patient.mhid} name_hash={summary.patient.name_hash}")
    print(f"  Medications: {summary.total_medication_events} "
          f"(psychotropic {len(summary.psychotropic_medications)})")
    print(f"  Visits: {summary.total_visits} (psychiatric-name {summary.psychiatric_visit_count})")
    print(f"  has_psychiatric_history={summary.has_psychiatric_history}")
    print(f"  classes={classes} · date_range={summary.date_range}")
    print(f"  System prompt note: {agent.to_system_prompt_note(summary)}")
    for m in summary.psychotropic_medications:
        print(f"    · {m.dispensed_at} {m.product_name} [{m.psychotropic_class}] "
              f"{m.days_supply}일 · {m.daily_frequency}회/일 · {m.dose_per_take}")

    # Assertions vs expected
    exp = EXPECTED.get(vp_id)
    if exp is not None:
        exp_has, exp_min_meds, exp_min_visits, exp_classes = exp
        assert summary.has_psychiatric_history == exp_has, (
            f"{vp_id}: has_psychiatric_history={summary.has_psychiatric_history}, "
            f"expected {exp_has}"
        )
        assert summary.total_medication_events >= exp_min_meds, (
            f"{vp_id}: medications={summary.total_medication_events} < {exp_min_meds}"
        )
        assert summary.total_visits >= exp_min_visits, (
            f"{vp_id}: visits={summary.total_visits} < {exp_min_visits}"
        )
        assert set(classes) == exp_classes, (
            f"{vp_id}: classes={set(classes)}, expected {exp_classes}"
        )
        print("  ✅ assertions passed")

    return {
        "vp_id": vp_id,
        "name": name,
        "has_psychiatric_history": summary.has_psychiatric_history,
        "medications": summary.total_medication_events,
        "psychotropic": len(summary.psychotropic_medications),
        "visits": summary.total_visits,
        "psychiatric_visits": summary.psychiatric_visit_count,
        "classes": classes,
        "date_range": (
            [summary.date_range[0].isoformat(), summary.date_range[1].isoformat()]
            if summary.date_range else None
        ),
    }


async def main() -> int:
    print("=" * 78)
    print("PHR Reader/Parser Smoke Test")
    print("=" * 78)
    results = []
    for vp_id, name in PERSONAS:
        try:
            results.append(await run_one(vp_id, name))
        except AssertionError as exc:
            print(f"  ✗ FAIL: {exc}")
            return 1

    out = SAMPLES_DIR / "smoke_summary.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== summary written to {out} ===")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
