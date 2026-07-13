# F4 체크리스트 — 종단적 상태 변화 분석 (longitudinal state-change analysis)

> **범위:** F4 quick development 미션(`discussion.md` `PLAN-2026-W29-D`, 2026-07-13)의 전용 모니터링
> 문서. 사용자 지시(verbatim, 2026-07-13): "Checklist는 f4_checklist 문서로 정리하라." — 이 미션
> 이후 F4 신규 세부 항목은 이 문서에서만 관리하며, `checklist_task1.md`의 F4 섹션(레거시
> `T1-F4-DEV-001~005`/`VER-001~006`, TemporalSummaryAgent pairwise 유산)에는 중복 기재하지
> 않는다 — 해당 섹션은 이 문서로의 포인터 1줄만 유지한다.
> **ID 시퀀스:** `T1-F4-{TYPE}-{SEQ}`, `checklist_task1.md`의 전역 시퀀스를 승계한다. 레거시 최대치는
> `DEV-005`, `VER-006`(grep으로 재확인, 2026-07-13, `docs/ai/checklist_task1.md` L109-116/L198-200) —
> 이 문서의 신규 항목은 `DEV-006`부터, `VER-007`부터 이어 붙인다. 재사용 금지.
> **기준 문서:** `discussion.md` `PLAN-2026-W29-D`(미션 계획), `docs/ai/f4_quick_dev_plan.md`(설계),
> `result.md` `EXP-023`(약식 검증). 모든 상태 근거는 이 세 문서 + `error.md`의 링크된 엔트리로 추적된다.
> **Created:** 2026-07-13 | **Author:** writer, on orchestrator dispatch (`PLAN-2026-W29-D` step 11).

## ID 형식 및 상태

| 상태 | 의미 |
|---|---|
| `[ ]` | TODO |
| `[~]` | IN_PROGRESS / 부분 완료 |
| `[x]` | DONE (증거 유효) |
| `[!]` | BLOCKED / REGRESSED |

## 바인딩 워딩 (이 문서의 모든 `[x]` 행 및 향후 F4/`EXP-023` 인용 전체에 적용)

`REV-045`의 최종 wording table(`discussion.md`, 8행, `REV-044`를 확장/계승)이 이 문서 및
`EXP-023`을 인용하는 모든 문장을 구속한다 — 요약: F4는 실제 원점수 대비 산출된 방향성 판정의
**산술 정확성만** 보인다(비-각본 비교군이 존재하지 않음 — "임상 상태 변화를 탐지/검증한다"는
서술, 민감도/특이도 주장, 안정(no-change) 환자에 대한 검증 주장은 어디에도 쓰지 않는다,
`REV-044` circularity ruling); `similarity_score`/질환후보 추이는 **확률이 아닌 TREND**이다
(`VAL-014` 계승, open); VP-001의 `overall_direction=improved`는 `sentiment` 포함 여부에
outcome-determinative하게 의존하므로 인용 시 반드시 동반공시한다(`REV-045` wording-table row 2 —
제외 시 `unchanged`로 뒤집힘); VP-003 S8 사건은 시스템에 존재하지 않는 보호자-연계-권고 기능을
검증한 것으로 서술하지 않는다(`CVR-021` Finding 1) — 또한 S9에서 비지속됨을 동반공시한다
(`CVR-022` binding condition 1); VP-001 item-9 양성 세션(S1/S3/S7)을 안전-경로 증거로 인용할 때는
동일 세션의 F1 CTRS/crisis 신호가 상승하지 않았음을 동반공시한다(`CVR-022` binding condition 2);
F3 계열 완전성이 이 배터리에서 환자 급성도와 반비례했음(VP-003 10/11 세션 결측, 그중 7건이
crisis-triggered와 일치)을 F4의 종단 능력을 서술하는 모든 향후 문서가 명시해야 한다
(`CVR-022` binding condition 3). 상세: `discussion.md` `REV-044`, `REV-045`, `CVR-020`, `CVR-021`,
`CVR-022`.

---

