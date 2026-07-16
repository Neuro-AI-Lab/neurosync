"""RAG-corpus <-> VP-persona leakage audit (DATASET-005, PLAN-2026-W28-G T2-data/W1c).

Read-only. Checks whether `rag.case_card` / `rag.qa` (the two tables F2 Stage 1's
`retrieve_domain_chunks()` queries, see `apps/ai-server/src/rag/retrieval.py:183-225`)
contain any VP-001~004 persona-derived content (names, golden-label chief-complaint
quotes, distinctive residence details), and cross-checks row counts / provenance
(`source_ref`) against the AI-Hub loaders (`load_case_cards.py`, `load_qa.py`).

Never prints DATABASE_URL / secrets — only aggregate counts, booleans, and
non-sensitive `source_ref` path samples (AI-Hub file-path strings, not clinical
content). Requires DATABASE_URL in the environment (see apps/ai-server/.env).

Usage (from repo root):
  cd apps/ai-server && set -a && source .env && set +a && \
    .venv/bin/python ../../analysis/rag_corpus_leakage_audit.py

Run once, 2026-07-09, against the live workstation DB (223.194.33.26:28881) as
part of DATASET-005's leakage checklist. Deterministic given the DB state (no
randomness affects results; the one `ORDER BY random()` sample is provenance-only
illustration, not a checked assertion).
"""

from __future__ import annotations

import sys

sys.path.insert(0, "apps/ai-server")
sys.path.insert(0, "apps/ai-server/src")

from src.rag.tooling._db import connect  # noqa: E402

VP_NAMES = ["김서연", "이준호", "박민수", "최하은"]

# Exact chief-complaint quotes cited as DATASET-004 golden-label evidence
# (discussion.md DATASET-004, "Golden domain sets" table).
VP_GOLDEN_QUOTES = [
    "최근 3주간 지속되는 불안감과 수면 문제",
    "6주 전 경도 우울로 첫 방문 후 재진",
    "극심한 우울, 자살 사고, 절망감",
    "공황 발작이 새로 발생",
]

# Distinctive residence fragments from the 4 persona files (DATASET-003 precedent
# grep list, discussion.md DATASET-003 "Known leakage risks").
VP_REGIONS = ["관악구", "강서구", "분당구", "마포구", "반지하"]


def _count(cur, sql: str, params: tuple) -> int:
    cur.execute(sql, params)
    return cur.fetchone()[0]


