# F5 quick development plan — handoff report assembly (static + longitudinal)

> **Status:** design v1 — pre-implementation. No code changes in this mission; this document gates
> critic (REV) and clinical-validator (CVR) review before any `src/f5.py` work starts, mirroring
> `docs/ai/f4_quick_dev_plan.md`'s structural pattern.
> **Source of record:** orchestrator dispatch (this mission), building on
> `docs/ai/f5_charting_research.md` (brainstorm, 2026-07-14) and `docs/ai/f4_quick_dev_plan.md`
> (developer, `PLAN-2026-W29-D`). Design decisions D1–D7 below were handed to this document as
> orchestrator directives — presented here as the plan's design decisions, **proposed, ADR pending**.
> **Created:** 2026-07-14 | **Author:** writer, on orchestrator dispatch.

---

## 0. Reading map / verification note

Read in full this session: `docs/ai/f5_charting_research.md` (485 lines); `docs/ai/f4_quick_dev_plan.md`
(748 lines, structural template); `docs/ai/f4_checklist.md` (first 90 lines, conventions);
`docs/ai/checklist_task1.md` §F5 (lines 123–137) and its F4 pointer precedent (lines 105–122);
`discussion.md` `REV-039` (lines 994–1096), `CVR-021` (2008–2059), `REV-045` (2061–2157), `CVR-022`
(2159–2247). Code read in full or in relevant part: `apps/ai-server/src/agents/clinical_slot.py`
(`ALL_SLOT_KEYS` lines 26–39), `apps/ai-server/src/schemas/handoff.py` (`SlotData`, `HandoffInput`,
`HandoffOutput`), `apps/ai-server/src/agents/handoff_generator.py` (prompt pin, evidence-packet
construction), `apps/ai-server/src/routes/handoff.py` (regen loop, `_MAX_REGENERATE_ATTEMPTS = 2`,
line 25), `apps/ai-server/src/schemas/common.py` (`CTRSLevel`, `CTRS_TO_RISK`, lines 20–41),
`apps/ai-server/src/schemas/ai_predicted_disease.py`, `apps/ai-server/src/schemas/survey_result.py`,
`apps/ai-server/src/schemas/longitudinal.py`, `apps/ai-server/src/services/f4_report.py` (full),
`apps/ai-server/src/services/trend_plotter.py` (`TrendDataPoint`/`NamedSeriesPoint`/
`generate_trend_plot`/`generate_similarity_trend_plot`/`generate_domain_trend_plot` signatures),
`apps/ai-server/src/continuous_test.py` (`STAGE_REGISTRY` lines 1009–1016, CLI flags around
1076–1149), `apps/ai-server/src/grounding.py` (full — `SYSTEM_SLOT_KEYS`, `QUESTIONABLE_SLOT_KEYS`,
`OBSERVATION_SLOT_KEY`, `RISK_SLOT_KEY`, lines 28–52), `apps/ai-server/pyproject.toml` (dependency
list — confirms no PDF/FHIR library present today). Real on-disk artifacts opened directly:
`docs/ai/simulation_results/VP-001/VP-001_20260713_200133_conversation.json` (S11, full top-level
key scan), `experiments/EXP-023/runs/vp001/artifacts/VP-001/VP-001_20260713_200149_domain_inference.json`,
`experiments/EXP-023/runs/vp001/artifacts/VP-001/VP-001_20260713_200152_survey.json`,
`experiments/EXP-023/runs/vp001/artifacts/VP-001/VP-001_session_ledger.json` (first entry),
plus a full file listing of both VPs' `experiments/EXP-023/runs/{vp001,vp003}/artifacts/` directories
(confirms VP-003 has no `_temporal_disease_similarity.png`, matching the `min_sessions=2` recurrence
filter). Any claim below not traceable to one of these is marked `[DESIGN INTENT]` (this document's
own proposal, not yet code) or `UNVERIFIED`.

**Load-bearing fact not previously surfaced in any handed-off note:** `grounding.py:28–34` defines
`SYSTEM_SLOT_KEYS = frozenset({"encounter_metadata", "clinical_assessment", "treatment_plan"})` —
"Slots produced by the system, never by the conversation extractor." A repo-wide grep of `f1.py` for
these three key names returns **zero hits** — no component in this codebase has ever populated them.
Of the 12 canonical slots, only 9 are ever reachable via F1's conversation pipeline: the 8
`QUESTIONABLE_SLOT_KEYS` (`grounding.py:43–52`: `chief_complaint`, `history_of_present_illness`,
`past_psychiatric_history`, `medical_history`, `personal_social_history`, `family_history`,
`substance_use_history`, `risk_assessment`) plus the 1 `OBSERVATION_SLOT_KEY`
(`mental_status_exam`, `grounding.py:40`, "only accepted with lexical evidence" — rare by design).
This fact drives §2's A0/A4/A8 design and §4's 12→17 mapping table below; it is the single most
important grounding fact this plan rests on and is cited repeatedly.

**Amendment record:** Amended per `ADR-037` (2026-07-14) after `REV-046`/`CVR-023` — see the
amendment marks in §2.2 (A0/A3/A6/A7/A8 rows), §4.3/§4.4 (narrative path), §7.1/§7.3 (`EXP-024`
scope/budget), §9 (Wave 3/6), and the citation fix in §4.1; full disposition in `discussion.md`
`ADR-037`.

---

## 1. Purpose and scope

**User directive (verbatim intent):** an F5 임상 hand-off report that renders F1–F4's 종단적
(longitudinal) + 정적 (static, current-session) state 체계적이고 가독성 좋게(systematically,
readably), grounded in real psychiatric charting/REPORT conventions
(`docs/ai/f5_charting_research.md`), exportable as PDF and FHIR.

**What this plan covers:** report content design (§2), the charting-convention grounding for every
section (§3), production/harness architecture including the 12→17 legacy-schema mapping for the
optional narrative section (§4), the markdown/PDF/FHIR export spec (§5), binding wording and hard
red lines inherited from prior reviews (§6), a 약식 validation design for `EXP-024` (§7), genuine
open questions (§8), and an implementation wave plan for developer (§9).

**What this plan does not cover (explicit exclusions, mirrors F4's own discipline):**
- No code. No schema/module is written this mission.
- No change to any file under `docs/ai/prompts/**` — `handoff_generator` v2's prompt pin
  (`_PROMPT_VERSION = "v2"`, `handoff_generator.py:21`) is reused unchanged, never touched.
- No new LLM agent. The narrative section (§4) calls the EXISTING `HandoffGeneratorAgent` +
  `EvidenceVerifierAgent` in-process; no new prompt, no new model call type.
- No FHIR server integration or `$validate` service call — file-export-only, per D3; a future
  server-side validate is named as a future option, not built here.
- No clinical validation of report *usefulness* beyond what clinical-validator performs on this
  plan and on `EXP-024`'s output — that gate is clinical-validator's, not this document's own claim.
- Acceptance-criteria pre-registration for `EXP-024` is critic's job (§7 only proposes criteria for
  critic to adopt or revise), per the F4 precedent (`REV-044`).
- PRD fold (`docs/ai/PRD_task1_v2.md` §6) happens at mission end, per the handoff — not this
  document's job.

---

## 2. Report content design

### 2.1 Design principles (from `f5_charting_research.md` §2a, restated for traceability)

