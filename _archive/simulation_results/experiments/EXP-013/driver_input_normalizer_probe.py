"""EXP-013 task 2, method B — throwaway diagnostic driver (NOT part of src/).

Calls the merged branch's real InputNormalizerAgent.run() directly (same
ModelRouter/PromptLoader construction as F1Pipeline) on a small, representative
set of texts, to positively confirm/characterize the ISS-039 prompt-v1/schema
mismatch (critic ruling d, PLAN-2026-W28-N). No src/ edits. Read-only probe.

Run from apps/ai-server:
    PYTHONPATH=. .venv/bin/python /path/to/driver_input_normalizer_probe.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.getcwd())

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

if not os.environ.get("PROMPTS_BASE_DIR"):
    from pathlib import Path
    os.environ["PROMPTS_BASE_DIR"] = str(Path(__file__).resolve())  # overridden below anyway

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Force the corrected absolute PROMPTS_BASE_DIR (same fix applied for task 1/3 this wave).
os.environ["PROMPTS_BASE_DIR"] = "/tmp/wt-f1-stt-ocr-integration/docs/ai/prompts"

from src.agents.input_normalizer import InputNormalizerAgent  # noqa: E402
from src.dependencies import get_model_router, get_prompt_loader  # noqa: E402
from src.schemas.input_normalizer import InputNormalizerInput  # noqa: E402

# Representative texts:
#  - 3 lifted verbatim from the v1 prompt's own STT-교정-대상 example table (docs/ai/prompts/
#    input_normalizer/v1.system.md) — designed to require an actual correction (STT typo,
#    colloquial, dialect), i.e. force a non-empty `changes` array.
#  - 1 filler/repetition example (also from the prompt's own table).
#  - 1 already-clean control (no correction needed — expect a genuine no-op).
#  - 1 risk-phrase + colloquial combination (safety-preservation check under fallback).
SAMPLES = [
    ("stt_typo", "잠이 안 와여"),
    ("colloquial", "맨날 피곤해여"),
    ("dialect", "머하노 요즘"),
    ("filler_repeat", "그 그 그래서 음... 아 힘들어여"),
    ("already_clean_control", "요즘 잠을 잘 못 자고 식욕이 줄었어요."),
    ("risk_phrase_plus_colloquial", "죽고싶다는 생각이 자꾸 들어여 맨날"),
]


async def main() -> None:
    mr = get_model_router()
    pl = get_prompt_loader()
    agent = InputNormalizerAgent(model_router=mr, prompt_loader=pl)

    results = []
    for tag, text in SAMPLES:
        out = await agent.run(InputNormalizerInput(
            session_id=f"probe_{tag}",
            raw_text=text,
            input_type="user_text",
        ))
        row = {
            "tag": tag,
            "raw_text": text,
            "reason_summary": out.reason_summary,
            "normalized_text": out.normalized_text,
            "change_count": out.change_count,
            "changes": [c.model_dump() for c in out.changes],
            "risk_expressions_preserved": out.risk_expressions_preserved,
            "clinical_content_preserved": out.clinical_content_preserved,
            "fallback": out.reason_summary is not None and out.reason_summary.startswith("fallback"),
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False))

    n_fallback = sum(1 for r in results if r["fallback"])
    print(f"\nSUMMARY: {n_fallback}/{len(results)} calls hit the fallback path "
          f"(reason_summary starts with 'fallback:')")


if __name__ == "__main__":
    asyncio.run(main())
