# Orchestration system — evidence-based build review

Read-only code scan, branch `feat/f1f5-total-validation`. All citations are `file:line`
against `apps/ai-server/src/` unless stated otherwise. No prior review docs or the
underscore-prefixed archive folder were read (blocked by the archive-access hook, as
instructed).

**Scope disclosure (finding, not assumption):** there are two separate orchestration
surfaces in this codebase, not one:

1. **Live per-turn state machine** — `agents/orchestrator.py` + `schemas/orchestrator.py`,
   reached only via `POST /ai/chat/respond` (`routes/chat.py`). Covers safety-gate →
   dialogue → slot-extraction → handoff for the F1 conversation only.
2. **Offline F1→F5 artifact-chain scripts** — `f1.py`…`f5.py`, invoked as CLI/harness
   modules (`continuous_test.py`), never as FastAPI routes. `routes/domain.py:1-7` and
   `routes/survey.py` expose *pieces* of F2/F3 as standalone endpoints but state in their
   own docstrings that they are **not wired into `orchestrator.py` or the 11-state
   machine** (`routes/domain.py:2-7`: "production integration is deferred to gate G-D").

Every claim below is tagged `[live]` or `[offline]` accordingly.

---

## 1. State machine

**What exists.** `SessionStage` enumerates 11 states (`schemas/orchestrator.py:14-27`):
`input_received, safety_gate, context_retrieval, dialogue_loop, slot_extraction,
handoff_generation, evidence_verification, handoff_delivery, crisis_flow, completed,
error`. `SessionState` (`schemas/orchestrator.py:57-78`) is a plain Pydantic model
carrying `current_stage`, history, slots, etc.

**How it works.** There is **no transition table** — no `dict[SessionStage, set[SessionStage]]`
or equivalent. Transitions are hard-coded procedural writes to `state.current_stage`
inside `_execute_pipeline`/`_run_safety_gate`/`_run_post_dialogue_pipeline`
(`agents/orchestrator.py:172-457`), e.g. `state.current_stage = SessionStage.safety_gate`
at line 219, `= SessionStage.crisis_flow` at line 239/254, `= SessionStage.completed` at
line 446. The "legality" of a transition is whatever the linear code path happens to do
next; there is no independent validator that would reject e.g. `dialogue_loop →
handoff_generation` skipping `slot_extraction`.

**Gaps (evidence).**
- **No illegal-transition defense.** `_execute_pipeline` (`agents/orchestrator.py:166-211`)
  unconditionally sets `state.current_stage = SessionStage.input_received` at the top of
  every call (line 172), regardless of what stage the incoming `state` was already in.
  There is no guard such as `if state.current_stage in {completed, error}: reject`. A
  client that re-POSTs a `session_state` already at `completed` or `crisis_flow` will
  silently re-enter the pipeline from scratch.
- **Re-entrancy / idempotency gap.** Because of the above, calling `process_turn` twice on
  a `completed` session state (e.g. client retry after a dropped response) re-runs
  `_run_post_dialogue_pipeline` (`agents/orchestrator.py:346-457`) in full — a second
  slot-extraction LLM call, a second handoff-generation + evidence-verification loop
  (up to `1 + _MAX_HANDOFF_REGEN` = 3 more LLM calls, line 384), and a second
  `handoff_report`/`stage_history` block appended, with no dedupe or "already completed"
  short-circuit. This is a genuine double-billing / duplicate-artifact risk, not just a
  theoretical one, since `routes/chat.py` round-trips the full `session_state` through the
  client (see §5) and any client bug or retry logic can resubmit it.
- **State persistence across turns/sessions:** there is **no server-side session store**.
  `SessionState` is serialized to JSON and handed back to the caller
  (`orch_result.session_state.model_dump()`, `routes/chat.py:105/121/147`), and the next
  turn's request must resupply it (`routes/chat.py:66-78`, `SessionState.model_validate(body.session_state)`).
  `dependencies.py:155-166` only wires a DB session-maker for RAG retrieval, not for chat
  session state — grep for `AsyncSession|sessionmaker|redis` in `routes/*.py` returns
  nothing beyond the RAG one. Crash recovery / cross-device continuity depends entirely on
  the client persisting and correctly resending the last `session_state` blob; nothing in
  the server validates that the resupplied blob is the one *it* actually issued (no
  signature, no server-side turn counter cross-check against session_id).