1. Situation-first micro-header (SBAR, §1c of the research note).
2. SOAP/APA-derived body with risk promoted to its own top-level section (§1a/§1b).
3. MSE section explicitly marked partial — never silently omits an unassessed domain.
4. AI-predicted-disease kept structurally separate (hard constraint) — never merged into narrative.
5. Two-part static + longitudinal split — a design choice, not literature-derived (research note
   flags this explicitly; carried here unchanged, flagged again in §8 for clinical-validator review).

### 2.2 Section → data-source mapping (complete)

All field paths below were verified against the real artifacts read in §0 (VP-001 S11) unless
marked `[DESIGN INTENT]` for a field that exists in the schema but was not populated in the sample
read (e.g. an empty `ai_predicted_disease.candidates` list).

**Part A — static (current-session hand-off), rendered from the LATEST session's artifacts.**
"Latest" means the most recent session with a saved `conversation.json`; for the questionnaire
section (A5) specifically, "latest" means the most recent session with `survey.json.outcome ==
"administered"`, which is **not always the same session** — VP-003's real `EXP-023` data has its
latest conversation at session 11 but its latest *administered* PHQ-9 at session 9 (session 11's
`survey.json` has `outcome` without `score_result`). A5 must date-stamp its own session index
separately from A0–A4/A6–A8's session index whenever the two diverge, and disclose the gap via F4's
`crisis_f3_gaps` (temporal.json) when the divergent sessions fall in a risk-elevated window.

**A3 is a second, deliberate exception to the Part A "latest session only" rule** (`ADR-037`
Decision 2, superseding this plan's original current-session-only A3 framing per `CVR-023`
conditions 2–3): A3's header-level current-session risk fields still render from the latest session
per the rule above, but A3 additionally owns a cross-session "종단 위험 신호" subsection that is
deliberately NOT scoped to the latest session alone — see the amended A3 row below.

