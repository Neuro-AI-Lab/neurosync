#!/usr/bin/env python3
"""SC-3 contract assertions (MET-6/MET-7): F1 slot-key consistency + HPI
isolation, cross-checked against the paired F2 (A+B) ai_predicted_disease
outputs. Read-only; no production code touched."""
import json
from pathlib import Path

BASE = Path("/home/neuroai/users/dhkim/aichampion/neurosync")

ALL_SLOT_KEYS = {
    "encounter_metadata", "chief_complaint", "history_of_present_illness",
    "past_psychiatric_history", "medical_history", "personal_social_history",
    "family_history", "substance_use_history", "mental_status_exam",
    "risk_assessment", "clinical_assessment", "treatment_plan",
}

F1_ARTIFACTS = {
    ("VP-001", "rep1"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220428_conversation.json",
    ("VP-001", "rep2"): "docs/ai/simulation_results/VP-001/VP-001_20260711_220529_conversation.json",
    ("VP-002", "rep1"): "docs/ai/simulation_results/VP-002/VP-002_20260711_220423_conversation.json",
    ("VP-002", "rep2"): "docs/ai/simulation_results/VP-002/VP-002_20260711_220528_conversation.json",
    ("VP-003", "rep1"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220424_conversation.json",
    ("VP-003", "rep2"): "docs/ai/simulation_results/VP-003/VP-003_20260711_220518_conversation.json",
    ("VP-004", "rep1"): "docs/ai/simulation_results/VP-004/VP-004_20260711_220438_conversation.json",
    ("VP-004", "rep2"): "docs/ai/simulation_results/VP-004/VP-004_20260711_220604_conversation.json",
}

DI_ARTIFACTS = {
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
}


def main():
    results = {}
    for (vp, rep), rel in F1_ARTIFACTS.items():
        f1 = json.loads((BASE / rel).read_text(encoding="utf-8"))
        final_slots = {s["key"]: s["value"] for s in f1.get("final_slots", []) if s.get("value")}
        keys = set(final_slots.keys())
        slot_key_pass = keys.issubset(ALL_SLOT_KEYS)
        hpi_isolation_pass = "clinical_assessment" not in final_slots and "treatment_plan" not in final_slots
        slot_text_blob = " | ".join(final_slots.values())

        leak_hits = []
        for policy in ("A", "B"):
            di_rel = DI_ARTIFACTS.get((vp, rep, policy))
            if not di_rel:
                continue
            di_path = BASE / di_rel
            if not di_path.exists():
                continue
            di = json.loads(di_path.read_text(encoding="utf-8"))
            apd = di.get("ai_predicted_disease") or {}
            for c in apd.get("candidates") or []:
                name = c.get("disease", "")
                if name and name in slot_text_blob:
                    leak_hits.append({"policy": policy, "disease": name})

        results[f"{vp}/{rep}"] = {
            "final_slots_keys": sorted(keys),
            "slot_key_consistency_pass": slot_key_pass,
            "hpi_isolation_pass": hpi_isolation_pass,
            "ai_predicted_disease_leak_into_slots": leak_hits,
            "prior_handoff": f1.get("prior_handoff"),
            "is_revisit": f1.get("is_revisit"),
        }
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