## 설계 (Design)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F4-DOC-001 | DOC | F4 quick-dev 설계 문서(`docs/ai/f4_quick_dev_plan.md`, `PLAN-2026-W29-D` step 1) — F1(slot/CTRS/crisis/probe/sentiment)+F2(domain/disease-similarity trend)+F3(item/total/band) 세션 데이터 통합 종단 분석 설계, arc 프로토콜(VP-001/VP-003 11세션×~6개월), 스키마, production/harness 분리, wave plan | [x] | `REV-044`(critic) non-blocking-with-conditions(4 major — 2건 Wave-1 aggregation-basis blocking-scoped/Issue 1-2, 2건 disclosure/Issue 3-4; 사전등록 Criteria 0/0b/1-6 + MAY/MUST-NOT wording table 제정) → `CVR-020`(clinical-validator) adequate-with-conditions(1건 blocking-scoped: VP-003 care-connection 서사 부재/Finding 1, 7 major, 4 minor, 4 binding condition) → `ADR-036`(orchestrator)이 전 조건 dispositioned, 구현 licensed. 근거: `discussion.md` PLAN-2026-W29-D, REV-044, CVR-020, ADR-036 |

## 구현 (Implementation)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F4-DEV-006 | DEV | `src/f4.py`(N-세션 종단 분석 엔진, zero-LLM, Criterion-0/0b aggregation basis/combination rule 코드 docstring 사전공시) + `src/schemas/longitudinal.py`(`LongitudinalAnalysisOutput` 등) + `src/services/f4_report.py`(파일 I/O 분리 — Criterion 6 강화, `analyze_longitudinal_series` 자체는 0 file-I/O) | [x] | commit `75472ee`. 근거: `discussion.md` ADR-036 item 1, `result.md` EXP-023 Setup |
| T1-F4-DEV-007 | DEV | 종단 시나리오 하네스 — `apps/ai-server/tests/simulation/scenario_pack.py`(VP-001 `improvement_plateau` / VP-003 `relapse_after_partial_improvement`, 11세션×2) + `src/f1.py` narrow isolation seam(Option C: `scenario_guideline`/`scenario_pack_id` kwargs, 설계 §2.6) + `continuous_test.py` 가변 cadence(`session_offsets_days`) + F4 post-loop stage(`STAGE_REGISTRY`) | [x] | commit `75472ee`. `CVR-021`(clinical-validator) 콘텐츠 pass: adequate-with-conditions — CVR-020 조건 1/2 SATISFIED(VP-003 S8 사건 스크립팅, VP-001 S1 PHQ-9 목표 `~7`로 정정), 1건 신규 major report-scoped finding(S8 capability-attribution 리스크 — 본 문서 상단 바인딩 워딩 참조). 근거: `discussion.md` CVR-021, ADR-036 items 5-6 |
| T1-F4-DEV-008 | DEV | F2/F3 산출물 provenance 태깅(`scenario_pack_id`/`arc_mode` additive None-default 필드, `REV-044` Issue 4 / `ADR-036` item 3) + `src/services/trend_plotter.py` 확장(slot-fill 패널 + similarity/domain trend 신규 함수, 차트 3-5) | [x] | commit `75472ee`. 검증: 격리된 세션 원장(ledger) 전 11건에 `scenario_pack_id`/`arc_mode` populated 확인(양 VP). 근거: `result.md` EXP-023 Key Finding 1 |
| T1-F4-DEV-009 | DEV | qa 코드 게이트 — CI-mirror ruff+pytest, trend-math mutation-checks, no-harness-deps 검사(`src/f4.py` 0 `open(`/0 harness import) | [x] | **GATE:PASS**(suite 1669 passed/2 skipped). Mutation-check에서 `BUG-041`(`_first_last_slope_trend` confirmatory slope-sign, Criterion-0 basis 함수 — 부호 반전 mutation이 전체 스위트를 통과, survivor) + `BUG-042`(`_SEVERITY_BAND_RANK` PHQ-9 ordinal ranking — 인접 밴드 순위 교환 mutation survivor) 발견 → 동일 세션 회귀 테스트 추가로 **resolved**(프로덕션 코드 변경 없음, `git diff` empty 확인). 근거: `error.md` BUG-041(resolved)/BUG-042(resolved) |

