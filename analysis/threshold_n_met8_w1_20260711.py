"""Threshold N (slot-insufficiency, Policy A trigger) + THRESHOLD_1b (MET-8) basis.

REV-022 precondition (discussion.md), front-loaded to W1 per PLAN-2026-W28-Q's
W0 status ("data's threshold-N + THRESHOLD_1b computation FRONT-LOADED from W4
to W1 ... so ADR-023's scheduling rule is honored before any experiments-dir
archival").

Read-only. Reads only harness/eval artifacts already on disk under
`experiments/EXP-008`, `experiments/EXP-009`, `experiments/EXP-011`,
`experiments/EXP-012` (domain_inference.json outputs + EXP-012's metrics.json)
and the production risk lexicon `apps/ai-server/src/eval/f2_grounding.py`'s
`_RISK_PHRASES`. No golden-label file (DATASET-004/006) is read or used —
N and THRESHOLD_1b must not encode golden answers (leakage discipline).

`retrieval_meta.queries` in each `domain_inference.json` is built directly by
`f2.py` from `final_slots["chief_complaint"]` + `final_slots["history_of_present_illness"]`
(`_STAGE1_QUERY_SLOTS = ("chief_complaint", "history_of_present_illness")`,
`apps/ai-server/src/f2.py:82,174,863`) — reading `queries` is therefore
equivalent to reading the cc+HPI slot values themselves, without touching any
F1 conversation transcript directly.

EXP-008/009/011 reuse byte-identical 2026-07-07-era F1 conversation inputs
(confirmed by each EXP's own config.yaml sha256 verification), so the same
underlying VP+run combination produces IDENTICAL combined-length values
across all three EXPs. Pooling all 24 persona-run records as independent
observations therefore triplicate-weights 8 of the 12 genuinely distinct
sessions. This script reports BOTH the raw pooled-24 set (as literally named
in REV-022's instruction) and a deduplicated distinct-12 set (8 reused
sessions, first occurrence only, + 4 fresh EXP-012 sessions) as the
statistically primary basis.

Run: cd /home/neuroai/users/dhkim/aichampion/neurosync && \
  apps/ai-server/.venv/bin/python3 analysis/threshold_n_met8_w1_20260711.py
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "ai-server" / "src"))

from eval.f2_grounding import _RISK_PHRASES  # noqa: E402


def risk_hits(text: str) -> list[str]:
    """Risk-lexicon stems (production `_RISK_PHRASES`) found in *text*."""
    return [p for p in _RISK_PHRASES if p in text]


def load_domain_inference_records(exp_id: str) -> list[dict]:
    pattern = str(REPO_ROOT / "experiments" / exp_id / "runs" / "*" / "*" / "*" / "*_domain_inference.json")
    files = sorted(glob.glob(pattern))
    records = []
    for f in files:
        d = json.loads(Path(f).read_text())
        rm = d.get("retrieval_meta", {})
        queries = rm.get("queries", [])
        rel = Path(f).relative_to(REPO_ROOT)
        vp = str(rel).split("runs/")[1].split("/")[0]
        run = str(rel).split("runs/")[1].split("/")[1]
        records.append(
            {
                "exp": exp_id,
                "path": str(rel),
                "vp": vp,
                "run": run,
                "queries": queries,
                "combined_len": sum(len(q) for q in queries),
                "risk_hits": [risk_hits(q) for q in queries],
            }
        )
    return records


def load_exp012_records() -> list[dict]:
    m = json.loads((REPO_ROOT / "experiments" / "EXP-012" / "metrics.json").read_text())
    records = []
    for vp, d in m.items():
        slots = {s["key"]: s["value"] for s in d["f1"]["final_slots"]}
        cc = slots.get("chief_complaint", "")
        hpi = slots.get("history_of_present_illness", "")
        queries = d["f2"]["retrieval_meta"]["queries"]
        records.append(
            {
                "exp": "EXP-012",
                "path": f"experiments/EXP-012/metrics.json[{vp}]",
                "vp": vp,
                "run": "fresh",
                "queries": queries,
                "combined_len": len(cc) + len(hpi),
                "risk_hits": [risk_hits(q) for q in queries],
            }
        )
    return records


def percentiles(values: list[int]) -> dict:
    return {
        "n": len(values),
        "min": min(values),
        "p25": float(np.percentile(values, 25)),
        "median": float(np.percentile(values, 50)),
        "p75": float(np.percentile(values, 75)),
        "max": max(values),
    }


def main() -> None:
    exp008 = load_domain_inference_records("EXP-008")
    exp009 = load_domain_inference_records("EXP-009")
    exp011 = load_domain_inference_records("EXP-011")
    exp012 = load_exp012_records()

    pooled = exp008 + exp009 + exp011 + exp012
    print(f"Pooled persona-runs (as literally named by REV-022): n={len(pooled)}")
    for exp, recs in [("EXP-008", exp008), ("EXP-009", exp009), ("EXP-011", exp011), ("EXP-012", exp012)]:
        lens = [r["combined_len"] for r in recs]
        print(f"  {exp}: {percentiles(lens)}")
    pooled_lens = [r["combined_len"] for r in pooled]
    print(f"  POOLED: {percentiles(pooled_lens)}")

    # Distinct-12: EXP-009's 8 records (first occurrence of the reused
    # 2026-07-07 inputs also present in EXP-008/EXP-011) + EXP-012's 4 fresh.
    distinct = exp009 + exp012
    distinct_lens = [r["combined_len"] for r in distinct]
    print(f"\nDistinct sessions (primary basis): n={len(distinct)}")
    print(f"  {percentiles(distinct_lens)}")
    for p in (10, 25, 50, 75, 90):
        print(f"  p{p} = {np.percentile(distinct_lens, p):.2f}")

    for N in (60, 75, 90):
        flagged = [l for l in distinct_lens if l < N]
        print(f"  N={N}: {len(flagged)}/{len(distinct_lens)} distinct sessions flagged insufficient -> {sorted(flagged)}")

    # Verify EXP-008/EXP-011 duplicate EXP-009 exactly for shared VP/run keys.
    def by_key(recs):
        return {f"{r['vp']}_{r['run']}": r["combined_len"] for r in recs}

    k009, k008, k011 = by_key(exp009), by_key(exp008), by_key(exp011)
    for k, v in k008.items():
        assert k009[k] == v, f"EXP-008/EXP-009 mismatch at {k}: {v} vs {k009[k]}"
    for k, v in k011.items():
        assert k009[k] == v, f"EXP-009/EXP-011 mismatch at {k}: {v} vs {k009[k]}"
    print("\nVerified: EXP-008 and EXP-011 combined-lengths are byte-identical to EXP-009 for every shared VP/run key (confirms reused-input non-independence).")

    # Risk-lexicon incidence (MET-8 baseline-path context; NOT the fallback/
    # judge-path THRESHOLD_1b measurement, which does not exist yet — Policy
    # A/B are unimplemented).
    print(f"\n_RISK_PHRASES: {len(_RISK_PHRASES)} raw entries (spaced+unspaced stem variants)")

    def incidence(recs, label):
        total_q = sum(len(r["queries"]) for r in recs)
        hit_q = sum(1 for r in recs for h in r["risk_hits"] if h)
        total_runs = len(recs)
        hit_runs = sum(1 for r in recs if any(r["risk_hits"]))
        print(f"  {label}: query-level {hit_q}/{total_q} = {hit_q/total_q:.3f}; run-level {hit_runs}/{total_runs} = {hit_runs/total_runs:.3f}")

    incidence(pooled, "pooled-24")
    incidence(distinct, "distinct-12")
    for exp, recs in [("EXP-008", exp008), ("EXP-009", exp009), ("EXP-011", exp011), ("EXP-012", exp012)]:
        incidence(recs, exp)


if __name__ == "__main__":
    main()
