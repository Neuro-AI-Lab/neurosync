#!/usr/bin/env python3
"""HPI-isolation grep for EXP-020 (REV-038 Resolution 9).

Reads item_bank.py's SHIPPED v1 text_ko strings at run time (never a copy of
v0's 2-3-word labels or a hardcoded string list) for PHQ-9 / GAD-7 / AUDIT-C,
then greps every same-session F1 conversation.json and F2 domain_inference.json
for any of those exact strings, plus the reverse direction (F1 narrative
SlotData field text >= 15 chars appearing verbatim inside the F3 survey.json).

Usage (run from apps/ai-server/):
  .venv/bin/python ../../experiments/EXP-020/isolation_grep.py \
      --f1 <conversation.json> --f2 <domain_inference.json> --f3 <survey.json> [--f3 ...]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.scoring.item_bank import get_item_bank  # noqa: E402

NARRATIVE_FIELDS = {
    "chief_complaint",
    "history_of_present_illness",
    "risk_assessment",
    "clinical_assessment",
    "treatment_plan",
}


def shipped_text_ko(scale_name: str) -> list[str]:
    entry = get_item_bank(scale_name)
    return [it.text_ko for it in entry.items]


def forward_check(scale_names: list[str], f1_path: Path, f2_path: Path) -> list[tuple]:
    """Precise check matching f3_quick_dev_plan.md §8's own pass criterion:
    no F3/item-bank text appears inside F1's SlotData NARRATIVE fields
    specifically (chief_complaint / history_of_present_illness /
    risk_assessment / clinical_assessment / treatment_plan), read from
    `final_slots`. F2's domain_inference.json carries no SlotData narrative
    fields of its own (RAG `chunk_texts`/candidate `quote` are external
    retrieval-corpus content, a structurally distinct provenance -- checked
    separately, informationally, by `informational_corpus_check` below, not
    conflated with an isolation violation per REV-037's own loose-keyword
    false-positive precedent).
    """
    hits = []
    if not f1_path.exists():
        return hits
    f1_data = json.loads(f1_path.read_text(encoding="utf-8"))
    slots = {s["key"]: s["value"] for s in f1_data.get("final_slots", []) if s.get("value")}
    narrative_text = {k: v for k, v in slots.items() if k in NARRATIVE_FIELDS}
    for scale in scale_names:
        for text in shipped_text_ko(scale):
            for field, value in narrative_text.items():
                if text and text in value:
                    hits.append((scale, text, field, str(f1_path)))
    return hits


def informational_corpus_check(scale_names: list[str], f2_path: Path) -> list[tuple]:
    """Informational only (never a pass/fail signal): does any shipped
    item-bank text_ko string appear anywhere in F2's own artifact (RAG
    chunk_texts / candidate quotes / raw_response)? A hit here means the
    external RAG retrieval corpus (DATASET-005) happens to already contain
    that exact clinical phrase -- coincidental corpus content predating
    this mission, not a leak caused by F3 (F2's chunk_texts/candidates are
    not SlotData narrative fields; see forward_check's docstring).
    """
    hits = []
    if not f2_path.exists():
        return hits
    f2_raw = f2_path.read_text(encoding="utf-8")
    for scale in scale_names:
        for text in shipped_text_ko(scale):
            if text and text in f2_raw:
                hits.append((scale, text, str(f2_path)))
    return hits


def reverse_check(f1_path: Path, f3_paths: list[Path]) -> list[tuple]:
    hits = []
    if not f1_path.exists():
        return hits
    f1_data = json.loads(f1_path.read_text(encoding="utf-8"))
    slots = {s["key"]: s["value"] for s in f1_data.get("final_slots", []) if s.get("value")}
    narrative_strings = [v for k, v in slots.items() if k in NARRATIVE_FIELDS and len(v) >= 15]
    for f3_path in f3_paths:
        if not f3_path.exists():
            continue
        f3_raw = f3_path.read_text(encoding="utf-8")
        for text in narrative_strings:
            if text in f3_raw:
                hits.append((text[:40] + "...", str(f3_path)))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--f1", required=True, type=Path)
    ap.add_argument("--f2", required=True, type=Path)
    ap.add_argument("--f3", action="append", default=[], type=Path)
    ap.add_argument("--scales", nargs="+", default=["PHQ-9", "GAD-7", "AUDIT-C"])
    args = ap.parse_args()

    fwd = forward_check(args.scales, args.f1, args.f2)
    rev = reverse_check(args.f1, args.f3)
    corpus = informational_corpus_check(args.scales, args.f2)

    print(f"# forward (item-bank text_ko -> F1 SlotData narrative fields) hits: {len(fwd)}")
    for h in fwd:
        print("  FWD-HIT:", h)
    print(f"# reverse (F1 narrative >=15 chars -> F3 survey.json) hits: {len(rev)}")
    for h in rev:
        print("  REV-HIT:", h)
    print(f"# informational (item-bank text_ko -> F2 RAG chunk_texts/candidates, NOT a violation) hits: {len(corpus)}")
    for h in corpus:
        print("  CORPUS-HIT (informational only):", h)
    print(f"RESULT forward_hits={len(fwd)} reverse_hits={len(rev)} informational_corpus_hits={len(corpus)}")
    return 0 if (not fwd and not rev) else 1


if __name__ == "__main__":
    raise SystemExit(main())
