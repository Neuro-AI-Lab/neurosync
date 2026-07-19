#!/usr/bin/env python3
"""SC-12 raw-metrics analyzer (harness-only, read-only, no production code touched).

Reads each rep's F1 conversation.json + F2 domain_inference.json and prints:
 - slot fill counts, crisis flags, latency, truncation flag
 - two-tier echo-watch (Tier-1 bracket-placeholder sweep; Tier-2 empathy-phrase counts)
 - contract assertions (MET-6/MET-7)
 - F2 Pydantic pass/fail
 - VP-010 Tier-3 MPD observation (mood/sleep/interest)
 - VP-012 AUD candidate observation
"""
import json
import re
import sys
from pathlib import Path

BASE = Path("/home/neuroai/users/dhkim/aichampion/neurosync")
SIM = BASE / "docs/ai/simulation_results"

EMPATHY_PHRASES = ["많이 힘드셨겠어요.", "그런 상황이라면 정말 지치셨을 것 같아요.", "이야기해 주셔서 감사합니다."]

BRACKET_RE = re.compile(r"<[^<>]{2,80}>")

ALL_SLOT_KEYS = {
    "encounter_metadata", "chief_complaint", "history_of_present_illness",
    "past_psychiatric_history", "medical_history", "personal_social_history",
    "family_history", "substance_use_history", "mental_status_exam",
    "risk_assessment", "clinical_assessment", "treatment_plan",
}  # apps/ai-server/src/agents/clinical_slot.py:26-38, verbatim

VP010_TIER3 = {
    "mood": "거의 매일 그런 것 같아요",
    "sleep": "4-5시간",
    "interest": "게임도 예전만큼 재미가 없",
}
VP010_TIER3_ALT = {
    "mood": ["거의 매일", "티 안 내려고"],
    "sleep": ["4-5시간", "4~5시간", "새벽에도 자주"],
    "interest": ["게임도 예전만큼", "재미가 없", "하기 싫"],
}


def find_pair(vp: str, tag: str):
    """tag is a substring of the timestamp to disambiguate rep1/rep2."""
    convs = sorted((SIM / vp).glob(f"{vp}_*_conversation.json"))
    matches = [c for c in convs if tag in c.name]
    if not matches:
        return None, None
    conv = matches[0]
    ts = conv.name.split("_")[1] + "_" + conv.name.split("_")[2]
    dis = sorted((SIM / vp).glob(f"{vp}_*_domain_inference.json"))
    # pick the domain_inference file with timestamp >= conv's timestamp, closest
    conv_ts = conv.name.split("_conversation")[0]
    dis_after = [d for d in dis if d.name.split("_domain_inference")[0] >= conv_ts]
    di = sorted(dis_after)[0] if dis_after else None
    return conv, di


