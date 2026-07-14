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

---

## 설계 (Design)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F5-DOC-001 | DOC | F5 charting-convention/FHIR R4 연구 노트(`docs/ai/f5_charting_research.md`, brainstorm, 485줄) — SOAP/intake/SBAR/MSE 텍스트-도출가능성 분석, 정신과 triage, 한국 임상 맥락, FHIR R4 리소스·LOINC 매핑(VERIFIED/UNVERIFIED 태그 보존) | [x] | 파일 존재 확인(직접 열람, 2026-07-14). Open items(미해결, 명시적으로 disclosed): Media 리소스(FHIR 차트 첨부) 미연구, CTRS 검증 LOINC 코드 없음, 의료법 시행규칙 제14조 항목 목록 미확보. 근거: `docs/ai/f5_charting_research.md` 전체 |
| T1-F5-DOC-002 | DOC | F5 quick-dev 설계 문서(`docs/ai/f5_quick_dev_plan.md`, writer, 이 미션) — §2 섹션별 데이터소스 매핑표, §3 charting-convention grounding, §4 아키텍처(production/harness 분리 + 12→17 SlotData 매핑), §5 export 사양(markdown/PDF/FHIR + FHIR 매핑표), §6 바인딩 워딩+red line, §7 `EXP-024` 약식 검증 설계, §8 gap, §9 wave plan | [x] | 파일 존재 확인(직접 작성, 2026-07-14). **Review-gate 통과 완료:** `REV-046`(non-blocking-with-conditions) + `CVR-023`(adequate-with-conditions) → `ADR-037`(2026-07-14, 구현 licensed) — F4의 `PLAN-2026-W29-D`(REV-044→CVR-020→ADR-036)와 동일 게이트 순서. **`ADR-037`에 따라 계획 문서 amended:** A8 내러티브 경로 이번 미션 descope(Decision 1), A3 종단 위험 신호 서브섹션 신설(Decision 2), A6 tie-handling(Decision 3), A0 disclaimer 추가(Decision 4), A7 약물 메모(Decision 5), REV-022→REV-044 Criterion 6 인용 수정(Decision 6) — 계획 문서 자체의 §0/self-check amendment record 참조. 근거: `docs/ai/f5_quick_dev_plan.md` 전체, `discussion.md` `ADR-037` |

