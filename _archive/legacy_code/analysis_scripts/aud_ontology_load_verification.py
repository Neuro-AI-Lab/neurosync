"""Independent re-verification of the AUD ontology DB load (DATASET-005 addendum,
PLAN-2026-W28-Q W6 close-out).

Read-only. Re-runs the three row-count SELECTs developer's disclosed W6-status
evidence reports (`discussion.md` PLAN-2026-W28-Q, "ALL W6 GATES GREEN" status,
2026-07-11, commit 1f47c54): rag.disease 26->27, rag.disease_symptom 169->171,
rag.symptom unchanged 40 -- plus a direct check of the new `alcohol-use-disorder`
row's `source` column and the two new DISEASE_SYMPTOMS flags, independently of
developer's own prose.

Never prints DATABASE_URL / secrets -- only aggregate counts and non-sensitive
ontology-slug/flag-name values (no clinical/session content in this table).
Requires DATABASE_URL in the environment (see apps/ai-server/.env).

Usage (from repo root):
  cd apps/ai-server && set -a && source .env && set +a && \\
    .venv/bin/python ../../analysis/aud_ontology_load_verification.py

Run 2026-07-11 against the live workstation DB, independently of developer's
own loader run, as data's REV-026-close-out DATASET-005 re-verification.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "apps/ai-server")
sys.path.insert(0, "apps/ai-server/src")

from src.rag.tooling._db import connect  # noqa: E402


def _count(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    return cur.fetchone()[0]


def main() -> None:
    with connect() as conn, conn.cursor() as cur:
        print("=== Row counts (developer's disclosed claim: disease=27, symptom=40,"
              " disease_symptom=171) ===")
        for tbl in ("disease", "symptom", "disease_symptom"):
            print(f"  rag.{tbl}: {_count(cur, f'SELECT count(*) FROM rag.{tbl}')}")

        print("\n=== rag.disease source-column breakdown (expect 26 'ada' + 1 'team') ===")
        cur.execute("SELECT source, count(*) FROM rag.disease GROUP BY source ORDER BY source")
        print(f"  {cur.fetchall()}")

        print("\n=== alcohol-use-disorder row (expect exactly 1, source='team') ===")
        cur.execute(
            "SELECT slug, name, name_ko, source FROM rag.disease WHERE slug = %s",
            ("alcohol-use-disorder",),
        )
        rows = cur.fetchall()
        print(f"  count={len(rows)}: {rows}")

        print("\n=== disease_symptom rows for alcohol-use-disorder (expect craving +"
              " perceived_loss_of_control) ===")
        cur.execute(
            "SELECT s.name FROM rag.disease_symptom ds "
            "JOIN rag.disease d ON d.disease_id = ds.disease_id "
            "JOIN rag.symptom s ON s.symptom_id = ds.symptom_id "
            "WHERE d.slug = %s ORDER BY s.name",
            ("alcohol-use-disorder",),
        )
        print(f"  {cur.fetchall()}")

        print("\n=== idempotency spot-check: duplicate slug groups in rag.disease (expect 0) ===")
        cur.execute(
            "SELECT count(*) FROM (SELECT slug FROM rag.disease GROUP BY slug "
            "HAVING count(*) > 1) t"
        )
        print(f"  duplicate slug groups: {cur.fetchone()[0]}")

    print("\nDONE")


if __name__ == "__main__":
    main()
