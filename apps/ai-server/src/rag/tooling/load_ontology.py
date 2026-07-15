"""disease / symptom / disease_symptom 적재 (ontology.py 기반, 데이터셋 불필요).

python -m src.rag.tooling.load_ontology
"""

from __future__ import annotations

from psycopg.types.json import Jsonb

from src.rag import ontology as O
from src.rag.tooling._db import connect


def main() -> None:
    with connect() as conn, conn.cursor() as cur:
        for slug, (name, name_ko, kcd, cat, desc) in O.DISEASES.items():
            # Per-entry source (PLAN-2026-W28-Q W6, plan §9 provenance
            # fix): was hardcoded 'ada' for every row — now 'ada' for the
            # original 26, 'team' for W6+ team-authored entries (e.g.
            # alcohol-use-disorder), via O.disease_source(). Unpacking
            # above is untouched (DISEASES stays a 5-tuple; see
            # ontology.py's DISEASE_SOURCE comment for why).
            source = O.disease_source(slug)
            cur.execute(
                """INSERT INTO rag.disease (slug,name,name_ko,kcd_code,category,description,source)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (slug) DO NOTHING""",
                (slug, name, name_ko, kcd, cat, desc, source),
            )
        for flag in O.SYMPTOMS:
            src = "ada" if flag in O.ADA_SOURCE else "flag"
            cur.execute(
                """INSERT INTO rag.symptom (name,name_ko,bucket,synonyms,source)
                   VALUES (%s,%s,'symptom',%s,%s) ON CONFLICT (name) DO NOTHING""",
                (flag, O.SYMPTOM_KO.get(flag), Jsonb(O.SYNONYMS.get(flag, [])), src),
            )
        cur.execute("SELECT slug, disease_id FROM rag.disease")
        did = dict(cur.fetchall())
        cur.execute("SELECT name, symptom_id FROM rag.symptom")
        sid = dict(cur.fetchall())
        for slug, flags in O.DISEASE_SYMPTOMS.items():
            for f in flags:
                if slug in did and f in sid:
                    cur.execute(
                        """INSERT INTO rag.disease_symptom (disease_id,symptom_id,source)
                           VALUES (%s,%s,'ada') ON CONFLICT DO NOTHING""",
                        (did[slug], sid[f]),
                    )
        conn.commit()
        for t in ("disease", "symptom", "disease_symptom"):
            cur.execute(f"SELECT count(*) FROM rag.{t}")
            print(f"{t}: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
