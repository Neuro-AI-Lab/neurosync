# F1-F5 total-validation cohort — new longitudinal arc packs (brainstorm design, 2026-07-15)

5 new 10-session arc packs, completing the F1-F5 total-validation cohort alongside the EXP-023
precedent (`tests/simulation/scenario_pack.py`: VP-001 `improvement_plateau`, VP-003
`relapse_after_partial_improvement`). None of the 5 files below are wired into
`scenario_pack.py`'s `_SCENARIO_PACKS` dict yet — each file's own docstring states the one-line
`_ARC_MODE_TO_PERSONA` addition a developer needs to make. **All 5 are flagged for critic REV +
clinical-validator CVR review before any harness run**; no ADR ratifies them yet.

Day-offset schedule (all 5, per the user's explicit "10 sessions, ≤6 months" directive — distinct
from EXP-023's own 11-session/6.0-month schedule): `[0, 7, 14, 21, 35, 49, 63, 91, 137, 183]` days
(4 weekly acute-engagement -> 3 biweekly response-consolidation -> 3 tapered-monthly maintenance;
day 183 = ~6.0 months, satisfies "≤6 months").

| VP | Arc mode | File | Session cadence | Key transitions |
|---|---|---|---|---|
| VP-002 (우울 에피소드 의심, 재진) | `treatment_response_setback` | `vp002_treatment_response_setback.py` | S1 = persona's own documented 6-week revisit state (PHQ-9 ~7); weekly→biweekly→monthly taper | S1-S5 gradual improvement (PHQ-9 ~7→~4); **S6-S7 scripted setback** (new-semester homeroom+생활지도부 recurrence of the persona's own root stressor, missed doses, PHQ-9 peaks ~10) but never crisis; S8-S10 recovery resumes, ends better than baseline (PHQ-9 ~4, medication-taper conversation raised) |
| VP-004 (공황 발작 + MDD 의심, 중증 재진) | `fluctuating_panic_recurrence` | `vp004_fluctuating_panic_recurrence.py` | S1 = persona's own documented 2-month revisit state (PHQ-9 ~21, panic 1-2x/week); same taper | S1-S5 cautious stabilization (panic frequency declining to a 2-week clear stretch); **S6-S7 scripted panic-recurrence** (deadline + ER-visit-anniversary confluence, PHQ-9 back to ~20, passive SI intensifies but stays plan-free per persona's own SI ceiling); S8-S10 partial (not full) stabilization via CBT-adjacent coping, ends PHQ-9 ~14, residual anticipatory anxiety, panic ~monthly |
| VP-010 (최소화형/non-crisis) | `stable_minimizing_slow_disclosure` | `vp010_stable_minimizing_slow_disclosure.py` | S1 = persona's own documented first-visit ground truth (PHQ-9 ~13); same taper | Ground truth stays roughly stable-to-mildly-improving throughout (PHQ-9 ~13→~9), never a large swing, never crisis; disclosure STYLE is the arc's real axis — Tier-1-dominant S1-S5, **first unprompted partial disclosure at S6**, spontaneous Tier-2/3-equivalent content becomes the default from **S7**, brief minimization relapse under stress at S9 (self-corrected), ends with an open, still-occasionally-hedged disclosure style at S10 |
| VP-011 (신체화 가면형) | `somatic_persistent_late_mood_disclosure` | `vp011_somatic_persistent_late_mood_disclosure.py` | S1 = persona's own documented first-visit state (somatic-focal, PHQ-9 ~14 ground truth); same taper — **deviates from the persona file's own "no multi-session run" scoping note, per coordinator ruling 2026-07-15 (documented at the top of the file, persona file itself untouched)** | Somatic presentation persists S1-S6 (specific probes still reveal anhedonia/sleep-pain-independence in isolation, never connected to mood); **new reveal-partition gate opens at S7** — first spontaneous, unprompted mood-connection acknowledgment; S8 referral agreement; S9 first behavioral-activation attempt; S10 partial integration (mood named as a contributing factor, "우울증" self-label still avoided) |
| VP-012 (알코올사용장애 동반) | `aud_escalation_contemplation` | `vp012_aud_escalation_contemplation.py` | S1 = persona's own documented first-visit state (AUDIT-C 8, soju-track v2; PHQ-9 ~10 comorbid); same taper | Precontemplation/escalation S1-S5 (AUDIT-C peaks ~9-10 under financial stress, one failed ambivalent cut-down attempt at S2); **S6 external prompt** (worsened labs) triggers **S7 shift into contemplation** (spouse conversation, openly voiced ambivalence, Prochaska/DiClemente stages-of-change framing); S8 first sustained cut-down attempt (~5x/week); S9-S10 partial, non-abstinent reduction stabilizes (~4x/week, AUDIT-C ~5-6), comorbid PHQ-9 mildly improves (~10→~8) |

## Cross-cutting design notes

- **Crisis-content licensing:** VP-002/010/011/012 carry zero new crisis content (matching each
  persona's own non-crisis/SI-negative ground truth, unchanged across all 10 sessions). VP-004's
  crisis-adjacent content (passive, fear-based SI; intermittent self-harm impulse) is licensed
  entirely by the persona file's own documented profile and never escalated beyond it — no active
  SI/plan is scripted at any session.
- **No fabricated clinical facts:** every arc's stressor/trigger events are grounded in each
  persona's own documented history (VP-002's homeroom+생활지도부 stressor pattern, VP-004's
  translation-deadline/ER-visit anniversary, VP-012's health-scare/labs/spousal-conflict already
  present in the base file) — never an invented, unrelated plot device.
- **VP-011 deviation, explicit:** the persona file's header/§8 state "no multi-session run
  scheduled" as a W6 SC-12-battery scoping note. The coordinator ruled (2026-07-15) that the
  user's current directive supersedes this scoping; the arc file itself carries the deviation
  notice and authors a new reveal-partition table (persona fact -> gating session) since one did
  not previously exist for a multi-session VP-011. The persona `.md` file was NOT edited.
- **Review status:** none of these 5 packs are clinically validated yet. All 5 require critic REV
  (design-time review, same gate EXP-023's VP-001/003 packs went through per `REV-044`/`ADR-036`)
  and clinical-validator CVR (adequacy of the escalation/relapse/gating content) before any
  `_SCENARIO_PACKS` wiring or harness run.
