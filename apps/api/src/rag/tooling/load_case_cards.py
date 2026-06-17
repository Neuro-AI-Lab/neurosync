"""rag.case_card 적재 — AI-Hub 16.심리상담 라벨 JSON → 회기 단위 1행.

데이터셋은 레포 미포함(용량·라이선스). 경로를 env로:
  CASE_DATA_DIR=".../16.심리상담_데이터/3.개방데이터/1.데이터" \
  python -m src.rag.tooling.load_case_cards

NORMAL 제외 · total_time/silence 적재 · gender 정규화 · 멱등(source_ref UNIQUE).
"""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

from psycopg.types.json import Jsonb

from src.rag.tooling._db import connect

SPLITS = ["Training", "Validation"]
META = {
    "start_point",
    "end_point",
    "character_count",
    "cps",
    "paragraph_speaker",
    "paragraph_text",
    "index",
}
GENDER = {"여": "F", "남": "M", "여자": "F", "남자": "M"}


def _clean(s):
    return s.replace("\x00", "") if isinstance(s, str) else s


def _session_no(folder: str, fname: str):
    m = re.search(r"_(\d+)\s*회기", folder)
    if m:
        return int(m.group(1))
    m = re.search(r"label_[a-z]+_(\d+)_", fname)
    return int(m.group(1)) if m else None


def _split_summary(summary: str):
    sit, interv = [], []
    for chunk in summary.split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        label, sep, body = chunk.partition(":")
        body = (body if sep else chunk).strip()
        if re.search(r"증상|위험|문제|호소|특성", label):
            sit.append(body)
        elif re.search(r"개선|개입|상담|변화", label):
            interv.append(body)
        else:
            sit.append(body)
    return ("  ".join(x for x in sit if x) or summary.strip(), "  ".join(x for x in interv if x))


def _agg_flags(paragraphs):
    agg: dict[str, int] = {}
    for p in paragraphs:
        for k, v in p.items():
            if k in META:
                continue
            if isinstance(v, (int, float)) and v > 0:
                agg[k] = agg.get(k, 0) + int(v)
    return agg


def main() -> None:
    base = os.getenv("CASE_DATA_DIR")
    if not base or not os.path.isdir(base):
        raise SystemExit("CASE_DATA_DIR 에 16.심리상담 데이터 경로를 지정하세요.")

    files: list[str] = []
    for sp in SPLITS:
        files += glob.glob(os.path.join(base, sp, "02.라벨링데이터", "*", "*.json"))

    rows, errors, skipped = [], 0, 0
    for fp in files:
        try:
            with open(fp, encoding="utf-8-sig") as f:
                d = json.load(f)
            if d.get("class") == "NORMAL":
                skipped += 1
                continue
            folder, fname = Path(fp).parent.name, Path(fp).stem
            flags = _agg_flags(d.get("paragraph", []))
            sit, interv = _split_summary(d.get("summary", ""))
            rows.append(
                {
                    "person_id": d.get("id"),
                    "session_no": _session_no(folder, fname),
                    "class": d.get("class"),
                    "age": d.get("age"),
                    "gender": GENDER.get(str(d.get("gender", "")).strip()),
                    "sev_depression": d.get("depression"),
                    "sev_anxiety": d.get("anxiety"),
                    "sev_addiction": d.get("addiction"),
                    "total_time": d.get("total_time"),
                    "silence": d.get("silence"),
                    "flag_suicidal": flags.get("suicidal", 0) > 0,
                    "flags": Jsonb(flags),
                    "situation": _clean(sit),
                    "intervention": _clean(interv),
                    "summary_full": _clean(d.get("summary", "")),
                    "source_ref": os.path.relpath(fp, base),
                }
            )
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"  [err] {fp}: {e}")

    print(f"파싱: {len(rows)} (NORMAL 제외 {skipped}, 오류 {errors})")
    with connect() as conn, conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO rag.case_card
                 (person_id,session_no,class,age,gender,sev_depression,sev_anxiety,
                  sev_addiction,total_time,silence,flag_suicidal,flags,situation,
                  intervention,summary_full,source_ref)
               VALUES (%(person_id)s,%(session_no)s,%(class)s,%(age)s,%(gender)s,
                  %(sev_depression)s,%(sev_anxiety)s,%(sev_addiction)s,%(total_time)s,
                  %(silence)s,%(flag_suicidal)s,%(flags)s,%(situation)s,%(intervention)s,
                  %(summary_full)s,%(source_ref)s)
               ON CONFLICT (source_ref) DO NOTHING""",
            rows,
        )
        conn.commit()
        cur.execute("SELECT count(*) FROM rag.case_card")
        print(f"case_card 합계 {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
