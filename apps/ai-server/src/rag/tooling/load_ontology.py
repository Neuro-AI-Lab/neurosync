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
            cur.execute(
                """INSERT INTO rag.disease (slug,name,name_ko,kcd_code,category,description,source)
                   VALUES (%s,%s,%s,%s,%s,%s,'ada') ON CONFLICT (slug) DO NOTHING""",
                (slug, name, name_ko, kcd, cat, desc),
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
