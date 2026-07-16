#!/usr/bin/env python3
"""Read-only extraction of rag_trigger / domain_candidates / ai_predicted_disease
/ Pydantic-validity / HPI-isolation fields from SC-2/SC-3/SC-3b domain_inference.json
artifacts. No production code touched; this is a report-generation aid only."""
import json
import sys
from pathlib import Path

BASE = Path("/home/neuroai/users/dhkim/aichampion/neurosync")

CELLS = {
    "sc2": {
        ("VP-001", "rep1", "A"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220214_domain_inference.json",
        ("VP-001", "rep1", "B"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220233_domain_inference.json",
        ("VP-001", "rep2", "A"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220259_domain_inference.json",
        ("VP-001", "rep2", "B"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220315_domain_inference.json",
        ("VP-002", "rep1", "A"): "docs/ai/simulation_results/VP-002/VP-002_20260711_220214_domain_inference.json",
        ("VP-002", "rep1", "B"): "docs/ai/simulation_results/VP-002/VP-002_20260711_220231_domain_inference.json",
        ("VP-002", "rep2", "A"): "docs/ai/simulation_results/VP-002/VP-002_20260711_220241_domain_inference.json",
        ("VP-002", "rep2", "B"): "docs/ai/simulation_results/VP-002/VP-002_20260711_220300_domain_inference.json",
        ("VP-003", "rep1", "A"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220200_domain_inference.json",
        ("VP-003", "rep1", "B"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220220_domain_inference.json",
        ("VP-003", "rep2", "A"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220228_domain_inference.json",
        ("VP-003", "rep2", "B"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220240_domain_inference.json",
        ("VP-004", "rep1", "A"): "docs/ai/simulation_results/VP-004/VP-004_20260711_220220_domain_inference.json",
        ("VP-004", "rep1", "B"): "docs/ai/simulation_results/VP-004/VP-004_20260711_220232_domain_inference.json",
        ("VP-004", "rep2", "A"): "docs/ai/simulation_results/VP-004/VP-004_20260711_220251_domain_inference.json",
        ("VP-004", "rep2", "B"): "docs/ai/simulation_results/VP-004/VP-004_20260711_220312_domain_inference.json",
    },
    "sc3": {
        ("VP-001", "rep1", "A"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220440_domain_inference.json",
        ("VP-001", "rep1", "B"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220451_domain_inference.json",
        ("VP-001", "rep2", "A"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220551_domain_inference.json",
        ("VP-001", "rep2", "B"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220603_domain_inference.json",
        ("VP-002", "rep1", "A"): "docs/ai/simulation_results/VP-002/VP-002_20260711_220440_domain_inference.json",
        ("VP-002", "rep1", "B"): "docs/ai/simulation_results/VP-002/VP-002_20260711_220445_domain_inference.json",
        ("VP-002", "rep2", "A"): "docs/ai/simulation_results/VP-002/VP-002_20260711_220550_domain_inference.json",
        ("VP-002", "rep2", "B"): "docs/ai/simulation_results/VP-002/VP-002_20260711_220554_domain_inference.json",
        ("VP-003", "rep1", "A"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220431_domain_inference.json",
        ("VP-003", "rep1", "B"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220440_domain_inference.json",
        ("VP-003", "rep2", "A"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220533_domain_inference.json",
        ("VP-003", "rep2", "B"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220541_domain_inference.json",
        ("VP-004", "rep1", "A"): "docs/ai/simulation_results/VP-004/VP-004_20260711_220459_domain_inference.json",
        ("VP-004", "rep1", "B"): "docs/ai/simulation_results/VP-004/VP-004_20260711_220521_domain_inference.json",
        ("VP-004", "rep2", "A"): "docs/ai/simulation_results/VP-004/VP-004_20260711_220628_domain_inference.json",
        ("VP-004", "rep2", "B"): "docs/ai/simulation_results/VP-004/VP-004_20260711_220638_domain_inference.json",
    },
    "sc3b": {
        ("VP-003", "repeat1", "B"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220804_domain_inference.json",
        ("VP-003", "repeat2", "B"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220845_domain_inference.json",
        ("VP-003", "repeat3", "B"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220852_domain_inference.json",
        ("VP-001", "repeat1", "B"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220816_domain_inference.json",
        ("VP-001", "repeat2", "B"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220831_domain_inference.json",
        ("VP-001", "repeat3", "B"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220851_domain_inference.json",
    },
}


def extract(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    rt = d.get("rag_trigger") or {}
    apd = d.get("ai_predicted_disease") or {}
    dc = d.get("domain_candidates") or []
    return {
        "input_sha256": d["repro"]["input_sha256"],
        "input_file": d["repro"]["input_file"],
        "mode": d["repro"]["mode"],
        "rag_trigger.policy": rt.get("policy"),
        "rag_trigger.retrieve": rt.get("retrieve"),
        "rag_trigger.queries": rt.get("queries"),
        "rag_trigger.dropped_queries": rt.get("dropped_queries"),
        "rag_trigger.trigger_reason": rt.get("trigger_reason"),
        "rag_trigger.fallback_used": rt.get("fallback_used"),
        "judge_output": rt.get("judge_output"),
        "domain_candidates": [{"domain": c["domain"], "confidence": c["confidence"]} for c in dc],
        "ai_predicted_disease.mode": apd.get("mode"),
        "ai_predicted_disease.candidates": [
            {"disease": c["disease"], "similarity_score": c["similarity_score"]}
            for c in (apd.get("candidates") or [])
        ],
        "validation_errors": d.get("validation_errors"),
        "finish_reason": d.get("finish_reason"),
        "clinical_assessment_leak_check": "n/a (F2-only artifact, no final_slots persisted here)",
    }


def main():
    out = {}
    for sc, cells in CELLS.items():
        out[sc] = {}
        for (vp, rep, policy), rel in cells.items():
            path = BASE / rel
            if not path.exists():
                out[sc][f"{vp}/{rep}/{policy}"] = {"ERROR": f"missing file {rel}"}
                continue
            out[sc][f"{vp}/{rep}/{policy}"] = extract(path)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
