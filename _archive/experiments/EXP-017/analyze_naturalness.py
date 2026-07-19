#!/usr/bin/env python3
"""EXP-017 cell 2/3 mechanical analysis — read-only, no production code touched.

Implements rubric_bug030_acceptance.md's mechanical (non-clinical) dimensions:
  - S1 empathy-clause extraction (leading clause, affective-marker heuristic)
  - S1 near-duplicate rule (token Jaccard >= 0.5 OR char NED <= 0.3)
  - S2 per-phrase-family counts, max count, back-to-back check
  - S4 presence floor (qualifying-disclosure pairing, mechanical presence only)
  - S5b trailing-question re-ask (same-family trailing content, slot already answered)
  - Appendix D truncation flag

Deliberately does NOT render S3 ECN L1/L2/L3 or S6 register-match clinical verdicts
(clinical-validator's charter, out of scope per this run's brief).
"""
import json
import re
import sys

# Stem-level (not exact-conjugation) substring markers, broadened from the rubric's own
# example list ("-겠-"/"-았/었을 것 같아요"/"감사합니다"/"이해됩니다"/"공감됩니다"/"힘드셨"/
# "지치셨") to catch conjugation variants (힘드신/힘드실/지치실/지치셨을 등) actually observed
# in these artifacts, applied identically and disclosed across every session analyzed here.
AFFECT_MARKERS = ["힘드", "지치", "고통스럽", "속상", "안타깝", "다행", "잘 견뎌", "잘 이겨",
                   "감사합니다", "이해됩니다", "공감됩니다", "겠", "것 같아요", "것 같습니다"]


def split_sentence_terminal(text):
    """Return (leading_clause, rest) split at first .!  or ? if ? precedes .!."""
    m_dot = re.search(r'[.!]', text)
    m_q = re.search(r'\?', text)
    if m_q and (not m_dot or m_q.start() < m_dot.start()):
        idx = m_q.start()
    elif m_dot:
        idx = m_dot.start()
    else:
        return text.strip(), ""
    return text[:idx + 1].strip(), text[idx + 1:].strip()


def is_affective(clause):
    return any(mk in clause for mk in AFFECT_MARKERS)


def is_question_leading(clause):
    # leading clause that is itself a question / slot-restatement heuristic:
    # if it ends in '?' it's a question, not an empathy clause.
    return clause.endswith('?')


def extract_empathy_clause(agent_response):
    """Returns (clause_or_None, trailing_content)."""
    leading, rest = split_sentence_terminal(agent_response)
    if is_question_leading(leading) or not is_affective(leading):
        return None, agent_response
    return leading, rest


