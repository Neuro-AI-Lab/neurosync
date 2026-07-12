"""F3 simulator score-selection modes — HARNESS ONLY, never `src/`.

`docs/ai/f3_quick_dev_plan.md` §7. Builds the `answer_fn` seam
`src.f3.administer_survey`/`run_f3_administration` expects:
``Callable[[ScaleItem], Awaitable[int]]``. `src/f3.py` imports nothing from
this module (or any other module under `tests/`) — the harness
(`src/continuous_test.py`) is the sole caller, exactly the direction
`continuous_test.py` already imports `src.f1`/`src.f2` (never the reverse).

Two modes:

- `SurveyAnswerLLM` (§7.1, default): in-persona per-item score selection
  over K-EXAONE (`friendli.ai`, `LG_K_EXAONE_API_KEY`/
  `LG_K_EXAONE_ENDPOINT_ID`, temperature 0.7 — same vendor as
  `tests/simulation/patient_llm.py::PatientLLM`, verified byte-accurate by
  REV-036). A NEW, separate client instance per survey administration — no
  shared `_history` with an in-progress F1 conversation.
- `expected_answer_fn` (§7.2, fallback): deterministic, zero LLM — reads the
  persona markdown's own "### {SCALE} 예상 항목별 점수" table. Raises
  loudly (never guesses) if a persona has no such table for the requested
  scale.
"""

from __future__ import annotations

import logging
import os
import re

import openai

from src.scoring.item_bank import ScaleItem
from tests.simulation.patient_llm import PERSONAS_DIR, PatientPersona

logger = logging.getLogger(__name__)

_INTEGER_RE = re.compile(r"-?\d+")


def _parse_first_integer(text: str) -> int | None:
    match = _INTEGER_RE.search(text)
    if match is None:
        return None
    return int(match.group(0))


class SurveyAnswerLLM:
    """In-persona per-item score selection over K-EXAONE (plan §7.1).

    Per item: one-shot prompt = persona system prompt + a bare `[min,max]`
    integer ask (no anchor phrases — none exist repo-wide, plan §2.2).
    Strict first-standalone-integer parse; out-of-range/unparseable -> ONE
    re-prompt; still failing -> clamp to the nearest valid bound + WARNING
    log (never a silent default). `self.clamped_items` records which item
    indices needed clamping, for harness-side diagnostics.
    """

    def __init__(
        self,
        persona: PatientPersona,
        api_key: str | None = None,
        base_url: str = "https://api.friendli.ai/dedicated/v1",
        model: str | None = None,
    ) -> None:
        _api_key = api_key or os.environ.get("LG_K_EXAONE_API_KEY", "")
        _model = model or os.environ.get("LG_K_EXAONE_ENDPOINT_ID", "")
        if not _api_key or not _model:
            raise ValueError(
                "LG_K_EXAONE_API_KEY and LG_K_EXAONE_ENDPOINT_ID must be set for SurveyAnswerLLM"
            )
        self.persona = persona
        self._client = openai.AsyncOpenAI(api_key=_api_key, base_url=base_url)
        self._model = _model
        self.clamped_items: list[int] = []

    async def __call__(self, item: ScaleItem) -> int:
        return await self.answer(item)

    async def answer(self, item: ScaleItem) -> int:
        prompt = self._build_prompt(item)
        raw = await self._ask(prompt)
        value = _parse_first_integer(raw)

        if value is None or not (item.response_min <= value <= item.response_max):
            logger.warning(
                "survey_answer_llm.retry — item=%d raw=%r out of range or unparseable, "
                "re-prompting once",
                item.index,
                raw,
            )
            retry_prompt = (
                f"{prompt}\n\n숫자 하나만, {item.response_min}-{item.response_max} "
                "범위 내로만 답하세요."
            )
            raw = await self._ask(retry_prompt)
            value = _parse_first_integer(raw)

        if value is None or not (item.response_min <= value <= item.response_max):
            clamped = max(
                item.response_min,
                min(item.response_max, value if value is not None else item.response_min),
            )
            logger.warning(
                "survey_answer_llm.clamped — item=%d raw=%r clamped_to=%d range=[%d,%d]",
                item.index,
                raw,
                clamped,
                item.response_min,
                item.response_max,
            )
            self.clamped_items.append(item.index)
            return clamped

        return value

    def _build_prompt(self, item: ScaleItem) -> str:
        return (
            "다음 항목에 대해 지난 2주간 당신의 상태를 가장 잘 나타내는 숫자를 "
            f"{item.response_min}-{item.response_max} 사이에서 하나만 답하세요: {item.text_ko}"
        )

    async def _ask(self, user_content: str) -> str:
        messages = [
            {"role": "system", "content": self.persona.system_prompt},
            {"role": "user", "content": user_content},
        ]
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.7,
            max_tokens=20,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": False},
                "parse_reasoning": True,
                "include_reasoning": False,
            },
        )
        return (resp.choices[0].message.content or "").strip()


