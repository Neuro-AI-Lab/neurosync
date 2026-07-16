# Design note — BUG-030 iteration-2 + BUG-035 companion fix

**Status:** DESIGN ONLY. No code, prompt, or test file has been changed by this document.
**Plan reference:** `discussion.md` `PLAN-2026-W28-T` step 1.
**Linked:** `BUG-030` (open, 2026-07-12 status block), `BUG-035`, `BUG-028` (adjacent, not resolved
by this design), `ADR-028`, `REV-031`, `CVR-010`, `docs/ai/fix_proposal_bug030.md` (iteration-1),
`docs/ai/rubric_bug030_acceptance.md` (pre-registered acceptance rubric),
`experiments/EXP-017/diagnose_used_empathy.py` (residual root-cause diagnosis).
**Out of scope:** BUG-033 (probing-depth/slot-targeting) — no change proposed to
`compute_target_slot` or round-robin slot selection. Prompt files (`v4.system.md`, safety v2) stay
byte-identical; every runtime string this design adds is composed in code and injected into the
per-call `user_message`, exactly the mechanism the existing `is_repeated` guard already uses at
`dialogue.py:247-251` — not a prompt-file edit.

**Why code-level enforcement, not prompt work (grounding).** `experiments/EXP-017/
diagnose_used_empathy.py`'s residual diagnosis (`discussion.md` `STATE-2026-07-12`): in 18/18
measured violations the negative constraint (`used_empathy` X-list) was correctly shown to the
model that turn and regenerated over anyway — pure LLM non-adherence, not a code bug. Prompt-only
strengthening has already been tried (v3→v4, `ADR-028`) and the repetition bar still FAILED all 3
probe sessions (`REV-031`). This design does not touch the prompt; it adds a post-generation
check-and-retry gate, the same architecture the codebase already ships for exact-repeat detection.

---

## 0. Current code, read directly (baseline for every diff below)

`apps/ai-server/src/agents/dialogue.py` (540 lines total, read in full 2026-07-12):

- **Guard, lines 221–260** (`# 7. Repetition detection` through the retry's `except: pass`):
  full-response exact-equality only (`llm_resp.assistant_response in prev_responses`, or equal to
  any prior response `len(prev) >= 80`). On a hit: exactly **one** regeneration attempt at
  `temperature=0.7`, no re-check of the regenerated output, no telemetry beyond a log line.
- **`used_empathy` extraction + injection, lines 448–465** (inside `_build_slot_context`, the
  round-robin branch only — reached only when neither `opening_turn` nor `probe_instruction` is
  set in `session_state`, per the early returns at lines 428–432): `first_sent =
  m["content"].split(".")[0].split("?")[0][:30]`, deduped into `used_empathy`, and the last 5
  entries rendered as `X "..."` lines. The `[:30]` cap is the finding `fix_proposal_bug030.md`
  (c-v) flagged as a latent under-match risk once any negative-constraint filter is added on top —
  this design is that filter, so the cap must go.
- **`_build_opening_context` (turn 0, lines 331–389) and `_build_probe_context` (probe-protocol
  turns, lines 391–408) never compute or inject `used_empathy` at all** — confirmed by direct read,
  zero references to `used_empathy` in either method. This is a real, pre-existing gap: probe-mode
  turns get zero repetition-avoidance hint in the prompt. It is **not** fixed by editing those two
  methods in this design (would touch runtime prompt-composition logic beyond the guard's
  post-generation architecture and risks re-opening BUG-030's own "juxtaposition/menu" failure
  mode inside a new branch); instead §1 below shows why the post-generation guard, living in
  `run()` and not inside any of the three context-builder branches, closes this gap structurally.
- **`DialogueInput` schema** (`src/schemas/dialogue.py:13-48`): `user_message: str`,
  `conversation_history: list[dict[str,str]]`, `filled_slots: dict[str,str]`, `safety_result:
  dict[str,str] | None`, `session_state: dict[str, Any] | None`.
- **`f1.py` dialogue call site, turn loop** (`f1.py:1521-1533`):
  ```python
  safety_result_for_dialogue = {
      "risk_level": str(safety_out.risk_level),
      "ctrs_level": str(safety_out.ctrs_level),
  }
  dialogue_out = await self.dialogue.run(DialogueInput(
      session_id=session_id, user_message=patient_message,
      conversation_history=conversation_history, filled_slots=filled_slots,
      safety_result=safety_result_for_dialogue, session_state=session_state,
  ))
  ```
  `safety_out` (the `SafetyClassifierAgent` output for the **current** patient message) is computed
  earlier in the same turn, `f1.py:1295`, before this call — so `risk_level`/`ctrs_level` for the
  turn just received are always available to `DialogueAgent.run` via `inp.safety_result`.
  `session_state["probe_instruction"]` is set at `f1.py:1500-1503` (`probe.active`, the SI
  safety-probe state machine, triggered by `_probe_should_trigger` at `f1.py:804-808` — CTRS==3 +
  `{"suicidal_ideation","self_harm"}` category) or `f1.py:1505-1510` (the mandatory end-of-session
  SI screen). **CTRS 1–2 (`crisis_protocol_activated=True`, `schemas/safety.py:71-73`) is
  intercepted at `f1.py:1440-1456` before this call — `DialogueAgent.run` is never invoked on a
  crisis turn** (`agent_response = CRISIS_RESPONSE` directly); so the maximum `risk_level` this
  design will ever observe inside `DialogueAgent.run` is `"high"`.
  Turn-0's own call (`f1.py:1088-1098`) always passes `safety_result=None` and
  `session_state={"opening_turn": True, ...}` (no `probe_instruction` key) — confirmed by direct
  read; this matters for §4 (turn 0 auto-excludes from the presence check with zero special-case
  code).
  **`sentiment` for the current patient message is computed AFTER the dialogue call**
  (`_analyze_utterance_sentiment`, `f1.py:1585-1590`, sequentially after `dialogue_out` at
  `f1.py:1526`) — the rubric's own "qualifying disclosure" definition (`rubric_bug030_acceptance.md`
  §4, `sentiment.polarity`/`sentiment.emotions`) is therefore **structurally unavailable** to
  `DialogueAgent` at generation time for the turn it is currently answering. This is why §4 below
  defines "crisis-adjacent" from safety/probe signals, not sentiment — a deliberate, verified
  divergence from the rubric's own (retrospective, scoring-time) definition, not an oversight.

---

## 1. Guard extension architecture