## 구현 (Implementation — 전 항목 review-gate 통과 전 착수 금지)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F5-DEV-008 | DEV | `src/f5.py`(순수 엔진, zero-LLM, zero file-I/O, A0-A8/B1-B5 typed report model 조립) + `src/schemas/handoff_report.py`(`extra="forbid"`, `is_diagnostic: Literal[False]`, standalone lineage — `SlotData`/`HandoffInput`/`DomainCandidate`/`LongitudinalAnalysisOutput`와 상호 import 금지) | [ ] | `f5_quick_dev_plan.md` §4.1-§4.2. 선행: T1-F5-DOC-002의 review-gate 통과(REV+CVR+ADR) — **완료**(`REV-046`/`CVR-023`/`ADR-037`). **`ADR-037` 반영 필수:** A0 disclaimer 블록(Decision 4), A3 종단 위험 신호 서브섹션(Decision 2), A6 tie-handling(Decision 3), A7 약물 메모(Decision 5)는 이 스키마/엔진 모듈에 포함; A8은 hardcoded `False` 플래그로 서브모델만 존재(Decision 1, 실제 narrative 호출 없음) |
| T1-F5-DEV-009 | DEV | Export 모듈 3종 — `src/services/f5_report.py`(markdown, `f4_report.py` 패턴 미러링) + PDF 렌더러(reportlab, `HYSMyeongJo-Medium`/`HYGothic-Medium` CID 폰트, 기존 F4 PNG 4종 임베드) + FHIR bundle builder(`Bundle(type=document)`, §5.3 매핑표) + §5.3 구조 검증 스크립트. `reportlab` 신규 의존성을 `uv`로 `pyproject.toml`에 추가 | [ ] | `f5_quick_dev_plan.md` §5. 선행: T1-F5-DEV-008. **`ADR-037` 반영:** 3개 export 포맷 전체에서 A0/A3/A6/A7의 amended 콘텐츠(disclaimer, 종단 위험 신호, tie-handling, 약물 메모)를 렌더; A8은 3개 포맷 전체에서 부재-마커만 출력(narrative descoped, Decision 1) |
| T1-F5-DEV-010 | DEV | 내러티브 경로 — `src/services/f5_narrative_adapter.py`(12→17 `SlotData` 매핑, §4.3 표) + `routes/handoff.py`의 max-2-regenerate 루프를 공유 헬퍼로 추출(route와 F5 양쪽에서 재사용, 중복 구현 금지) + feature flag 배선(기본값은 결정 대기 — `f5_quick_dev_plan.md` §8 gap 1 참조) | [ ] | `f5_quick_dev_plan.md` §4.4. **DESCOPED this mission — `ADR-037` Decision 1**: feature flag ships hardcoded `False`, no `HandoffGeneratorAgent`/`EvidenceVerifierAgent` call anywhere this mission; `EXP-024`는 zero LLM calls로 실행. 향후 내러티브 웨이브는 프롬프트 v3 재설계(v2의 강제 12-섹션 템플릿과 hard red line #1 충돌 해소) + 신규 REV/CVR 통과가 선행되어야 착수 가능 — `REV-046`/`CVR-023`의 narrative-scoped 조건이 그 웨이브에 그대로 구속됨. `handoff_generator` v2 프롬프트 pin(`_PROMPT_VERSION="v2"`) 불변 |
| T1-F5-DEV-011 | DEV | 하네스 — `continuous_test.py`에 `run_f5_stage` post-loop 진입점(`STAGE_REGISTRY`의 `Stage("F5", ...)` → `implemented=True`) + 기존 `EXP-023` 산출물을 재생하는 독립 CLI 진입점(신규 세션 실행 없음), `--out`-aware | [ ] | `f5_quick_dev_plan.md` §4.1/§9 Wave 4. 선행: T1-F5-DEV-008~010 |
| T1-F5-DEV-012 | DEV | qa 코드 게이트 — CI-mirror ruff+pytest, `src/f5.py` no-harness-deps 검사(0 `open(`/0 harness import), 12→17 매핑·A3 co-display 로직 mutation-check | [ ] | `f5_quick_dev_plan.md` §9. `CLAUDE.md` 라우팅 규칙 3(실험 실행 전 qa 게이트 필수) — `EXP-024` 착수 전 GATE:PASS 필수 |

## 검증 (Validation — `EXP-024`)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F5-VER-009 | VER | `EXP-024` VP-001 전체 리포트 생성(md+PDF+FHIR, **결정론적 섹션만 — 내러티브 이번 미션 제외, `ADR-037` Decision 1**) — 기존 `EXP-023` VP-001 산출물로부터, 신규 세션 실행 없음, zero LLM calls | [ ] | `f5_quick_dev_plan.md` §7.1. 선행: T1-F5-DEV-012 GATE:PASS |
| T1-F5-VER-010 | VER | `EXP-024` VP-003 전체 리포트 생성(md+PDF+FHIR, **결정론적 섹션만 — 내러티브 이번 미션 제외, `ADR-037` Decision 1**) — A5는 최신 세션(S11)이 아닌 최신 **투여** 세션(S9)을 명시적으로 식별·날짜표기해야 함(`CVR-022` binding condition 3); A3의 종단 위험 신호 서브섹션(`ADR-037` Decision 2)도 동일 S9(27/27, item-9 양성, safety_referral) staleness pointer를 S11 대비 표기해야 함 | [ ] | `f5_quick_dev_plan.md` §7.1. 선행: T1-F5-DEV-012 GATE:PASS |
| T1-F5-VER-011 | VER | Section completeness 검사(Check a) — A0-A8/B1-B5 전 섹션이 렌더되거나 명시적으로 "정보 없음"/"평가 불가"로 표기됨을 확인, 침묵 누락 0건 | [ ] | `f5_quick_dev_plan.md` §7.2. qa 수행 |
| T1-F5-VER-012 | VER | Number traceability 재계산(Check b) — 리포트 내 모든 수치를 원본 아티팩트 필드와 대조, qa 독립 재계산 | [ ] | `f5_quick_dev_plan.md` §7.2. 불일치 발견 시 BUG 파일링, note로 대체 금지 |
| T1-F5-VER-013 | VER | FHIR 구조 검증(Check c) — 필수 필드, `urn:uuid` 참조 해석, entry count 일치, `is_diagnostic`/disclaimer 검증 | [ ] | `f5_quick_dev_plan.md` §5.3/§7.2. `$validate` 서버 호출 아님 — 구조 검증 스크립트만 |
| T1-F5-VER-014 | VER | PDF 렌더 무결성(Check d) — 파일 존재/크기/페이지 수, 한국어 텍스트 렌더링 가독성(텍스트 추출 표본 확인, tofu-box/깨짐 없음) | [ ] | `f5_quick_dev_plan.md` §5.2/§7.2. reportlab CID 폰트 렌더링은 이 검증 전까지 UNVERIFIED |
| T1-F5-VER-015 | VER | Hard red line 준수 검사 — A6 섹션 경계(narrative 미혼입 — `ADR-037` Decision 1로 이번 미션 narrative 자체가 미호출이므로 구조적으로 자명 충족, 단 A6 tie-handling(Decision 3) co-rank 마커는 별도 확인 필요), `similarity_score` 인접부 "확률"/"probability"/"confidence" 부재, 모든 A5 수치 인접부 비-검증 문진 caveat 존재, 3개 export 포맷(md/PDF/FHIR) 전체 | [ ] | `f5_quick_dev_plan.md` §6.1/§7.4 acceptance criterion 6 |
| T1-F5-VER-016 | VER | `schemas/handoff_report.py` HPI-isolation adversarial 테스트 — `test_hpi_isolation.py`/`test_f3_hpi_isolation.py` 패턴 미러링, `SlotData`/`HandoffInput`/`DomainCandidate`/`LongitudinalAnalysisOutput` 상호 import 없음 확인 | [ ] | `f5_quick_dev_plan.md` §4.2/§9 Wave 5 |

## Open / 후속 항목 (licensed, non-blocking — 이번 미션 범위 밖)

| ID | Type | 항목 | 상태 | 선행 조건/비고 |
|---|---|---|---|---|
| T1-F5-DEV-013 | DEV | FHIR `$validate` 서버 측 검증(현재는 구조 검증 스크립트만) | [ ] | `f5_quick_dev_plan.md` §5.3/D3 — future option으로 명시, 이번 미션 범위 아님 |
| T1-F5-DEV-014 | DEV | `Media` 리소스(FHIR 차트 첨부) 연구 및 F5 B5 섹션 통합 | [ ] | `f5_charting_research.md` open item, `f5_quick_dev_plan.md` §5.3 B5 행 — "not researched this session either, by brainstorm or this plan" |
| T1-F5-DEV-015 | DEV | 내러티브 섹션(A8) 프로덕션 기본값(ON/OFF) 결정 | [ ] | `f5_quick_dev_plan.md` §8 gap 2 — 오케스트레이터/사용자 결정 필요, 이 미션은 기본값 `False` 제안만 함 |
| T1-F5-DOC-003 | DOC | 의료법 시행규칙 제14조 필수 기재 항목 목록 확보 | [ ] | `f5_charting_research.md` §1f open item, `f5_quick_dev_plan.md` §8 gap 1 — F5 출력의 법적 의무기록 지위 결정과 연동, brainstorm 후속 조사 필요 |
| T1-F5-DOC-004 | DOC | LOINC 언어-변이 정책(다국어 동일 코드 적용 가능성) 직접 출처 확인 | [ ] | `f5_charting_research.md` §3b — "not independently verified by fetching a LOINC-language-policy page," UNVERIFIED로 남음 |
| T1-F5-DEV-016 | DEV | A7 부서 추천의 `ServiceRequest.performer` 코드화 — `Organization`/`HealthcareService` 리소스 부재 갭 해소 | [ ] | `f5_quick_dev_plan.md` §5.3 — 이 계획에서 신규 식별된 갭(연구 노트 범위 밖), display-only 문자열로 v0 처리, future option |
| T1-F5-DEV-017 | DEV | 내러티브 경로(A8) 향후 웨이브 — `HandoffGeneratorAgent` v2 프롬프트를 v3로 재설계(강제 12-섹션 템플릿이 A0/A3/A6 결정론적 값 및 hard red line #1과 충돌하는 근본 원인 해소, `REV-046` Issue 1 / `CVR-023` Finding 1) 후, 신규 REV+CVR 통과 전까지 `src/services/f5_narrative_adapter.py` 구현·feature flag `True` 전환 금지 | [ ] | `ADR-037` Decision 1(내러티브 경로 이번 미션 descope). 구속 조건 carry-forward: `REV-046` Criterion 0/1/2b(narrative arm), MAY/MUST-NOT 표 row 3/4/6; `CVR-023` binding condition 1, weak-point 34 — moot-by-descope는 이번 미션 `EXP-024`에 한하며, 이 미래 웨이브에는 그대로 구속 |

---

**Linked:** `docs/ai/f5_charting_research.md`, `docs/ai/f5_quick_dev_plan.md`; 레거시 F5 항목(이 미션
으로 변경되지 않음): `docs/ai/checklist_task1.md` `T1-F5-DEV-001~007` / `VER-001~008`. F4 선례:
`docs/ai/f4_checklist.md`, `discussion.md` PLAN-2026-W29-D/REV-044/CVR-020/ADR-036/CVR-021/REV-045/
CVR-022. F5 설계 review-gate(2026-07-14): `discussion.md` `REV-046`/`CVR-023`/`ADR-037`.
