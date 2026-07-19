#!/usr/bin/env python3
"""SC-7/SC-11/SC-9 raw analysis: modality-provenance (AVC-15), crisis-path
(MET-5), F2 Pydantic + contract assertions (MET-6/MET-7). Read-only; no
production code touched."""
import json
from pathlib import Path

BASE = Path("/home/neuroai/users/dhkim/aichampion/neurosync")

ALL_SLOT_KEYS = {
    "encounter_metadata", "chief_complaint", "history_of_present_illness",
    "past_psychiatric_history", "medical_history", "personal_social_history",
    "family_history", "substance_use_history", "mental_status_exam",
    "risk_assessment", "clinical_assessment", "treatment_plan",
}

RUNS = {
    ("SC-7", "VP-001", "run1"): {
        "conv": "docs/ai/simulation_results/VP-001/VP-001_20260711_225022_conversation.json",
        "sidecar": "docs/ai/simulation_results/VP-001/VP-001_20260711_225022_modality_provenance.json",
        "di": "docs/ai/simulation_results/VP-001/VP-001_20260711_225032_domain_inference.json",
    },
    ("SC-7", "VP-003", "run2"): {
        "conv": "docs/ai/simulation_results/VP-003/VP-003_20260711_224947_conversation.json",
        "sidecar": "docs/ai/simulation_results/VP-003/VP-003_20260711_224947_modality_provenance.json",
        "di": "docs/ai/simulation_results/VP-003/VP-003_20260711_224955_domain_inference.json",
    },
    ("SC-11", "VP-003", "run1"): {
        "conv": "docs/ai/simulation_results/VP-003/VP-003_20260711_225316_conversation.json",
        "sidecar": "docs/ai/simulation_results/VP-003/VP-003_20260711_225316_modality_provenance.json",
        "di": "docs/ai/simulation_results/VP-003/VP-003_20260711_225335_domain_inference.json",
    },
    ("SC-11", "VP-004", "run2a-preempted"): {
        "conv": "docs/ai/simulation_results/VP-004/VP-004_20260711_224924_conversation.json",
        "sidecar": "docs/ai/simulation_results/VP-004/VP-004_20260711_224924_modality_provenance.json",
        "di": "docs/ai/simulation_results/VP-004/VP-004_20260711_224936_domain_inference.json",
    },
    ("SC-11", "VP-004", "run2b-supplementary"): {
        "conv": "docs/ai/simulation_results/VP-004/VP-004_20260711_225520_conversation.json",
        "sidecar": "docs/ai/simulation_results/VP-004/VP-004_20260711_225520_modality_provenance.json",
        "di": "docs/ai/simulation_results/VP-004/VP-004_20260711_225534_domain_inference.json",
    },
    ("SC-9", "VP-003", "run1"): {
        "conv": "docs/ai/simulation_results/VP-003/VP-003_20260711_225424_conversation.json",
        "sidecar": "docs/ai/simulation_results/VP-003/VP-003_20260711_225424_modality_provenance.json",
        "di": "docs/ai/simulation_results/VP-003/VP-003_20260711_225436_domain_inference.json",
    },
    ("SC-9", "VP-004", "run2"): {
        "conv": "docs/ai/simulation_results/VP-004/VP-004_20260711_225306_conversation.json",
        "sidecar": "docs/ai/simulation_results/VP-004/VP-004_20260711_225306_modality_provenance.json",
        "di": "docs/ai/simulation_results/VP-004/VP-004_20260711_225329_domain_inference.json",
    },
}

TIER1_STRINGS = [
    "<", ">",  # generic bracket sweep handled separately
]

TIER2_PHRASES = ["많이 힘드셨겠어요.", "그런 상황이라면 정말 지치셨을 것 같아요.", "이야기해 주셔서 감사합니다."]


