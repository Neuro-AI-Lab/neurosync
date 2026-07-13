"""Canary zero-hit verification — DATASET-006, `PLAN-2026-W28-Q` W6 (data).

Read-only. Verifies that none of the 21 exact-match canary tokens embedded in
`docs/ai/personas/_canary_audit/VP-0NN_*.md` (7 personas x 3 canaries each,
wave W7A, `REV-023` section 6 canary design) appear anywhere in the three RAG
tables a leak could plausibly reach:

  - rag.case_card  (F2 Stage-1 retrieval corpus, external AI-Hub content)
  - rag.qa         (F2 Stage-1 retrieval corpus, external AI-Hub content)
  - rag.session_insights (VP-derived table; BUG-022's ground-truth channel;
    `REV-023` ruling 1a Issue 2 — extends DATASET-006's canary zero-hit check
    here now that the canary-copy storage-location fix (`_canary_audit/`,
    `REV-023` Issue 1) has landed)

This is a PRE-RUN check: no SC-13 canary session has executed yet (no
canary-augmented F1/F2 session exists), so a zero-hit result here confirms
"no accidental prior leak channel already deposited this wave's tokens" —
it does NOT substitute for the live SC-13 behavioral sweep once canary-
augmented sessions actually run (`REV-023` section 6, "Assertion sweep").

`rag.session_insights.situation_encrypted`/`intervention_encrypted` are
AES-GCM encrypted BYTEA columns (`apps/api/alembic/versions/0005`) and are
NOT SQL-ILIKE-searchable without decryption; this script checks the
plaintext-queryable columns instead (`slots` JSONB — migration 0007 — plus
`class`), which is the union of what BUG-022's own named ground-truth
channel (`class`/`phq9_score`/`gad7_score`/`flag_suicidal`) could structurally
carry (all typed scalars except `slots`, none of which can contain an
inserted-string canary token via the existing `load_simulations.py` write
path, since no canary-augmented session has ever been loaded). This
limitation is disclosed, not silently skipped — see `DATASET-006` in
discussion.md.

Never prints DATABASE_URL / secrets / ENCRYPTION_KEY — only aggregate counts.

Usage (from repo root):
  cd apps/ai-server && set -a && source .env && set +a && \
    .venv/bin/python ../../analysis/canary_zero_hit_verification.py
"""

from __future__ import annotations

import sys

sys.path.insert(0, "apps/ai-server")
sys.path.insert(0, "apps/ai-server/src")

from src.rag.tooling._db import connect  # noqa: E402

# The 21 canary_id tokens, wave W7A — verbatim from the `_canary_audit/`
# copies (`docs/ai/personas/_canary_audit/VP-0NN_*.md`, DATASET-006).
CANARY_IDS: list[str] = [
    "CANARY-VP001-W7A-U4PHS", "CANARY-VP001-W7A-ZRT7L", "CANARY-VP001-W7A-AMLEL",
    "CANARY-VP002-W7A-K9KLY", "CANARY-VP002-W7A-D1Q4Z", "CANARY-VP002-W7A-XJTVE",
    "CANARY-VP003-W7A-F740L", "CANARY-VP003-W7A-4W4KB", "CANARY-VP003-W7A-0AWKQ",
    "CANARY-VP004-W7A-8ACL6", "CANARY-VP004-W7A-PW9MV", "CANARY-VP004-W7A-NJ4MA",
    "CANARY-VP010-W7A-WABJ9", "CANARY-VP010-W7A-GZGAZ", "CANARY-VP010-W7A-VFM5J",
    "CANARY-VP011-W7A-0QVXK", "CANARY-VP011-W7A-XIG0C", "CANARY-VP011-W7A-WGENH",
    "CANARY-VP012-W7A-PNCLQ", "CANARY-VP012-W7A-RF6CJ", "CANARY-VP012-W7A-5ETFU",
]

assert len(CANARY_IDS) == 21, f"expected 21 canary tokens, got {len(CANARY_IDS)}"


def _count(cur, sql: str, params: tuple) -> int:
    cur.execute(sql, params)
    return cur.fetchone()[0]


def main() -> None:
    with connect() as conn, conn.cursor() as cur:
        print("=== Row counts (context only; unrelated to canary hits) ===")
        for tbl in ("case_card", "qa", "session_insights"):
            print(f"  rag.{tbl}: {_count(cur, f'SELECT count(*) FROM rag.{tbl}', ())}")

        total_hits = 0

        print("\n=== rag.case_card (situation/intervention/summary_full) ===")
        cc_hits = 0
        for tok in CANARY_IDS:
            n = _count(
                cur,
                "SELECT count(*) FROM rag.case_card WHERE situation ILIKE %s "
                "OR intervention ILIKE %s OR summary_full ILIKE %s",
                (f"%{tok}%", f"%{tok}%", f"%{tok}%"),
            )
            cc_hits += n
            if n:
                print(f"  HIT {tok}: {n}")
        print(f"  case_card total hits across 21 tokens: {cc_hits}")
        total_hits += cc_hits

        print("\n=== rag.qa (question/answer) ===")
        qa_hits = 0
        for tok in CANARY_IDS:
            n = _count(
                cur,
                "SELECT count(*) FROM rag.qa WHERE question ILIKE %s OR answer ILIKE %s",
                (f"%{tok}%", f"%{tok}%"),
            )
            qa_hits += n
            if n:
                print(f"  HIT {tok}: {n}")
        print(f"  qa total hits across 21 tokens: {qa_hits}")
        total_hits += qa_hits

        print("\n=== rag.session_insights (slots::text, class — plaintext-queryable only;"
              " situation_encrypted/intervention_encrypted are AES-GCM BYTEA, not"
              " ILIKE-searchable, see module docstring) ===")
        si_hits = 0
        for tok in CANARY_IDS:
            n = _count(
                cur,
                "SELECT count(*) FROM rag.session_insights WHERE slots::text ILIKE %s "
                "OR class ILIKE %s",
                (f"%{tok}%", f"%{tok}%"),
            )
            si_hits += n
            if n:
                print(f"  HIT {tok}: {n}")
        print(f"  session_insights total hits across 21 tokens (plaintext columns): {si_hits}")
        total_hits += si_hits

        print(f"\n=== GRAND TOTAL hits across 21 tokens x 3 tables: {total_hits} ===")
        print("PASS (zero-hit)" if total_hits == 0 else "FAIL (non-zero hit — investigate before SC-13)")

    print("\nDONE")


if __name__ == "__main__":
    main()
