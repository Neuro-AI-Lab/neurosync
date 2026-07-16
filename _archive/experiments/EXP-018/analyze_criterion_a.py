#!/usr/bin/env python3
"""EXP-018 cell 2 — criterion A (repetition bar) scorer, read-only, no production code touched.

Ports `apps/ai-server/src/agents/dialogue.py`'s own guard primitives VERBATIM
(`_extract_leading_clause`, `_is_empathy_clause`, `_same_phrase_family`) so the scorer's
phrase-family clustering is provably identical to the code the guard runs against at
retry time -- not a re-derivation with independent thresholds. `_EMPATHY_MARKERS` is
copied from dialogue.py post-ADR-029-D2 (bare "겠" removed, "-군요" family added).

Criterion A (REV-032, docs/ai/critic_scratch_rev032_bug030iter2.md, "A. Repetition bar"):
  1. Normalization PINNED: empathy clause = `_extract_leading_clause` output, whitespace
     stripped, punctuation INCLUDED (matches production code).
  2. PASS(a): no phrase-family occurs more than 2 times among the session's empathy
     clauses (Jaccard>=0.5 OR NED<=0.3).
  3. PASS(b): zero occurrences of the same phrase-family across two turn-adjacent
     (consecutive, non-excluded) empathy clauses.
  4. Auto-FAIL override: any single phrase-family reaching >=7 occurrences among the
     session's <=10 scored turns -> FAIL (a) regardless of exact-string identity to a
     previously deleted phrase.
  5. Session verdict: PASS only if both (a) and (b) hold.

"Empathy clause" scope: only leading clauses that pass `_is_empathy_clause` (the marker
check) are entered into phrase-family clustering -- mirrors the production guard, which
only evaluates near-dup on `is_empathy=True` candidates (dialogue.py:269-273). Turns whose
leading clause is "" (no clause, or opens with '?') are excluded from clustering and
counted separately under presence (descriptive only, criterion B's charter, not A's).

Exclusions applied before scoring: turn 0 (greeting); turns >= crisis_turn if
crisis_triggered; turns whose agent_response is empty (schema-parse failure marker in
this pipeline is an empty string / missing field, checked explicitly).
"""
import json
import sys

_NEAR_DUP_JACCARD_THRESHOLD = 0.5
_NEAR_DUP_NED_THRESHOLD = 0.3

_EMPATHY_MARKERS = (
    "것 같아요", "것 같습니다",
    "감사합니다", "이해", "공감",
    "힘드셨", "힘드시", "지치셨", "지치시",
    "어려우셨", "어려우시",
    "군요",
)


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


def is_empathy_clause(clause):
    return bool(clause) and any(m in clause for m in _EMPATHY_MARKERS)


def levenshtein(a, b):
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * lb
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[lb]


def same_phrase_family(a, b):
    a_n, b_n = a.strip(), b.strip()
    if not a_n or not b_n:
        return False
    ta, tb = set(a_n.split()), set(b_n.split())
    union = ta | tb
    if union and len(ta & tb) / len(union) >= _NEAR_DUP_JACCARD_THRESHOLD:
        return True
    ned = levenshtein(a_n, b_n) / max(len(a_n), len(b_n))
    return ned <= _NEAR_DUP_NED_THRESHOLD


def cluster_families(clauses):
    """clauses: list of (turn, clause). Greedy first-fit clustering by anchor
    (matches dialogue.py's own retry-time comparison: a candidate is compared against
    every prior session clause via `_same_phrase_family`, so transitive-closure
    clustering -- not just anchor-vs-candidate -- is the correct scorer-side
    generalization of that pairwise rule)."""
    families = []
    for turn, clause in clauses:
        placed = False
        for fam in families:
            if any(same_phrase_family(clause, c) for _, c in fam):
                fam.append((turn, clause))
                placed = True
                break
        if not placed:
            families.append([(turn, clause)])
    return families


def analyze_session(path):
    d = json.load(open(path))
    turns = d["turns"]
    crisis_triggered = d.get("crisis_triggered", False)
    crisis_turn = d.get("crisis_turn")

    scored = []
    excluded = []
    for t in turns:
        n = t["turn"]
        if n == 0:
            excluded.append((n, "turn0_greeting"))
            continue
        if crisis_triggered and crisis_turn is not None and n >= crisis_turn:
            excluded.append((n, "crisis_substituted"))
            continue
        ar = t.get("agent_response")
        if not ar:
            excluded.append((n, "empty_agent_response"))
            continue
        scored.append(t)

    empathy_clauses = []  # (turn, clause) for is_empathy=True only
    non_empathy_leading = []  # (turn, clause_or_none) for descriptive presence
    for t in scored:
        n = t["turn"]
        clause = extract_leading_clause(t.get("agent_response", ""))
        if is_empathy_clause(clause):
            empathy_clauses.append((n, clause))
        else:
            non_empathy_leading.append((n, clause))

    families = cluster_families(empathy_clauses)
    family_sizes = sorted((len(f) for f in families), reverse=True)
    max_family = family_sizes[0] if family_sizes else 0
    max_family_turns = None
    if families:
        biggest = max(families, key=len)
        max_family_turns = [n for n, _ in biggest]

    # back-to-back: consecutive SCORED turn numbers (post-exclusion) both carrying
    # empathy clauses in the same phrase-family.
    empathy_by_turn = dict(empathy_clauses)
    scored_turn_nums = sorted(t["turn"] for t in scored)
    back_to_back_pairs = []
    for i in range(len(scored_turn_nums) - 1):
        a, b = scored_turn_nums[i], scored_turn_nums[i + 1]
        if b - a != 1:
            continue  # not actually consecutive turn indices (exclusion gap)
        ca, cb = empathy_by_turn.get(a), empathy_by_turn.get(b)
        if ca and cb and same_phrase_family(ca, cb):
            back_to_back_pairs.append((a, b))

    pass_a = max_family <= 2 and max_family < 7
    pass_b = len(back_to_back_pairs) == 0
    auto_fail = max_family >= 7
    verdict = "PASS" if (pass_a and pass_b and not auto_fail) else "FAIL"

    return {
        "path": path,
        "scored_turns": len(scored),
        "excluded": excluded,
        "n_empathy_clauses": len(empathy_clauses),
        "n_families": len(families),
        "max_family_count": max_family,
        "max_family_turns": max_family_turns,
        "family_sizes": family_sizes,
        "back_to_back_count": len(back_to_back_pairs),
        "back_to_back_pairs": back_to_back_pairs,
        "auto_fail_override": auto_fail,
        "pass_a": pass_a,
        "pass_b": pass_b,
        "verdict": verdict,
        "presence_count": len(empathy_clauses),
        "non_empathy_leading_turns": [n for n, c in non_empathy_leading],
    }


def main():
    paths = sys.argv[1:]
    for p in paths:
        r = analyze_session(p)
        print(f"=== {p} ===")
        print(f"scored_turns={r['scored_turns']} excluded={r['excluded']}")
        print(f"empathy_clauses={r['n_empathy_clauses']} families={r['n_families']} "
              f"family_sizes={r['family_sizes']}")
        print(f"max_family_count={r['max_family_count']} turns={r['max_family_turns']}")
        print(f"back_to_back_count={r['back_to_back_count']} pairs={r['back_to_back_pairs']}")
        print(f"auto_fail_override={r['auto_fail_override']} pass_a={r['pass_a']} "
              f"pass_b={r['pass_b']} VERDICT={r['verdict']}")
        print(f"presence(empathy_clause_count/scored_turns)={r['presence_count']}/{r['scored_turns']}")
        print()


if __name__ == "__main__":
    main()