def load(rel):
    p = BASE / rel
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    for (sc, vp, tag), paths in RUNS.items():
        print(f"\n{'='*90}\n{sc} {vp} {tag}\n{'='*90}")
        conv = load(paths["conv"])
        sidecar = load(paths["sidecar"])
        di = load(paths["di"])

        events = sidecar.get("events", []) if sidecar else []
        print(f"injected_events: {len(events)}")
        for ev in events:
            composer_idx = ev["turn_index"]
            expected_persisted_turn = composer_idx if composer_idx == 0 else composer_idx + 1
            turns_by_idx = {t.get("turn"): t for t in conv.get("turns", [])}
            landed = None
            for cand_turn in (expected_persisted_turn, composer_idx):
                t = turns_by_idx.get(cand_turn)
                if t and t.get("normalizer_meta", {}).get("original") == ev["text"]:
                    landed = cand_turn
                    break
            print(f"  modality={ev['modality']} vendor={ev['vendor']} char_count={ev['char_count']} "
                  f"latency_ms={ev['latency_ms']:.1f} composer_turn_index={composer_idx} "
                  f"-> landed_in_persisted_turn={landed} (expected {expected_persisted_turn})")
            if landed is None:
                print("    ** NO EXACT normalizer_meta.original MATCH FOUND **")

        print(f"crisis_triggered={conv.get('crisis_triggered')} crisis_turn={conv.get('crisis_turn')} "
              f"total_turns={conv.get('total_turns')} is_revisit={conv.get('is_revisit')}")

        # crisis resource substitution text check
        if conv.get("crisis_triggered"):
            ct = conv.get("crisis_turn")
            turn_rec = next((t for t in conv["turns"] if t.get("turn") == ct), None)
            resp = (turn_rec or {}).get("agent_response", "")
            has_109 = "109" in resp
            has_119 = "119" in resp
            print(f"  crisis agent_response (turn {ct}): {resp[:200]!r}")
            print(f"  resource substitution: 109={has_109} 119={has_119}")

        # organic hotline mention outside formal crisis flag (raw observation)
        if not conv.get("crisis_triggered"):
            for t in conv.get("turns", []):
                resp = t.get("agent_response", "") or ""
                if "109" in resp or "119" in resp:
                    print(f"  ** organic hotline mention at turn {t.get('turn')} despite crisis_triggered=False: "
                          f"{resp[:200]!r}")

        # contract checks
        final_slots = {s["key"]: s["value"] for s in conv.get("final_slots", []) if s.get("value")}
        keys = set(final_slots.keys())
        slot_key_pass = keys.issubset(ALL_SLOT_KEYS)
        hpi_isolation_pass = "clinical_assessment" not in final_slots and "treatment_plan" not in final_slots
        print(f"MET-6(1) F1 slot-key consistency: {'PASS' if slot_key_pass else 'FAIL'} (keys={sorted(keys)})")
        print(f"MET-7(4) HPI isolation (final_slots): {'PASS' if hpi_isolation_pass else 'FAIL'}")

        if di is not None:
            val_errors = di.get("validation_errors")
            di_pass = not val_errors
            print(f"MET-6(3) F2 Pydantic validation: {'PASS' if di_pass else 'FAIL'} "
                  f"(validation_errors={val_errors})")
            apd = di.get("ai_predicted_disease") or {}
            print(f"  ai_predicted_disease.mode={apd.get('mode')} "
                  f"candidates={len(apd.get('candidates') or [])}")
            slot_text_blob = " | ".join(final_slots.values())
            leak = [c.get("disease") for c in (apd.get("candidates") or [])
                    if c.get("disease") and c.get("disease") in slot_text_blob]
            print(f"  MET-7 disease-name leak into final_slots text: {leak or 'none'}")

            # evidence citing the injected turn specifically
            turns_by_idx = {t.get("turn"): t for t in conv.get("turns", [])}
            injected_landed_turns = set()
            for ev in events:
                composer_idx = ev["turn_index"]
                expected = composer_idx if composer_idx == 0 else composer_idx + 1
                t = turns_by_idx.get(expected)
                if t and t.get("normalizer_meta", {}).get("original") == ev["text"]:
                    injected_landed_turns.add(expected)
            cite_hits = []
            for cand in di.get("domain_candidates") or []:
                for e in cand.get("evidence") or []:
                    sid = e.get("source_id", "")
                    if sid.startswith("turn_"):
                        try:
                            tn = int(sid.split("_", 1)[1])
                        except ValueError:
                            tn = None
                        if tn in injected_landed_turns:
                            cite_hits.append({"domain": cand.get("domain"), "source_type": e.get("source_type"),
                                               "source_id": sid, "quote": e.get("quote")})
            print(f"  F2 evidence citing injected-turn utterance: {cite_hits or 'none'}")
        else:
            print("  (no domain_inference.json found for this run)")

        # Tier-1 / Tier-2 echo-watch, generic bracket sweep + literal phrase counts
        import re
        surfaces_text = json.dumps(conv, ensure_ascii=False)
        if di:
            surfaces_text += json.dumps(di, ensure_ascii=False)
        bracket_hits = re.findall(r"<[^<>]{2,80}>", surfaces_text)
        print(f"Tier-1 echo-watch (bracket placeholders <...>): {len(bracket_hits)} hits "
              f"{bracket_hits[:5] if bracket_hits else ''}")
        for phrase in TIER2_PHRASES:
            n = surfaces_text.count(phrase)
            if n:
                print(f"Tier-2 echo-watch: {phrase!r} x{n}")


if __name__ == "__main__":
    main()