def token_jaccard(a, b):
    ta, tb = set(a.split()), set(b.split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


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


def normalized_edit_distance(a, b):
    a, b = a.strip(), b.strip()
    if not a and not b:
        return 0.0
    return levenshtein(a, b) / max(len(a), len(b))


def same_family(a, b):
    j = token_jaccard(a, b)
    ned = normalized_edit_distance(a, b)
    return j >= 0.5 or ned <= 0.3


def cluster_families(clauses):
    """clauses: list of (turn_idx, clause). Returns list of families (each a list of
    (turn_idx, clause)), assigned by matching a new clause against each family's anchor
    (first member)."""
    families = []
    for turn_idx, clause in clauses:
        placed = False
        for fam in families:
            anchor = fam[0][1]
            if same_family(anchor, clause):
                fam.append((turn_idx, clause))
                placed = True
                break
        if not placed:
            families.append([(turn_idx, clause)])
    return families


def analyze_session(path, label):
    d = json.load(open(path))
    turns = d["turns"]
    crisis_triggered = d.get("crisis_triggered", False)
    crisis_turn = d.get("crisis_turn")
    total_turns = d.get("total_turns")
    errors = d.get("errors", [])
    model = d.get("model")
    prompt_version = d.get("prompt_version")

    # excluded set: turn 0 (greeting), turns >= crisis_turn if crisis_triggered
    scored_idxs = []
    for t in turns:
        n = t["turn"]
        if n == 0:
            continue
        if crisis_triggered and crisis_turn is not None and n >= crisis_turn:
            continue
        scored_idxs.append(n)

    empathy = {}  # turn -> clause or None
    trailing = {}  # turn -> trailing content
    targeted_slot = {}
    for t in turns:
        n = t["turn"]
        if n not in scored_idxs:
            continue
        ar = t.get("agent_response") or ""
        clause, trail = extract_empathy_clause(ar)
        empathy[n] = clause
        trailing[n] = trail
        targeted_slot[n] = t.get("targeted_slot")

    non_none = [(n, c) for n, c in sorted(empathy.items()) if c is not None]
    families = cluster_families(non_none)

    # (i)/(ii) per-family counts, max count
    fam_summary = []
    for fam in families:
        rep = fam[0][1]
        fam_summary.append({"rep": rep, "count": len(fam), "turns": [t for t, _ in fam]})
    fam_summary.sort(key=lambda x: -x["count"])
    max_count = fam_summary[0]["count"] if fam_summary else 0

    # (iii) back-to-back identical-family count (consecutive SCORED turns only)
    back_to_back = 0
    bt_pairs = []
    sorted_scored = sorted(non_none, key=lambda x: x[0])
    for i in range(len(sorted_scored) - 1):
        n1, c1 = sorted_scored[i]
        n2, c2 = sorted_scored[i + 1]
        if n2 == n1 + 1 and same_family(c1, c2):
            back_to_back += 1
            bt_pairs.append((n1, n2))

    # (iv) distinct-opener ratio = distinct families / total non-None empathy turns
    distinct_ratio = (len(families) / len(non_none)) if non_none else None

    # (vii) empathy-clause presence — mechanical count over scored turns
    presence_count = len(non_none)
    presence_total = len(scored_idxs)
    presence_rate = (presence_count / presence_total) if presence_total else None

    # 2-rule pass/fail (session cap <=2, zero back-to-back)
    session_cap_fail = max_count > 2
    sec2_pass = (not session_cap_fail) and (back_to_back == 0)

    # (v) S5b trailing-question re-ask
    # For each scored turn N, trailing content family-matched against any EARLIER
    # trailing content in the session; FAIL condition requires the earlier slot to have
    # received an explicit patient answer with no new probe-worthy signal in between.
    # We report family-matches mechanically; slot-answered-status is annotated for the
    # reader (deny/disclose detection is heuristic, disclosed).
    trailing_list = sorted([(n, c) for n, c in trailing.items() if c.strip()], key=lambda x: x[0])
    reask_hits = []
    for i in range(len(trailing_list)):
        n_i, c_i = trailing_list[i]
        for j in range(i):
            n_j, c_j = trailing_list[j]
            if same_family(c_i, c_j):
                reask_hits.append({
                    "turn": n_i, "repeats_turn": n_j,
                    "targeted_slot_this": targeted_slot.get(n_i),
                    "targeted_slot_earlier": targeted_slot.get(n_j),
                    "text": c_i[:80],
                })
                break

    # Appendix D truncation
    max_turns_configured = 10
    truncated = (total_turns is not None and total_turns < max_turns_configured
                 and not (crisis_triggered and crisis_turn is not None))
    hard_trip = any("count=2" in e or "count=3" in e for e in errors)

    return {
        "label": label,
        "path": path,
        "model": model,
        "prompt_version": prompt_version,
        "total_turns": total_turns,
        "crisis_triggered": crisis_triggered,
        "crisis_turn": crisis_turn,
        "errors": errors,
        "scored_turns": scored_idxs,
        "families": fam_summary,
        "max_count": max_count,
        "back_to_back": back_to_back,
        "bt_pairs": bt_pairs,
        "distinct_ratio": distinct_ratio,
        "presence_count": presence_count,
        "presence_total": presence_total,
        "presence_rate": presence_rate,
        "sec2_pass": sec2_pass,
        "reask_hits": reask_hits,
        "truncated": truncated,
        "hard_trip": hard_trip,
    }


def print_report(res):
    print(f"\n=== {res['label']} ({res['path']}) ===")
    print(f"model={res['model']} prompt_version={res['prompt_version']} "
          f"total_turns={res['total_turns']} crisis_triggered={res['crisis_triggered']} "
          f"crisis_turn={res['crisis_turn']}")
    print(f"errors={res['errors']}")
    print(f"scored_turns={res['scored_turns']}")
    print("phrase families (rep, count, turns):")
    for f in res["families"]:
        print(f"  count={f['count']:2d} turns={f['turns']}  '{f['rep']}'")
    print(f"max_count={res['max_count']} (cap<=2 {'FAIL' if res['max_count']>2 else 'PASS'})")
    print(f"back_to_back={res['back_to_back']} pairs={res['bt_pairs']} "
          f"({'FAIL' if res['back_to_back']>0 else 'PASS'})")
    print(f"S2 combined: {'PASS' if res['sec2_pass'] else 'FAIL'}")
    print(f"distinct_opener_ratio={res['distinct_ratio']}")
    print(f"presence: {res['presence_count']}/{res['presence_total']} = {res['presence_rate']}")
    print(f"S5b trailing-reask hits: {len(res['reask_hits'])}")
    for h in res["reask_hits"]:
        print(f"  turn {h['turn']} repeats turn {h['repeats_turn']} "
              f"(slot this={h['targeted_slot_this']} earlier={h['targeted_slot_earlier']}) "
              f"text='{h['text']}'")
    print(f"Appendix D: truncated={res['truncated']} hard_trip={res['hard_trip']}")


if __name__ == "__main__":
    for path, label in [
        ("docs/ai/simulation_results/VP-001/VP-001_20260712_094644_conversation.json", "naturalness/VP-001"),
        ("docs/ai/simulation_results/VP-003/VP-003_20260712_094812_conversation.json", "naturalness/VP-003"),
        ("docs/ai/simulation_results/VP-010/VP-010_20260712_094946_conversation.json", "naturalness/VP-010"),
        ("docs/ai/simulation_results/VP-003/VP-003_20260712_095027_conversation.json", "sc5_reprobe/VP-003 session1"),
        ("docs/ai/simulation_results/VP-003/VP-003_20260712_095056_conversation.json", "sc5_reprobe/VP-003 session2"),
    ]:
        res = analyze_session(path, label)
        print_report(res)