Replace `dialogue.py:221-260` (the standalone exact-equality block) with a single bounded
check-and-retry loop inside `run()` that evaluates **three** independent violation conditions each
attempt — exact-repeat (existing, unchanged semantics), near-duplicate empathy clause (new, BUG-030
iter-2), and empathy-presence-missing on a crisis-adjacent turn (new, BUG-035) — and shares one
retry budget (§3) across all three, because they are symptoms of the same underlying failure
(post-generation non-adherence to a negative constraint the model was shown) and a turn should never
pay for more than one bounded regeneration cycle regardless of which check(s) fire.

**Why one loop, not three separate retry blocks:** a candidate response can fail more than one
check at once (e.g. an exact-repeat that is also, incidentally, a near-duplicate); running
independent retry blocks in sequence would multiply the worst-case call count (up to 3× today's
single retry) with no additional benefit — the loop re-evaluates ALL conditions on every new
candidate, so a single regeneration that happens to fix two conditions at once is recognized
immediately.

**Why the guard lives in `run()`, not inside `_build_slot_context`/`_build_opening_context`/
`_build_probe_context`:** the guard evaluates the LLM's output after generation, independent of
which of the three context-builder branches produced the prompt that led to it. This is what lets
the same mechanism catch BUG-035's probe-protocol-dominated turns (`_build_probe_context`, which —
per §0 — has zero `used_empathy` awareness today) without adding a fourth prompt-injection surface
or touching probe-instruction text.

### New shared primitives (all `@staticmethod` on `DialogueAgent`, mirroring the existing
`_get_previous_responses`/`_parse_response` convention)

```python
# Module-level constants, near the existing _SLOT_COVERAGE_THRESHOLD/_MAX_HISTORY_TURNS block.
_MAX_REGENERATION_ATTEMPTS = 2          # see §3 for the latency justification
_NEAR_DUP_JACCARD_THRESHOLD = 0.5       # rubric_bug030_acceptance.md §1, token-level rule
_NEAR_DUP_NED_THRESHOLD = 0.3           # rubric_bug030_acceptance.md §1, character-level rule
_EMPATHY_MARKERS = (                    # rubric_bug030_acceptance.md §1's own marker set,
    "겠", "것 같아요", "것 같습니다",       # kept in sync by direct copy — do not diverge
    "감사합니다", "이해", "공감",
    "힘드셨", "힘드시", "지치셨", "지치시",
    "어려우셨", "어려우시",
)


@staticmethod
def _extract_leading_clause(text: str) -> str:
    """Leading clause up to (not including) the first '.', '!', or '?' — no
    length cap. Replaces dialogue.py:453's `[:30]`-capped, `.`/`?`-only
    split (fix_proposal_bug030.md finding c-v: a cap silently under-matches
    any clause >30 chars once a filter is compared against it). If the
    earliest terminal punctuation found is '?', the response opens directly
    with a question — no leading clause exists (return ""). If no
    terminal punctuation exists at all, conservatively return "" rather
    than guess a boundary (no silent partial-match)."""
    stripped = text.strip()
    if not stripped:
        return ""
    positions = [(stripped.find(c), c) for c in (".", "!", "?")]
    positions = [(p, c) for p, c in positions if p != -1]
    if not positions:
        return ""
    end, term_char = min(positions, key=lambda t: t[0])
    if term_char == "?":
        return ""
    return stripped[:end].strip()


@staticmethod
def _is_empathy_clause(clause: str) -> bool:
    """Deterministic, string-level, Korean-marker-based check: does `clause`
    read as an affective acknowledgment? Mirrors
    rubric_bug030_acceptance.md §1's own marker list exactly, so the
    production guard and the offline clinical-validator scoring instrument
    agree on what counts as an empathy clause."""
    return bool(clause) and any(m in clause for m in _EMPATHY_MARKERS)


@staticmethod
def _extract_used_empathy_clauses(
    conversation_history: list[dict[str, str]] | None,
) -> list[str]:
    """Full-session (unwindowed), no-cap replacement for the extraction
    currently inlined at dialogue.py:449-455. Shared by both consumers:
    _build_slot_context's X-list (which still windows to the last 5 for the
    SHOWN prompt hint — unchanged, a separate soft-nudge design choice) and
    the retry guard below (which needs the FULL session list, unwindowed,
    to enforce rubric §2's session-wide ≤2-uses / zero-back-to-back bar —
    windowing to last-5 there would let an early-session phrase silently
    re-qualify for reuse after 5 more turns)."""
    used: list[str] = []
    if not conversation_history:
        return used
    for m in conversation_history:
        if m.get("role") == "assistant":
            clause = DialogueAgent._extract_leading_clause(m["content"])
            if clause and clause not in used:
                used.append(clause)
    return used


@staticmethod
def _levenshtein(a: str, b: str) -> int:
    """Pure-stdlib edit distance (Wagner-Fischer DP, O(len(a)*len(b))).
    Empathy clauses are short (observed <=40 chars in every artifact read
    for this design); no external dependency needed or added."""
    m, n = len(a), len(b)
    if m == 0:
        return n
    if n == 0:
        return m
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i] + [0] * n
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[n]


@staticmethod
def _same_phrase_family(a: str, b: str) -> bool:
    """rubric_bug030_acceptance.md §1's near-duplicate rule, restated
    exactly: same family if token Jaccard >= 0.5 OR normalized edit
    distance <= 0.3. Normalization: strip surrounding whitespace only
    (punctuation kept — matches the rubric's own worked examples, which
    compare clauses with trailing periods intact); tokenize on whitespace
    (어절 units), no stemming."""
    a_n, b_n = a.strip(), b.strip()
    if not a_n or not b_n:
        return False
    tokens_a, tokens_b = set(a_n.split()), set(b_n.split())
    union = tokens_a | tokens_b
    if union and len(tokens_a & tokens_b) / len(union) >= _NEAR_DUP_JACCARD_THRESHOLD:
        return True
    ned = DialogueAgent._levenshtein(a_n, b_n) / max(len(a_n), len(b_n))
    return ned <= _NEAR_DUP_NED_THRESHOLD


@staticmethod
def _empathy_repetition_violation(
    candidate_clause: str, session_clauses: list[str],
) -> str | None:
    """Operationalizes rubric §2 exactly: zero back-to-back (checked first,
    zero-tolerance even on a single prior use) + session cap of 2 uses per
    phrase family (checked second — a 3rd same-family use violates).
    Returns a reason string or None. `session_clauses` must be the FULL,
    unwindowed session list (see _extract_used_empathy_clauses)."""
    if not candidate_clause or not session_clauses:
        return None
    if DialogueAgent._same_phrase_family(candidate_clause, session_clauses[-1]):
        return "back_to_back"
    prior_family_count = sum(
        1 for c in session_clauses
        if DialogueAgent._same_phrase_family(candidate_clause, c)
    )
    if prior_family_count >= 2:
        return "session_cap"
    return None


@staticmethod
def _is_crisis_adjacent_turn(inp: DialogueInput) -> bool:
    """BUG-035 'crisis-adjacent turn' definition — reuses exactly the two
    runtime safety signals already threaded onto DialogueInput by
    f1.py:1521-1533; zero new classifier call, zero persona/ground-truth
    read.
      1. inp.session_state["probe_instruction"] truthy: the SI safety-probe
         state machine (f1.py _ProbeState, CTRS==3 + suicidal_ideation/
         self_harm, f1.py:804-808) or the mandatory end-of-session SI
         screen (f1.py:1505-1510) is driving this turn — the exact
         mechanism behind BUG-035's SC-5 multi-cycle-probe reproduction and
         CVR-010 F2.
      2. inp.safety_result["risk_level"] in {"medium","high"} — this turn's
         own SafetyClassifier verdict on the just-received patient message
         (f1.py:1295, before dialogue runs). "critical"/CTRS 1-2 never
         reaches here (f1.py:1440-1456 intercepts crisis turns before
         DialogueAgent.run is called)."""
    if inp.session_state and inp.session_state.get("probe_instruction"):
        return True
    if inp.safety_result and inp.safety_result.get("risk_level") in ("medium", "high"):
        return True
    return False


@staticmethod
def _build_retry_hint(
    violation: str, inp: DialogueInput, candidate_clause: str,
) -> str:
    """Runtime hint injected into the per-call user_message (code, not a
    prompt-file edit — same mechanism as the existing exact-repeat hint at
    dialogue.py:247-251)."""
    if violation == "exact_repeat":
        missing = DialogueAgent.missing_questionable_slots(inp.filled_slots)
        missing_text = ", ".join(missing) if missing else "risk_assessment (안전 확인)"
        return (
            f"\n\n[주의: 이전과 동일한 응답입니다. 반드시 다른 질문을 하세요. "
            f"미수집 슬롯: {missing_text}]"
        )
    if violation.startswith("near_dup"):
        return (
            f'\n\n[주의: 방금 응답의 공감 표현("{candidate_clause}")이 이전 턴과 '
            "거의 같은 표현입니다. 완전히 다른 표현으로, 환자가 방금 한 말에 맞춰 "
            "새로 공감하세요. 같은 문구나 비슷한 문구를 반복하지 마세요.]"
        )
    if violation == "presence_missing":
        return (
            "\n\n[주의: 지금은 위기 인접 상황입니다. 질문만으로 바로 시작하지 말고, "
            "반드시 공감하는 문장 1개로 먼저 시작한 뒤 질문하세요.]"
        )
    return ""
```