_EXPECTED_TABLE_ROW_RE = re.compile(r"\|\s*(\d+)\.[^|]*\|\s*(\d+)\s*\|")


def _extract_expected_scores_table(persona_md_content: str, scale_name: str) -> dict[int, int]:
    """Parse the persona markdown's own "### {scale} 예상 항목별 점수" table
    into ``{item_index: expected_score}``. Raises `ValueError` (loud, never a
    guess) if no such table exists in the given content.
    """
    section_pattern = re.compile(
        rf"###\s*{re.escape(scale_name)}\s*예상\s*항목별\s*점수(.*?)(?=\n###|\n##\s|\n---|\Z)",
        re.DOTALL,
    )
    section_match = section_pattern.search(persona_md_content)
    if not section_match:
        raise ValueError(
            f"No '### {scale_name} 예상 항목별 점수' table found in persona markdown — "
            "expected_answer_fn does not guess a score for an undocumented scale/persona"
        )

    scores: dict[int, int] = {}
    for row_match in _EXPECTED_TABLE_ROW_RE.finditer(section_match.group(1)):
        idx, score = int(row_match.group(1)), int(row_match.group(2))
        scores[idx] = score

    if not scores:
        raise ValueError(
            f"'### {scale_name} 예상 항목별 점수' table found but no item rows parsed"
        )
    return scores


class ExpectedAnswerFn:
    """Deterministic answer_fn bound to one persona/scale (plan §7.2). Zero
    LLM — reads the persona markdown's own documented expected per-item
    score table. Raises loudly (never guesses) on an undocumented item or
    an out-of-range documented value (a persona-data bug, not something to
    silently paper over).
    """

    def __init__(self, persona_id: str, scale_name: str) -> None:
        matches = list(PERSONAS_DIR.glob(f"{persona_id}_*.md"))
        if not matches:
            raise FileNotFoundError(f"Persona file not found: {PERSONAS_DIR}/{persona_id}_*.md")
        content = matches[0].read_text(encoding="utf-8")
        self.persona_id = persona_id
        self.scale_name = scale_name
        self._scores = _extract_expected_scores_table(content, scale_name)

    async def __call__(self, item: ScaleItem) -> int:
        if item.index not in self._scores:
            raise ValueError(
                f"No documented expected score for {self.scale_name} item {item.index} in "
                f"persona {self.persona_id} — expected_answer_fn does not guess"
            )
        value = self._scores[item.index]
        if not (item.response_min <= value <= item.response_max):
            raise ValueError(
                f"Persona {self.persona_id}'s documented {self.scale_name} item {item.index} "
                f"score {value} is out of the item bank's valid range "
                f"[{item.response_min},{item.response_max}]"
            )
        return value


def expected_answer_fn(persona_id: str, scale_name: str) -> ExpectedAnswerFn:
    """Factory — returns a callable `answer_fn` bound to one persona/scale."""
    return ExpectedAnswerFn(persona_id, scale_name)
