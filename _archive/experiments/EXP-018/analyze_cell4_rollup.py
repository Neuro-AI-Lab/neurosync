#!/usr/bin/env python3
"""EXP-018 cell 4 -- FULL-EXPERIMENT telemetry rollup (cell 1 SM + cell 2 naturalness +
cell 3 SC-5 reprobe), read-only, no production code touched. Extends the cell-1-only
analysis already reported (see analyze_retry_telemetry.py) to all 3 cells that ran.

Computes, per the BRIEF's cell-4 spec:
  - retry rate, retry_reasons distribution, fall-through count (with the qa
    cross-reference: fall_through is budget-exhaustion specifically)
  - p95 per-turn latency delta vs EXP-017 same-cell artifacts, cells 2/3 only
    (cell 1's delta already reported in the EXP-018 entry's existing cell-4 section)
  - crisis_adjacent subset reported SEPARATELY (CVR-011 condition 3)
  - exact_repeat x denied-slot cross-tab (CVR-011 condition 4)
  - criterion D invariants on 100% of turns (all 3 cells)
  - criterion E marker-hit distribution + single-marker-decision check (E's "any
    is_empathy decision resting on a single marker" ask)
"""
import json
import sys

_DENIAL_MARKERS = ["아니요", "아니에요", "없어요", "없었어요", "안 해봤", "안 가봤",
                    "받아 본 적 없", "한 적 없", "몰라요", "안 먹", "안 마셔"]

_EMPATHY_MARKERS = ["것 같아요", "것 같습니다", "감사합니다", "이해", "공감",
                    "힘드셨", "힘드시", "지치셨", "지치시", "어려우셨", "어려우시", "군요"]

_MAX_REGEN = 2


def extract_leading_clause(text):
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


def load_turns(path, cell):
    d = json.load(open(path))
    d = d.get("result", d)
    return d.get("turns", []), cell, d