### `run()` replacement (conceptual diff, lines 221–260 → new loop; NOT applied)

```python
# 7. Repetition / near-duplicate / empathy-presence guard
# (BUG-030 iter-2, BUG-035; replaces the exact-equality-only block)
session_clauses = self._extract_used_empathy_clauses(inp.conversation_history)
crisis_adjacent = self._is_crisis_adjacent_turn(inp)

retry_count = 0
retry_reasons: list[str] = []
fall_through = False
retry_latency_ms = 0.0

while True:
    prev_responses = self._get_previous_responses(inp.conversation_history)
    is_repeated = (
        llm_resp.assistant_response in prev_responses
        or any(
            llm_resp.assistant_response == prev
            for prev in prev_responses
            if len(prev) >= 80
        )
    )

    candidate_clause = self._extract_leading_clause(llm_resp.assistant_response)
    is_empathy = self._is_empathy_clause(candidate_clause)
    near_dup_reason = (
        self._empathy_repetition_violation(candidate_clause, session_clauses)
        if is_empathy else None
    )
    presence_missing = crisis_adjacent and not is_empathy

    if is_repeated:
        violation: str | None = "exact_repeat"
    elif near_dup_reason:
        violation = f"near_dup_{near_dup_reason}"
    elif presence_missing:
        violation = "presence_missing"
    else:
        violation = None

    if violation is None:
        break
    if retry_count >= _MAX_REGENERATION_ATTEMPTS:
        fall_through = True
        logger.warning(
            "DialogueAgent guard exhausted retry budget (%d) — shipping "
            "with unresolved violation(s) %s",
            _MAX_REGENERATION_ATTEMPTS, retry_reasons + [violation],
        )
        retry_reasons.append(violation)
        break

    retry_count += 1
    retry_reasons.append(violation)
    logger.warning(
        "DialogueAgent guard violation (%s) — retry %d/%d",
        violation, retry_count, _MAX_REGENERATION_ATTEMPTS,
    )
    hint = self._build_retry_hint(violation, inp, candidate_clause)
    messages[-1] = ChatMessage(role="user", content=inp.user_message + hint)
    retry_started = time.perf_counter()
    try:
        resp = await adapter.chat_timed(
            messages, model=selection.model_id,
            temperature=0.7, max_tokens=512,
            response_format=response_format,
        )
        llm_resp = self._parse_response(resp.content)
    except Exception:
        fall_through = True
        break
    finally:
        retry_latency_ms += (time.perf_counter() - retry_started) * 1000
```

Note on the `fall_through` branch: when the budget is exhausted, `violation` (the reason that would
have triggered attempt `_MAX_REGENERATION_ATTEMPTS + 1`) is appended to `retry_reasons` too, so the
telemetry always records the FINAL unresolved reason alongside every reason that triggered an actual
regeneration — the tracker can distinguish "2 near-dup retries, still near-dup on ship" from "1
near-dup retry that then became presence-missing."

### `_build_slot_context` change (lines 449–455 only)

```python
used_empathy = self._extract_used_empathy_clauses(conversation_history)
```
replaces the inlined 7-line loop. Everything downstream (`lines.append('  X "{e}..."')` for
`used_empathy[-5:]`) is unchanged — the `[:30]` cap disappears because `_extract_leading_clause` has
none; the last-5 windowing for the SHOWN prompt hint is preserved (a separate, intentional
soft-nudge design choice, distinct from the guard's own unwindowed session-wide tracking — see the
docstring above).

---

## 2. Near-duplicate metric choice, justified