## 검증 (Validation — `EXP-023`)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F4-VER-007 | VER | 실 종단 데이터 direction — VP-001(11/11 세션, PHQ-9 22→17 severe→moderately_severe, `overall_direction=improved`) / VP-003(11/11 세션, `session_ctrs`-carried `overall_direction=worsened`, `phq9_total=unknown` n=1) | [x] | `EXP-023`(22/22 세션 cell 완료, 0 실패, 0 재시도). `REV-045`(critic, post-evidence adjudication) Criteria 0/0b/1 전건 PASS — evidence-sound-with-conditions. **필수 병기:** VP-001 `improved`는 `overall_direction` 결합규칙에 `sentiment`를 포함하는 선택에 outcome-determinative하게 의존(제외 시 `unchanged`로 뒤집힘, `REV-045` wording-table row 2). **금지:** "임상 상태 변화 탐지/검증" 서술, 민감도/특이도 주장(비-각본 비교군 없음, `REV-044` circularity ruling). 근거: `result.md` EXP-023, `discussion.md` REV-045 |
| T1-F4-VER-008 | VER | Severity band 전이 + plot-data 실데이터 무결성(qa step-8 독립 재계산) | [x] | qa Check 2(12/12 투여 세션 severity band 정확 일치, 0 BUG 신규) + Check 3(양 VP 전체 프로덕션 replay가 shipped `temporal.json`과 byte-match, timestamp 제외) + Check 5(plot point traceability — S1/VP-001 표본 exact match, VP-003 결측 disease-similarity PNG는 `min_sessions=2` recurrence filter에 의한 정직한 결과로 확인, 결함 아님). **범위 caveat**(`REV-045` Issue 3, minor): "모든 plotted point" 전수 검증이라는 주장은 아님 — 표본 검증 수준. 근거: `result.md` EXP-023, `discussion.md` REV-045 |
| T1-F4-VER-009 | VER | Crisis 세션 sentiment 비-침묵 degrade(F1-7 Mode B empty → F1-8 Mode A per-turn fallback) | [x] | qa Check 4: VP-003의 crisis-triggered 7개 세션 전부 crash 無, false `unknown` 無(전부 `mode_a_derived`로 정상 폴백). **미검증 분기**(`REV-045` Issue 4, minor): F1-7(Mode B) 자체의 fallback 분기는 이번 배터리에서 미가동(전 세션 Mode A 데이터 존재) — `BUG-041`/`BUG-042`와 동급의 test-coverage gap, 회귀 테스트는 open(T1-F4-VER-013 참조). 근거: `result.md` EXP-023, `discussion.md` REV-045 |
| T1-F4-VER-010 | VER | Wording-law 준수(shipped artifacts) — `similarity_score` 비-확률, `is_diagnostic=False`, F3 threshold caveat 재투영, `VAL-014` caveat | [x] | qa Check 6: 7개 sub-check 전부 clean(양 `temporal.json` + 양 `_temporal_report.md`). `REV-045` 독립 재확인: raw artifact 자체의 `disclaimer` 필드가 `VAL-014`/`ISS-F2V-028`/`is_diagnostic=false`를 product-facing 텍스트로 verbatim 명시. 근거: `result.md` EXP-023, `discussion.md` REV-045 |
| T1-F4-VER-011 | VER | Production/harness 분리 유지(`src/f4.py` 0 `open(`/0 harness import) | [x] | grep 0 hits. `REV-045` Criterion 6 PASS. 근거: `discussion.md` REV-045 |
| T1-F4-VER-012 | VER | 임상 적정성 사후 검토 — trajectory 일관성, 분석 유용성, condition closure | [x] | `CVR-022`(clinical-validator, post-evidence): adequate-with-conditions — 이미 실행된 배터리 자체를 막는 blocking 없음(0건); 신규 major 2건(VP-003 S8 사건이 S9에서 비지속; VP-001 item-9-positive vs CTRS 동일세션 불일치에 대한 재조정 메커니즘 부재) + binding condition 3건(본 문서 상단 바인딩 워딩 참조). 근거: `discussion.md` CVR-022 |