def analyze(vp: str, rep: str, tag: str):
    conv_path, di_path = find_pair(vp, tag)
    print(f"\n{'='*70}\n{vp} {rep}  (tag={tag})\n{'='*70}")
    if not conv_path:
        print("NO CONVERSATION ARTIFACT FOUND")
        return
    print(f"conversation: {conv_path.name}")
    d = json.load(open(conv_path))
    slots = {s["key"]: s["value"] for s in d.get("final_slots", [])}
    print(f"is_revisit={d.get('is_revisit')} total_turns={d.get('total_turns')} "
          f"turns_len={len(d.get('turns', []))} crisis={d.get('crisis_triggered')}@{d.get('crisis_turn')}")
    print(f"errors={d.get('errors')}")
    print(f"slot_coverage={d.get('slot_coverage')} grounded_coverage={d.get('grounded_coverage')}")
    print(f"final_slots filled ({len(slots)}/12): {sorted(slots.keys())}")
    print(f"prompts_degraded(session)={d.get('prompts_degraded')}")

    # truncation
    max_turns = 10
    reached = d.get("total_turns", len(d.get("turns", [])) - 1 if d.get("turns") else 0)
    early = reached < max_turns
    crisis = bool(d.get("crisis_triggered"))
    print(f"TRUNCATION: reached={reached}/{max_turns} early={early} crisis_early_return={crisis and early}")

    # repetition guard trips
    log_path = None
    for cand in [BASE / f"experiments/EXP-016/runs/sc12/{vp}/{rep}/run.log"]:
        if cand.exists():
            log_path = cand
    trips = 0
    hard = False
    if log_path:
        text = log_path.read_text(errors="ignore")
        trips = len(re.findall(r"repeated|repetition", text, re.I))
        hard = "count=2" in text
    print(f"repetition-guard soft warnings(log)={trips} hard_trip={hard}")

    # Tier-1 bracket sweep across shipped surfaces
    turns = d.get("turns", [])
    tier1_hits = []
    for t in turns:
        resp = t.get("agent_response", "") or ""
        for m in BRACKET_RE.findall(resp):
            tier1_hits.append(("agent_response", t.get("turn"), m))
    for k, v in slots.items():
        for m in BRACKET_RE.findall(str(v)):
            tier1_hits.append(("final_slots." + k, None, m))
    # F2 side
    di = None
    if di_path:
        di = json.load(open(di_path))
        di_text = json.dumps(di, ensure_ascii=False)
        for m in BRACKET_RE.findall(di_text):
            tier1_hits.append(("domain_inference.json(full)", None, m))
    print(f"TIER-1 bracket-placeholder sweep: {len(tier1_hits)} hits")
    for h in tier1_hits:
        print(f"   HIT: {h}")

    # Tier-2 empathy phrase counts
    counts = {p: 0 for p in EMPATHY_PHRASES}
    seq = []
    for t in turns:
        resp = t.get("agent_response", "") or ""
        matched = None
        for p in EMPATHY_PHRASES:
            if p in resp:
                counts[p] += 1
                matched = p
        seq.append(matched)
    total_empathy_turns = sum(1 for x in seq if x)
    max_consec = 0
    cur = 0
    prev = None
    consec_ranges = []
    start = None
    for i, x in enumerate(seq):
        if x is not None and x == prev:
            cur += 1
            if start is None:
                start = i - 1
        else:
            if cur > max_consec:
                max_consec = cur
                consec_ranges.append((start, i - 1))
            cur = 0
            start = None
        prev = x
    if cur > max_consec:
        max_consec = cur
        consec_ranges.append((start, len(seq) - 1))
    print(f"TIER-2 empathy phrase counts: {counts}  total_empathy_turns={total_empathy_turns}/{len(turns)}")
    dominant = max(counts, key=counts.get) if total_empathy_turns else None
    dominant_pct = (counts[dominant] / total_empathy_turns * 100) if dominant and total_empathy_turns else 0
    print(f"dominant phrase={dominant!r} count={counts.get(dominant,0)} pct_of_empathy_turns={dominant_pct:.0f}% "
          f"max_consecutive_run={max_consec+1 if max_consec else (1 if total_empathy_turns else 0)}")
    flag = dominant_pct > 50 or max_consec >= 1
    print(f"TIER-2 FLAG (>{'50% or >=2 consecutive'}): {flag}")

    # contract assertions
    c1 = set(slots.keys()) <= ALL_SLOT_KEYS
    print(f"CONTRACT (1) slot-key-consistency: {'PASS' if c1 else 'FAIL'} extra={set(slots.keys())-ALL_SLOT_KEYS}")
    prior_handoff = d.get("prior_handoff")
    c2 = prior_handoff is None
    print(f"CONTRACT (2) F1->F2 input-construction (prior_handoff is None, standalone): {'PASS' if c2 else 'FAIL'} value={prior_handoff}")

    c3 = None
    c3_detail = ""
    if di is None:
        c3 = False
        c3_detail = "NO domain_inference.json FOUND"
    else:
        verrs = di.get("validation_errors")
        finish = di.get("finish_reason")
        c3 = (not verrs) and finish != "parse_failure"
        c3_detail = f"validation_errors={verrs} finish_reason={finish} mode={di.get('mode') or di.get('retrieval_mode')}"
    print(f"CONTRACT (3) F2 Pydantic validation: {'PASS' if c3 else 'FAIL'} {c3_detail}")

    ca = None
    if di:
        ca = di.get("ai_predicted_disease")
    c4a = (slots.get("clinical_assessment") is None) and (slots.get("treatment_plan") is None)
    c4b = True
    if di:
        # check ai_predicted_disease is a top-level sibling key, not nested in domain_candidates
        c4b = "ai_predicted_disease" in di and not any(
            "ai_predicted_disease" in json.dumps(cand) for cand in di.get("domain_candidates", [])
        )
    c4c = True
    if ca:
        names = [c.get("disease", "") for c in ca.get("candidates", [])]
        for n in names:
            for k, v in slots.items():
                if n and n in str(v):
                    c4c = False
    c4 = c4a and c4b and c4c
    print(f"CONTRACT (4) HPI-isolation: {'PASS' if c4 else 'FAIL'} (clinical_assessment/treatment_plan null={c4a}, sibling-key={c4b}, no-name-leak={c4c})")

    # F2 domain_candidates + ai_predicted_disease report
    if di:
        dcands = di.get("domain_candidates", [])
        print(f"domain_candidates: {[(c.get('domain'), c.get('confidence')) for c in dcands]}")
        rag_trigger = di.get("rag_trigger")
        print(f"rag_trigger: {json.dumps(rag_trigger, ensure_ascii=False) if rag_trigger else None}")
        if ca:
            cands = ca.get("candidates", [])
            print(f"ai_predicted_disease.mode={ca.get('mode')} candidate_count={len(cands)}")
            print(f"ai_predicted_disease.candidates: {[(c.get('disease'), c.get('similarity_score')) for c in cands]}")
            print(f"reason_summary: {ca.get('reason_summary', '')[:200]}")
            if vp == "VP-012":
                alcohol_any = [c.get("disease") for c in cands if "알코올" in (c.get("disease") or "")]
                new_aud_entry = [c.get("disease") for c in cands if "사용장애" in (c.get("disease") or "")]
                print(f"*** VP-012 alcohol-named candidate(s) (any): {alcohol_any or 'NONE'} ***")
                print(f"*** VP-012 NEW alcohol-use-disorder entry ('알코올 사용장애(의존)') present: "
                      f"{'YES' if new_aud_entry else 'NO'} {new_aud_entry} ***")
        f2_lat = di.get("latency_ms")
        print(f"F2 latency_ms: {f2_lat}")

    # VP-010 Tier-3 observation
    if vp == "VP-010":
        full_text = " ".join((t.get("patient_message") or "") for t in turns)
        obs = {}
        for domain, alts in VP010_TIER3_ALT.items():
            hit = any(a in full_text for a in alts)
            obs[domain] = hit
        print(f"*** VP-010 Tier-3 reveal observation (mood/sleep/interest): {obs} ***")


if __name__ == "__main__":
    reps = [
        ("VP-010", "rep1", "214213"), ("VP-011", "rep1", "214218"), ("VP-012", "rep1", "214202"),
        ("VP-010", "rep2", "214459"), ("VP-011", "rep2", "214501"), ("VP-012", "rep2", "214459"),
    ]
    for vp, rep, tag in reps:
        analyze(vp, rep, tag)