def main() -> None:
    with connect() as conn, conn.cursor() as cur:
        print("=== Row counts (expect case_card=1248, qa=1789, symptom=40, disease=26,"
              " session_insights=4 — pinned 2026-07-09, matches EXP-005 preflight for"
              " case_card/qa/symptom/disease) ===")
        for tbl in ("case_card", "qa", "symptom", "disease", "session_insights"):
            print(f"  rag.{tbl}: {_count(cur, f'SELECT count(*) FROM rag.{tbl}', ())}")

        print("\n=== VP persona name occurrence in case_card/qa text columns ===")
        for name in VP_NAMES:
            cc = _count(
                cur,
                "SELECT count(*) FROM rag.case_card WHERE situation ILIKE %s "
                "OR intervention ILIKE %s OR summary_full ILIKE %s",
                (f"%{name}%", f"%{name}%", f"%{name}%"),
            )
            qa = _count(
                cur,
                "SELECT count(*) FROM rag.qa WHERE question ILIKE %s OR answer ILIKE %s",
                (f"%{name}%", f"%{name}%"),
            )
            print(f"  '{name}': case_card={cc}, qa={qa}")

        print("\n=== DATASET-004 golden-label chief-complaint quote overlap (exact substring) ===")
        for q in VP_GOLDEN_QUOTES:
            cc = _count(
                cur,
                "SELECT count(*) FROM rag.case_card WHERE situation ILIKE %s "
                "OR intervention ILIKE %s OR summary_full ILIKE %s",
                (f"%{q}%", f"%{q}%", f"%{q}%"),
            )
            qa = _count(
                cur,
                "SELECT count(*) FROM rag.qa WHERE question ILIKE %s OR answer ILIKE %s",
                (f"%{q}%", f"%{q}%"),
            )
            print(f"  {q[:24]}...: case_card={cc}, qa={qa}")

        print("\n=== VP distinctive region occurrence ===")
        for r in VP_REGIONS:
            cc = _count(
                cur,
                "SELECT count(*) FROM rag.case_card WHERE situation ILIKE %s "
                "OR intervention ILIKE %s OR summary_full ILIKE %s",
                (f"%{r}%", f"%{r}%", f"%{r}%"),
            )
            qa = _count(
                cur,
                "SELECT count(*) FROM rag.qa WHERE question ILIKE %s OR answer ILIKE %s",
                (f"%{r}%", f"%{r}%"),
            )
            print(f"  '{r}': case_card={cc}, qa={qa}")

        print("\n=== source_ref provenance (AI-Hub file paths, no clinical content) ===")
        cur.execute("SELECT source_ref FROM rag.case_card ORDER BY random() LIMIT 3")
        for row in cur.fetchall():
            print(f"  case_card sample: {row[0]}")
        cur.execute("SELECT source_ref FROM rag.qa ORDER BY random() LIMIT 3")
        for row in cur.fetchall():
            print(f"  qa sample: {row[0]}")
        cc_vp = _count(cur, "SELECT count(*) FROM rag.case_card WHERE source_ref ILIKE %s", ("%VP-%",))
        qa_vp = _count(cur, "SELECT count(*) FROM rag.qa WHERE source_ref ILIKE %s", ("%VP-%",))
        print(f"  case_card source_ref LIKE 'VP-%%': {cc_vp}")
        print(f"  qa source_ref LIKE 'VP-%%': {qa_vp}")

        print("\n=== AI-Hub split provenance (Training/Validation merged into flat corpus) ===")
        for tbl in ("case_card", "qa"):
            cur.execute(
                f"""SELECT CASE WHEN source_ref LIKE 'Training/%%' THEN 'Training'
                                WHEN source_ref LIKE 'Validation/%%' THEN 'Validation'
                                ELSE 'other' END AS split, count(*)
                    FROM rag.{tbl} GROUP BY split"""
            )
            print(f"  {tbl}: {cur.fetchall()}")

        print("\n=== case_card class / flag_suicidal distribution (AI-Hub label, not VP-derived) ===")
        cur.execute("SELECT class, count(*) FROM rag.case_card GROUP BY class ORDER BY count(*) DESC")
        print(f"  class: {cur.fetchall()}")
        cur.execute("SELECT flag_suicidal, count(*) FROM rag.case_card GROUP BY flag_suicidal")
        print(f"  flag_suicidal: {cur.fetchall()}")

        print("\n=== qa specialty distribution ===")
        cur.execute("SELECT specialty, count(*) FROM rag.qa GROUP BY specialty")
        print(f"  specialty: {cur.fetchall()}")

        print("\n=== duplicate source_ref (UNIQUE constraint sanity) ===")
        cur.execute(
            "SELECT count(*) FROM (SELECT source_ref FROM rag.case_card "
            "GROUP BY source_ref HAVING count(*) > 1) t"
        )
        print(f"  case_card dup source_ref groups: {cur.fetchone()[0]}")
        cur.execute(
            "SELECT count(*) FROM (SELECT source_ref FROM rag.qa WHERE source_ref IS NOT NULL "
            "GROUP BY source_ref HAVING count(*) > 1) t"
        )
        print(f"  qa dup source_ref groups: {cur.fetchone()[0]}")

        print("\n=== session_insights isolation (should hold exactly the 4 VP sim sessions,"
              " never queried by F2 Stage 1 per retrieval.py:183-225) ===")
        cur.execute("SELECT class, flag_suicidal FROM rag.session_insights ORDER BY generated_at")
        print(f"  rows: {cur.fetchall()}")

    print("\nDONE")


if __name__ == "__main__":
    main()