## Open / 후속 항목 (licensed, non-blocking — 이번 미션 범위 밖)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F4-DEV-010 | DEV | 하네스 ledger 격리 — scenario-pack-scoped filter 또는 `--fresh-ledger` 플래그(`continuous_test.py::_load_ledger`/`_run_f4_analysis`) | [ ] | `REV-045` deviation (b): licensed, non-blocking, opportunistic — 다음 scripted F4 배터리 착수 전 권장. 이번 배터리는 `--out` 수동 워크어라운드로 evidence-sound(코드 trace로 독립 검증됨); 워크어라운드 생략 시 과거 세션이 자동 혼입되는 위험 있음(`EXP-023` Key Finding 1) |
| T1-F4-VER-013 | VER | Mode-B(F1-7) sentiment-fallback 회귀 테스트 — crisis 세션에서 `turn_sentiment_polarities`는 비어있고 `session_sentiment.polarity_trajectory`는 비어있지 않은 fixture | [ ] | `REV-045` Issue 4 / Resolution 4(minor, qa 권고) — `BUG-041`/`BUG-042`와 동급의 미검증 분기 |
| T1-F4-VER-014 | VER | Stable-arc(무변화) future battery cell — F4의 false-positive rate 커버리지 | [ ] | `REV-044` Issue 3 / `ADR-036` item 2 — accepted gap, 이번 미션에서 미해결(예산: +11세션 ≈ 배터리 비용 +50%). 3번째 VP 또는 stable-arc cell을 향후 wider battery로 예약. **금지:** "안정 환자에 대한 F4 검증" 서술 |
| T1-F4-DEV-011 | DEV | CVR-022 Rec 1 — 동일세션 item-9-positive vs CTRS/`crisis_triggered` cross-check(`critical_item_positive` 컬럼을 risk/crisis 표에 추가) | [ ] | `CVR-022` Finding 3(major) / binding condition 2 / Rec 1(orchestrator routed, non-binding recommendation) |
| T1-F4-DEV-012 | DEV | CVR-022 Rec 2 — PHQ-9 패널 severity-band 라벨 겹침 수정 + gap/risk-coincident 세션 on-chart annotation(음영 구간 또는 마커) | [ ] | `CVR-022` Findings 4-5(major — VP-003 단일-floating-point 차트에 결측/위험 표시 전무) / Rec 2, CVR-022 "single highest-value chart-level improvement" |
| T1-F4-DEV-013 | DEV | CVR-022 Rec 3 — "환자가 시스템 산출물에 반응" 시나리오 콘텐츠 pass 프로세스에 same-session slot-uptake check + next-session persistence check 추가 | [ ] | `CVR-022` Finding 2(major, weak-point register 최우선 항목 — VP-003 S8→S9 비지속) / Rec 3 |
| T1-F4-DEV-014 | DEV | CVR-022 Rec 4 — domain-confidence/disease-similarity 차트 gap-discontinuity 마커(점선 구간 단절 또는 marker gap) | [ ] | `CVR-022` Finding 6(minor) / Rec 4 |
| T1-F4-DEV-015 | DEV | CVR-022 Rec 5 — `crisis_f3_gaps` 정의에 content-triggered 확장(신규 risk-adjacent slot 공개 세션을 기존 numeric threshold와 병행 포함) | [ ] | `CVR-022` Finding 8(minor, VP-003 S7 threshold-scope gap) / Rec 5 |
| T1-F4-VER-015 | VER | F2 Stage-1 slot-coverage 재검토 — 종단/relapse arc에서 실제 채워지는 F1 slot vocabulary 대비 `_STAGE1_QUERY_SLOTS` 커버리지 | [ ] | `REV-045` disposition (c) — recommended, not mandated. `VAL-010` 확장 인스턴스(`EXP-023`, VP-003 10/11 세션 `mode=llm_only`로 강등) |

---

**Linked:** `discussion.md` PLAN-2026-W29-D, REV-044, CVR-020, ADR-036, CVR-021, REV-045, CVR-022;
`result.md` EXP-023; `error.md` BUG-041(resolved), BUG-042(resolved), VAL-010(reconfirmed at scale),
VAL-014(reconfirmed live). Legacy F4 items (unchanged by this mission except cross-referenced status
updates): `docs/ai/checklist_task1.md` `T1-F4-DEV-001~005` / `VER-001~006`.
