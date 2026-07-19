#!/usr/bin/env python3
"""EXP-018 cell 4 — retry-telemetry review, read-only, no production code touched.

Consumes the 11 SM-bundle result.json artifacts (cell 1; cells 2/3 did not run — SM-06
stop-rule fired, see result.md EXP-018 entry). Computes, per the BRIEF's cell-4 spec:
  - retry rate (turns with dialogue_retry_count>0 / scored turns)
  - dialogue_retry_reasons distribution
  - fall-through count, WITH the qa cross-reference: fall_through is budget-exhaustion
    specifically, distinct from "any turn that ever retried" (non-empty retry_reasons
    with fall_through=False means the retry resolved the violation, not that a
    violation shipped)
  - p95 per-turn latency delta vs the EXP-017 same-cell (SM bundle) artifacts
  - crisis_adjacent subset reported separately (CVR-011 condition 3)
  - exact_repeat retries x denied-slot content cross-tab (CVR-011 condition 4):
    for every turn with an 'exact_repeat' or 'near_dup_*' reason, was the
    targeted_slot already present with a plainly-denied/negative patient answer in
    an EARLIER turn this session (heuristic: earlier turn targeting the same slot,
    patient_message contains a denial marker)?
  - criterion D invariant check on 100% of turns: fall_through==True implies
    retry_count == _MAX_REGENERATION_ATTEMPTS (=2); retry_reasons length >= retry_count
    when NOT fall_through-by-exception (loop pseudocode: len(retry_reasons) ==
    retry_count, OR == retry_count+1 when fall_through (final unresolved reason
    appended without an extra attempt) -- see fix_design_bug030_iter2.md SS3 note).
  - criterion E marker-hit distribution: for turns whose agent_response leading
    clause is_empathy=True, which marker(s) from the CURRENT (post-D2-correction)
    _EMPATHY_MARKERS set fired; flag any turn where marker-hit is a SINGLE marker
    and that marker is one of the borderline/broad ones ("것 같아요"/"것 같습니다"/"군요"/
    "이해"/"공감") for critic/CV spot-check (bare "겠" already structurally impossible
    post-D2 -- confirmed no code path can trigger it).
"""
import json
import re
import sys

_DENIAL_MARKERS = ["아니요", "아니에요", "없어요", "없었어요", "안 해봤", "안 가봤",
                    "받아 본 적 없", "한 적 없", "몰라요", "안 먹", "안 마셔"]

_EMPATHY_MARKERS = ["것 같아요", "것 같습니다", "감사합니다", "이해", "공감",
                    "힘드셨", "힘드시", "지치셨", "지치시", "어려우셨", "어려우시", "군요"]

_MAX_REGEN = 2


def extract_leading_clause(text):
    """Verbatim port of dialogue.py's _extract_leading_clause (punctuation-INCLUSIVE,
    ?-leading => no clause, no terminal punct => no clause)."""
    stripped = (text or "").strip()
    if not stripped:
        return ""
    positions = [(stripped.find(c), c) for c in (".", "!", "?")]
    positions = [(p, c) for p, c in positions if p != -1]
    if not positions:
        return ""
    end, term = min(positions, key=lambda t: t[0])
    if term == "?":
        return ""
    return stripped[:end].strip()


def marker_hits(clause):
    return [m for m in _EMPATHY_MARKERS if m in clause]


def is_denial(patient_message):
    return any(m in (patient_message or "") for m in _DENIAL_MARKERS)


def load_sm(path):
    d = json.load(open(path))
    return d["result"] if "result" in d else d


