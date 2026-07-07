"""rag.qa 적재 — AI-Hub 08.전문_의학지식 '정신건강의학과' 라벨 → question/answer.

데이터셋 레포 미포함. 경로를 env로:
  QA_DATA_DIR=".../08.전문_의학지식_데이터/3.개방데이터/1.데이터" \
  python -m src.rag.tooling.load_qa
"""

from __future__ import annotations

import glob
import json
import os

from src.rag.tooling._db import connect


def main() -> None:
    base = os.getenv("QA_DATA_DIR")
    if not base or not os.path.isdir(base):
        raise SystemExit("QA_DATA_DIR 에 08.전문_의학지식 데이터 경로를 지정하세요.")

    files = glob.glob(os.path.join(base, "*", "02.라벨링데이터", "*정신건강의학과*", "*.json"))
    rows, err = [], 0
    for fp in files:
        try:
            with open(fp, encoding="utf-8-sig") as f:
                d = json.load(f)
            q, a = d.get("question"), d.get("answer")
            if q and a:
                rows.append(
                    (
                        "정신건강의학과",
                        q.replace("\x00", ""),
                        str(a).replace("\x00", ""),
                        os.path.relpath(fp, base),
                    )
                )
        except Exception:  # noqa: BLE001
            err += 1

    with connect() as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO rag.qa (specialty,question,answer,source_ref)
               VALUES (%s,%s,%s,%s) ON CONFLICT (source_ref) DO NOTHING""",
            rows,
        )
        conn.commit()
        cur.execute("SELECT count(*) FROM rag.qa")
        print(f"qa {cur.fetchone()[0]} (파일 {len(files)}, 파싱오류 {err})")


if __name__ == "__main__":
    main()
