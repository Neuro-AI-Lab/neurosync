"""
W7b golden-scored metrics worksheet (blind scorer, reveal-partitioned).

Scores MET-1 (slot-fill/grounded-coverage proxy) and MET-3 (domain_candidates
top-1/top-3 vs golden domain labels) for SC-1, SC-12, SC-3.

Sources (whitelisted only):
- docs/ai/golden_labels_f1f2.md (Part A golden domain sets, scoring rule)
- docs/ai/simulation_results/**/*_domain_inference.json, *_conversation.json
- result.md EXP-016 (session/run identification; cross-verified against raw artifacts)

MET-3 scoring-field resolution (see RESULT for full rationale): golden_labels_f1f2.md's
own "Scoring rule" section operationalizes top-1/top-3 hit against
domain_candidates[].domain (the 8-value domain enum) -- not ai_predicted_disease
(disease-name granularity, no golden disease-name key exists in the whitelisted spec).

Read-only. No production code touched. Deterministic given the artifact files on disk.
"""
import json

D = "docs/ai/simulation_results"

GOLDEN = {
    "VP-001": {"anxiety", "sleep"},
    "VP-002": {"depression"},
    "VP-003": {"depression"},
    "VP-004": {"depression", "anxiety"},
    "VP-010": {"depression", "anxiety"},
    "VP-011": {"depression"},
    "VP-012": {"alcohol", "depression"},
}


def load(p):
    with open(p) as f:
        return json.load(f)


def conv_summary(path):
    d = load(path)
    fs = d.get("final_slots", [])
    keys = sorted(x["key"] for x in fs) if isinstance(fs, list) else sorted(fs.keys())
    return {
        "turns": d.get("total_turns", len(d.get("turns", []))),
        "crisis": d.get("crisis_triggered"),
        "slot_coverage": d.get("slot_coverage"),
        "grounded_coverage": d.get("grounded_coverage"),
        "n_filled": len(fs),
        "keys": keys,
    }


def dom_summary(path):
    d = load(path)
    return {
        "domain_candidates": d.get("domain_candidates"),
        "validation_errors": d.get("validation_errors"),
    }


def score_met3(vp, dc, validation_errors):
    if validation_errors:
        return ("excluded_pydantic", None, None)
    golden = GOLDEN[vp]
    dc = dc or []
    domains_returned = [c["domain"] for c in dc]
    top1 = (domains_returned[0] in golden) if domains_returned else False
    top3 = any(d_ in golden for d_ in domains_returned[:3])
    return ("scored", top1, top3)


# session -> (conv_ts, dom_ts)
SC1 = {
    ("VP-001", "rep1"): ("210745", "210805"),
    ("VP-001", "rep2"): ("211256", "211311"),
    ("VP-002", "rep1"): ("210751", "210806"),
    ("VP-002", "rep2"): ("211249", "211300"),
    ("VP-003", "rep1"): ("210747", "210753"),
    ("VP-003", "rep2"): ("211250", "211303"),
    ("VP-004", "rep1"): ("211023", "211039"),
    ("VP-004", "rep2"): ("211146", "211220"),
}

SC12 = {
    ("VP-010", "rep1"): ("214213", "214227"),
    ("VP-010", "rep2"): ("214459", "214514"),
    ("VP-011", "rep1"): ("214218", "214236"),
    ("VP-011", "rep2"): ("214501", "214517"),
    ("VP-012", "rep1"): ("214202", "214227"),
    ("VP-012", "rep2"): ("214459", "214516"),
}

# SC-3: Policy A arm used for primary golden scoring (consistent arm with
# SC-1/SC-12's own default). Policy B artifacts also exist but are reserved
# for the RAG A/B adjudication (critic's charter, out of scope here).
SC3 = {
    ("VP-001", "rep1"): ("220428", "220440"),
    ("VP-001", "rep2"): ("220529", "220551"),
    ("VP-002", "rep1"): ("220423", "220440"),
    ("VP-002", "rep2"): ("220528", "220550"),
    ("VP-003", "rep1"): ("220424", "220431"),
    ("VP-003", "rep2"): ("220518", "220533"),
    ("VP-004", "rep1"): ("220438", "220459"),
    ("VP-004", "rep2"): ("220604", "220628"),
}


def run_class(name, sessions):
    print(f"\n=== {name} ===")
    rows = []
    for (vp, rep), (conv_ts, dom_ts) in sorted(sessions.items()):
        conv_path = f"{D}/{vp}/{vp}_20260711_{conv_ts}_conversation.json"
        dom_path = f"{D}/{vp}/{vp}_20260711_{dom_ts}_domain_inference.json"
        c = conv_summary(conv_path)
        dm = dom_summary(dom_path)
        status, top1, top3 = score_met3(vp, dm["domain_candidates"], dm["validation_errors"])
        rows.append({"vp": vp, "rep": rep, "conv": c, "dom": dm,
                      "met3_status": status, "top1": top1, "top3": top3})
        dc_short = [(x["domain"], x["confidence"]) for x in (dm["domain_candidates"] or [])]
        print(f"{vp} {rep}: turns={c['turns']} crisis={c['crisis']} "
              f"slot_cov={c['slot_coverage']} grounded_cov={c['grounded_coverage']} "
              f"filled={c['n_filled']}/12 keys={c['keys']} | "
              f"MET3={status} top1={top1} top3={top3} dc={dc_short}")
    return rows


def aggregate_met1(rows, exclude=()):
    inc = [r for r in rows if (r["vp"], r["rep"]) not in exclude]
    n = len(inc)
    gc = sum(r["conv"]["grounded_coverage"] for r in inc) / n
    sc = sum(r["conv"]["slot_coverage"] for r in inc) / n
    fl = sum(r["conv"]["n_filled"] for r in inc) / n
    print(f"  MET-1 aggregate (n={n}, excluded={list(exclude)}): "
          f"mean_grounded_coverage={gc:.4f} mean_slot_coverage={sc:.4f} mean_filled={fl:.3f}/12")


def aggregate_met3(rows):
    scored = [r for r in rows if r["met3_status"] == "scored"]
    excl = [r for r in rows if r["met3_status"] != "scored"]
    t1 = sum(1 for r in scored if r["top1"])
    t3 = sum(1 for r in scored if r["top3"])
    print(f"  MET-3 aggregate: top1={t1}/{len(scored)} top3={t3}/{len(scored)} "
          f"excluded_pydantic={[(r['vp'], r['rep']) for r in excl]}")


if __name__ == "__main__":
    sc1_rows = run_class("SC-1", SC1)
    aggregate_met1(sc1_rows)
    aggregate_met1(sc1_rows, exclude={("VP-002", "rep1"), ("VP-004", "rep2")})
    aggregate_met3(sc1_rows)

    sc12_rows = run_class("SC-12", SC12)
    aggregate_met1(sc12_rows)
    aggregate_met1(sc12_rows, exclude={("VP-012", "rep2")})
    aggregate_met3(sc12_rows)

    sc3_rows = run_class("SC-3 (Policy A arm, truncated --max-turns 3)", SC3)
    aggregate_met1(sc3_rows)
    aggregate_met3(sc3_rows)