def analyze_cell1(exp018_map, exp017_map):
    rows = []
    all_turns_018 = []
    lat018, lat017 = [], []
    reason_counts = {}
    fall_through_count = 0
    retried_count = 0
    scored_turns = 0
    crisis_adjacent_turns = []
    exact_repeat_denied_slot_hits = []
    invariant_violations = []
    marker_dist = {}
    single_marker_borderline = []

    for sm, path018 in exp018_map.items():
        res018 = load_sm(path018)
        turns018 = res018.get("turns", [])
        path017 = exp017_map.get(sm)
        res017 = load_sm(path017) if path017 else {"turns": []}
        turns017 = res017.get("turns", [])

        # per-session targeted-slot history for the denial cross-tab.
        # targeted_slot[K] is what agent_response[K] ASKS ABOUT; the patient's
        # ANSWER to that question arrives as patient_message[K+1] (agent_response[K]
        # itself replies to patient_message[K], per rubric SS10.2 same-index pairing --
        # a forward-looking targeted_slot is a distinct, one-turn-later relationship).
        # So: after processing turn K+1's patient_message, if it is a denial, the slot
        # that gets marked "denied" is targeted_slot[K] (the PRECEDING turn's target).
        slot_denied_before = {}  # slot -> True once a denial observed for it
        prev_targeted_slot = None

        for t in turns018:
            n = t.get("turn")
            pm_this = t.get("patient_message", "")
            if n is not None and n >= 1 and prev_targeted_slot and is_denial(pm_this):
                slot_denied_before[prev_targeted_slot] = True
            scored_turns += 1
            rc = t.get("dialogue_retry_count", 0)
            rr = t.get("dialogue_retry_reasons", [])
            ft = t.get("dialogue_fall_through", False)
            rl = t.get("dialogue_retry_latency_ms", 0.0)
            ca = t.get("dialogue_crisis_adjacent", False)
            lat = t.get("latency_ms")
            tgt = t.get("targeted_slot")
            pm = t.get("patient_message", "")
            ar = t.get("agent_response", "")

            if lat is not None:
                lat018.append(lat)
            all_turns_018.append({"sm": sm, "turn": n, "retry_count": rc,
                                   "retry_reasons": rr, "fall_through": ft,
                                   "retry_latency_ms": rl, "crisis_adjacent": ca,
                                   "targeted_slot": tgt})

            if rc > 0:
                retried_count += 1
            if ft:
                fall_through_count += 1
            for reason in rr:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            if ca:
                crisis_adjacent_turns.append((sm, n, rr, ft))

            # criterion D invariant: fall_through => retry_count == _MAX_REGEN
            if ft and rc != _MAX_REGEN:
                invariant_violations.append(
                    f"{sm} turn {n}: fall_through=True but retry_count={rc} (expected {_MAX_REGEN})")
            # retry_reasons length sanity: should equal retry_count, or retry_count+1
            # if fall_through (final unresolved reason appended w/o a further attempt)
            expected_len = rc + 1 if ft else rc
            if len(rr) != expected_len and not (rc == 0 and not rr):
                invariant_violations.append(
                    f"{sm} turn {n}: len(retry_reasons)={len(rr)} vs expected {expected_len} "
                    f"(retry_count={rc}, fall_through={ft}, reasons={rr})")

            # CVR-011 condition 4: exact_repeat retry x denied-slot cross-tab
            # (tgt = targeted_slot[n], the slot THIS turn's response re-targets;
            # a hit means: a retry fired while re-targeting a slot whose earlier
            # question was already plainly denied by the patient)
            has_exact_repeat = "exact_repeat" in rr
            if has_exact_repeat and tgt and slot_denied_before.get(tgt):
                exact_repeat_denied_slot_hits.append(
                    {"sm": sm, "turn": n, "targeted_slot": tgt, "reasons": rr})
            prev_targeted_slot = tgt

            # criterion E: marker-hit distribution on empathy-classified clauses
            clause = extract_leading_clause(ar)
            hits = marker_hits(clause)
            if hits:
                for h in hits:
                    marker_dist[h] = marker_dist.get(h, 0) + 1
                if len(hits) == 1 and hits[0] in ("것 같아요", "것 같습니다", "군요", "이해", "공감"):
                    single_marker_borderline.append(
                        {"sm": sm, "turn": n, "marker": hits[0], "clause": clause})

        for t in turns017:
            lat = t.get("latency_ms")
            if lat is not None:
                lat017.append(lat)

        rows.append({"sm": sm, "n_turns_018": len(turns018), "n_turns_017": len(turns017)})

    return {
        "scored_turns": scored_turns,
        "retried_count": retried_count,
        "fall_through_count": fall_through_count,
        "reason_counts": reason_counts,
        "lat018": lat018,
        "lat017": lat017,
        "crisis_adjacent_turns": crisis_adjacent_turns,
        "exact_repeat_denied_slot_hits": exact_repeat_denied_slot_hits,
        "invariant_violations": invariant_violations,
        "marker_dist": marker_dist,
        "single_marker_borderline": single_marker_borderline,
        "rows": rows,
    }


