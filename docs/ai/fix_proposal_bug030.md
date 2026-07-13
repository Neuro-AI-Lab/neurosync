# Fix proposal — BUG-030 empathy-phrase repetition

**Scope:** BUG-030 only (dialogue empathy-phrase repetition). BUG-033 (probing-depth) and
BUG-028 (retry-hint reliability) are explicitly out of scope; this document proposes no fix for
either and notes interactions only where this proposal's changes touch their code paths.
**User directive (fixed design direction, verbatim):** "공감구 반복 문제 해결하자. system
prompt에 예시 기반으로 너무 overcontrol해서 발생한 문제 아닌가? 자연스러운 공감으로
변경해보자." — natural empathy GENERATION, not example-menu selection.
**Status:** read-only diagnosis + design proposal. No code, prompt, or test file has been
changed by this document. Plan reference: `discussion.md` `PLAN-2026-W28-S` step 1.

---

## 1. Diagnosis

### Channel (a) — hardcoded `alternatives` list re-recommends banned phrases — **CONFIRMED**

`apps/ai-server/src/agents/dialogue.py`, `_build_slot_context`, lines 438–464:

```python
438	        # ── 2. 공감 표현 반복 금지 ──
439	        used_empathy: list[str] = []
440	        if conversation_history:
441	            for m in conversation_history:
442	                if m.get("role") == "assistant":
443	                    first_sent = m["content"].split(".")[0].split("?")[0][:30]
444	                    if first_sent and first_sent not in used_empathy:
445	                        used_empathy.append(first_sent)
446	
447	        lines.append("## 공감 표현 규칙")
448	        lines.append("- 공감은 1문장으로 끝내고, 바로 새 질문을 하세요.")
449	        lines.append("- 환자 말을 장황하게 반복하지 마세요.")
450	        if used_empathy:
451	            lines.append("- 아래 표현은 이전 턴에서 이미 사용했으므로 **절대 다시 사용하지 마세요**:")
452	            for e in used_empathy[-5:]:
453	                lines.append(f'  X "{e}..."')
454	            lines.append("- 대신 다른 표현을 사용하세요:")
455	            alternatives = [
456	                "그런 상황이라면 정말 지치셨을 것 같아요.",
457	                "이야기해 주셔서 감사합니다.",
458	                "쉽지 않은 시간이셨겠어요.",
459	                "말씀하신 상황이 충분히 이해됩니다.",
460	                "그 마음 충분히 공감됩니다.",
461	            ]
462	            for alt in alternatives[:3]:
463	                lines.append(f'  O "{alt}"')
464	        lines.append("")
```

`alternatives` is a fixed 5-item array; only `alternatives[:3]` is ever shown, and it is **never
filtered against `used_empathy`**. Items 1–2 of `alternatives` are byte-identical to 2 of the 3
canonical example phrases in `v3.system.md` rule 2 (see channel (b)). Once the model has used
either of those two phrases once, `used_empathy` bans it in the X block, and the very next
(unconditional) O block re-lists the same string as "use this instead" — a directive
self-contradiction on every subsequent turn. **CONFIRMED** as the primary mechanism.

Live artifact evidence, `docs/ai/simulation_results/VP-001/VP-001_20260711_211256_conversation.json`
(`turns[]`, `agent_response` field, verified by direct read, not by memory):

