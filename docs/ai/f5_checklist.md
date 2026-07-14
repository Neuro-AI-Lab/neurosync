# F5 체크리스트 — Handoff Report 조립 (static + longitudinal, PDF/FHIR export)

> **범위:** F5 quick development 미션(오케스트레이터 dispatch, 2026-07-14)의 전용 모니터링 문서.
> `docs/ai/checklist_task1.md`의 F4 섹션이 이미 `f4_checklist.md`로 포인터화된 것과 동일한 패턴 —
> 이 미션 이후 F5 신규 세부 항목은 이 문서에서만 관리하며, `checklist_task1.md`의 F5 섹션(레거시
> `T1-F5-DEV-001~007`/`VER-001~008`)에는 중복 기재하지 않는다 — 해당 섹션은 이 문서로의 포인터
> 1줄만 유지한다.
> **ID 시퀀스:** `T1-F5-{TYPE}-{SEQ}`, `checklist_task1.md`의 전역 시퀀스를 승계한다. 레거시
> 최대치는 `DEV-007`, `VER-008`(직접 확인, 2026-07-14, `docs/ai/checklist_task1.md` L127-137) —
> 이 문서의 신규 `DEV` 항목은 `DEV-008`부터, 신규 `VER` 항목은 `VER-009`부터 이어 붙인다.
> `DOC` 타입은 레거시 F5 섹션에 선례가 없어(grep 0건) `DOC-001`부터 신규 시작한다. 재사용 금지.
> **기준 문서:** `docs/ai/f5_charting_research.md`(brainstorm, 연구 노트), `docs/ai/f5_quick_dev_plan.md`
> (writer, 이 미션의 설계 문서), `docs/ai/f4_quick_dev_plan.md`/`docs/ai/f4_checklist.md`(구조적
> 선례). 모든 상태 근거는 이 문서 + `discussion.md`/`error.md`의 링크된 엔트리로 추적된다.
> **Created:** 2026-07-14 | **Author:** writer, on orchestrator dispatch.

## ID 형식 및 상태

| 상태 | 의미 |
|---|---|
| `[ ]` | TODO |
| `[~]` | IN_PROGRESS / 부분 완료 |
| `[x]` | DONE (증거 유효) |
| `[!]` | BLOCKED / REGRESSED |

## 바인딩 워딩 (이 문서의 모든 `[x]` 행 및 향후 F5/`EXP-024` 인용 전체에 적용)

F5는 `EXP-023`(F4 배터리)의 VP-001/VP-003 산출물을 재사용하여 리포트를 생성한다 — 따라서
`EXP-023` 콘텐츠에 이미 구속력을 갖는 모든 워딩 규칙이 F5가 생성하는 리포트/문서 전체에도 그대로
적용된다: `REV-045`의 8행 wording table(F4 산출물 인용 전체 — `overall_direction` sentiment
포함 민감도 공시 의무, `similarity_score` 비-확률, VP-003 S8 사건의 보호자-연계-권고 능력 미보유
공시), `CVR-022`의 3개 binding condition(S8 사건의 S9 비지속 공시, VP-001 item-9 양성 세션의
동일세션 CTRS 비상승 공시, F3 완전성-급성도 반비례 명시), `CVR-021`의 S8 능력-귀속 caveat,
`REV-039`의 F3 v1 최종 MAY/MUST-NOT 표(척도 "검증됨" 서술 금지, item fidelity≠behavioral
fidelity, GAD-7 threshold_caveat 비대칭 공시). 상세: `discussion.md` REV-045, CVR-022, CVR-021,
REV-039; 본 문서 companion `docs/ai/f5_quick_dev_plan.md` §6이 이 규칙들을 F5 섹션별로 재정리한다.
F5 자체의 설계/구현에 대한 REV/CVR/ADR은 아직 제정되지 않았다 — 본 문서의 구현·검증 행은 그
게이트가 실제로 통과하기 전까지 `[x]`로 표기하지 않는다.