**Metric:** rubric `docs/ai/rubric_bug030_acceptance.md` §1 "Near-duplicate rule" restated exactly
(not reinvented): two clauses are the same phrase-family if **either** token-level Jaccard
`J = |tokens(A) ∩ tokens(B)| / |tokens(A) ∪ tokens(B)| ≥ 0.5` **or** character-level normalized edit
distance `NED = levenshtein(A, B) / max(len(A), len(B)) ≤ 0.3`. Rubric §1 defines the rule and its
worked examples; rubric §2 ("No-repetition") applies it to the session-level pass bar this design
targets — cited together here since the brief refers to "§2's Jaccard/NED clustering rule" and the
two sections should be read as one instrument, not two.

**Threshold grounding — the known data point.** `CVR-010` finding F3 / `REV-031`: EXP-017's VP-003
dominant clause is "a NED≈0.2 near-duplicate of the deleted v3 phrase." Verified directly against
the artifact (`docs/ai/simulation_results/VP-003/VP-003_20260712_094812_conversation.json`, turns
1, 3–10): the dominant clause is **"정말 힘드셨겠어요."** (9/10 turns); the deleted v3 canonical
phrase (`docs/ai/prompts/dialogue/v3.system.md` line 37, `fix_proposal_bug030.md` §2) is
**"많이 힘드셨겠어요."**. Recomputed with this design's own `_levenshtein`/`_same_phrase_family`
(not assumed from the cited number):

| A | B | Jaccard | Levenshtein | NED | Verdict |
|:--|:--|--:|--:|--:|:--|
| "정말 힘드셨겠어요." | "많이 힘드셨겠어요." | 1/3 = 0.33 | 2 | 2/10 = **0.20** | same family (via NED; Jaccard alone would MISS it) |

This confirms two things: (1) the cited NED=0.20 figure is exact, not approximate, when computed
against the real strings; (2) **Jaccard alone (0.33 < 0.5) would not have caught this pair** — the
OR-combination is load-bearing, not redundant. A near-dup detector implemented with only the
token-Jaccard half of the rule would silently pass exactly the case CVR-010/REV-031 named as the
must-catch example. `_same_phrase_family` implements both halves for this reason.