| turn | `agent_response` (leading clause) |
|:--|:--|
| 1 | "그런 상황이라면 정말 지치셨을 것 같아요. 혹시 이전에 정신건강의학과 진료나..." |
| 2 | "이야기해 주셔서 감사합니다. 혹시 기존에 진단받은 신체질환이..." |
| 3 | "그런 상황이라면 정말 지치셨을 것 같아요. 혹시 힘들 때 연락하거나..." |
| 4–10 | same opening clause, "그런 상황이라면 정말 지치셨을 것 같아요.", 7 more times (9/10 turns total counting turn 1's own occurrence of this clause above — only turn 2 differs; turns 3–10 back‑to‑back) |

**Correction (critic condition 4, `discussion.md` ADR-028):** turn 1's leading clause in the row above is itself an occurrence of "그런 상황이라면 정말 지치셨을 것 같아요." — so the phrase-family count across the 10 non-greeting scored turns is **9/10** (turns 1, 3, 4, 5, 6, 7, 8, 9, 10), not 8/10; only turn 2 ("이야기해 주셔서 감사합니다.") differs. The original count undercounted by omitting turn 1's own occurrence from the tally.

This is exactly `alternatives[0]` — the model settles on the FIRST item of the unconditional
O list every turn after it was banned by the X list, i.e. it is picking off the recommendation
menu, not generating.

### Channel (b) — v3 prompt example-based overcontrol (user's hypothesis) — **CONFIRMED**

`docs/ai/prompts/dialogue/v3.system.md`, rule 2, lines 35–39:

```
35	2. **공감은 1문장으로 끝낸다.** 환자의 말을 장황하게 반복하지 않는다. 매 턴 **다른 표현**을
36	   사용한다.
37	   - 턴마다 다르게: "많이 힘드셨겠어요.", "그런 상황이라면 정말 지치셨을 것 같아요.",
38	     "이야기해 주셔서 감사합니다."
39	   - **같은 공감 표현을 2턴 연속 사용하지 마세요.**
```

The prompt licenses exactly 3 canonical example phrases and separately states an explicit
anti-repetition rule. Two of the three ("그런 상황이라면 정말 지치셨을 것 같아요.",
"이야기해 주셔서 감사합니다.") are duplicated verbatim into the hardcoded `alternatives` array
above — so the SAME small closed set is offered by both the static prompt (as "vary between
these") and the runtime injection (as "use this instead of what's banned"), with no mechanism to
ever fall back to something outside the set. The user's hypothesis — that the prompt's
example-based instruction over-controls the model into a small menu rather than genuine
generation — is **CONFIRMED**: the model has near-zero exposure, anywhere in its instructions,
to permission or encouragement to invent its own phrasing; every empathy-related instruction it
receives (static examples + runtime X/O block) is menu-shaped. Channels (a) and (b) are not
independent — (a) is the runtime amplifier of the same closed-menu design (b) establishes
statically; error.md's own BUG-030 entry names this ("Two of the hardcoded alternatives are 2 of
the prompt's own 3 canonical examples").

### Channel (c) — other contributing/structural findings

**(c-i) O-list static ordering is an independent aggravator — CONFIRMED, latent.** Even with
(a) fixed (filtering `alternatives` against `used_empathy`), `alternatives[:3]` is a fixed slice,
never rotated/shuffled. A menu-selecting model would still gravitate to the first surviving
option every turn, reproducing a slower version of the same failure once 1–2 items get exhausted
in a long session. This is evidence FOR the user's "stop offering a menu at all" direction over a
narrower "just filter the menu" patch.

**(c-ii) X/O juxtaposition format — CONFIRMED contributing, not the root cause.** Presenting the
banned phrase immediately above a recommended-phrase list (3 lines apart) is a salience/recency
setup that primes reuse of nearby text even before considering that the lists overlap. Removing
the O list (channel-(a) fix) removes this structural risk entirely rather than requiring careful
re-ordering.

**(c-iii) Repetition guard `dialogue.py:213–220` — CONFIRMED structurally blind to this failure
mode (does not itself cause it).**

```python
211	        # 7. Repetition detection
212	        prev_responses = self._get_previous_responses(inp.conversation_history)
213	        is_repeated = (
214	            llm_resp.assistant_response in prev_responses
215	            or any(
216	                llm_resp.assistant_response == prev
217	                for prev in prev_responses
218	                if len(prev) >= 80
219	            )
220	        )
```

Both branches require FULL-RESPONSE equality. Every turn in the VP-001 artifact has a distinct
trailing question, so `assistant_response` never equals a prior full response — `is_repeated` is
`False` on all 8 reused-opener turns; the retry-with-stronger-hint path (lines 222–250) never
fires for this failure mode. **CONFIRMED as a gap, not a driver.**

**(c-iv) `f1.py:1663` pipeline-level repetition guard — CONFIRMED same blind spot, second layer.**
`F1Pipeline`'s own termination guard (`if agent_response == prev_agent_response and turn > 1:` →
stop after 2 consecutive exact repeats) is likewise full-string equality and never trips on
sub-phrase reuse — consistent with the artifact running the full 10/10 turns without early
termination despite 8 reused openers.

**(c-v) `used_empathy` extraction / truncation — CONFIRMED not currently triggered, latent risk
for the fix design.** `first_sent = m["content"].split(".")[0].split("?")[0][:30]` truncates to
30 chars. All 5 current `alternatives` strings are ≤22 chars (verified: 22, 14, 13, 18, 14 chars
respectively), so no truncation mismatch occurs today, but any negative-constraint filter added
in the fix must match on the SAME truncated/split representation the extraction already produces
(or re-derive it consistently) — an exact-string filter using the full untruncated alternative
text against a 30-char-truncated `used_empathy` entry would silently under-match for phrases
`>30` chars.

**(c-vi) `routes/chat.py:32` stale prompt-version label — CONFIRMED pre-existing drift,
unrelated to BUG-030's mechanism.**

```python
26	_DIALOGUE_AGENT_NAME = "dialogue"
...
32	_PROMPT_VERSION = "v2"
```

Used only on the two LLM-bypass response paths (crisis, line 97; handoff-ready, line 113) where
`DialogueAgent.run()` — and hence `_build_slot_context` — is never invoked. It is already
inconsistent with the live pin (`dialogue.py:62` = `"v3"`) today; this proposal does not touch it
and it is unaffected either way (no execution reaches the empathy block on those two paths), but
it is a place "the dialogue prompt version" is displayed and is worth flagging per AVC-17
discipline (see §2 "Prompt version pin" and §4).

**(c-vii) Zero existing test coverage of the empathy directive block — CONFIRMED gap.** `grep -rl
"공감\|alternatives\|used_empathy" apps/ai-server/tests` returns no hits. `test_dialogue_v3_opening.py`
covers `_build_opening_context` and the continuity hint only; `test_prompt_v3.py::TestDialogueV3File`
covers static file content (absolute rules, opening/continuity sections, output schema key) but
never asserts anything about rule 2's example phrases or the runtime `alternatives` array. This
is why BUG-030 shipped undetected through the W2 SM-regression gate (`4be9818`, `error.md` BUG-025
resolution) and reached W7b before being caught by the blind battery's own dialogue output.

**(c-viii) `TestDialogueV3File.test_line_budget` asserts `DIALOGUE_V2`, not `DIALOGUE_V3` —
CONFIRMED test bug, unrelated to BUG-030 mechanism, noted for the v4 test design.**
`tests/test_prompt_v3.py:336-337`:
```python
336	    def test_line_budget(self) -> None:
337	        assert len(DIALOGUE_V2.splitlines()) <= 50
```
inside `class TestDialogueV3File`. v3 is actually 79 lines / 2513 chars on disk (measured) with
no enforced ceiling anywhere in the suite. Not a cause of BUG-030; flagged because §3 below
recommends the v4 test class fix this rather than copy the same error forward.

---

## 2. Proposed fix (atomic, minimal)

### Code — `apps/ai-server/src/agents/dialogue.py`, `_build_slot_context` lines 438–464

Delete the hardcoded `alternatives` array and its O-block entirely. Keep the X (negative
constraint) block, and replace the "대신 다른 표현을 사용하세요" pointer-to-menu line with a
principle-level instruction (natural generation, not selection). Conceptual diff (not applied):

```python
        # ── 2. 공감 표현 반복 금지 ──
        used_empathy: list[str] = []
        if conversation_history:
            for m in conversation_history:
                if m.get("role") == "assistant":
                    first_sent = m["content"].split(".")[0].split("?")[0][:30]
                    if first_sent and first_sent not in used_empathy:
                        used_empathy.append(first_sent)

        lines.append("## 공감 표현 규칙")
        lines.append("- 공감은 1문장으로 끝내고, 바로 새 질문을 하세요. 공감 문장을 생략하지 마세요.")
        lines.append("- 환자 말을 장황하게 반복하지 마세요.")
        lines.append("- 정해진 문구를 고르지 말고, 환자가 방금 한 말의 내용과 감정에 맞춰 그때그때 새로 표현하세요.")
        if used_empathy:
            lines.append("- 아래 표현은 이전 턴에서 이미 사용했으므로 **절대 다시 사용하지 마세요**:")
            for e in used_empathy[-5:]:
                lines.append(f'  X "{e}..."')
        lines.append("")
```

Net effect: `alternatives` (positive re-recommendation) is deleted, not filtered — matching the
brief's "compact negative constraint only, nothing re-recommended." `used_empathy` computation is
untouched (still the existing 30-char/first-sentence heuristic — see (c-v) for the one caveat: no
new filter logic is added that depends on matching truncated vs. untruncated strings, since there
is no longer an `alternatives` list to filter against).

### Prompt — new `docs/ai/prompts/dialogue/v4.system.md`, v3 left untouched

Per repo versioning policy (v1/v2 kept on disk through v3; `TestDialogueV3File`/`TestSafetyClassifierV2File`
etc. all assert prior versions still exist) and AVC-17 (a certified prompt file must never change
on disk without a version bump + re-validation), this is a NEW FILE, not an edit to v3. Rule 2
conceptual replacement:

```
Current v3 rule 2:
2. **공감은 1문장으로 끝낸다.** 환자의 말을 장황하게 반복하지 않는다. 매 턴 **다른 표현**을
   사용한다.
   - 턴마다 다르게: "많이 힘드셨겠어요.", "그런 상황이라면 정말 지치셨을 것 같아요.",
     "이야기해 주셔서 감사합니다."
   - **같은 공감 표현을 2턴 연속 사용하지 마세요.**

Proposed v4 rule 2 (principle-level, no canned examples):
2. **공감은 1문장으로 끝낸다(생략 금지).** 환자의 말을 장황하게 반복하지 않는다.
   - 정해진 문구를 암기해 반복하지 말고, 환자가 방금 한 말의 내용과 감정에 맞춰 그때그때
     새로 표현한다.
   - 환자의 존댓말 어조를 따라가고, 상황에 맞는 톤으로 공감한다(예: 힘든 이야기에는 더
     신중하게, 호전 소식에는 인정하는 톤으로 — 안심시키려 하지 않는다).
   - 같은 공감 표현을 2턴 연속 사용하지 않는다. 시스템이 알려주는 "이전에 사용한 표현"은
     반드시 피한다.
```

This removes all 3 literal example phrases (the specific echo-risk targets) while keeping every
existing structural constraint verbatim: one-sentence cap, no rambling repetition of the
patient's words, no 2-consecutive-turn repeat. All other v3 sections (session-start greeting,
continuity phrasing, absolute rules 1–6, Safety-instruction precedence, output-format contract)
are proposed UNCHANGED — carried forward into v4 exactly as v2→v3 carried the clinical-dialogue
core forward unmodified (design doc precedent, `v3.system.md` header note). This keeps the change
atomic to rule 2 only.