**상태 갱신(2026-07-14, `PLAN-2026-W29-E` 완료):** 위 문단이 서술한 게이트가 이제 전건 통과했다 —
`REV-046`(non-blocking-with-conditions)+`CVR-023`(adequate-with-conditions) → `ADR-037`(구현
licensed, 내러티브 DESCOPED) → 구현(commit `9514798`/`0771534`/`8717382`/`50dd255`) → qa
GATE:PASS(suite 1817 passed/2 skipped) → `EXP-024`(r1→r2→r3, r3 최종) → `REV-047`(evidence-sound-
with-corrections)+`CVR-024`(adequate-with-conditions) post-evidence 검토, 양자 모두 r3 closure
addendum으로 갱신. 아래 표의 `[x]` 행은 이 전체 체인을 근거로 한다 — 개별 근거 포인터는 각 행의
"선행 조건/비고" 열에 명시. 신규 F5 wording binding: `REV-047`의 8행 wording table + r3 addendum,
`CVR-024`의 binding condition(narrowed)이 이 문서 및 향후 F5/`EXP-024` 인용 전체에 추가로 적용된다
— "검증 완료"/"validated"/"FHIR-conformant" 금지, FHIR은 "이 프로젝트 자체 `validate_fhir_bundle`
구조 검증 통과"로만 서술, PDF legibility는 테스트된 3개 렌더러 config + critic 4번째 시각-검사
경로로 한정(`mutool` 미검증). 상세: `discussion.md` REV-047, CVR-024.

---

## 설계 (Design)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F5-DOC-001 | DOC | F5 charting-convention/FHIR R4 연구 노트(`docs/ai/f5_charting_research.md`, brainstorm, 485줄) — SOAP/intake/SBAR/MSE 텍스트-도출가능성 분석, 정신과 triage, 한국 임상 맥락, FHIR R4 리소스·LOINC 매핑(VERIFIED/UNVERIFIED 태그 보존) | [x] | 파일 존재 확인(직접 열람, 2026-07-14). Open items(미해결, 명시적으로 disclosed): Media 리소스(FHIR 차트 첨부) 미연구, CTRS 검증 LOINC 코드 없음, 의료법 시행규칙 제14조 항목 목록 미확보. 근거: `docs/ai/f5_charting_research.md` 전체 |
| T1-F5-DOC-002 | DOC | F5 quick-dev 설계 문서(`docs/ai/f5_quick_dev_plan.md`, writer, 이 미션) — §2 섹션별 데이터소스 매핑표, §3 charting-convention grounding, §4 아키텍처(production/harness 분리 + 12→17 SlotData 매핑), §5 export 사양(markdown/PDF/FHIR + FHIR 매핑표), §6 바인딩 워딩+red line, §7 `EXP-024` 약식 검증 설계, §8 gap, §9 wave plan | [x] | 파일 존재 확인(직접 작성, 2026-07-14). **Review-gate 통과 완료:** `REV-046`(non-blocking-with-conditions) + `CVR-023`(adequate-with-conditions) → `ADR-037`(2026-07-14, 구현 licensed) — F4의 `PLAN-2026-W29-D`(REV-044→CVR-020→ADR-036)와 동일 게이트 순서. **`ADR-037`에 따라 계획 문서 amended:** A8 내러티브 경로 이번 미션 descope(Decision 1), A3 종단 위험 신호 서브섹션 신설(Decision 2), A6 tie-handling(Decision 3), A0 disclaimer 추가(Decision 4), A7 약물 메모(Decision 5), REV-022→REV-044 Criterion 6 인용 수정(Decision 6) — 계획 문서 자체의 §0/self-check amendment record 참조. 근거: `docs/ai/f5_quick_dev_plan.md` 전체, `discussion.md` `ADR-037` |