**Normalization rule — CORRECTED per REV-032 Issue 2 (`docs/ai/critic_scratch_rev032_bug030iter2.md`
Issue 2).** The original text here claimed "the rubric's own worked examples compare clauses with
trailing periods intact" — this was checked against the rubric and is **factually wrong**: rubric
§1's near-duplicate worked-example table (`docs/ai/rubric_bug030_acceptance.md` §1, the "많이
힘드셨겠어요" / "정말 힘드셨겠어요" row) is **punctuation-FREE** — none of its three example pairs
carry a trailing period, and the rubric's own stated figure for that pair is **NED≈0.22**, not 0.20.
Independent re-derivation both ways: **with** trailing periods (this design/code's own convention) —
`NED("정말 힘드셨겠어요.", "많이 힘드셨겠어요.") = 2/10 = 0.20` (matches §2's cited number exactly).
**Without** periods (the rubric's actual worked-table convention) — `NED("정말 힘드셨겠어요", "많이
힘드셨겠어요") = 2/9 = 0.222` (matches the rubric's own "≈0.22"). Both cross the ≤0.3 threshold, so
the must-catch case is unaffected either way — but the two systems were not actually pinned to the
same convention, which REV-032 correctly flagged as a genuine instrument-mismatch risk (a boundary
case near NED≈0.3 could classify oppositely).

**Resolution (binding, REV-032 criterion A.1, adopted verbatim by ADR-029 Decision 1).** The
production code's own convention — **punctuation-INCLUSIVE** normalization (strip surrounding
whitespace only; keep internal/trailing punctuation) — is PINNED as the convention `_same_phrase_
family` implements and the one any EXP-018 rubric re-scoring of the repetition bar must also use
(REV-032 criterion A.1: "empathy clause = `_extract_leading_clause` output, ... terminal punctuation
included ... any rubric re-scoring must use the identical convention"). Rubric §1's own worked-table
text is the one that needs a corresponding correction to match this pinned convention — flagged here,
not silently reconciled, per REV-032's own routing (Issue 2, "CV's rubric to correct... but... my
review scope as an instrument-validity finding"); tokenize on whitespace (어절 units) for Jaccard; no
stemming, no external tokenizer.

**Pure-stdlib implementation.** `_levenshtein` above is a standard Wagner-Fischer DP,
`O(len(a)·len(b))`, no dependency beyond the standard library — clause strings observed across every
artifact read for this design are under ~40 characters, so the cost is negligible per call.

---

## 3. Retry budget

**Recommendation: `_MAX_REGENERATION_ATTEMPTS = 2`** (up to 2 regenerations beyond the first draft
→ **max 3 LLM calls per turn**, up from today's max 2).

**Latency arithmetic (grounded, with an honest caveat on precision).** EXP-017's 2026-07-12
naturalness-probe + SC-5-reprobe artifacts (`docs/ai/simulation_results/VP-001|VP-003|VP-010/
*_094644|094812|094946|095027|095056_conversation.json`, 5 sessions, dialogue v4, the same fix
generation this design extends) give 47 scored turns' `latency_ms`: **mean 4364 ms, range
1282–9001 ms** (measured directly, not estimated). This is per-TURN pipeline latency (the chained
safety → slot-extraction → dialogue call, and today already sometimes includes one dialogue retry
when `is_repeated` fires) — the artifact schema does not expose a dialogue-only latency breakdown, so
this design cannot cite an isolated per-call number and does not invent one. Reasoning from what is
verifiable: the existing single retry already adds one more `adapter.chat_timed` call of the same
shape (`max_tokens=512`, same model/adapter) as the initial generation, and the project already
accepts that cost (it shipped in the BUG-030-iteration-1 fix, `dd4eba2`). Raising the budget from 1
to 2 adds **at most one further call of that same shape** to the worst case — not a new order of
magnitude, not unbounded.

**Why 2, not 1 or higher.** The residual diagnosis (`experiments/EXP-017/diagnose_used_empathy.py`,
`STATE-2026-07-12`) measured the negative-constraint violation rate at **18/18** — the model ignored
the shown X-list on every checked opportunity under the OLD (prompt-hint-only) mechanism. Near-dup
and presence conditions are expected to fire far more often than the narrow exact-full-response-
equality case the existing single-retry guard was built for; a budget of 1 gives the guard exactly
one chance to fix whichever of three conditions fired, with no chance to recover if the SAME
regeneration accidentally trips a DIFFERENT condition (e.g., a regeneration that fixes near-dup by
switching to a bare-question opener, tripping presence-missing instead, on a crisis-adjacent turn —
a realistic outcome given the model already ignores explicit instructions at scale). A budget of 2
gives the loop a second, still-bounded chance to converge. A budget higher than 2 is explicitly
rejected here: it would risk exactly the "infinite loop / latency blowup" the brief warns against,
and there is no evidence yet (this design predates any run) that 2 is insufficient — EXP-018 step 7
measures the actual retry rate, fall-through rate, and p95 latency delta empirically; if the data
shows 2 is starving legitimate cases, that is a finding for the NEXT iteration, not a guess to bake
in now.

**On exhaustion — fall-through, never block.** If a violation still holds after
`_MAX_REGENERATION_ATTEMPTS` regenerations, the loop breaks with `fall_through = True` and the
**last-generated** response ships (not the original first draft — later attempts carry the most
specific hint and are, if anything, marginally more likely to have partially improved even when not
fully compliant). `retry_reasons` records every reason that triggered an attempt, including the
final unresolved one. A `logger.warning` fires (never silent — matches the "no silent failures"
discipline) and the telemetry (§6) exposes the flag to the tracker. On an LLM-call exception during
a retry, the loop also falls through immediately (same `except: pass`-then-ship semantics the
existing code already has for its single retry) rather than raising — a guard defect must never take
the session down.

---

## 4. Empathy-presence check (BUG-035 companion)

**Trigger — crisis-adjacent turn, defined and grounded in §1's `_is_crisis_adjacent_turn`.** Reuses
only fields already on `DialogueInput` (`safety_result: dict[str,str] | None`, `session_state:
dict[str, Any] | None`) and already populated by `f1.py:1500-1533` — no new classifier call, no
persona/ground-truth field, no harness dependency. The two OR-ed conditions:
1. `session_state.get("probe_instruction")` truthy — the SI safety-probe state machine or the
   mandatory SI screen is active this turn. This is the exact mechanism BUG-035's reproduction
   (`docs/ai/simulation_results/VP-003/VP-003_20260712_095027_conversation.json`, "SC5-session1
   turns 5–8", per `error.md` BUG-035) sits inside — a multi-turn probe cycle.
2. `safety_result.get("risk_level") in ("medium", "high")` — this turn's own just-computed safety
   verdict, independent of whether the probe state machine happens to be active (covers e.g. a
   single elevated-risk turn that does not (yet) trigger the CTRS==3 probe threshold).
Turn 0 auto-excludes (verified: `session_state={"opening_turn": True, ...}` never carries
`probe_instruction`, and `safety_result=None` at that call site) — no special-case code needed,
matching rubric §1's own turn-0 exclusion for a different, independently-verified reason.

**Check.** `presence_missing = crisis_adjacent and not is_empathy` — where `is_empathy` is computed
by the SAME `_extract_leading_clause` + `_is_empathy_clause` pair the near-dup check uses (§5). A
crisis-adjacent turn whose candidate response opens directly with a bare question, or whose leading
clause carries no affective marker, triggers a retry with the presence hint (`_build_retry_hint`,
`"presence_missing"` branch, §1).

**Shares the near-dup/exact-repeat retry budget, not a separate one.** A single shared
`_MAX_REGENERATION_ATTEMPTS` (§3) across all three conditions keeps the worst-case per-turn call
count bounded to the same number regardless of how many conditions a candidate violates
simultaneously — a crisis-adjacent turn that is BOTH near-dup and presence-missing (plausible: a
bare-question opener is automatically presence-missing, and cannot be near-dup since `near_dup_reason`
is only computed `if is_empathy`, so in practice these two conditions are close to mutually
exclusive per-candidate, but the loop's re-evaluation on every new candidate still needs the shared
budget to avoid double-spending retries across two "different" bugs that are really one turn).

**Scope discipline — this is presence, not content quality.** The check only asks "is there an
empathy clause at all" (`is_empathy` boolean), never whether it is well-anchored to what the patient
said (rubric §3's L1/L2/L3 naturalness ladder) or register-matched (rubric §6) — those remain
clinical-adequacy judgments for the CVR at EXP-018 step 8, not string checks this design invents,
consistent with the "verification is external" discipline `fix_proposal_bug030.md` §2's guard-rail
section already applied to the iteration-1 fix.

---

## 5. Empathy-clause detection rule

Defined once, in §1, as the shared primitive both the near-dup check (§2) and the presence check
(§4) operate on — restated here per the brief's own numbering:

`_extract_leading_clause(text)`: scan `text` (after `.strip()`) for the earliest occurrence of `.`,
`!`, or `?`. If the earliest is `?`, the response opens with a bare question — no leading clause
(`""`). If none of the three exist, conservatively return `""` (never guess a boundary). Otherwise
return everything before that character, stripped.

`_is_empathy_clause(clause)`: `True` iff the extracted clause is non-empty and contains at least one
of a fixed Korean affective-marker set — `겠 / 것 같아요 / 것 같습니다 / 감사합니다 / 이해 / 공감 /
힘드셨 / 힘드시 / 지치셨 / 지치시 / 어려우셨 / 어려우시` — copied directly from
`rubric_bug030_acceptance.md` §1's own marker list so the production guard and the offline
clinical-validator scoring instrument classify the same clause the same way.

**Known limitation, disclosed rather than solved.** Korean questions do not always carry a literal
`?` (e.g. `-나요`/`-까요`/`-습니까` endings without terminal punctuation). This design's `?`-position
check will miss such a case (treat it as "no terminal punctuation found" → `""` → correctly still
"no empathy clause," so the presence check is NOT fooled into a false pass — but a genuinely
empathetic clause that happens to lack punctuation before a later `.`/`!` could also be
under-detected). This is a real, named residual risk, not solved here because the brief's own
scoping — "deterministic, string-level... e.g., leading sentence ends before the first question
mark" — asks for exactly this class of check, and a heavier NLP/sentence-boundary model is out of
the "pure stdlib" / "no harness dependency" constraint. EXP-018's telemetry (§6) will surface this
empirically if it matters at scale: a high `presence_missing` retry rate on turns whose SHIPPED
final response (after fall-through) visibly does contain empathy content would be the signal to
revisit this rule in a later iteration — flagged for qa/critic at the gate, not resolved by guessing
here.

---

## 6. Telemetry fields

All fields ride the **existing** `DialogueOutput` → `F1TurnLog` → conversation-JSON artifact path
(the same path `prompts_degraded` already uses, `f1.py:1535` extraction → `f1.py:1566-1583`
`F1TurnLog(...)` construction → `docs/ai/simulation_results/.../conversation.json` `turns[]`
entries, confirmed by direct read of a live artifact's turn schema, §0). **No new file is written by
production code.**

**`src/schemas/dialogue.py` `DialogueOutput` — new fields (all with safe defaults, additive):**
```python
retry_count: int = Field(default=0, description="Regeneration attempts this turn (BUG-030 iter-2 / BUG-035 guard)")
retry_reasons: list[str] = Field(default_factory=list, description="Ordered violation reasons that triggered each attempt: exact_repeat | near_dup_back_to_back | near_dup_session_cap | presence_missing")
fall_through: bool = Field(default=False, description="True if the retry budget was exhausted while a violation still held — response shipped anyway")
retry_latency_ms: float = Field(default=0.0, description="Wall-clock time spent in regeneration LLM calls only (subset of latency_ms)")
crisis_adjacent: bool = Field(default=False, description="True if this turn qualified for the BUG-035 empathy-presence check")
```
Defaults mean the two non-guard `DialogueOutput` construction sites (`routes/chat.py:95,111`, the
crisis/handoff-ready LLM-bypass paths, which never call `DialogueAgent.run`) need **zero** changes —
confirmed via `grep -rn "DialogueOutput(" src/` (4 non-class-definition hits: `dialogue.py:265`,
`routes/chat.py:95,111`, plus test fixtures).

**`f1.py` `F1TurnLog` dataclass (lines 178-205) — new fields**, threaded the same way
`dialogue_prompts_degraded` already is (extracted right after `dialogue_out` at `f1.py:1534-1535`,
then passed straight into the `F1TurnLog(...)` constructor call at `f1.py:1566-1583` — no
cross-agent OR-fold needed, unlike `prompts_degraded`, since these values come from Dialogue alone):
```python
dialogue_retry_count: int = 0
dialogue_retry_reasons: list[str] = field(default_factory=list)
dialogue_fall_through: bool = False
dialogue_retry_latency_ms: float = 0.0
dialogue_crisis_adjacent: bool = False
```

**What this unlocks for EXP-018 (tracker, step 7, not this design's job to run):** retry rate
(`retry_count > 0` / total turns), broken out by `retry_reasons` (near-dup vs presence vs
exact-repeat, since one turn can log more than one reason across its attempts); fall-through count
and rate; p95 turn latency delta attributable to the guard specifically via
`sum(dialogue_retry_latency_ms)` vs total `latency_ms` (not conflating guard cost with
safety/slot-extraction latency); crisis-adjacent turn count vs `presence_missing` rate within that
subset (the BUG-035-specific number CVR-010 F1/F2 needs).

---

## 7. Test plan sketch

New unit tests, `tests/repro/test_bug_030_iter2.py` (new file, mirrors `test_bug_030.py`'s existing
style — direct `DialogueAgent.__new__(DialogueAgent)` construction for pure-function tests of the
new `@staticmethod`s, and the `_wire_adapter_with_responses(agent, [...])` mock-adapter pattern
already established in `tests/repro/test_bug_025.py:66-87` for `run()`-level integration tests):

1. **`_same_phrase_family` true/false positives, including the grounded NED=0.20 case.**
   `assert DialogueAgent._same_phrase_family("정말 힘드셨겠어요.", "많이 힘드셨겠어요.") is True`
   (the exact CVR-010/REV-031 pair, §2) — locks in that NED alone (Jaccard 0.33 < 0.5) must decide
   it. A true-negative case with genuinely different content (e.g. "이야기해 주셔서 감사합니다." vs
   "정말 힘드셨겠어요.") asserts `False`. A Jaccard-only true positive (e.g. the rubric §1 worked
   example, "그런 상황이라면 정말 지치셨을 것 같아요" vs "정말 지치셨을 것 같아요") asserts `True`
   via the Jaccard branch, checked independently of NED (assert Jaccard alone would already decide
   it, i.e. `>= 0.5`).
2. **`_extract_leading_clause` + `_is_empathy_clause` on a bare-question opener.** A response like
   `"혹시 최근에 잠은 잘 주무시나요?"` (question-only, no preceding clause) →
   `_extract_leading_clause` returns `""` (earliest terminal punctuation is `?`) →
   `_is_empathy_clause("")` is `False`. Contrast with a genuine empathy-clause response (e.g. the
   real VP-003 turn-1 text) → non-empty clause containing `겠`/`것 같아요` → `True`.
3. **Presence detector on a synthetic crisis-adjacent bare-question turn.** Construct
   `DialogueInput` with `session_state={"probe_instruction": "..."}` and a mocked LLM response that
   opens with a bare question (no clause) → assert the guard fires `"presence_missing"` and a retry
   is attempted (via `_wire_adapter_with_responses` with 2 queued responses: bare-question, then a
   compliant empathy-first response) → assert `retry_count == 1`, `"presence_missing" in
   retry_reasons`, `fall_through is False`.
4. **Crisis-adjacent gating on/off.** `_is_crisis_adjacent_turn` unit tests: `True` for
   `session_state={"probe_instruction": "..."}`; `True` for `safety_result={"risk_level": "high",
   ...}` with `session_state=None`; `False` for `safety_result={"risk_level": "low", ...}` and no
   probe instruction; `False` for `safety_result=None, session_state={"opening_turn": True}` (the
   real turn-0 shape, confirmed against `f1.py:1088-1098`) — locks in that turn 0 never enters the
   presence check.
5. **Retry-budget exhaustion → fall-through.** Wire `_MAX_REGENERATION_ATTEMPTS + 1` (3) queued
   mock responses that ALL reproduce the same near-dup clause against a seeded
   `conversation_history` → assert exactly `_MAX_REGENERATION_ATTEMPTS` regenerations occur (not
   more — the adapter mock's `side_effect` list length proves no 4th call is attempted), the loop
   exits with `fall_through is True`, `retry_count == _MAX_REGENERATION_ATTEMPTS`, and the SHIPPED
   `assistant_response` is the LAST queued response (not the first draft) — locks in "ship the last
   attempt, never block."
6. **Near-dup session-cap vs back-to-back distinction.** Seed `conversation_history` with the SAME
   phrase-family clause at turns 1 and 3 (2 non-consecutive prior uses) and a candidate at turn 5
   also matching that family → assert `_empathy_repetition_violation` returns `"session_cap"` (not
   `"back_to_back"`, since turn 3 is not the immediately-preceding turn if turn 4 differs). Seed a
   candidate immediately following a same-family prior turn → assert `"back_to_back"` takes
   priority even on the FIRST reuse (zero-tolerance, no session-cap count needed).
7. **Regression — `_build_slot_context`'s X-list still renders, uncapped.** Extend
   `test_bug_030.py::TestNegativeConstraintOnly` (existing file, not rewritten) with one new case: a
   prior assistant turn whose first clause is `>30` chars (a case the OLD `[:30]`-capped extraction
   would have truncated) → assert the X-list line contains the FULL untruncated clause, not a
   30-char-truncated one — the direct regression lock for the cap removal (item 1 of the brief).
8. **`test_previously_used_phrase_never_recommended_again`-style mutation check for the new guard**
   (mirrors `test_bug_030.py`'s own explicit mutation-check convention): seed a candidate response
   whose leading clause is a known near-duplicate (the NED=0.20 pair from item 1) of a prior turn →
   assert the guard's `run()`-level loop actually retries (not just that the pure-function detector
   returns `True` in isolation) — this is the test that would FAIL if someone wired
   `_empathy_repetition_violation`'s result into the loop but forgot to also gate it on `is_empathy`
   (or any other integration slip), catching a class of bug the pure unit tests above cannot.

**Mutation-check discipline (qa gate, step 5 of `PLAN-2026-W28-T`):** items 1, 6, and 8 are
specifically constructed to FAIL against a naive implementation (Jaccard-only, no back-to-back
priority, or a detector wired but not gated on `is_empathy`) and PASS against this design — the same
discipline `fix_proposal_bug030.md` §3 item 5 established for iteration-1.

---

## 8. Regression surface

**SM-01..08b.** Any `dialogue.py` change forces the full SM regression re-run
(`PLAN-2026-W28-T` step 7, vs the on-branch `EXP-014 r2` baseline) — no way around this given the
guard sits in `DialogueAgent.run`'s main path. Expectation, not a guarantee this design can verify:
assertion-level parity with `EXP-014 r2` and the iteration-1 `EXP-017` run (`SM-08b`'s known
`BUG-026` fail stays unchanged — this design touches nothing safety-classifier-related). New
`DialogueOutput`/`F1TurnLog` fields are additive with defaults (§6) — confirmed via `grep -rn
"DialogueOutput("` that both `routes/chat.py` construction sites never pass guard-related kwargs and
need no edits; no `model_dump() == {...}` exact-equality test pattern was found in `tests/` (checked
by grep) that additive fields could break.

**BUG-028 territory (`dialogue.py:211-250`, now `211-`~330 post-change).** `fix_proposal_bug030.md`
§2 explicitly argued AGAINST widening the guard in iteration-1 specifically because it overlaps
BUG-028's own flagged region ("retry-hint fires but fails to diversify," `error.md` BUG-028). This
design does exactly what that argument warned against — deliberately, per the user-ratified
iteration-2 direction (`STATE-2026-07-12`, `PLAN-2026-W28-T`). Consequence, named honestly rather
than smoothed over: the new near-dup/presence retries can ALSO fail to diversify (same class of risk
BUG-028 already documented at n=1), and this design does NOT resolve BUG-028 — it gives BUG-028 a
much larger, structured n via `retry_reasons`/`fall_through` telemetry (§6), which is new empirical
evidence for that bug, not a fix for it. EXP-018's report must not claim BUG-028 addressed.

**Latency.** §3's budget increase (1→2 max regenerations) is explicitly bounded, but the EXPECTED
TRIGGER RATE is the real open risk, not the per-attempt cost: the residual diagnosis measured an
18/18 negative-constraint violation rate under the OLD (prompt-only) mechanism, so if near-dup alone
fires on a large fraction of turns, AVERAGE (not just worst-case) per-turn latency could shift
materially, not just the tail. EXP-018 step 7's "retry telemetry (retry rate, fall-through count,
p95 latency delta)" is the empirical check this design cannot substitute for — if the observed
near-dup trigger rate turns out to dominate (e.g. >50% of scored turns), that is itself a signal
worth flagging back to the design (the guard would no longer be "a backstop," it would be the
primary mechanism), not something to silently accept as intended.

**Probe-context turns (`_build_probe_context`, `dialogue.py:391-408`).** These turns have zero
`used_empathy`/X-list prompt hint today (§0) — this design's guard is the FIRST repetition/presence
enforcement mechanism to reach them at all, since it operates in `run()` regardless of branch. This
is the intended fix surface for BUG-035, but it also means probe turns will see a NEW category of
retry (`presence_missing`, since `_is_crisis_adjacent_turn` is `True` on essentially every active
probe turn by construction) that never existed before — expected and desired, but the tracker must
report the probe-turn subset's retry/fall-through rate SEPARATELY from round-robin turns (already
supported by `crisis_adjacent` in the telemetry, §6), not pooled into one session-wide number, since
these are structurally the highest-stakes turns (SI/self-harm content) where a fall-through matters
clinically most.

**De-escalation-turn boundary (named, not resolved).** The single turn where a probe cycle
concludes (`outcome == "deescalate"`, `f1.py:1340-1356`, sets `probe.active=False` and
`risk_grounded=True` in the SAME turn before the dialogue call) falls through to the ordinary
round-robin branch at generation time — `session_state` for that turn carries no
`probe_instruction` key, so `_is_crisis_adjacent_turn` returns `False` unless `safety_result` for
that specific answer is independently medium/high. Whether this boundary turn (immediately following
an SI disclosure/denial cycle) SHOULD count as crisis-adjacent for the presence check is a genuine
open design question this document flags rather than guesses at — routed to critic/clinical-validator
at `PLAN-2026-W28-T` step 2 for a ruling, since resolving it either way changes the guard's trigger
surface and should be reviewed, not silently decided here.

**Prompt files.** `docs/ai/prompts/dialogue/v4.system.md` stays byte-identical — every string this
design adds is composed in `dialogue.py` and injected into the per-call `user_message` (§1), never
into the loaded system-prompt file. AVC-17 pin table: **no new row** — the existing v4 pin (`
f93e995f68e3a3bc88ddd5ce1f6b01ef8feb5e5663bda46ce4958ae8e6317144`) and safety v2 pin
(`3e9ca6b44ba3373f70c068758a2e1ae860f3c58483394a85fed9e13a90b3390c`) are both untouched; confirmed no
code in this design reads or writes either prompt file's content. Re-verified post-implementation:
`sha256sum docs/ai/prompts/dialogue/v4.system.md docs/ai/prompts/safety_classifier/v2.system.md`
still reads both pins verbatim, `git status` shows zero changes under `docs/ai/prompts/`.

---

## 9. As-implemented amendments (ADR-029 Decisions 2/3/5) — 2026-07-12, developer

Recorded post-implementation, per the HANDOFF's requirement that this design note carry the
mechanism actually shipped. All three amendments are binding per ADR-029; none is a deviation from
that ADR — this section documents HOW each was mechanized, since the ADR left the mechanism to
developer's judgment for D2's exact marker set and D3's mechanism.

**D2 — marker-set correction (REV-032 Issue 1 ∩ CVR-011 Finding 5).**
`apps/ai-server/src/agents/dialogue.py:59-71` (`_EMPATHY_MARKERS`). Bare `"겠"` removed as a
standalone tuple element (was the false-positive channel REV-032 Issue 1 named — a procedural clause
like `"여쭤보겠습니다"` no longer matches on that substring alone). `"군요"` added to close CVR-011
Finding 5's near-dup blind spot (unmarked reflective templates, e.g. `"그러시군요"`, are now detected
as empathy clauses so they participate in the near-dup/session-cap check instead of repeating
undetected). The other 8 markers (`것 같아요`/`것 같습니다`/`감사합니다`/`이해`/`공감`/`힘드셨`/
`힘드시`/`지치셨`/`지치시`/`어려우셨`/`어려우시`) are unchanged from the original design. Locked in by
`tests/repro/test_bug_030_iter2.py::TestMarkerSetCorrectionD2` (bare-`겠` procedural clause →
`is_empathy=False`; `-군요` reflective clause → `is_empathy=True`; a genuinely-affective
`겠`-containing clause that also carries another marker, e.g. `"정말 힘드셨겠어요"`, is unaffected).
REV-032 criterion E's own bare-`겠`-solely-triggered spot-check is now structurally impossible to
trigger in production (bare `겠` is no longer a marker at all) — criterion E stands as written for
completeness but its precondition can no longer occur.

**D3 — de-escalation-concluding-turn coverage (REV-032 Issue 3/B.4 ∩ CVR-011 Findings 3/4 + binding
condition 1).** Mechanism: `f1.py` already computes a local `probe_just_concluded` flag at Step 1b
(`f1.py:1317`, set `True` at the "deescalate" outcome or stage-exhaustion branches) for an unrelated
purpose (the probe-retrigger cooldown check). This design threads that SAME already-computed local,
unchanged, into the round-robin branch's `session_state` construction
(`f1.py:1535-1550`) as a new key, `probe_just_concluded: True` — added to the EXISTING, already-
licensed, schema-unconstrained `session_state: dict[str, Any]` field (`DialogueInput`, `src/schemas/
dialogue.py`), the identical mechanism `prior_missing_slots` already established, per rubric §10.3's
own non-binding recommendation ("a one-turn 'probe just concluded' flag threaded the same way
`prior_missing_slots` already is"). No new `DialogueInput` field, no new business logic — only an
existing value routed through an existing polymorphic channel. `DialogueAgent._is_crisis_adjacent_
turn` (`dialogue.py`) checks `session_state.get("probe_just_concluded")` as a third OR-condition
alongside `probe_instruction` and `safety_result.risk_level`. This structurally guarantees the
de-escalation-CONCLUDING turn itself is always crisis-adjacent, independent of that turn's own
recomputed CTRS (CVR-011 binding condition 1) — closing exactly the incidental-coverage gap REV-032
Issue 3 and CVR-011 Finding 3 identified. The WIDER post-de-escalation population (turns several
steps after de-escalation, e.g. `VP-003_095027` turns 9–10) remains structurally unenforceable at
generation time (sentiment is computed after the dialogue call, §0) and is measured, not
runtime-guarded, per ADR-029 Decision 3 and REV-032 criterion B.2/B.3 — unchanged from the original
design's own honest scoping.

Consequence for the caller-scoped `session_state` allowlist test (`tests/repro/
test_session_state_allowlist.py`, REV-024 ruling 3): `probe_just_concluded` was added to
`APPROVED_SESSION_STATE_KEYS` (5 → 6 keys) as a necessary, in-scope consequence of this change — the
existing `test_probe_mode_trigger_and_deescalation` fixture already exercises a "deescalate" outcome
end-to-end and was extended with a direct assertion that `probe_just_concluded=True` appears on the
capture dialogue call for that turn, proving the mechanism live rather than only in a unit test.

**D5 — presence-priority ordering (CVR-011 Finding 8).** `dialogue.py`'s unified guard loop checks
`presence_missing` FIRST, before `is_repeated`/`near_dup_reason` (`dialogue.py`, the `if
presence_missing: violation = "presence_missing"` branch precedes the `exact_repeat`/`near_dup`
`elif`s). This is sufficient to implement D5's exact requirement without a separate `crisis_adjacent`
guard wrapper: `presence_missing` is defined as `crisis_adjacent and not is_empathy` (§4, unchanged),
so `presence_missing` can only be `True` when `crisis_adjacent` already is — checking it first
therefore elevates it above `exact_repeat`/`near_dup` precisely and only in the crisis-adjacent case,
matching D5's wording exactly ("when `crisis_adjacent=True`, `presence_missing` takes PRIORITY").
Locked in by `tests/repro/test_bug_030_iter2.py::TestPresencePriorityD5`, which constructs a candidate
that is SIMULTANEOUSLY an exact repeat of a prior turn AND a bare-question opener on a crisis-adjacent
turn, and asserts the retry fires with reason `"presence_missing"` (not `"exact_repeat"`) and the
retry hint sent to the LLM is the presence hint text, not the repeat hint.

**Telemetry invariant note (REV-032 criterion D, brief-mandated — not an ADR decision but recorded
here for completeness).** The original §1 pseudocode set `fall_through = True` in BOTH the
budget-exhaustion branch AND the retry-LLM-call-exception branch. As implemented, `fall_through` is
set ONLY in the budget-exhaustion branch — the exception branch logs a warning and ships the last
successfully-parsed response without setting the flag, matching `fall_through`'s own field
description (§6: "the retry budget was exhausted") and guaranteeing REV-032 criterion D's invariant
`fall_through == True ⟹ retry_count == _MAX_REGENERATION_ATTEMPTS` holds unconditionally (an exception
on the FIRST retry would otherwise produce `fall_through=True` with `retry_count=1`, violating that
invariant). This is a deliberate, disclosed refinement of the original pseudocode, not a behavioral
regression from the pre-existing single-retry code's own `except: pass`-then-ship semantics.