- Malformed `session_state` from the client is caught and silently discarded
  (`routes/chat.py:67-71`, bare `except Exception` → "starting fresh") — safe-by-default,
  but means a corrupted/tampered state loses all prior slot/safety history with only a
  WARNING log, no user-visible signal.

---

## 2. Pipeline contracts (F1 per-turn Safety→Slot→Dialogue) `[live]`

**I/O typing.** All agent I/O is Pydantic (`agents/base.py:11-24`: `AgentInput`/
`AgentOutput` base with `session_id`, `request_id`, `latency_ms`, `reason_summary`,
`prompts_degraded`). Concrete schemas exist per agent (`schemas/safety.py`,
`schemas/clinical_slot.py`, `schemas/handoff.py`, `schemas/dialogue.py`).
`OrchestratorAgent.run()` explicitly rejects non-`OrchestratorInput` payloads with
`TypeError` (`agents/orchestrator.py:131-132`) — the orchestrator sits outside the
`AgentInput`/`BaseAgent` contract by design (documented at line 128-129), which is a
deliberate exception, not an oversight.

**Failure propagation — fail-closed, verified.**
- Safety LLM failure → orchestrator explicitly assumes CTRS 2 / `RiskLevel.high` and
  forces `crisis_flow` (`agents/orchestrator.py:228-242`, comment "assume CTRS 2
  (safe-side default)"). Inside `SafetyClassifierAgent` itself, both the pre-adapter setup
  path (`agents/safety_classifier.py:270-313`, `ISS-026`) and the LLM-call path
  (`:344-380`, `ISS-019`) fail closed to `_FAIL_CLOSED_LEVEL`, and unparsable LLM JSON is
  treated as failure, not as safe (`:326-340`, "unparsable safety response must not be
  treated as safe"). This is a well-evidenced, intentionally engineered fail-safe.
- Slot-extraction failure → does **not** fail closed to crisis; it degrades gracefully,
  logging a warning and proceeding with whatever slots already exist
  (`agents/orchestrator.py:369-374`, `"proceeding with existing slots"`). Correct choice
  for a non-safety-critical stage, but note it means a session can reach
  `handoff_generation` with stale/incomplete slots and no visible flag beyond
  `stage_history` detail text — nothing surfaces this to the clinician-facing report.
- Handoff-generation/evidence-verification failure → caught at the outer
  `try/except` (`agents/orchestrator.py:435-441`), appended to `state.error_log`, then
  falls through to `handoff_delivery`/`completed` anyway with `handoff_report=None`
  (`:443-457`) — the turn result claims `current_stage=completed` and `handoff_ready=True`
  even when no report was produced. **This is a silent-failure risk**: the caller
  (`routes/chat.py:109-123`) branches only on `orch_result.handoff_ready`, which is always
  `True` at this point regardless of whether `handoff_report` is populated — a caller
  that doesn't null-check `handoff_report` will crash or silently show an empty report.
- Uncaught pipeline exception → outer `process_turn` try/except
  (`agents/orchestrator.py:148-161`) sets `SessionStage.error` and returns a typed
  `OrchestratorTurnResult` with `error=str(exc)` — no unhandled 500 leaks through
  `process_turn` itself, though `routes/chat.py:80-86` also wraps the call and converts to
  HTTP 500 (double-guarded, consistent).

**Retry/timeout per agent call.**
- Vendor-adapter level: `AkLlmAdapter.chat()` retries up to `_MAX_RETRIES=3` with
  exponential backoff on `RateLimitError`/5xx/`APIConnectionError`
  (`adapters/ak_llm.py:105-148`); JSON parsing gets one "repair" retry
  (`adapters/ak_llm.py:178-228`). httpx-based adapters (HIRA, Kakao, STT, document-parse)
  all set explicit `timeout_s` on their `httpx.AsyncClient` calls
  (e.g. `adapters/hira_base.py:114`, `adapters/skt_ak_stt.py:131/167/200`).
- **Gap:** the two OpenAI-SDK-based LLM adapters that back the safety/slot/dialogue/domain
  pipeline (`adapters/ak_llm.py:39-42`, `adapters/solar_pro3.py:27`,
  `adapters/k_exaone.py:35`) construct `openai.AsyncOpenAI(...)` with **no `timeout=`
  argument** — falls back to the SDK default (10 minutes). A hung safety-classifier call
  would block that turn for up to ~10 minutes before the SDK's own timeout fires and the
  orchestrator's fail-closed path engages, not a small number by clinical-response-latency
  standards. `fallback_policy.py:46-48`/`:143-146` even defines a `get_backoff()`/
  `backoff_seconds()` helper that is **never called anywhere** (grepped — zero call sites
  outside its own definition and `ModelRouter`'s unrelated circuit-breaker bookkeeping);
  dead code suggesting an intended-but-unwired backoff-before-fallback step.
- Model-level fallback: `ModelRouter.get_fallback()` (`routing/model_router.py:140-198`)
  and `FallbackPolicy` circuit breaker (`routing/fallback_policy.py:54-146`, 3 consecutive
  failures → 30s open) are real and exercised by `SafetyClassifierAgent`
  (`agents/safety_classifier.py:344-380`).

**Ordering guarantees.** Strictly sequential and synchronous within one `process_turn`
call — no fan-out/parallel agent calls to reason about ordering for. Safety gate always
runs before dialogue/slot/handoff (`agents/orchestrator.py:176-186`), enforced by plain
control flow, not by a scheduler.

---

## 3. Cross-feature handoffs `[offline for F2→F5, live for F1 only]`

- **F1→F2:** F2 reads F1's `conversation.json` on disk via a glob/path CLI arg
  (`f2.py:18`, `f2.py:90-91`, `--conversation` flag at `f2.py:1130`) — ad-hoc filesystem
  contract, not a typed handoff object. `f2.py:684-687`/`:1098` note the F1 `data` dict
  fields are read "never re-derived", i.e. trust-the-artifact, not validate-the-artifact —
  no evidence of Pydantic validation of the *upstream* `conversation.json` shape before
  F2 consumes it (F2's own *output* is typed, per `schemas/ai_predicted_disease.py`).
- **F2→F3:** typed at the boundary — `f3.py:108` declares
  `recommended_questionnaire: ScaleName | None` sourced from
  `ai_disease.get("recommended_questionnaire")` (`f3.py:134`), i.e. still a `dict.get()`
  off a loaded JSON blob rather than `AIPredictedDiseaseOutput.model_validate(...)`, but
  the consuming side is a typed dataclass/model. `f3.py:141` (`load_recommendation`)
  is the seam that would need to raise on a missing/malformed upstream artifact — not
  inspected further in this pass, flagged as unverified.
- **F3→ledger, F4:** deliberately typed and decoupled — `f4.py:66-100` defines
  `SessionRecord`/`LongitudinalSeriesInput` as frozen dataclasses and states explicitly
  that `analyze_longitudinal_series` performs **zero filesystem/ledger access** itself
  (`f4.py:7-16`, "never reads the ledger file... Reading those artifacts and building
  `SessionRecord`s is the harness's own job"). This is a clean pure-function boundary — the
  contract type is real, but the *thing that builds the contract from the ledger* lives
  in the un-reviewed harness/test tree, so the actual JSON→`SessionRecord` mapping (the
  highest-risk step for silent field drops) is outside this module and outside this scan.
- **F4→ledger consumption, F5:** same pattern — `f5.py:14-15` states F5 "never reads the
  session ledger, never reads a `conversation.json`/... path itself"; inputs are
  pre-assembled by the harness. `f5.py:684/713` consume `apd.recommended_questionnaire`
  off what is presumably a typed object at that call site (not confirmed by this pass —
  the assembly code itself wasn't read).
- **Versioning of artifacts:** `PromptLoader` versions *prompts* (`{agent}/{version}.system.md`,
  `prompts/loader.py:76-77`) but no evidence of a schema/artifact version field on
  `conversation.json`/`domain_inference.json`/`survey.json`/`temporal.json` themselves
  (no `schema_version` field seen in `schemas/longitudinal.py` or
  `schemas/ai_predicted_disease.py` in the portions read). Forward/backward compatibility
  of the F1→F5 artifact chain across schema changes is not demonstrated in what was
  scanned — a plausible gap, not confirmed absent (would need `schemas/*.py` read in full).
- **Overall pattern:** contract types exist at nearly every module boundary
  (`SessionRecord`, `LongitudinalSeriesInput`, `LongitudinalAnalysisOutput`,
  `AIPredictedDiseaseOutput`), but the *glue* that reads raw JSON off disk and populates
  those types is explicitly pushed out of every F-module and into an unreviewed harness —
  by design (stated rationale: keeps each F-module a pure, testable function), but it also
  means the actual F1→F5 orchestration — the part that decides "read this file, call this
  function, write that file" — has no single owner module in `src/`. It's not a pipeline
  the production system runs at all; it's a chain of pure functions the *validation
  harness* wires together. `[live]` production only wires F1 (chat).

---

## 4. Observability

**Logging coverage.** Every route logs on entry with `request_id`/`session_id`
(`routes/chat.py:58-62`, `routes/domain.py:41-44`) and generates a `request_id` if absent
(`routes/chat.py:55-56`, `uuid.uuid4()`). `AgentOutput.latency_ms` is a first-class field
(`agents/base.py:24`) and populated by adapters (`adapters/ak_llm.py:161-166` reads
`resp.latency_ms`; `chat_timed` wrapper implied by call sites).

**Gap — request_id does not propagate past the route layer.** `AgentInput.request_id`
(`agents/base.py:15`) is declared but grep across `agents/*.py` for `request_id` returns
**zero hits** inside any agent's logic or logging calls — only the base schema field.
`schemas/safety.py`, `schemas/clinical_slot.py`, `schemas/handoff.py` (checked directly)
have **no `request_id` field at all**, so `OrchestratorAgent._run_safety_gate`
(`agents/orchestrator.py:222-226`) cannot even carry the route's `request_id` into
`SafetyInput`. Internal orchestrator error logs
(`agents/orchestrator.py:151`, `logger.error("Orchestrator pipeline error: %s", exc, ...)`)
also omit `session_id`/`request_id`. Net effect: a request can be traced at the HTTP-route
boundary but **not stitched through the safety→slot→handoff sub-agent calls** by
request_id — cross-agent correlation for one turn depends on grepping `session_id` (which
*is* threaded through every schema) plus timestamp proximity, not a shared trace id.

**Reproducibility metadata.** `AgentOutput.model_used`/`prompt_version` are populated per
call (e.g. `routes/chat.py:96-97/112-113` for the orchestrator-bypass paths), giving
after-the-fact reconstruction of which model/prompt served a turn. `stage_history`
(`StageRecord`, `schemas/orchestrator.py:38-45`) timestamps every stage transition with
`agent`/`result`/`detail` — a genuinely useful per-turn audit trail, and it's returned to
the caller each turn (not just logged), so it survives in the client-held session state.

**Silent-fallback inventory (grep-verified, `except ... pass` / generic-fallback class).**
- `dialogue.py:1215-1219` — nested `except Exception: pass` when a markdown-fenced JSON
  repair-parse fails; falls through to `DialogueLLMResponse(assistant_response=content,
  reason_summary="JSON parse failed — raw response used")` at line 1221 — visible via
  `reason_summary`, not truly silent, but not flagged by any boolean the caller checks.
- `patient_history.py:61,67` — bare `pass` statements (not read in this pass; flagged for
  follow-up, not evidence of severity either way).
- **The documented generic-prompt-fallback class (tracked as BUG-021) is explicitly
  mitigated, not merely present.** `prompts/loader.py:14-68` (`resolve_prompts_base_dir`)
  now *raises* `RuntimeError` rather than silently degrading when `PROMPTS_BASE_DIR`
  doesn't resolve — its own docstring names the exact prior failure mode this fixes. At
  the individual-agent level, the fallback *still exists* by design but is now
  **machine-visible**: `AgentOutput.prompts_degraded` (`agents/base.py:29-37`) is
  explicitly set `True` when an agent substitutes its hardcoded fallback prompt
  (`agents/safety_classifier.py:281-284`, `prompts_degraded = True` on
  `FileNotFoundError`). This is a solid before/after: the failure mode isn't eliminated (a
  missing prompt file still produces a degraded run) but it's no longer silent — a WARNING
  log line plus a typed output field.
- `avc12_instrumentation.py:1-40` is a dedicated read-only instrumentation module built
  specifically to detect "verified-to-exist-but-0%-activation" code paths (tracked as the
  BUG-020 class — `InputNormalizer` suspected no-op). Its existence is itself evidence
  that silent-no-op bugs have been a recurring, named failure class in this project,
  serious enough to warrant a standing instrumentation layer rather than one-off fixes.

---

## 5. Concurrency / resource

- **Shared mutable state:** `ModelRouter`/`PromptLoader`/`Settings` are process-wide
  singletons via `functools.lru_cache(maxsize=1)` (`dependencies.py:28-79`). The one
  piece of *mutating* shared state is `FallbackPolicy._records`
  (`routing/fallback_policy.py:76`, a plain `dict`), mutated by every concurrent request's
  `record_failure`/`record_success`/`is_circuit_open` calls
  (`model_router.py:200-206`). Under FastAPI's single-threaded asyncio event loop this
  isn't a data race in the traditional sense (no true parallel writes), but concurrent
  coroutines can interleave between the `now - record.last_failure_ts` read and the
  `record.consecutive_failures += 1` write (`fallback_policy.py:104-110`) — a low-severity
  correctness wobble in circuit-breaker accounting under load, not a crash risk.
  `OrchestratorAgent` itself is **not** a singleton (`routes/chat.py:35-39`,
  `_get_orchestrator` constructs fresh per request, no `lru_cache`) — correct, since it
  would otherwise leak `_safety_agent`/`_slot_agent` lazy-init state across unrelated
  sessions were those sub-agents themselves stateful (they are not, per inspection).
- **Async correctness in routes:** all route handlers and agent `run()` methods are
  `async def` and `await` their sub-calls (`routes/chat.py:81,138`; `agents/orchestrator.py`
  throughout). No blocking I/O calls (`requests`, sync file I/O in the hot path) were
  observed in the reviewed files — `httpx.AsyncClient`/`openai.AsyncOpenAI` used
  consistently.
- **DB session handling:** the only DB usage found is RAG retrieval's
  `async_sessionmaker` (`dependencies.py:155-166`), lazily constructed once and cached;
  not exercised by the chat/orchestrator path at all (confirmed no `AsyncSession` import
  in `routes/chat.py` or `agents/orchestrator.py`). No session-per-request
  scoping/cleanup pattern was found for it in the files read — not confirmed either way,
  flagged as unverified (would need a grep of the RAG route's own DB usage, out of this
  scan's dimension list).
- **Backpressure:** `AkLlmAdapter` rate-limits itself to 3 concurrent requests via
  `asyncio.Semaphore` (`adapters/ak_llm.py:21,44,107`). No evidence of a
  request-level concurrency cap or queue at the FastAPI/route layer itself (no
  `Semaphore`/`Limiter` middleware found in `main.py` in what was read) — backpressure is
  delegated entirely to each adapter's own per-vendor semaphore, so a burst of concurrent
  `/ai/chat/respond` calls has no global admission control.

---

## 6. Orchestration-standard comparison table

| Property | Verdict | Evidence |
|---|---|---|
| Explicit state model | **Partial** | 11 named `SessionStage` enum values exist (`schemas/orchestrator.py:14-27`) and every transition is logged to `stage_history`, but there is no declarative transition table and no guard rejecting an illegal `current_stage` on entry (`agents/orchestrator.py:172`, no pre-condition check) |
| Typed contracts | **Partial** | Per-agent Pydantic I/O is thorough (`agents/base.py`, `schemas/*.py`); but F1→F2/F2→F3 artifact reads are `dict.get()` off loaded JSON, not `model_validate()` at the read site (`f2.py:684-687`, `f3.py:134`), and cross-agent `request_id` isn't in the shared contract (`schemas/safety.py` etc. have no `request_id` field) |
| Fail-safe defaults | **Present** | Safety path fails closed to high-risk at every failure point, twice-engineered (issue IDs ISS-019, ISS-026) with direct evidence (`agents/safety_classifier.py:270-380`, `agents/orchestrator.py:228-242`) |
| Idempotent steps | **Absent** | No re-entrancy guard; resubmitting a `completed`/`crisis_flow` session state re-runs the full post-dialogue pipeline including new LLM calls (`agents/orchestrator.py:166-211`, no stage precondition) |
| Retries w/ backoff | **Partial** | Real exponential backoff at the vendor-adapter layer (`adapters/ak_llm.py:105-148`) and a circuit breaker at the router layer (`routing/fallback_policy.py`), but the two core LLM adapters have no explicit client-level timeout (`adapters/ak_llm.py:39-42`) and a defined `get_backoff()` helper is dead code (`fallback_policy.py:143-146`, zero call sites) |
| Timeouts | **Partial** | httpx-based adapters set explicit timeouts everywhere (`adapters/hira_base.py:114`); OpenAI-SDK LLM adapters rely on the 10-minute SDK default (`adapters/ak_llm.py:39-42`, `adapters/solar_pro3.py:27`, `adapters/k_exaone.py:35`) |
| Observability | **Partial** | Route-level request_id + per-stage `stage_history` audit trail is strong (`schemas/orchestrator.py:38-45`, `routes/chat.py:55-62`); request_id does not propagate into sub-agent calls or their logs (zero hits grepping `agents/*.py`), and one confirmed silent-completion bug: `handoff_ready=True` is returned even when `handoff_report=None` after a pipeline failure (`agents/orchestrator.py:435-457`) |
| Versioned artifacts | **Partial** | Prompts are versioned (`prompts/loader.py:76-77`); no `schema_version` field found on the F1-F5 JSON artifacts themselves in the files read |
| Backpressure | **Partial** | Per-adapter semaphore caps exist (`adapters/ak_llm.py:21,44`); no route-/app-level admission control found in `main.py` |

---

## RESULT
**Status:** complete
**Deliverables:** `docs/ai/orchestration_review_evidence.md` (this scan's only write)

**Top-5 strongest aspects:**
1. Safety fail-closed is real and doubly-engineered (issue IDs ISS-019/ISS-026) — LLM setup failure, LLM call failure, and unparsable JSON all route to high-risk/crisis, never to "safe" (`agents/safety_classifier.py:270-380`).
2. `prompts_degraded` + `resolve_prompts_base_dir`'s hard `RuntimeError` turn a previously-silent generic-fallback-prompt bug (tracked as BUG-021) into a machine-visible, typed signal (`prompts/loader.py:14-68`, `agents/base.py:29-37`).
3. Vendor-adapter layer has genuine resilience engineering: exponential backoff, JSON-repair retry, per-adapter concurrency semaphore, and a router-level circuit breaker (`adapters/ak_llm.py`, `routing/fallback_policy.py`).
4. Per-turn `stage_history` audit trail (`StageRecord`) gives a genuine reconstructable timeline of every pipeline stage per session, returned to the caller each turn, not just logged.
5. F1→F5 offline chain uses clean pure-function contract types at the F3/F4/F5 boundary (`SessionRecord`, `LongitudinalSeriesInput`) with an explicitly enforced zero-filesystem-access rule inside the analysis functions (`f4.py:7-16`).

**Top-5 weakest aspects:**
1. No illegal-transition defense or idempotency guard — resubmitting a `completed`/`crisis_flow` `session_state` silently re-runs the full handoff pipeline including new LLM calls (`agents/orchestrator.py:166-211`).
2. `handoff_ready=True` is returned even when the handoff pipeline failed and `handoff_report=None` (`agents/orchestrator.py:435-457`) — the one caller (`routes/chat.py:109-123`) doesn't null-check it.
3. No server-side session persistence — full `SessionState` round-trips through the client every turn with no signature/integrity check, and malformed state is silently discarded to "fresh" (`routes/chat.py:66-78`).
4. `request_id` is declared on `AgentInput` but never threaded into sub-agent schemas or logs — cross-agent tracing for one turn has no shared trace id (`agents/base.py:15`, zero hits in `agents/*.py`).
5. Core LLM adapters set no client-level timeout (10-minute SDK default) and a defined backoff helper (`get_backoff`) is dead code (`adapters/ak_llm.py:39-42`, `routing/fallback_policy.py:143-146`).

**Evidence:** every claim above cites `file:line`; commands run were `Read`/`grep -n`/`grep -rn` against `apps/ai-server/src/` only (no test execution, no prior review docs read, the underscore-prefixed archive folder untouched).

**Open items:**
- F2→F3 upstream artifact validation (`f3.py:141 load_recommendation`) and the F4/F5 harness-side JSON→dataclass assembly were not read — flagged `unverified`, not asserted absent.
- `schemas/longitudinal.py`/`schemas/ai_predicted_disease.py` were not read in full — artifact schema-versioning gap is a plausible-not-confirmed finding.
- RAG-route DB session scoping (commit/rollback/close pattern) not verified — out of the six requested scan dimensions but adjacent to §5.

**Next:** none — scan is complete per brief; downstream use (critic/qa review of these findings) is the orchestrator's call.