## 구현 (Implementation — 전 항목 review-gate 통과 전 착수 금지)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F5-DEV-008 | DEV | `src/f5.py`(순수 엔진, zero-LLM, zero file-I/O, A0-A8/B1-B5 typed report model 조립) + `src/schemas/handoff_report.py`(`extra="forbid"`, `is_diagnostic: Literal[False]`, standalone lineage — `SlotData`/`HandoffInput`/`DomainCandidate`/`LongitudinalAnalysisOutput`와 상호 import 금지) | [x] | `f5_quick_dev_plan.md` §4.1-§4.2. Landed commit `9514798`(F5 테스트 95건). A0 disclaimer 블록(Decision 4), A3 종단 위험 신호 서브섹션(Decision 2), A6 tie-handling(Decision 3), A7 약물 메모(Decision 5) 전건 구현·`EXP-024` r3에서 렌더 확인. A8은 `narrative_enabled=True` 시 `ValueError` raise하는 코드-레벨 하드 가드(`f5.py:551-559`, `REV-047` Ruling 1 독립 확인) — 서브모델만 존재, 실제 narrative 호출 없음(Decision 1). |
| T1-F5-DEV-009 | DEV | Export 모듈 3종 — `src/services/f5_report.py`(markdown, `f4_report.py` 패턴 미러링) + PDF 렌더러(reportlab, `HYSMyeongJo-Medium`/`HYGothic-Medium` CID 폰트, 기존 F4 PNG 4종 임베드) + FHIR bundle builder(`Bundle(type=document)`, §5.3 매핑표) + §5.3 구조 검증 스크립트. `reportlab` 신규 의존성을 `uv`로 `pyproject.toml`에 추가 | [x] | `f5_quick_dev_plan.md` §5. Landed commit `9514798`(초기, non-embedded CID 폰트) → `8717382`(A3 캐비트+B5 per-chart absent-marker 수정, `EXP-024` r1 checks 5c/7) → `50dd255`(`BUG-044` — non-embedded CID 폰트를 SHA256-pinned 임베디드 subsetted Noto Sans/Serif CJK KR TrueType 폰트로 교체 + A6/A7/FHIR disclosure 4건, `ADR-038`). `EXP-024` r3에서 3개 export 포맷 전체 확인: A0/A3/A6/A7 amended 콘텐츠 렌더, A8은 3개 포맷 전체 부재-마커만 출력(narrative descoped). |
| T1-F5-DEV-010 | DEV | 내러티브 경로 — `src/services/f5_narrative_adapter.py`(12→17 `SlotData` 매핑, §4.3 표) + `routes/handoff.py`의 max-2-regenerate 루프를 공유 헬퍼로 추출(route와 F5 양쪽에서 재사용, 중복 구현 금지) + feature flag 배선(기본값은 결정 대기 — `f5_quick_dev_plan.md` §8 gap 1 참조) | [~] | `f5_quick_dev_plan.md` §4.4. **DESCOPED this mission — `ADR-037` Decision 1**: feature-flag 하드 가드만 구현됨(T1-F5-DEV-008 참조, `narrative_enabled=True` → `ValueError`); `src/services/f5_narrative_adapter.py` 모듈 자체는 코드 0줄 — 미착수. `EXP-024`는 zero LLM calls로 실행(`REV-047` Ruling 1 독립 확인). 향후 내러티브 웨이브는 프롬프트 v3 재설계(v2의 강제 12-섹션 템플릿과 hard red line #1 충돌 해소) + 신규 REV/CVR 통과가 선행되어야 착수 가능 — `REV-046`/`CVR-023`의 narrative-scoped 조건이 그 웨이브에 그대로 구속됨(carry-forward: `T1-F5-DEV-017`). `handoff_generator` v2 프롬프트 pin(`_PROMPT_VERSION="v2"`) 불변. |
| T1-F5-DEV-011 | DEV | 하네스 — `continuous_test.py`에 `run_f5_stage` post-loop 진입점(`STAGE_REGISTRY`의 `Stage("F5", ...)` → `implemented=True`) + 기존 `EXP-023` 산출물을 재생하는 독립 CLI 진입점(신규 세션 실행 없음), `--out`-aware | [x] | `f5_quick_dev_plan.md` §4.1/§9 Wave 4. Landed commit `9514798` — `--f5-from-artifacts <ARTIFACTS_DIR> --out <OUT_DIR>` CLI(`continuous_test.py:1201-1330,1595-1601`), `EXP-024` r1/r2/r3 전 라운드 이 CLI로 실행 확인. |
| T1-F5-DEV-012 | DEV | qa 코드 게이트 — CI-mirror ruff+pytest, `src/f5.py` no-harness-deps 검사(0 `open(`/0 harness import), 12→17 매핑·A3 co-display 로직 mutation-check | [x] | `f5_quick_dev_plan.md` §9. `CLAUDE.md` 라우팅 규칙 3 충족 — GATE:PASS 매 커밋(`9514798`/`0771534`/`8717382`/`50dd255`), 최종 suite **1817 passed / 2 skipped**(F5 테스트 148건). A3 co-display 로직 mutation-check: `BUG-043`(qa) 파일링+회귀 테스트로 종결. 12→17 매핑 mutation-check는 **미적용**(어댑터 모듈 자체가 미구현, T1-F5-DEV-010 참조) — 이 항목이 원래 요구한 mutation-check 범위와의 불일치는 T1-F5-DEV-010의 기존 스코프-불일치와 동일한 근본 원인. |

## 검증 (Validation — `EXP-024`)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F5-VER-009 | VER | `EXP-024` VP-001 전체 리포트 생성(md+PDF+FHIR, **결정론적 섹션만 — 내러티브 이번 미션 제외, `ADR-037` Decision 1**) — 기존 `EXP-023` VP-001 산출물로부터, 신규 세션 실행 없음, zero LLM calls | [x] | `f5_quick_dev_plan.md` §7.1. `EXP-024` r1(commit `0771534`)→r2(`8717382`)→**r3(`50dd255`, 최종)** — r3에서 exit 0, md+PDF+FHIR 전 포맷 생성, 5페이지 PDF, FHIR violations=[], 폰트 emb=yes 확인. |
| T1-F5-VER-010 | VER | `EXP-024` VP-003 전체 리포트 생성(md+PDF+FHIR, **결정론적 섹션만 — 내러티브 이번 미션 제외, `ADR-037` Decision 1**) — A5는 최신 세션(S11)이 아닌 최신 **투여** 세션(S9)을 명시적으로 식별·날짜표기해야 함(`CVR-022` binding condition 3); A3의 종단 위험 신호 서브섹션(`ADR-037` Decision 2)도 동일 S9(27/27, item-9 양성, safety_referral) staleness pointer를 S11 대비 표기해야 함 | [x] | `f5_quick_dev_plan.md` §7.1. `EXP-024` r3(`50dd255`, 최종) — A5는 S9(2026-11-12, PHQ-9 27/27, severe)를 명시적 날짜표기, A3 staleness pointer가 "2회차(61일) 경과" 문구로 S11 대비 표기 확인(check 2, r1부터 일관). |
| T1-F5-VER-011 | VER | Section completeness 검사(Check a) — A0-A8/B1-B5 전 섹션이 렌더되거나 명시적으로 "정보 없음"/"평가 불가"로 표기됨을 확인, 침묵 누락 0건 | [x] | `f5_quick_dev_plan.md` §7.2. qa/experiment-tracker 수행 — 15/15 `##` 헤더, exact order, 양 VP, 전 라운드(r1/r2/r3) PASS. |
| T1-F5-VER-012 | VER | Number traceability 재계산(Check b) — 리포트 내 모든 수치를 원본 아티팩트 필드와 대조, qa 독립 재계산 | [x] | `f5_quick_dev_plan.md` §7.2. qa step-9 독립 재계산 — 약 350+개 수치 대조, **0 불일치, 0 orphan 인용**. |
| T1-F5-VER-013 | VER | FHIR 구조 검증(Check c) — 필수 필드, `urn:uuid` 참조 해석, entry count 일치, `is_diagnostic`/disclaimer 검증 | [x] | `f5_quick_dev_plan.md` §5.3/§7.2. `validate_fhir_bundle()` — violations=[] 양 VP, 전 라운드. `$validate` 서버 호출 아님 — 구조 검증 스크립트만(FHIR "conformant" 서술 금지, `REV-047` wording row 2). |
| T1-F5-VER-014 | VER | PDF 렌더 무결성(Check d) — 파일 존재/크기/페이지 수, 한국어 텍스트 렌더링 가독성(텍스트 추출 표본 확인, tofu-box/깨짐 없음) | [x] | `f5_quick_dev_plan.md` §5.2/§7.2. **r3(최종)에서 clean PASS** — `BUG-044`(r1/r2: 비-embedded CID 폰트가 `·`/`⚠` tofu-box 유발, 2/3 non-default 렌더러 config에서 전면 한글 dropout) 폰트-임베딩 수정(`50dd255`) 후 qa 멀티-렌더러 GATE:PASS(3개 config 전건) + critic/clinical-validator 독립 시각 검사(4번째 경로) 3중 확인. **r1/r2 PDF는 historical tofu 아티팩트로 잔존, 소급 PASS 적용 안 됨.** `mutool`은 미검증(호스트 미설치, 저비용 후속 항목). |
| T1-F5-VER-015 | VER | Hard red line 준수 검사 — A6 섹션 경계(narrative 미혼입 — `ADR-037` Decision 1로 이번 미션 narrative 자체가 미호출이므로 구조적으로 자명 충족, 단 A6 tie-handling(Decision 3) co-rank 마커는 별도 확인 필요), `similarity_score` 인접부 "확률"/"probability"/"confidence" 부재, 모든 A5 수치 인접부 비-검증 문진 caveat 존재, 3개 export 포맷(md/PDF/FHIR) 전체 | [x] | `f5_quick_dev_plan.md` §6.1/§7.4 acceptance criterion 6. `REV-047` Criterion 6 PASS(6b: CVR-022 조건 verbatim 확인 both VPs/rounds; 6a: FHIR `Composition.section`에 별도 A8 섹션 자체가 생략됨 — 원 pre-registration의 "checkable placeholder" 기대보다 강한 처분으로 PASS-via-stronger-disposition, self-flagged pre-registration gap). A6 tie-handling(`ADR-037` Decision 3) — VP-001 "공동 1위"/"공동 4위" co-rank 마커 확인. |
| T1-F5-VER-016 | VER | `schemas/handoff_report.py` HPI-isolation adversarial 테스트 — `test_hpi_isolation.py`/`test_f3_hpi_isolation.py` 패턴 미러링, `SlotData`/`HandoffInput`/`DomainCandidate`/`LongitudinalAnalysisOutput` 상호 import 없음 확인 | [x] | `f5_quick_dev_plan.md` §4.2/§9 Wave 5. `tests/test_f5_hpi_isolation.py` — F5 전용 테스트 148건 중 일부, 전체 suite 1817 passed/2 skipped(commit `50dd255`)에 포함. narrative 미호출로 인해 narrative-flag=True 조건의 content-level 체크는 PASS-via-moot(`REV-047` Criterion 1) — 향후 내러티브 웨이브에 binding으로 이월. |

## Open / 후속 항목 (licensed, non-blocking — 이번 미션 범위 밖)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F5-DEV-013 | DEV | FHIR `$validate` 서버 측 검증(현재는 구조 검증 스크립트만) | [ ] | `f5_quick_dev_plan.md` §5.3/D3 — future option으로 명시, 이번 미션 범위 아님 |
| T1-F5-DEV-014 | DEV | `Media` 리소스(FHIR 차트 첨부) 연구 및 F5 B5 섹션 통합 | [ ] | `f5_charting_research.md` open item, `f5_quick_dev_plan.md` §5.3 B5 행 — "not researched this session either, by brainstorm or this plan" |
| T1-F5-DEV-015 | DEV | 내러티브 섹션(A8) 프로덕션 기본값(ON/OFF) 결정 | [ ] | `f5_quick_dev_plan.md` §8 gap 2 — 오케스트레이터/사용자 결정 필요, 이 미션은 기본값 `False` 제안만 함 |
| T1-F5-DOC-003 | DOC | 의료법 시행규칙 제14조 필수 기재 항목 목록 확보 | [ ] | `f5_charting_research.md` §1f open item, `f5_quick_dev_plan.md` §8 gap 1 — F5 출력의 법적 의무기록 지위 결정과 연동, brainstorm 후속 조사 필요 |
| T1-F5-DOC-004 | DOC | LOINC 언어-변이 정책(다국어 동일 코드 적용 가능성) 직접 출처 확인 | [ ] | `f5_charting_research.md` §3b — "not independently verified by fetching a LOINC-language-policy page," UNVERIFIED로 남음 |
| T1-F5-DEV-016 | DEV | A7 부서 추천의 `ServiceRequest.performer` 코드화 — `Organization`/`HealthcareService` 리소스 부재 갭 해소 | [ ] | `f5_quick_dev_plan.md` §5.3 — 이 계획에서 신규 식별된 갭(연구 노트 범위 밖), display-only 문자열로 v0 처리, future option |
| T1-F5-DEV-017 | DEV | 내러티브 경로(A8) 향후 웨이브 — `HandoffGeneratorAgent` v2 프롬프트를 v3로 재설계(강제 12-섹션 템플릿이 A0/A3/A6 결정론적 값 및 hard red line #1과 충돌하는 근본 원인 해소, `REV-046` Issue 1 / `CVR-023` Finding 1) 후, 신규 REV+CVR 통과 전까지 `src/services/f5_narrative_adapter.py` 구현·feature flag `True` 전환 금지 | [ ] | `ADR-037` Decision 1(내러티브 경로 이번 미션 descope, `EXP-024`에서 moot-by-descope로 재확인 — `REV-047` Ruling 1). 구속 조건 carry-forward: `REV-046` Criterion 0/1/2b(narrative arm), MAY/MUST-NOT 표 row 3/4/6; `CVR-023` binding condition 1, weak-point 34 — 이 미래 웨이브에는 그대로 구속. 상태 불변, 착수 0건. |
| T1-F5-DEV-018 | DEV | `VAL-016`/`BUG-031` 근본원인 수정 — F2 `DomainInferenceAgent`의 atomic Pydantic 검증(`DomainInferenceLLMResponse` 전체 실패 시 `domain_candidates`뿐 아니라 무관한 `department_candidates`까지 동반 소실)을 per-item salvage로 교체 | [ ] | `error.md` VAL-016(open)/BUG-031(open, `ADR-027` Decision C 원 스코핑은 MET-3 통계 채점 한정, F5 A7 렌더링에는 미적용). `REV-047` fix-licensing table: "NOT licensed by this evidence" — 단일-VP 라이브 인스턴스 1건만으로는 F2 코드 변경 미승인, 이 프로젝트의 atomicity discipline과 일관. 이번 미션은 disclosure-only 완화(A7 `VAL-016` 문구, `ADR-038` Decision 2(a))만 licensed·구현됨(T1-F5-DEV-009 참조) |
| T1-F5-DEV-019 | DEV | A6 face-validity flag — age/sex-mismatched RAG 후보(예: 28세 성인 환자에 "소아·청소년 우울증" 후보, `VAL-014` 확장)에 대한 자동 플래그 | [ ] | `CVR-024` recommendation 5(원 verdict) — deferred, `ADR-038` Decision 3. `CVR-024` addendum(r3 closure): "acceptable deferral" 판정 — 원본 정보(후보명/score/테이블 위치)는 이미 전부 가시적이며 자동 플래그만 부재, 신규 위험 없음. 착수 0건 |
| T1-F5-DEV-020 | DEV | A6 `reason_summary` 한글 현지화 — 후보 부재 시(`mode != "rag_live"`) 노출되는 사유 설명이 현재 미번역 영어 파이프라인 용어("Stage 1", "llm_only mode", "chunk-derived evidence")로 렌더됨 | [ ] | `CVR-024` addendum recommendation 7(NEW finding, item 46, minor) — VP-003(이 2-VP 데이터셋의 최고-급성도, `session_ctrs=2`/`crisis_triggered=True` 리포트)에서 발생, 한글 미숙 임상의에게 "silence vs. drop" 구분이 register 상 불명확. `ADR-038` Decision 2(b)로 구현된 노출 메커니즘 자체는 정확·유효 — 번역만 미착수 |
| T1-F5-DEV-021 | DEV | Near-ceiling `ISS-F2V-028` 캐비트 커버리지 확장 — 현재 `total_score == max_score`(정확 천장) 케이스만 A3/A5 co-location 구현, near-ceiling(예: 26/27, 25/27)은 `threshold_caveat: null`로 미표기 잔존 | [ ] | `CVR-024` binding condition 3(NARROWED, r3 addendum) — "NOT closed for near-ceiling scores... condition 3 remains fully binding, unweakened, for this residual half". `ADR-038` Decision 2(c)가 명시적으로 스코프 제한(새 threshold 판단 필요, 이번 미션 미착수). `CVR-024` addendum recommendation 8 |
| T1-F5-DEV-022 | DEV | `mutool` PDF 래스터 테스트 — `BUG-044`의 폰트-임베딩 수정을 4번째 렌더러 경로로 재확인 | [ ] | `error.md` BUG-044 Status 잔여 스코프("mutool remains untested (not installed on this host, both this and the original adjudication)"). `CVR-024` addendum recommendation 9 — "cheap, low-priority follow-up (not required to close condition 1)". Condition 1은 이미 3개 config + 2개 독립 시각-검사 경로로 CLOSED, 이 항목은 추가 확증용 |
| T1-F5-DOC-005 | DOC | 폰트 자산 크기 최적화(optional) — `NotoSerifKR-Subset.ttf`(`ADR-038` Decision 1, commit `50dd255`)가 약 7.0MB로, r1/r2 대비 PDF 파일 크기가 VP당 +55~58KB(임베드 글리프 데이터) 증가함(`EXP-024` r3 Results — VP-001 460,208→518,157B, VP-003 350,513→405,196B) | [ ] | 클리니컬/기능 리스크 없음(font-embedding 자체가 `BUG-044`의 필수 수정) — 순수 배포/저장 최적화 항목. 서브셋 재타겟팅(사용 글리프만 추가 축소) 검토 가능, non-blocking |

---

**Linked:** `docs/ai/f5_charting_research.md`, `docs/ai/f5_quick_dev_plan.md`; 레거시 F5 항목(이 미션
으로 변경되지 않음): `docs/ai/checklist_task1.md` `T1-F5-DEV-001~007` / `VER-001~008`. F4 선례:
`docs/ai/f4_checklist.md`, `discussion.md` PLAN-2026-W29-D/REV-044/CVR-020/ADR-036/CVR-021/REV-045/
CVR-022. F5 설계 review-gate(2026-07-14): `discussion.md` `REV-046`/`CVR-023`/`ADR-037`. F5
post-evidence review + fix wave(2026-07-14): `discussion.md` `REV-047`(+ r3 addendum)/`CVR-024`
(+ r3 addendum)/`ADR-038`; `error.md` `BUG-043`(resolved)/`BUG-044`(resolved)/`VAL-016`(open);
`result.md` `EXP-024`(r1/r2/r3); `docs/ai/development_report.md` `DR-022`.