def process(turn_sources):
    """turn_sources: list of (path, cell_label)."""
    scored_turns = 0
    retried_count = 0
    fall_through_count = 0
    reason_counts = {}
    lat = {"cell1": [], "cell2": [], "cell3": []}
    crisis_adjacent_turns = []
    exact_repeat_denied_slot_hits = []
    invariant_violations = []
    marker_dist = {}
    single_marker_turns = []

    for path, cell in turn_sources:
        turns, _, _ = load_turns(path, cell)
        slot_denied_before = {}
        prev_targeted_slot = None
        for t in turns:
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
            latency = t.get("latency_ms")
            tgt = t.get("targeted_slot")
            ar = t.get("agent_response", "")

            if latency is not None:
                lat[cell].append(latency)
            if rc > 0:
                retried_count += 1
            if ft:
                fall_through_count += 1
            for reason in rr:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            if ca:
                crisis_adjacent_turns.append((cell, n, rr, ft))

            if ft and rc != _MAX_REGEN:
                invariant_violations.append(
                    f"{cell} turn {n}: fall_through=True but retry_count={rc} (expected {_MAX_REGEN})")
            expected_len = rc + 1 if ft else rc
            if len(rr) != expected_len and not (rc == 0 and not rr):
                invariant_violations.append(
                    f"{cell} turn {n}: len(retry_reasons)={len(rr)} vs expected {expected_len} "
                    f"(retry_count={rc}, fall_through={ft}, reasons={rr})")
            for field_name, val in [("retry_count", rc), ("retry_reasons", rr),
                                     ("fall_through", ft), ("retry_latency_ms", rl),
                                     ("crisis_adjacent", ca)]:
                if val is None:
                    invariant_violations.append(f"{cell} turn {n}: field {field_name} missing/None")
            if (rc > 0) != (rl > 0):
                invariant_violations.append(
                    f"{cell} turn {n}: retry_count>0 <=> retry_latency_ms>0 violated "
                    f"(retry_count={rc}, retry_latency_ms={rl})")

            has_exact_repeat = "exact_repeat" in rr
            if has_exact_repeat and tgt and slot_denied_before.get(tgt):
                exact_repeat_denied_slot_hits.append(
                    {"cell": cell, "turn": n, "targeted_slot": tgt, "reasons": rr})
            prev_targeted_slot = tgt

            clause = extract_leading_clause(ar)
            hits = marker_hits(clause)
            if hits:
                for h in hits:
                    marker_dist[h] = marker_dist.get(h, 0) + 1
                if len(hits) == 1:
                    single_marker_turns.append(
                        {"cell": cell, "turn": n, "marker": hits[0], "clause": clause})

    return {
        "scored_turns": scored_turns, "retried_count": retried_count,
        "fall_through_count": fall_through_count, "reason_counts": reason_counts,
        "lat": lat, "crisis_adjacent_turns": crisis_adjacent_turns,
        "exact_repeat_denied_slot_hits": exact_repeat_denied_slot_hits,
        "invariant_violations": invariant_violations, "marker_dist": marker_dist,
        "single_marker_turns": single_marker_turns,
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
    sm_ids = ["SM-01", "SM-02", "SM-03", "SM-04a", "SM-04b", "SM-05", "SM-06",
              "SM-07a", "SM-07b", "SM-08a", "SM-08b"]
    sm_ts = {"SM-01": "133847", "SM-02": "133937", "SM-03": "134045", "SM-04a": "134110",
              "SM-04b": "134237", "SM-05": "134324", "SM-06": "134455", "SM-07a": "134556",
              "SM-07b": "134613", "SM-08a": "134659", "SM-08b": "134747"}
    cell1_paths = [(f"docs/ai/simulation_results/safety_matrix/{sm}_20260712_{ts}_result.json", "cell1")
                   for sm, ts in sm_ts.items()]
    cell2_paths = [
        ("docs/ai/simulation_results/VP-001/VP-001_20260712_141413_conversation.json", "cell2"),
        ("docs/ai/simulation_results/VP-003/VP-003_20260712_141607_conversation.json", "cell2"),
        ("docs/ai/simulation_results/VP-010/VP-010_20260712_141728_conversation.json", "cell2"),
    ]
    cell3_paths = [
        ("docs/ai/simulation_results/VP-003/VP-003_20260712_142022_conversation.json", "cell3"),
        ("docs/ai/simulation_results/VP-003/VP-003_20260712_142223_conversation.json", "cell3"),
    ]
    all_paths = cell1_paths + cell2_paths + cell3_paths
    res = process(all_paths)

    print(f"TOTAL scored_turns (cell1+2+3) = {res['scored_turns']}")
    print(f"turns with retry_count>0: {res['retried_count']} ({res['retried_count']/res['scored_turns']:.1%})")
    print(f"fall_through=True turns: {res['fall_through_count']} ({res['fall_through_count']/res['scored_turns']:.1%})")
    print(f"retry_reasons distribution (all cells): {res['reason_counts']}")
    print()
    for cell in ("cell1", "cell2", "cell3"):
        vals = res["lat"][cell]
        if vals:
            print(f"latency_ms {cell} (n={len(vals)}): p50={percentile(vals,0.5):.0f} "
                  f"p95={percentile(vals,0.95):.0f} max={max(vals):.0f}")
    print()
    print(f"crisis_adjacent=True turns (n={len(res['crisis_adjacent_turns'])}):")
    for cell, n, rr, ft in res['crisis_adjacent_turns']:
        print(f"  {cell} turn {n}: retry_reasons={rr} fall_through={ft}")
    print()
    print(f"exact_repeat-retry x denied-slot cross-tab hits (n={len(res['exact_repeat_denied_slot_hits'])}):")
    for h in res['exact_repeat_denied_slot_hits']:
        print(f"  {h}")
    print()
    print(f"criterion D invariant violations (n={len(res['invariant_violations'])}):")
    for v in res['invariant_violations'][:30]:
        print(f"  {v}")
    print()
    print(f"criterion E marker-hit distribution: {res['marker_dist']}")
    print(f"single-marker-decision turns (is_empathy resting on exactly 1 marker), n={len(res['single_marker_turns'])}:")
    by_marker = {}
    for s in res['single_marker_turns']:
        by_marker.setdefault(s['marker'], []).append(f"{s['cell']}/t{s['turn']}")
    for m, locs in by_marker.items():
        print(f"  marker={m!r}: {len(locs)} turns -> {locs}")


if __name__ == "__main__":
    main()