| § | Section | Populated from (exact artifact.field) | Notes |
|:--|:--|:--|:--|
| A0 | Header / situation micro-summary | `conversation.json` top-level: `session_id`, `persona_id`, `persona_name`, `session_index`, `simulated_date`, `model`. `final_slots["chief_complaint"]` (1-line truncation). `session_ctrs` + `CTRS_TO_RISK[CTRSLevel(session_ctrs)]` (`common.py:33–39`, reused verbatim — zero new logic). `crisis_triggered`/`crisis_turn`. | **`encounter_metadata` (canonical slot 1) is never populated by F1** — it is a `SYSTEM_SLOT_KEYS` entry (`grounding.py:29–34`), by design meant to be produced by "the system," not the extractor. F5's A0 is the first system component to actually implement that design intent: it assembles session/report metadata deterministically from `conversation.json`'s own top-level fields, never from a slot value. This substitution is disclosed in-report, not silently substituted. **Header disclaimer block (`ADR-037` Decision 4, `CVR-023` Finding 6/recommendation 3):** A0 additionally carries a standing disclaimer stating the content is self-report-only (patient-reported via AI-administered chat; no clinician/family/other collateral informant contribution), AI-assembled, 비공식 문서 (not an official medical record entry), and non-diagnostic — independent of how §8 gap 1's legal record-status question eventually resolves. |
| A1 | Chief complaint | `conversation.json.final_slots["chief_complaint"]` | List-of-`{key,value}` in the raw artifact (`conversation.json:8–12`) — the F5 input builder normalizes this to a `dict[str,str]` (same normalization the harness ledger already performs, confirmed: `continuous_test.py` ledger entries store `final_slots` as a dict). |
| A2 | History of present illness | `conversation.json.final_slots["history_of_present_illness"]` | Same normalization as A1. |
| A3 | Risk / safety assessment | **Current-session fields** (Part A rule, latest session): `conversation.json.final_slots["risk_assessment"]` (may be absent — populated only by the Safety Probe protocol, never the extractor, `grounding.py:268–273`) + `conversation.json.{risk_floor, probe_events, crisis_triggered, crisis_turn, session_ctrs}` + F3 `survey.json.{safety_referral, score_result.critical_item_positive}` from the SAME session. **PLUS a "종단 위험 신호" (longitudinal risk-signal) subsection** (`ADR-037` Decision 2, `CVR-023` conditions 2–3): every item-9-positive/`safety_referral`-triggered F3 administration ACROSS ALL sessions, date-stamped, regardless of whether that session is current; F4 `temporal.json.concordance_flag` + an item-9-vs-CTRS same-session discordance line for each flagged administration; and a mandatory latest-scored-instrument staleness pointer whenever the current session itself has no F3 data (surfaces the most recent scored instrument's severity and how many sessions/how stale it is). | **A3 now owns F5's multi-session risk/F3 co-display role** (`ADR-037` Decision 2, adopting `CVR-023` recommendation 4) — this corrects the plan's original "current-session only" framing, which `CVR-023` Findings 2–3 showed cannot structurally deliver `CVR-022` binding condition 2 for either `EXP-024` VP (neither VP-001's item-9-positive sessions S1/S3/S7 nor VP-003's S9 are their own VP's latest session). The 종단 위험 신호 subsection is F5's report-layer delivery of `CVR-022` condition 2 inside Part A, ahead of F4's own `T1-F4-DEV-011` fix (open, non-blocking) landing. **VP-003 worked example** (`ADR-037` Decision 2, `CVR-023` Finding 3): S11 is the current session (active crisis — `crisis_triggered=true`, `session_ctrs=2`, zero F3 administration); the staleness pointer must surface that the only ever-administered PHQ-9 is S9 (27/27, item-9 positive, `safety_referral=true`), ~2 simulated months stale relative to S11. |
| A4 | Mental status summary (partial, text-derived) | `conversation.json.final_slots["mental_status_exam"]`, verbatim, WHEN present (rare by design: `OBSERVATION_SLOT_KEY`, "only accepted with lexical evidence," `grounding.py:275–279`) | **Design decision flagged for clinical-validator ratification (§8):** F1's schema carries MSE as ONE flat string, not per-domain sub-fields. A4 therefore CANNOT honestly present the research note's §1d 6-domain text-derivable breakdown (mood/thought process/thought content/insight/judgment/cognition) as independently populated — doing so would imply structure the underlying data does not have. A4 instead renders the raw slot text under a single label ("텍스트 기반 정신상태 메모 — 비구조화") plus the research note's canonical 11-domain checklist marked "이 슬롯에서 개별 추출 불가" for every domain, with the 5 observation-dependent domains (appearance/behavior/motor/speech/affect) additionally marked "평가 불가 — 텍스트 전용 문진" per design principle 3. When the slot is absent (the common case), A4 states this plainly, never silently omits the section. |
| A5 | Administered questionnaires | F3 `survey.json` for the latest **administered** session: `{scale_name, item_bank_version, item_bank_provenance, responses, score_result.{total_score,max_score,severity,critical_item_positive}, administration_mode, threshold_caveat}` + F4 `temporal.json.crisis_f3_gaps` for gap disclosure | Every number carries: (i) the non-validated-administration caveat (§6), (ii) `threshold_caveat` verbatim when non-null (AUDIT-C/GAD-7 only), (iii) an explicit date-stamp of the ADMINISTERING session, never presented as if current when stale (VP-003 case). |
| A6 | AI decision-support: candidate conditions (non-diagnostic) | `domain_inference.json.ai_predicted_disease.{candidates[].{disease, similarity_score, source_id, quote}, mode, disclaimer, recommended_questionnaire, recommendation_caveat}` from the SAME session as A0–A5 (or explicitly "정보 없음" when `mode="experimental_unpopulated"`/`candidates=[]`) | **HARD RED LINE:** own subsection, never merged into A1/A2/A3/A8. `similarity_score` rendered only as "유사도," never "확률"/"가능성"/"probability"/"confidence" (`REV-013 §4`, inherited verbatim). **Tie-handling (`ADR-037` Decision 3, `CVR-023` Finding 4/recommendation 1):** candidates sharing an identical `similarity_score` at the same rank render CO-RANKED (e.g. "공동 1위"), never given an arbitrary #1/#2 ordering — applies to VP-001 S11's tied 계절성 정동장애/월경전 불쾌장애 pair (`similarity_score=0.485` each, confirmed `domain_inference.json:233–265`) and any future tie. |
| A7 | Recommended department / questionnaires | `domain_inference.json.department_candidates[].{department, reason, domain_ref}` + `ai_predicted_disease.{recommended_questionnaire, recommendation_caveat}` | **Medication note (`ADR-037` Decision 5, `CVR-023` Finding 5/recommendation 2):** A7 carries the one-line disclose-only note "약물 정보: 별도 구조화 항목 없음, HPI/병력 서술 포함 여부만 확인" — no schema change; F1's 12-canonical-slot schema has no dedicated medication field (`clinical_slot.py:26–39`). |
| A8 | Clinician-facing synthesis (non-diagnostic, **optional, feature-flagged — DESCOPED this mission, `ADR-037` Decision 1**) | Output of `HandoffGeneratorAgent` v2 (`report_markdown`) — **not called this mission**; the narrative-flag path exists as design only (§4.3/§4.4), flag ships hardcoded `False` | **DESCOPED this mission per `ADR-037` Decision 1** (adopting `CVR-023` condition 1 option (c) / `REV-046` Resolution-1 direction): feature flag defaults `False`, zero `HandoffGeneratorAgent` calls anywhere, `EXP-024` runs deterministic-only (zero LLM calls, §7.3). A8 always renders the explicit "AI 종합 소견 미생성 (narrative disabled)" marker (§4.4), never blank or silently omitted. A future narrative wave requires a versioned prompt redesign (v3, resolving the v2 prompt's mandatory 12-section template colliding with hard red line #1) plus a fresh REV/CVR before re-enabling; `REV-046`'s narrative-scoped findings (Issues 1/3/5, Criterion 0, Criterion 2b's narrative arm) and `CVR-023`'s narrative-scoped findings (condition 1, weak-point 34) bind that future wave, not this mission. If/when enabled, A8 would be clearly labeled "AI 생성 — 임상 진단 아님" and would never populate `clinical_assessment`/`treatment_plan` (canonical slots 11/12, `SYSTEM_SLOT_KEYS`, no `SlotData` field mapped to either). |

**Part B — longitudinal (cross-session trend), rendered entirely from F4's `temporal.json`.**

| § | Section | Populated from | Notes |
|:--|:--|:--|:--|
| B1 | Trend verdicts per scale | `temporal.json.trend_verdicts[]` (dimension/direction/basis/n_comparable_points/evidence) + `temporal.json.scale_series` (per-scale point tables) | |
| B2 | CTRS trajectory | `temporal.json.ctrs_series[]` | |
| B3 | Event timeline | `temporal.json.ctrs_series[].{crisis_triggered, probe_event_count}` (F4 exposes counts only, not raw `probe_events` content) + `temporal.json.crisis_f3_gaps[]` (narrative gap list) | |
| B4 | Discordance flags | `temporal.json.concordance_flag` | **Trend-level only** (`f4.py::_concordance_flag`, per `CVR-022` Finding 3) — this field does NOT cover the same-session item-9-vs-CTRS discordance A3 already supplements at the report layer; B4 and A3's co-display table answer two different discordance questions and must not be conflated in prose. |
| B5 | Trend charts (PNG) | REUSE the 4 existing F4 chart files by path reference: `<VP>_<ts>_temporal_scales_ctrs_sentiment.png`, `_ctrs_zoom.png`, `_disease_similarity.png` (absent for VP-003 — honestly missing per `trend_plotter.py`'s `min_sessions=2` recurrence filter, confirmed: VP-003 has exactly 1 disease-bearing session), `_domain_confidence.png` | F5 **never regenerates charts** — it embeds/links the F4-produced PNGs already on disk. Zero new plotting code for B5 itself. |

### 2.3 What is deliberately NOT built this mission

- No new per-domain MSE extraction (A4 stays a single-flat-string rendering, per the design
  decision above).
- No new `crisis_f3_gaps`-style content-triggered threshold (`CVR-022` Rec 5, open, F4's own scope,
  not F5's).
- No same-session `concordance_flag` variant inside F4's schema itself — A3's co-display table is
  F5's report-layer answer to the same clinical need `T1-F4-DEV-011` (open) will eventually answer
  inside F4's own schema; the two are complementary, not duplicative, and F5's plan does not block
  on `T1-F4-DEV-011` landing first.

---

## 3. Charting-convention grounding

Every section in §2.2 traces to a specific subsection of `docs/ai/f5_charting_research.md`:

| F5 element | Research-note basis | Grounding strength |
|:--|:--|:--|
| Situation-first A0 header | §1c (SBAR, Joint Commission/AHRQ/WHO-endorsed) | Literature-grounded |
| A1–A2 (CC/HPI), A7 (referral) | §1a (SOAP-S), §1b (APA Practice Guidelines 3rd ed. + intake-note vendor sources) | Literature-grounded (APA is a professional-society guideline; vendor sources are corroborated across 4+ independent EHR vendors, not peer-reviewed) |
| A3 promoted to its own top-level section | §1a ("mandatory risk in Plan" convention), §1b (APA's named suicide-risk topic), §1e (psychiatric-triage safety-first logic) | Literature-grounded, 3-way corroborated |
| A4 partial/marked-incomplete MSE | §1d (StatPearls 11-domain MSE + text-derivability split, corroborated by ADAPTS arXiv:2605.03212 and telepsychiatry-fidelity literature) | Literature-grounded; the specific A4 rendering DECISION (flat-string, not per-domain) is this plan's own honesty-driven addition, not itself literature-derived — flagged in §8 |
| A6 kept structurally separate | Hard constraint (brief) + independently corroborated by §1a's "Assessment slot cannot carry an AI diagnosis" reasoning and §1b's distinct "quantitative assessment" APA topic | Literature-corroborated, not literature-mandated |
| A8 relabeled synthesis, not diagnosis | §1a's "Applicability to F5" note (SOAP-A relabeled) | Design choice, literature-informed |
| B1–B5 two-part static/longitudinal split | §2a point 5 — **explicitly flagged by the research note as a design choice, no direct single-encounter-note precedent** | **Not literature-derived** — carried forward for clinical-validator review, per the research note's own recommendation |
| B4 discordance flags | **No charting-convention precedent found** (research note §2b, B4 row) | Novel to this system |
| B5 chart attachment as supplementary visual | Loosely analogous to lab-trend graph attachment; no formal citation found | Weak analogy only |

---

## 4. Architecture

### 4.1 Production/harness split (mirrors F4, `f4_quick_dev_plan.md` §4)

```
PRODUCTION                                        HARNESS
src/f5.py (NEW, pure, zero-LLM, zero file-I/O)    continuous_test.py F5 stage (NEW) +
───────────────────────────────                   a standalone from-ledger entry
  assemble_handoff_report(                         ───────────────────────────────
    HandoffReportInput                              1. resolve conversation_path/
  ) -> HandoffReportOutput                             domain_inference_path/survey
        │  - NEVER opens conversation.json/              pointers from the isolated
        │    domain_inference.json/survey.json/           EXP-023-style ledger (or,
        │    temporal.json itself                         for a future live route,
        │  - NEVER reads the ledger (REV-044             from request-supplied paths)
        │    Criterion 6 rule: production never touches   2. open those JSON files, build
        │    harness-only artifacts. Citation corrected      HandoffReportInput per §2.2
        │    from REV-022 per REV-046 Issue 6 / ADR-037.)
        │  - pure function over the explicit           3. call src.f5.assemble_handoff_
        │    dataclass the caller built                    report(...)
        │  - deterministic (string/dict assembly       4. IF narrative flag set: build a
        │    only — no numeric aggregation                 HandoffInput via the 12→17
        │    logic like F4's trend math)                    adapter (§4.3), call
        ▼                                                  HandoffGeneratorAgent +
  save_f5_result(output, output_dir)                       EvidenceVerifierAgent
    -> <vp_id>_<ts>_handoff.md                           in-process (§4.4)
    -> <vp_id>_<ts>_handoff.pdf                        5. call src.services.f5_report.
    -> <vp_id>_<ts>_handoff_fhir.json                     save_f5_result(...)
                                                        6. print PASS/WARN, same
                                                           convention as F1–F4
```

`src/f5.py` never imports `json`/`pathlib` for I/O and never imports anything from `src.
continuous_test`/`tests/` — same discipline `f3.py`/`f4.py` already state for themselves. File I/O
lives in a NEW sibling module `src/services/f5_report.py` (mirrors `src/services/f4_report.py`,
same rationale: a whole-file grep for `open(` on `src/f5.py` must return 0 hits with zero ambiguity,
REV-044 Criterion-6 precedent).

### 4.2 New schema module

`[DESIGN INTENT]` `src/schemas/handoff_report.py` — standalone by design, same lineage discipline as
`schemas/ai_predicted_disease.py`/`schemas/survey_result.py`/`schemas/longitudinal.py`: `extra=
"forbid"`, `is_diagnostic: Literal[False]` fixed at the type level, own disclaimer constant. This
module never imports `schemas/handoff.py`/`schemas/domain_inference.py`, and neither of those may
import it — enforced at implementation time by an adversarial isolation test mirroring
`tests/test_hpi_isolation.py`/`tests/test_f3_hpi_isolation.py`/(the equivalent F4 suite named in
`f4_checklist.md` T1-F4-DEV-006's evidence). Sections mirror §2.2's A0–A8/B1–B5 breakdown as typed
sub-models; the narrative section (A8) is a plain `str | None` field on the container, populated
only when the narrative feature flag is set — `handoff_report.py` itself never imports
`agents/handoff_generator.py` (that call happens one layer up, in whatever module orchestrates the
optional narrative step, §4.4).

### 4.3 12 → 17 legacy `SlotData` mapping (for the optional narrative section only)

**Status: DESCOPED this mission (`ADR-037` Decision 1).** This adapter and the mapping table below
are a design reference only — no code in this mission's Waves 1–4 constructs
`src/services/f5_narrative_adapter.py` or calls it. Retained verbatim for the future narrative wave,
which additionally requires a versioned prompt redesign (v3) and a fresh REV/CVR before
implementation (`REV-046`/`CVR-023` narrative-scoped conditions bind that future wave).

`SlotData` (`schemas/handoff.py:11–33`) has 17 fields. F5's 12 canonical slots (`clinical_slot.py:
26–39`) do not map 1:1. This adapter is the ONLY new code touching the legacy schema boundary, and
per the design directive it does not modify `schemas/handoff.py` at all — it lives in a NEW module
(`[DESIGN INTENT]` `src/services/f5_narrative_adapter.py`), which is a lighter footprint than the
directive's own stated ceiling ("do NOT modify legacy `schemas/handoff.py` beyond an adapter
function") and keeps both standalone schema modules (§4.2's `handoff_report.py` and the legacy
`handoff.py`) importable independently of each other.

| Canonical slot (12) | SlotData field (17) | Mapping | Rationale |
|:--|:--|:--|:--|
| `chief_complaint` | `chief_complaint` | Direct | Exact name match |
| `history_of_present_illness` | `history_of_present_illness` | Direct | Exact name match |
| `past_psychiatric_history` | `past_psychiatric_history` | Direct | Exact name match |
| `substance_use_history` | `substance_use` | Direct | Semantic match |
| `personal_social_history` | `psychosocial_context` | Merged (with `family_history`) | Labeled concatenation: `"[개인/사회력] {text}\n[가족력] {text}"` when both present; single-labeled when only one is |
| `family_history` | `psychosocial_context` | Merged (with `personal_social_history`) | See above |
| `risk_assessment` | `risk_factors` | Direct | Semantic match |
| `medical_history` | **unmapped** | Left `None`, disclosed | No clean `SlotData` target exists. Rejected alternative: folding into `psychosocial_context` alongside two other slots already merging there — a 3-way merge into one free-text field risks losing which sentence belongs to which domain, which the narrative-generation prompt (unchanged, v2) was never designed to disambiguate. Leaving it unmapped-with-disclosure is the safer default; the deterministic core (A2 in particular, since medical comorbidity often appears in HPI free text) is unaffected. |
| `encounter_metadata` | **unmapped** | `SYSTEM_SLOT_KEYS` — never populated by F1, no `SlotData` target | Narrative-path-excluded; A0 (deterministic) is the only F5 section carrying this content |
| `mental_status_exam` | **unmapped** | `OBSERVATION_SLOT_KEY` — rarely populated, no `SlotData` target | Narrative-path-excluded; A4 (deterministic) is the only F5 section carrying this content |
| `clinical_assessment` | **unmapped** | `SYSTEM_SLOT_KEYS` — never populated by F1, no `SlotData` target | Narrative-path-excluded by design — the AI narrative must not author a diagnostic assessment (§2.2 A8) |
| `treatment_plan` | **unmapped** | `SYSTEM_SLOT_KEYS` — never populated by F1, no `SlotData` target | Narrative-path-excluded by design, same reasoning as above |

**SlotData fields with no canonical-12 source (`onset`, `duration`, `triggers`, `sleep`, `appetite`,
`mood`, `anxiety`, `concentration`, `energy`, `functional_impairment`, `medication` — 11 fields):**
stay `None` after the adapter runs. F1's flat 12-slot pipeline never produces this finer
granularity; this content, when present at all, is embedded as prose inside the wider
`chief_complaint`/`history_of_present_illness` narrative text the adapter DOES carry (confirmed in
the real VP-001 S11 sample: sleep/mood/functional detail all appear inline in `history_of_
present_illness`'s free text) — so the LLM narrative path is not blind to this content, only unable
to cite it under its own separate legacy field tag. This is a disclosed, honest information-loss
statement, not a functional gap in the report: A2's own deterministic rendering of the full HPI
text (§2.2) already carries everything these 11 fields would have.

**`ScaleScore`/`risk_events`/`prior_handoff` (`HandoffInput`, `schemas/handoff.py:47–62`):**
`scale_scores` populated from A5's F3 data (`ScaleScore(scale_name, total_score, severity)` per
administered scale in scope); `risk_events` populated from A3's co-display rows (one dict per
session-level risk signal, mirroring the existing `EvidenceSource.risk_event` convention already
used by `_extract_evidence_packets`, `handoff_generator.py:249–258`); `prior_handoff` populated from
the PREVIOUS session's own generated `_handoff.md` when one exists (longitudinal continuity,
mirrors F1's own `prior_handoff` seam) — `None`/`is_first_visit=True` on session 1.

### 4.4 Narrative section — in-process reuse, not an HTTP round-trip

**Status: DESCOPED this mission (`ADR-037` Decision 1).** Everything below (the in-process call
pattern, the shared regen-loop helper, the feature flag) is a design reference only — no code in
this mission calls `HandoffGeneratorAgent.run()`/`EvidenceVerifierAgent.run()`. `EXP-024` runs with
the narrative flag hardcoded `False`.

`routes/handoff.py`'s existing regen loop (`_MAX_REGENERATE_ATTEMPTS = 2`, line 25; lines 61–120)
is HTTP-route code, not a library function. F5's narrative step must call `HandoffGeneratorAgent.
run()` and `EvidenceVerifierAgent.run()` **directly, in-process** — never by having F5 issue an HTTP
request to `POST /ai/handoff/generate` — consistent with this codebase's existing pattern of
production modules (`f1.py`, `f3.py`) calling agents directly rather than through routes.
`[DESIGN INTENT]`: the max-2-regenerate loop logic must be extracted into a small SHARED helper
callable from both the existing route and F5's narrative step (never duplicated ad hoc in two
places) — exact placement (a new function in `agents/handoff_generator.py`, or a new
`src/services/handoff_regen.py`) is left to developer's implementation-time judgment, but the plan
requires sharing, not copy-pasting, the loop.

**Feature flag:** the deterministic core (§4.1–§4.3, A0–A7 + B1–B5) runs standalone with the
narrative flag `False`. **This is now a binding default for this mission, not a proposal** —
`ADR-037` Decision 1 supersedes §8 gap 2's original "proposal, not a resolved directive" framing: no
code path in this mission ever sets the flag `True`. A8 is always omitted from the report with an
explicit "AI 종합 소견 미생성 (narrative disabled)" marker, never silently blank.

---

## 5. Export spec

### 5.1 Markdown

`[DESIGN INTENT]` mirrors `f4_report.py::_build_report`'s pattern exactly: one `##`/`###` section per
§2.2 row, one markdown table per multi-row data group (A3's co-display table, A5's per-scale table,
B1's trend-verdict table, B2's CTRS-series table), the disclaimer block reprinted near the top (same
convention F4 uses), and B5's chart PNGs referenced by relative markdown image links (`![...](...)`)
pointing at the F4-produced files already on disk — no new image bytes.

### 5.2 PDF (D2 — reportlab, single new dependency)

**Library:** `reportlab` — the only new PyPI dependency this mission, declared via `uv` in
`apps/ai-server/pyproject.toml`'s `[project.dependencies]` list (confirmed absent today: no
`reportlab`/`weasyprint`/`fpdf2`/`jinja2`/`markdown` anywhere in the current dependency list,
`pyproject.toml:6–23`).

**Rationale (from the orchestrator directive, restated with the concrete grounding found this
session):** pure-Python — no system `cairo`/`pango` dependency, unlike `weasyprint`; built-in Adobe
CID Korean fonts (`HYSMyeongJo-Medium`/`HYGothic-Medium` via `reportlab.pdfbase.cidfonts.
UnicodeCIDFont`) — no font-file shipping requirement, unlike `fpdf2`'s external-TTF need, which
matters given this repo's Korean-primary content (§1f of the research note: Korean legal charting
context favors Korean-language export); mature `drawImage`/`Image` PNG-embedding support for B5's
4 chart files.

**Layout:** A0's situation header first (SBAR-motivated, §3), followed by A1–A8 in order, followed
by B1–B5, with B5's PNGs embedded directly (not linked) since a PDF has no external-file-reference
convention a clinician could reliably follow. Font selection: `HYGothic-Medium` for body text
(Korean sans-serif, closer to on-screen chart/UI text already used elsewhere in this project),
`HYSMyeongJo-Medium` reserved for section headers if visual distinction is wanted — exact choice is
a developer/`filemanager` implementation detail, not pinned here.

**Not yet empirically confirmed:** whether `reportlab`'s CID font rendering actually produces
legible Korean glyphs in this repo's specific environment is `UNVERIFIED` until `EXP-024` (§7)
actually renders a PDF and a human/qa check reads it — flagged as a validation-design item, not
assumed to work merely because the library documents CID font support.

### 5.3 FHIR R4 (D3 — file export only, structural validation script)

Bundle shape: `Bundle(type="document")`, first entry `Composition`. No FHIR server, no `$validate`
call this mission (future option, not built). Mapping adapted from `f5_charting_research.md` §4 to
this project's ACTUAL schemas and field paths (VERIFIED/UNVERIFIED status preserved from the
research note; nothing below upgrades or downgrades a status without a fresh citation):

| F5 section | FHIR resource | Code system + code | Our field source | Status |
|:--|:--|:--|:--|:--:|
| Document as a whole | `Bundle`(document), `Composition` | `Composition.type` = LOINC `57143-0` "Mental health Referral note" (best-fit, imperfect) | `handoff_report.py` container fields (`vp_id`, `generated_at`) | **VERIFIED** code exists; fit is a design judgment (research note §4) |
| A1 Chief complaint | `Composition.section` | LOINC `10154-3` "Chief complaint Narrative - Reported" | `conversation.json.final_slots["chief_complaint"]` | **VERIFIED** |
| A2 HPI | `Composition.section` | LOINC `10164-2` "History of Present illness Narrative" | `conversation.json.final_slots["history_of_present_illness"]` | **VERIFIED** |
| A3 Risk/safety | `RiskAssessment` + `Composition.section` | section = LOINC `84209-6`; `RiskAssessment.basis` → CTRS Observation + probe-event count; `.prediction.qualitativeRisk` = `CTRS_TO_RISK[CTRSLevel(session_ctrs)]` (`common.py:33–39`, REUSED verbatim — zero new mapping logic needed, the enum already exists); `.prediction.rationale` = `risk_assessment` slot text | `conversation.json.{session_ctrs, risk_floor, probe_events, crisis_triggered}` + `final_slots["risk_assessment"]` + F3 `safety_referral`/`critical_item_positive` (co-displayed per §2.2 A3) | **VERIFIED** section code + resource fields; the `qualitativeRisk` mapping via the existing `CTRS_TO_RISK` dict is this plan's own implementation choice, not independently sourced from FHIR guidance |
| A4 MSE (partial) | `Composition.section`, `Observation`(category=`exam`) | LOINC `10190-7` "Mental status Narrative" — **must carry `Observation.note` disclosing partial/text-only status**, per the research note's own caveat that this code presumes a complete clinician-observed MSE | `conversation.json.final_slots["mental_status_exam"]` (or explicit absence) | **VERIFIED** code; disclosure requirement non-optional |
| A5 Questionnaires | `QuestionnaireResponse` + `Observation`(category=`survey`) | PHQ-9 total `44261-6`; PHQ-9 panel/instrument `44249-1`; GAD-7 total `70274-6`; AUDIT-C total `75626-2`; every `Observation.note` carries the non-validated-administration caveat + `threshold_caveat` when non-null | F3 `survey.json.{scale_name, responses, score_result.total_score, threshold_caveat}` | **VERIFIED**, all 4 codes fetched directly by brainstorm (research note §3b) |
| A6 AI-predicted-disease | `Observation`(category=`survey`/`exam`, one `component` per candidate) | No LOINC/SNOMED code applies; locally-defined CodeSystem per candidate; `.note` states "not a diagnosis, not a probability" | F2 `domain_inference.json.ai_predicted_disease.candidates[].{disease, similarity_score, source_id, quote}` | **N/A/UNVERIFIED** — `ClinicalImpression` evaluated and rejected (Maturity Level 0, no numeric sub-field) per the research note |
| A7 Department recommendation | `ServiceRequest` | `.category`/`.performer` (department — **display-only, no `Organization`/`HealthcareService` resource exists in this system**, an additional local gap beyond the research note's own finding); `.reasonReference` → A6 Observation | F2 `domain_inference.json.department_candidates[].{department, reason, domain_ref}` | **VERIFIED** field definitions; department-as-coded-reference is **UNVERIFIED/not applicable** — this system has no Organization/HealthcareService resource, a gap this plan surfaces beyond what the research note scoped |
| A8 Clinician synthesis (optional) | `Composition.section` narrative only, no coded resource | LOINC `51847-2` "Evaluation + Plan note" (narrative framing only — must not carry a diagnosis code); **omitted entirely from the Bundle when the narrative flag is `False`** | `HandoffOutput.report_markdown` (via 12→17 adapter, §4.3–4.4) | **VERIFIED** code exists; applicability caveat per research note (requires explicit AI-authorship disclaimer in the section narrative) |
| B1–B3 Longitudinal trend/CTRS/event timeline | Repeated `Observation`, same code+category, differing `effectiveDateTime` | category=`survey`; CTRS = local CodeSystem (no LOINC) | F4 `temporal.json.{scale_series, ctrs_series}` | Mechanism **VERIFIED**; CTRS code **UNVERIFIED/not applicable — locally defined** |
| B4 Discordance flags | `Observation`(derived/flag), `.interpretation`/`.note` | No standard code found | F4 `temporal.json.concordance_flag` (+ A3's own report-layer same-session discordance, which has no FHIR resource of its own — carried only as `Observation.note` text on the A3 `RiskAssessment`) | **UNVERIFIED/not applicable** |
| B5 Trend charts | `Media` resource, referenced from `Composition.section.entry` — **NOT researched this session either, by brainstorm or this plan** | N/A | 4 existing F4 PNG files | **Not researched** — v0 bundle contains **NO images**; charts stay markdown/PDF-only, per D3 |
| Non-diagnostic disclosure (cross-cutting) | No dedicated resource; `Composition.section.text` + `Provenance` (algorithm authorship, not independently verified) | N/A | `is_diagnostic`/`disclaimer` fields on every F1–F5 schema | **No standard exists** — the single largest standards gap in this whole mapping, per the research note §3f |

**Structural validation script (`[DESIGN INTENT]`, developer's implementation, tests/ territory):**
checks (a) required fields present per resource type used above, (b) every `urn:uuid` reference
inside `Composition.section.entry` resolves to an actual entry elsewhere in the Bundle, (c) Bundle
entry count matches the number of sections that claim a coded resource (A3/A4/A5/A6/A7/B1–B4), (d)
`is_diagnostic=false` and the disclaimer text are present verbatim on every resource that carries
them in the source schema. This is a **structural** check only — it does not call any external FHIR
`$validate` service (D3, explicitly out of scope this mission).

---

## 6. Binding wording + hard red lines

### 6.1 Hard red lines (structural, not stylistic — apply to every export format)

1. **AI-predicted-disease (A6) is its own clearly-labeled non-diagnostic section, NEVER inside
   clinician-narrative sections** (A1–A5, A8) — in markdown, PDF, and FHIR (own `Composition.section`
   / own `Observation` resource) alike.
2. **`similarity_score` is never rendered as a probability/확률** — anywhere: A6's markdown table,
   the PDF's A6 panel, and the FHIR `Observation.note` on A6's resource.
3. **Every questionnaire number (A5, B1) carries the non-validated-administration caveat** — "AI가
   진행한 대화형 문진 결과이며, 검증된 임상 설문 시행이 아닙니다" (or equivalent), in every export
   format, every time a score is cited.

### 6.2 Binding wording inherited from prior review entries

Since `EXP-024` (§7) reports on VP-001/VP-003 content sourced from `EXP-023`, every wording
constraint those reviews attached to `EXP-023`'s content binds F5's generated report text wherever
it renders that same underlying data:

**From `REV-045` (8-row table, `discussion.md` 2121–2132) — binds every F4-derived F5 section
(B1–B5, and A3's `session_ctrs`/`crisis_f3_gaps` citations):**
- MAY say F4 correctly computed the shipped verdicts given the actual raw scores; MUST NOT say F4
  "detects"/"validates" clinical state change in general (no non-scripted comparison exists).
- **VP-001's `overall_direction=improved` is sensitive to whether `sentiment` is included in the
  vote** (excluding it flips the verdict to `unchanged`) — any F5 report citing VP-001's
  `overall_direction` in B1 must disclose this sensitivity in the same citation, not merely in a
  footnote elsewhere.
- `similarity_score`/disease-candidate trend content (A6, B1's disease-similarity references) is a
  TREND over noisy inputs, `VAL-014` inherited and open — never present it as clinically validated.
- Single-batch (n=1 arc per VP) evidence — no generalization across patients.
- No machine-computed field isolates VP-003's S5–S7 window as a distinct episode; F5 must not
  imply `crisis_f3_gaps` itself flagged an "episode" — it is a tracker-narrated disclosure of a data
  gap, not an F4-computed signal.
- VP-003's S8 event (if cited by A0's session-history context or B3's event timeline) is
  patient-initiated narrative content loosely motivated by the system's actual crisis-response
  output — never characterized as validating a guardian-liaison-recommendation capability (no such
  feature exists in `apps/ai-server/src`, 0 grep hits for `보호자`).
- VP-001's observed-vs-design-intent PHQ-9 divergence (22→17 vs. ~7→3–4 design intent) is an
  upstream (simulator/F1/F3) finding, not an F4 arithmetic error — extends `ISS-F2V-028`, not a new
  issue.
- The ledger-isolation workaround is confirmed clean for THIS battery only — do not assume future
  batteries are automatically isolated (the harness-side fix, `T1-F4-DEV-010`, is still open).

**From `CVR-022` (binding conditions 1–3, `discussion.md` 2229–2234) — binds A3, B3, and any
"system longitudinal capability" narrative F5's A8/A0 might generate:**
1. Any citation of VP-003's S8 care-connection event as evidence of durable improvement must first
   check S9's own record and disclose that the event's substance is absent one month later. F5's
   B3 event timeline (which surfaces only F4's own counts, not raw F1 event content) does not
   itself carry this risk directly — but any narrative prose (A8, if it ever references S8) must.
2. Any citation of VP-001's item-9-positive/`safety_referral` sessions (A3's co-display table
   surfaces exactly this) as safety-pathway evidence must disclose, in the same citation, that the
   same session's F1-derived CTRS/crisis signal showed no elevation — A3's row-level co-display
   satisfies this structurally; any prose SUMMARIZING A3 must preserve the disclosure.
3. Any description of this system's F4 longitudinal capability must state that F3-series
   completeness is inversely correlated with patient acuity (VP-003: 10/11 sessions gapped, 7
   coinciding with `crisis_triggered=true`) — not merely disclose the raw gap count. F5's A5/B1
   gap-disclosure text must use this framing, not a bare number.

**From `CVR-021` (binding condition, `discussion.md` 2052):** same S8 rule as `REV-045` row 6 above
— restated here because it is independently binding from the clinical-validator side, not merely a
critic echo.

**From `REV-039` (F3 v1 final wording table, `discussion.md` 1053–1064) — binds A5 whenever it
renders PHQ-9/GAD-7/AUDIT-C content:**
- MAY say the F3 administration/scoring/ledger engine was live-exercised with mechanically exact
  totals/bands; MUST NOT say any scale is "validated"/"instrument validated"/certified/
  deployment-ready.
- Item-text fidelity (byte-exact sourcing) is closed for all 23 sourced items, but this does NOT
  mean any item is "clinically re-verified" — text fidelity and behavioral fidelity are separate
  claims; A5 must not conflate them.
- GAD-7's `threshold_caveat` is structurally `null` on every artifact produced to date (an
  asymmetry with AUDIT-C, `CVR-016`/`CVR-017` binding condition, `REV-039` row 5) — if F5's A5 ever
  renders a GAD-7 score, it must disclose this caveat-field asymmetry explicitly, not merely omit
  the (currently absent) `threshold_caveat` value silently.
- The whole-instrument over-endorsement pattern (`ISS-F2V-028`) is real but its mechanism (item
  text vs. anchor-menu vs. instruction wording) is unconfirmed — A5 must not attribute a specific
  cause if it ever narrates the pattern.
- Item-9 safety-pathway routing is "invoked and correctly evaluated," never "validated" (no
  documented-positive item-9 case has occurred across `EXP-018`–`EXP-020`; VP-001's `EXP-023` data
  DOES have documented-positive item-9 sessions, S1/S3/S7 — A3's co-display table is where that
  content surfaces, bound by `CVR-022` condition 2 above, not this table's own wording).

---

## 7. Validation design (약식) and budget — `EXP-024`

### 7.1 Cells

2 VPs (VP-001, VP-003) × full report generation (markdown + PDF + FHIR, **deterministic sections
only — A0–A7/B1–B5; narrative section (A8) DESCOPED this mission per `ADR-037` Decision 1**) from
EXISTING `EXP-023` artifacts — **no new F1/F2/F3/F4 session runs**, **zero LLM calls**. 2 cells
total.

| VP | Source artifacts | A5 latest-administered session | Design tension to surface honestly |
|:--|:--|:--|:--|
| VP-001 | `docs/ai/simulation_results/VP-001/` (F1) + `experiments/EXP-023/runs/vp001/artifacts/VP-001/` (F2/F3/F4) | S11 (11/11 administered) | PHQ-9 never drops below `moderately_severe` across all 11 sessions while cadence metadata implies improvement-justified spacing (`CVR-022` Finding 1) — A0/B1's report text must not imply resolution the data does not show |
| VP-003 | `docs/ai/simulation_results/VP-003/` (F1) + `experiments/EXP-023/runs/vp003/artifacts/VP-003/` (F2/F3/F4) | **S9**, not S11 (only 1/11 scored administration) | A5 must date-stamp S9 explicitly and disclose the 2-session gap to S11 via `crisis_f3_gaps` framing (`CVR-022` binding condition 3) |

### 7.2 Machine checks

| Check | Method |
|:--|:--|
| (a) Section completeness | For each VP, every §2.2 row (A0–A8, B1–B5) is present in the output OR explicitly marked "정보 없음"/"평가 불가" — qa greps the rendered markdown for every section header, confirms none silently dropped |
| (b) Number traceability | qa independently recomputes/greps every number the report renders against its cited source artifact field (same discipline as F4's Criterion 3) — a mismatch is a BUG, not a note |
| (c) FHIR structural validity | The §5.3 structural script: required fields present, `urn:uuid` references resolve, entry count matches claimed sections, `is_diagnostic`/disclaimer present verbatim |
| (d) PDF render sanity | File exists, non-zero size, page count ≥ 1 (or matches an expected minimum given section count), a text-extraction pass confirms at least a sample of the Korean section headers/disclaimer text is present and legible (not garbled/tofu-boxed) |

### 7.3 Explicit budget estimate

Deterministic core: 0 LLM calls (pure assembly, per §4.1). **Narrative path: DESCOPED this mission
per `ADR-037` Decision 1** — the narrative flag ships hardcoded `False`, `HandoffGeneratorAgent`/
`EvidenceVerifierAgent` are never called, and `EXP-024` runs with **zero LLM calls total across both
VPs and both cells**. The up-to-12-call ceiling previously estimated here for the narrative path (2
VPs × up to 3 generation + up to 3 verifier-loop regeneration attempts, per `routes/handoff.py`'s
own loop, `_MAX_REGENERATE_ATTEMPTS = 2`, line 86–92 early-return on `VerifierAction.passed`) is
retained as a design reference for the future narrative wave only (§4.3/§4.4), not a budget for this
mission's `EXP-024` run.

### 7.4 Proposed acceptance criteria (for critic pre-registration — this plan proposes, does not bind)

1. Every §2.2 section renders or is explicitly marked absent — 0 silently-dropped sections across
   both VPs' markdown output.
2. Every number in both reports (markdown, and the same numbers re-extracted from the PDF's text
   layer) traces to a specific source-artifact field, independently re-derived by qa — 0 fabricated
   numbers.
3. Both FHIR bundles pass the §5.3 structural script with 0 unresolved references and 0 missing
   required fields.
4. Both PDFs render with legible Korean text on at least a sampled page (qa/human visual or
   text-extraction check) — a garbled/tofu-boxed Korean PDF is a FAILED check, not a cosmetic note.
5. VP-003's A5 section correctly identifies S9 (not S11) as the latest-administered session, with
   the gap explicitly disclosed per `CVR-022` binding condition 3's framing — a report that silently
   presents S9's score as "current" (implying S11-recency) is a FAILED check.
6. Every hard red line in §6.1 holds in all 3 export formats — machine-checkable via grep
   (A6 section boundary markers, absence of "확률"/"probability"/"confidence" near any
   `similarity_score` citation, presence of the non-validated-administration caveat adjacent to
   every A5 number).

### 7.5 What is NOT claimed

- No claim that F5's report LAYOUT is clinically useful beyond what clinical-validator's own
  `EXP-024` review states — this plan proposes a design, it does not certify usefulness.
- No claim that the PDF is legally sufficient as (or equivalent to) a formal medical record entry —
  the 의료법 Article 14 field-list gap (research note §1f) is open and unresolved; §8 surfaces this.
- No claim that the FHIR bundle is server-round-trip-validated — structural script only, no
  `$validate` call (D3).
- No generalization beyond 2 VPs × 1 report each — single-batch evidence, same discipline the F4
  battery already established for this project.
- No new clinical content is generated beyond what the EXISTING `handoff_generator` v2 prompt
  (unchanged) already produces — F5 does not add new LLM reasoning, only new assembly/export code
  around existing outputs.

---

## 8. Gaps → user questions

Two genuine, unresolved items requiring orchestrator/user input; everything else in this plan is a
proposed design decision made here (library choice excluded per instruction, and treated as
decided):

1. **Legal/medical-record status of F5's output.** The research note (§1f) found Korea's 의료법
   Article 22 requires "detail sufficient to judge treatment appropriateness" and Korean-language
   recording, but could not retrieve the enumerated field list in 시행규칙 Article 14 — this remains
   genuinely UNVERIFIED. If the user intends F5's output to ever be treated as (or feed into) an
   official chart entry rather than a pre-consultation intake aid, that changes retention/
   Korean-vs-bilingual export requirements and may require re-scoping A0–A8 against a legal field
   list this plan does not have. Non-blocking for `EXP-024` (dev/test artifacts only), but a real
   open question for any production rollout.
2. **Narrative-section default state once F5 is eventually wired beyond a standalone/harness
   module.** This plan proposes the feature flag defaults to `False` (deterministic-only) for any
   future live-route use, with `EXP-024` exercising `True` for validation coverage — but this is a
   proposal, not a resolved directive; the orchestrator directive (D1) specifies the flag exists,
   not its default.

One standing, non-blocking gap carried forward from the research note, restated for completeness:
the 의료법 시행규칙 Article 14 field list (item 1 above) and the LOINC language-variant policy
claim (research note §3b, "not independently verified") remain open research items for a future
brainstorm session, not this plan's job to close.

---

## 9. Implementation wave plan

| Wave | Scope | Files | Done when |
|:--|:--|:--|:--|
| 1 | `src/f5.py` (pure engine) + `src/schemas/handoff_report.py` | new `src/f5.py`, new `src/schemas/handoff_report.py` | `assemble_handoff_report` runs on a hand-built synthetic `HandoffReportInput` (toy fixture covering all of A0–A8/B1–B5) and produces a schema-valid `HandoffReportOutput`; grep-verified 0 `open(`/harness imports in `src/f5.py` |
| 2 | Exporters | new `src/services/f5_report.py` (markdown, mirrors `f4_report.py`), PDF renderer (reportlab + Korean CID fonts, embeds existing F4 PNGs), FHIR bundle builder + §5.3 structural validation script; `reportlab` added to `pyproject.toml` via `uv` | All three exporters run against Wave-1's toy fixture and produce non-empty files that pass their own structural sanity checks |
| 3 | Narrative path — **DESCOPED this mission (`ADR-037` Decision 1)** | *(not built this mission — design reference only)* `src/services/f5_narrative_adapter.py` (12→17 mapping, §4.3), shared regen-loop helper (§4.4), feature-flag wiring | **Deferred to a future narrative wave.** No code in this mission's Wave 3 slot; the feature flag ships hardcoded `False` and A8 always renders the explicit absent-marker (§4.4). The future wave additionally requires a versioned prompt redesign (v3, resolving the v2 prompt's mandatory-12-section collision with hard red line #1) plus a fresh REV/CVR before implementation — `REV-046`/`CVR-023`'s narrative-scoped conditions bind that future wave. |
| 4 | Harness | `run_f5_stage` post-loop entry in `continuous_test.py` (`STAGE_REGISTRY`'s `Stage("F5", ...)` flips to `implemented=True`) + a standalone from-ledger CLI entry that replays EXISTING `EXP-023` artifacts, `--out`-aware | A `--out` run against `EXP-023`'s existing VP-001/VP-003 artifacts produces `<VP>_<ts>_handoff.{md,pdf,fhir.json}` for both VPs, driving only production interfaces (external-verification principle) |
| 5 | Tests | new `tests/test_f5.py` (section-assembly unit tests, toy data), new `tests/test_f5_hpi_isolation.py` (adversarial isolation suite mirroring `test_hpi_isolation.py`/`test_f3_hpi_isolation.py`), FHIR structural-validator tests, PDF sanity tests, 12→17 adapter field-by-field tests | qa **GATE:PASS**; mutation-checks on the 12→17 mapping logic and the A3 co-display assembly (non-vacuous mutation-verification discipline, `REV-013 §3`/`BUG-041`/`BUG-042` precedent) |
| 6 | `EXP-024` (§7) | none (experiment-tracker territory) | Both cells complete (md+PDF+FHIR, **deterministic sections only — narrative DESCOPED per `ADR-037` Decision 1**), qa recompute + FHIR structural check + PDF sanity check run, critic REV filed, clinical-validator CVR filed — three side-by-side verdicts per D7 |
| 7 | Docs fold | `docs/ai/PRD_task1_v2.md` §6, `docs/ai/f5_checklist.md` item status flips, `checklist_task1.md` §F5 pointer already updated by this mission | Orchestrator/filemanager territory at mission end — out of this plan's own scope, noted for completeness |

A qa code gate (CI-mirror ruff+pytest, no-harness-deps check on `src/f5.py`, mutation-checks) is
mandatory before `EXP-024` launches, per `CLAUDE.md`'s routing rule 3 — same gate class F4 required.

---

## Self-check (fabrication audit)

Every field path, function/class name, and line-number citation in this document was verified
against an opened file or a real on-disk artifact this session (§0 lists exactly which). The 12→17
mapping table (§4.3) and the `SYSTEM_SLOT_KEYS`/`QUESTIONABLE_SLOT_KEYS`/`OBSERVATION_SLOT_KEY`
facts it rests on were confirmed by direct read of `grounding.py` and a repo-wide grep of `f1.py`
(0 hits for `encounter_metadata`/`clinical_assessment`/`treatment_plan`), not inferred from the
brief alone. The FHIR mapping table (§5.3) reuses `f5_charting_research.md` §4's VERIFIED/UNVERIFIED
tags verbatim where the resource/field is unchanged, and adds exactly two new UNVERIFIED items this
session identified beyond the research note's own scope (the A7 department-as-`ServiceRequest.
performer` gap, since no `Organization`/`HealthcareService` resource exists in this system; and the
A3 `qualitativeRisk` mapping via the existing `CTRS_TO_RISK` dict, which is this plan's own
implementation choice, not independently FHIR-sourced) — both flagged as such, not silently upgraded
to VERIFIED. No arc/persona/session content was invented — every VP-001/VP-003 example cited (S11
vs. S9 divergence, item-9 sessions, PHQ-9 series) traces to the real artifacts opened in §0 or to
the already-adjudicated `REV-045`/`CVR-022` entries read in full.

**Amendment record:** Amended per `ADR-037` (2026-07-14) after `REV-046`/`CVR-023` — narrative path
(A8) descoped, A3 gains the multi-session risk role, A6 tie-handling, A0 disclaimer additions, A7
medication note, and the REV-022→REV-044 Criterion 6 citation fix. See §0's amendment record and the
amendment marks throughout §2.2/§4.3/§4.4/§7/§9.

**Linked:** `docs/ai/f5_charting_research.md`, `docs/ai/f4_quick_dev_plan.md`, `docs/ai/f5_checklist.md`
(companion deliverable, this mission), `REV-039`, `CVR-021`, `REV-045`, `CVR-022`, `REV-046`,
`CVR-023`, `ADR-037` (discussion.md).
