"""코퍼스 임베딩 (Upstage passage 4096). embedding IS NULL 인 행만 (증분/재실행 안전).

UPSTAGE_API_KEY=... python -m src.rag.tooling.embed_corpus
EMBED_DUMMY=1 이면 키 없이 더미 벡터로 배관만 관통.
"""

from __future__ import annotations

from src.rag.embed import PASSAGE_MODEL, USE_DUMMY, embed_passages, to_pgvector
from src.rag.tooling._db import connect

MODEL_TAG = "dummy" if USE_DUMMY else PASSAGE_MODEL
BATCH = 32
MAXCHARS = 4000


def _clean(t: str | None) -> str:
    t = (t or "").strip()[:MAXCHARS]
    return t if t else "(내용 없음)"


def _embed_safe(texts: list[str]) -> list[list[float]]:
    try:
        return embed_passages(texts)
    except Exception:
        if len(texts) == 1:
            return [embed_passages([texts[0][:1500]])[0]]
        mid = len(texts) // 2
        return _embed_safe(texts[:mid]) + _embed_safe(texts[mid:])


def _run(cur, conn, table: str, id_col: str, text_sql: str, label: str) -> None:
    cur.execute(f"SELECT {id_col}, {text_sql} FROM rag.{table} WHERE embedding IS NULL")
    rows = cur.fetchall()
    print(f"{label}: {len(rows)}건 ({MODEL_TAG})", flush=True)
    done = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i : i + BATCH]
        vecs = _embed_safe([_clean(r[1]) for r in chunk])
        for (rid, _), v in zip(chunk, vecs, strict=False):
            cur.execute(
                f"UPDATE rag.{table} SET embedding=%s::vector, embedding_model=%s "
                f"WHERE {id_col}=%s",
                (to_pgvector(v), MODEL_TAG, rid),
            )
        conn.commit()
        done += len(chunk)
        print(f"  {done}/{len(rows)}", flush=True)


def main() -> None:
    with connect() as conn, conn.cursor() as cur:
        _run(cur, conn, "case_card", "card_id", "situation", "case_card")
        _run(cur, conn, "qa", "qa_id", "question", "qa")
        _run(
            cur,
            conn,
            "symptom",
            "symptom_id",
            "coalesce(name_ko,name) || ': ' || coalesce(synonyms::text,'')",
            "symptom",
        )


if __name__ == "__main__":
    main()
