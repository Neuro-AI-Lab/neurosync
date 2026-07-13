"""F3 simulator score-selection modes — HARNESS ONLY, never `src/`.

`docs/ai/f3_quick_dev_plan.md` §7, `PLAN-2026-W29-A` step 3. Builds the
`answer_fn` seam `src.f3.administer_survey`/`run_f3_administration` expects:
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
  shared `_history` with an in-progress F1 conversation. As of item bank v1
  (`PLAN-2026-W29-A`), `_build_prompt` presents the item's own
  `response_anchors` (when populated) and — when `scale_name` is supplied —
  the scale's entry-level `instruction_ko` (timeframe/instruction wording),
  replacing v0's bare `[min,max]` integer ask. `instruction_ko_override`
  (`EXP-021`/`REV-040` (2)/(6)) lets a caller decouple instruction-line
  presence from `scale_name`'s live-registry lookup entirely — anchors and
  instruction are independent inputs to `build_item_prompt`, never coupled
  by branch structure. Callers that also pass `scale_name` (e.g. for
  bookkeeping) MUST pass `instruction_ko_override` explicitly whenever they
  need `F_instr=off` with anchors populated — relying on the `_UNSET`
  default in that combination silently resolves the live registry's
  instruction text instead (REV-040 Issue 1; see
  `test_cell3_shaped_instruction_override_prevents_leak` below).
- `expected_answer_fn` (§7.2, fallback): deterministic, zero LLM — reads the
  persona markdown's own "### {SCALE} 예상 항목별 점수" table. Raises
  loudly (never guesses) if a persona has no such table for the requested
  scale. Unaffected by item bank v1 (matches by item INDEX against the
  persona's own table, not by item text).
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


class _Unset:
    """Sentinel type distinguishing 'argument not passed' from an explicit
    `None` (EXP-021/REV-040 (2)). A plain `None` default could not express
    "always use the scale_name-derived instruction" vs "explicitly no
    instruction, regardless of scale_name" — this sentinel can.
    """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return "<UNSET>"


_UNSET = _Unset()


def build_item_prompt(
    *,
    text_ko: str,
    response_min: int,
    response_max: int,
    response_anchors: dict[int, str] | None,
    instruction_ko: str | None,
) -> str:
    """Pure, side-effect-free prompt construction (EXP-021/REV-040 (2)).

    Decouples instruction-line presence from anchor-menu presence: the
    original `_build_prompt` only ever emitted `instruction_ko` inside the
    anchor-populated branch, making "instruction ON, anchors OFF" and
    "instruction OFF, anchors ON" unproducible. Here `instruction_ko` and
    `response_anchors` are independent inputs, checked in this fixed order
    (instruction line first, when present; anchor-menu-or-bare-ask second) —
    every combination of the two is producible, and neither branch's
    presence implies anything about the other.

    Byte-identical to the pre-EXP-021 `_build_prompt` output for both
    historical corners: `response_anchors=None, instruction_ko=None`
    reproduces the v0 bare-integer ask exactly (§EXP-021 Cell 1); anchors
    populated + instruction present reproduces the v1 anchor-menu ask
    exactly (§EXP-021 Cell 8) — see the golden tests in
    `test_survey_answer_llm.py`.
    """
    lines: list[str] = []
    if instruction_ko:
        lines.append(instruction_ko)

    if not response_anchors:
        lines.append(
            "다음 항목에 대해 지난 2주간 당신의 상태를 가장 잘 나타내는 숫자를 "
            f"{response_min}-{response_max} 사이에서 하나만 답하세요: {text_ko}"
        )
        return "\n".join(lines)

    anchor_text = " / ".join(
        f"{value}: {label}" for value, label in sorted(response_anchors.items())
    )
    lines.append(f"문항: {text_ko}")
    lines.append(f"응답 척도: {anchor_text}")
    lines.append(
        "위 응답 척도 중 당신의 상태를 가장 잘 나타내는 숫자 하나만 답하세요 "
        f"({response_min}-{response_max})."
    )
    return "\n".join(lines)


class SurveyAnswerLLM:
    """In-persona per-item score selection over K-EXAONE (plan §7.1).

    Per item: one-shot prompt = persona system prompt + an anchor-aware ask
    (item text, its `response_anchors` when populated, and — when
    `scale_name` is supplied — the scale's `instruction_ko` timeframe
    wording; item bank v1, `PLAN-2026-W29-A`). Falls back to v0's bare
    `[min,max]` integer ask only when an item has no `response_anchors`.
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
        scale_name: str | None = None,
        instruction_ko_override: str | None | _Unset = _UNSET,
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
        self.scale_name = scale_name
        self._instruction_ko = self._resolve_instruction(scale_name, instruction_ko_override)

    @staticmethod
    def _resolve_instruction(
        scale_name: str | None,
        instruction_ko_override: str | None | _Unset = _UNSET,
    ) -> str | None:
        """Entry-level `instruction_ko` resolution (item bank v1;
        EXP-021/REV-040 (2) for the override).

        `instruction_ko_override`, when explicitly passed (including
        explicit `None`), ALWAYS takes precedence over `scale_name`'s
        live-registry lookup — this is what lets a caller hold
        `F_instr=off` even while also passing `scale_name` for bookkeeping
        (REV-040 Issue 1/Resolution 1). Only when the override is left at
        its `_UNSET` default does this fall back to the original
        `scale_name`-based resolution, byte-identical to the pre-EXP-021
        behavior: `None` when `scale_name` wasn't supplied (backward-
        compatible construction), or the scale has no instruction wording
        on record. Never raises: an unrecognized scale degrades to no
        instruction line, same as v0's behavior, rather than crashing
        prompt construction.
        """
        if not isinstance(instruction_ko_override, _Unset):
            return instruction_ko_override
        if scale_name is None:
            return None
        from src.scoring.item_bank import get_item_bank  # noqa: PLC0415 — avoid import cycles

        try:
            return get_item_bank(scale_name).instruction_ko  # type: ignore[arg-type]
        except KeyError:
            return None

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
        """Anchor-aware ask (item bank v1). Falls back to v0's bare
        `[min,max]` integer ask when `item.response_anchors` is empty (e.g.
        a future not-yet-anchored entry) — this method never fabricates
        anchor wording that isn't on `item` itself. Delegates to the pure
        `build_item_prompt` (EXP-021/REV-040 (2)) — see that function's
        docstring for the instruction/anchor decoupling this enables.
        """
        return build_item_prompt(
            text_ko=item.text_ko,
            response_min=item.response_min,
            response_max=item.response_max,
            response_anchors=item.response_anchors,
            instruction_ko=self._instruction_ko,
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