**v3 design-rule compliance for v4 (per brief, cross-checked against `test_prompt_v3.py`):**
- Placeholder-only / zero example-echo risk: v4 rule 2 contains **zero literal empathy phrases**
  — strictly stronger than v3 on `TestNoRealisticExampleValues`'s intent (v3 already passes that
  suite's `_KNOWN_BAD_STRINGS`/ICD-pattern checks since generic empathy phrasing isn't a
  clinical-value echo risk, but v4 goes further by removing the literal strings BUG-030 actually
  reproduced).
- Token/char budget: v4 rule 2 is shorter than v3's (no 3-phrase list); overall file length is
  expected to shrink slightly, not grow — well inside v3's own measured 2513 chars / 79 lines,
  with no known budget ceiling currently enforced on v3 in tests (see (c-viii); §3 proposes v4
  fix this).

**AVC-17 pin — every place the active dialogue prompt version/SHA is selected or verified (must
all be updated together if this proposal is implemented):**

| Location | Current | Update needed |
|:--|:--|:--|
| `apps/ai-server/src/agents/dialogue.py:62` `PROMPT_VERSION = "v3"` | selects the file actually loaded at runtime (`load_system_prompt("dialogue", PROMPT_VERSION)`, line 121) and stamps `DialogueOutput.prompt_version` (line 257) | `"v3"` → `"v4"` |
| `apps/ai-server/tests/test_prompt_v3.py:531-536` `test_dialogue_pin` | `assert DIALOGUE_VERSION == "v3"` | → `"v4"` |
| `apps/ai-server/tests/test_prompt_v3.py:567-576` `test_dialogue_loads_and_reports_v3` | asserts `load_system_prompt` called with `("dialogue", "v3")`, `out.prompt_version == "v3"` | → `"v4"` (rename test) |
| `apps/ai-server/tests/test_prompt_v3.py:296-337` `TestDialogueV3File` | asserts on `DIALOGUE_V3` content only | ADD sibling `TestDialogueV4File` reading `docs/ai/prompts/dialogue/v4.system.md` (v3 class stays, unmodified, per rollback policy) |
| SHA256 pin value, currently `d8870e5dda81dffde9099a2e606e9656b7aeb8f897dbdd41f25705efbdc84325` (recorded in `discussion.md`, `docs/ai/workflow_results_f1f2.md` multiple rows, `tests/repro/test_bug_025.py` docstring) | pins `v3.system.md`'s current byte content | qa recomputes SHA256 of the NEW `v4.system.md`; every doc row citing the dialogue pin needs the new hash recorded (doc-owner's job — writer/filemanager/qa, not developer; listed here so nothing is missed) |
| `apps/ai-server/src/routes/chat.py:32` `_PROMPT_VERSION = "v2"` | already stale (pre-existing, see (c-vi)); only labels the 2 LLM-bypass paths, never loads a prompt file | out of this proposal's scope — flagged, not fixed, since it's pre-existing drift unrelated to BUG-030's mechanism and touches no code this fix changes |
| `discussion.md` line 51 "dialogue v3 is the only licensed change, atomic" + `workflow_results_f1f2.md` pin rows | narrative/tracking text | doc-owner update when the fix lands (not developer's write scope) |

### Guard — do NOT strengthen `dialogue.py:213–220` in this atomic change; argued explicitly

**Recommendation: leave the repetition guard as full-response equality for this fix.** Reasons:

1. **Root-cause vs. backstop.** The observed failure (9/10 turns, one exact phrase) was CAUSED by
   the code literally re-recommending a banned phrase (channel (a)). Once (a)/(b) are fixed, that
   specific mechanism is eliminated at the source. A detection-side guard change is a backstop for
   a DIFFERENT residual failure mode — organic model non-adherence to "vary your phrasing" absent
   any code-level contradiction — which `error.md` BUG-030 itself already separates out as "a
   second-order effect... independent of the code bug" (VP-003's repeated "정말 많이
   힘드셨겠어요" over turns 4–10). Fixing a cause should not be bundled with hardening a detector
   for an unrelated, already-disclosed symptom.
2. **BUG-028 code-path overlap.** Widening `is_repeated`'s trigger condition to sub-phrase
   equality would touch `dialogue.py:211-250` — the EXACT region `error.md` BUG-028 already flags
   ("retry-hint fires but fails to diversify"). Feeding more cases into a retry mechanism BUG-028
   already found unreliable at n=1 would conflate two open bugs in one commit and expand this
   fix's regression surface right where a known defect lives — the opposite of atomic.
3. **Regression-cost discipline.** Any `dialogue.py` change forces the SM-01..08b regression
   re-run (already scheduled once, `PLAN-2026-W28-S` step 6, for the rule-2 change alone, mirroring
   the BUG-025 precedent where a smaller diff still needed a targeted bisection). Widening the
   guard's semantics adds a second independent behavior change to attribute failures to if the
   regression flags something, without independent evidence it's needed.

**Follow-up, not fixed here:** if EXP-017's naturalness/SM re-probe (plan step 6) still shows
organic repeated phrasing at scale after this fix lands, that is evidence for BUG-028's territory
(retry-hint effectiveness), not a residual of BUG-030 — route it there, do not reopen this fix.

### Guard-rail — empathy presence is preserved, not just repetition removed

Cold interrogation (empathy vanishing) is guarded against structurally, not left to model
discretion:
- Rule 2's first clause, "공감은 1문장으로 끝낸다" (empathy = exactly one sentence, every turn),
  is UNCHANGED and made more explicit in the v4 draft ("생략 금지" — do not omit) rather than
  weakened; the fix removes only the literal example phrases and the broken recommendation menu,
  never the requirement that a turn opens with an empathetic acknowledgment before the question.
- The negative constraint (X list) still fires every turn once there is conversation history, so
  the model is never told "stop empathizing" — only "don't reuse this exact phrase again."
- Mechanical verification of presence (not just non-repetition) is a clinical-adequacy judgment,
  not a string check — this is exactly what `PLAN-2026-W28-S` step 2 (critic ∥ clinical-validator
  design review, pre-registering an "empathy-presence" rubric axis alongside naturalness/no-
  repetition) and step 7 (CVR verdict on the re-run artifacts) already schedule. This proposal
  does not invent a new empathy-presence test that could pass on hollow output; it defers that
  judgment to the rubric review already in the plan, consistent with "verification is external"
  discipline.

---

## 3. Test plan sketch

**New unit tests for `_build_slot_context`'s empathy block (fills the (c-vii) coverage gap):**

1. `test_negative_constraint_lists_used_phrases` — conversation history with 2+ distinct prior
   assistant turns → ctx contains one `X "..."` line per prior first-sentence (last 5, existing
   cap preserved).
2. `test_no_positive_recommendation_menu` — ctx must not contain any `O "` line, and must not
   contain any of the 5 literal strings that used to be in `alternatives` (locks in "menu
   deleted, not filtered").
3. `test_empty_history_no_used_phrase_block` — no assistant turns yet → no X block rendered
   (regression check, preserves existing `if used_empathy:` guard behavior for turn 0/1).
4. `test_principle_level_instruction_present` — ctx contains the new "그때그때 새로 표현" (or
   equivalent) principle-level guidance string, locking the prompt-injected nudge in place.
5. **Mutation-check test (explicit ask):** `test_previously_used_phrase_never_recommended_again`
   — seed `conversation_history` with one assistant turn whose content starts with exactly
   `"그런 상황이라면 정말 지치셨을 것 같아요. ..."` (the literal string BUG-030 reproduced).
   Assert the resulting ctx contains that string **exactly once**, as an `X` line, and does not
   also appear elsewhere in the ctx as a recommendation. This test is constructed to FAIL against
   the pre-fix code (where `alternatives[0]` duplicates it into an O line 3 lines below the X
   line) and PASS against the fix — i.e., if the negative-constraint-only design is reverted back
   to a filtered-or-unfiltered `alternatives` menu, this test catches it.

**New prompt-file tests (mirrors `TestDialogueV3File` pattern in `test_prompt_v3.py`):**

6. `TestDialogueV4File.test_v3_kept_per_versioning_policy` — v3 file still exists on disk.
7. `test_absolute_rules_present`, `test_output_schema_key_documented`,
   `test_opening_turn_section_present`, `test_continuity_phrasing_section_present`,
   `test_no_raw_risk_narration_licensed` — same assertions as `TestDialogueV3File`, re-run against
   `DIALOGUE_V4` (locks in that only rule 2 changed, nothing else regressed).
8. `test_no_canned_empathy_examples` — NEW: assert none of the 3 v3 example phrases
   ("많이 힘드셨겠어요.", "그런 상황이라면 정말 지치셨을 것 같아요.", "이야기해 주셔서
   감사합니다.") appear anywhere in `DIALOGUE_V4` — encodes the fix's actual intent at the
   prompt-file level, not just the runtime-injection level.
9. `test_char_budget` / `test_line_budget` against `DIALOGUE_V4` directly — fixes (c-viii)'s
   copy-paste bug rather than propagating it into the new class.

**`TestAgentPinsAndRuntimeVersion` updates:** `test_dialogue_pin` → `"v4"`;
`test_dialogue_loads_and_reports_v3` → rename + update expected version to `"v4"` (both listed in
§2's pin table).

**What existing tests already cover this area (verified by direct read, not assumed):**
`test_dialogue_v3_opening.py` covers `_build_opening_context` and the continuity hint in
`_build_slot_context` only — zero overlap with the empathy block. `test_prompt_v3.py::TestDialogueV3File`
covers static v3 file content (absolute rules, opening/continuity sections, schema key,
line/char budget) but never asserts on rule 2's example phrases. `tests/repro/test_bug_025.py`
covers the round-robin/target-selection retry-hint fix (BUG-025) — a different code path
(`missing_questionable_slots`/`compute_target_slot`), unaffected by and not covering this change.
**Net: before this fix, no test in the suite would fail if the `alternatives` menu were
reintroduced or widened — item 5 above is the first test that would catch a regression of this
specific bug.**

**Acceptance gate (already scheduled, not proposed here):** `PLAN-2026-W28-S` step 4 (qa gate:
ruff + full pytest + mutation-check + AVC-03 + pins) and step 6 (EXP-017 SM-01..08b regression +
naturalness probe + SC-5-style badgering re-probe) are the live-behavior acceptance gates for this
fix; this document only sketches the unit-test layer developer would add at step 3.

---

## 4. Blast radius

**Every caller/consumer of the changed code paths:**

- `_build_slot_context` (private method) — single production call site:
  `DialogueAgent.run`, `dialogue.py:133`. No other agent or route imports it; the only other
  callers are white-box tests (`test_dialogue_v3_opening.py:77,89,98,105`, direct
  `agent._build_slot_context(...)` calls) which exercise the opening/continuity branches, not the
  empathy block, and are unaffected by this change (early-return branches for `opening_turn`/
  `probe_instruction` are untouched; only the plain round-robin branch's rule-2 block changes).
- `PROMPT_VERSION` module constant, `dialogue.py:62` — read by `DialogueAgent.run` (lines 121,
  257) and imported directly by `test_prompt_v3.py` for the pin assertion (§2 table). No other
  production module imports `dialogue.PROMPT_VERSION`.
- `docs/ai/prompts/dialogue/v3.system.md` — read only via `PromptLoader.load_system_prompt("dialogue",
  PROMPT_VERSION)`; grep confirms the only non-test references are `dialogue.py` itself and the
  historical docstring in `tests/repro/test_bug_025.py`. Since v3 is proposed to stay on disk
  byte-for-byte unmodified (new v4 file instead), `TestDialogueV3File`'s existing assertions
  against the frozen v3 file remain green untouched, per the v1/v2/v3 rollback-kept precedent.
- `routes/chat.py:32` — pre-existing stale label, confirmed unreachable from the changed code
  (only read on the 2 LLM-bypass paths where `_build_slot_context` never executes); flagged in §2,
  not modified.
- `f1.py:479` (constructs `DialogueAgent`), `f1.py:1512` (`DialogueAgent.compute_target_slot`,
  a different classmethod, untouched) — structural callers, no assertions on prompt/empathy
  content; `f1.py:1663`'s own full-string repetition guard is a second consumer of
  `agent_response` values, expected to trip LESS often post-fix (a phrase repeated verbatim less
  is exact-string-equal to its predecessor less often), never more — no adverse interaction.
- `run_injected_session.py` / `continuous_test.py` (F1→F2 harness) — transitively call
  `DialogueAgent.run` via `F1Pipeline.run_session`; no direct coupling to the empathy block,
  benefit passively from reduced repetition in shipped transcripts.
- `grounding.py:255-260` (BUG-029's containment guard) — confirmed scoped to `ClinicalSlotAgent`
  only; does not process `DialogueAgent`'s output at all (per BUG-029's own root-cause text) — no
  interaction with this change.
- **AVC-05 two-tier echo-watch (`ADR-027` Decision B)** — Tier-2's stated basis is "dialogue v3's
  3 empathy phrases, the only known instance" of licensed-vocabulary echo. If v4 removes those 3
  literal phrases, Tier-2's named example no longer exists in the newly-pinned file. The
  echo-watch rule itself lives in `discussion.md`/`ADR-027`, not in code — nothing in this code
  proposal needs to change for it, but the wording will need revisiting once v4 ships. Flagged for
  whoever owns `ADR-027` (orchestrator/critic), not a developer action item.

**Safety prompt confirmed untouched:** `apps/ai-server/src/agents/safety_classifier.py` — separate
module, separate `PROMPT_VERSION = "v2"` (line 133), separate prompt directory
(`docs/ai/prompts/safety_classifier/v2.system.md`, pin
`3e9ca6b44ba3373f70c068758a2e1ae860f3c58483394a85fed9e13a90b3390c`). `grep -rn
"_build_slot_context\|alternatives\|dialogue/v[34]" apps/ai-server/src/agents/safety_classifier.py`
returns zero hits. `DialogueAgent._build_slot_context`'s `safety_context` string (dialogue.py:138-146)
is appended informational text INTO the dialogue prompt (read-only consumption of
`inp.safety_result`); nothing in this proposal writes to or reads from the safety prompt file or
its loading path. **CONFIRMED: safety_classifier v2 pin is untouched by this proposal.**