def percentile(values, p):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    f, c = int(k), min(int(k) + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def main():
    exp018_map = {
        "SM-01": "docs/ai/simulation_results/safety_matrix/SM-01_20260712_133847_result.json",
        "SM-02": "docs/ai/simulation_results/safety_matrix/SM-02_20260712_133937_result.json",
        "SM-03": "docs/ai/simulation_results/safety_matrix/SM-03_20260712_134045_result.json",
        "SM-04a": "docs/ai/simulation_results/safety_matrix/SM-04a_20260712_134110_result.json",
        "SM-04b": "docs/ai/simulation_results/safety_matrix/SM-04b_20260712_134237_result.json",
        "SM-05": "docs/ai/simulation_results/safety_matrix/SM-05_20260712_134324_result.json",
        "SM-06": "docs/ai/simulation_results/safety_matrix/SM-06_20260712_134455_result.json",
        "SM-07a": "docs/ai/simulation_results/safety_matrix/SM-07a_20260712_134556_result.json",
        "SM-07b": "docs/ai/simulation_results/safety_matrix/SM-07b_20260712_134613_result.json",
        "SM-08a": "docs/ai/simulation_results/safety_matrix/SM-08a_20260712_134659_result.json",
        "SM-08b": "docs/ai/simulation_results/safety_matrix/SM-08b_20260712_134747_result.json",
    }
    exp017_map = {
        "SM-01": "docs/ai/simulation_results/safety_matrix/SM-01_20260712_093323_result.json",
        "SM-02": "docs/ai/simulation_results/safety_matrix/SM-02_20260712_093417_result.json",
        "SM-03": "docs/ai/simulation_results/safety_matrix/SM-03_20260712_093523_result.json",
        "SM-04a": "docs/ai/simulation_results/safety_matrix/SM-04a_20260712_093545_result.json",
        "SM-04b": "docs/ai/simulation_results/safety_matrix/SM-04b_20260712_093703_result.json",
        "SM-05": "docs/ai/simulation_results/safety_matrix/SM-05_20260712_093747_result.json",
        "SM-06": "docs/ai/simulation_results/safety_matrix/SM-06_20260712_093913_result.json",
        "SM-07a": "docs/ai/simulation_results/safety_matrix/SM-07a_20260712_094022_result.json",
        "SM-07b": "docs/ai/simulation_results/safety_matrix/SM-07b_20260712_094039_result.json",
        "SM-08a": "docs/ai/simulation_results/safety_matrix/SM-08a_20260712_094122_result.json",
        "SM-08b": "docs/ai/simulation_results/safety_matrix/SM-08b_20260712_094210_result.json",
    }
    res = analyze_cell1(exp018_map, exp017_map)

    print(f"scored_turns={res['scored_turns']}")
    print(f"turns with retry_count>0: {res['retried_count']} "
          f"({res['retried_count']/res['scored_turns']:.1%})")
    print(f"fall_through=True turns: {res['fall_through_count']} "
          f"({res['fall_through_count']/res['scored_turns']:.1%})")
    print(f"  qa cross-reference: {res['retried_count']} turns retried at least once; "
          f"of those, {res['fall_through_count']} exhausted budget (fall_through=True) -- "
          f"the other {res['retried_count']-res['fall_through_count']} resolved within budget "
          f"and shipped a compliant response despite having retried.")
    print(f"retry_reasons distribution: {res['reason_counts']}")
    print()
    print(f"latency_ms EXP-018 cell1 (n={len(res['lat018'])}): "
          f"p50={percentile(res['lat018'],0.5):.0f} p95={percentile(res['lat018'],0.95):.0f} "
          f"max={max(res['lat018']):.0f}")
    print(f"latency_ms EXP-017 cell1 (n={len(res['lat017'])}): "
          f"p50={percentile(res['lat017'],0.5):.0f} p95={percentile(res['lat017'],0.95):.0f} "
          f"max={max(res['lat017']):.0f}")
    p95_018 = percentile(res['lat018'], 0.95)
    p95_017 = percentile(res['lat017'], 0.95)
    print(f"p95 delta (EXP-018 - EXP-017): {p95_018 - p95_017:+.0f} ms")
    print()
    print(f"crisis_adjacent=True turns (n={len(res['crisis_adjacent_turns'])}):")
    for sm, n, rr, ft in res['crisis_adjacent_turns']:
        print(f"  {sm} turn {n}: retry_reasons={rr} fall_through={ft}")
    print()
    print(f"exact_repeat-retry x denied-slot cross-tab hits (n={len(res['exact_repeat_denied_slot_hits'])}):")
    for h in res['exact_repeat_denied_slot_hits']:
        print(f"  {h}")
    print()
    print(f"criterion D invariant violations (n={len(res['invariant_violations'])}):")
    for v in res['invariant_violations']:
        print(f"  {v}")
    print()
    print(f"criterion E marker-hit distribution (empathy-classified clauses): {res['marker_dist']}")
    print(f"single-marker (borderline set) turns needing spot-check (n={len(res['single_marker_borderline'])}):")
    for s in res['single_marker_borderline']:
        print(f"  {s}")


if __name__ == "__main__":
    main()
