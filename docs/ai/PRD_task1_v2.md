# Task 1 개발 PRD v2: AI 기반 사전문진 Handoff Report 생성

> **Version**: v2.0
> **Created**: 2026-07-06
> **Status**: Active (supersedes `PRD_task1.md` v1.0 — v1은 참조용으로 보존)
> **Owner**: AI Research 팀
> **Parent Document**: [`docs/AI_master_plan.md`](../AI_master_plan.md)
> **Companion Documents**: `checklist_task1.md` (v2), `development_report.md` (append-only 작업 보고)

---

## 0. 문서 개요

### 0.1 목적

본 문서는 Task 1 (AI 기반 사전문진 Handoff Report 생성)의 PRD v2이다. v1이 **계획 문서**였다면, v2는 다음을 반영한다:

1. **F1 as-built 아키텍처**: 2026-07-03 확정된 F1 파이프라인(`apps/ai-server/src/f1.py`)의 실제 구현 구조 — 3-agent 협업, 12 Standard Clinical Slots, 역할 분리 원칙.
2. **각 기능(F0~F5)의 현재 구현/검증 상태**와 v1 계획 대비 변경 사항.
3. **Phase 2 검증·고도화 방향**: 종단(longitudinal) VP 데이터 기반 검증, 기능별 오케스트레이션 파이프라인(f2~f5), 통합 E2E 검증. 상세 계획은 `development_report.md` 참조.

### 0.2 버전 이력

| 버전 | 날짜 | 변경 사항 |
|------|------|----------|
| v1.0 | 2026-06-18 | 초안. 기능 1-1~1-5 개발/검증 체크리스트, API 명세, Agent 구성 정의 |
| v2.0 | 2026-07-06 | F1 as-built 반영: 12 Standard Clinical Slots 표준화, Safety→Slot→Dialogue 역할 분리 파이프라인, Turn 0 safety, 재상담(follow-up) 모드, 4VP 시뮬레이션 검증 결과. F3/F4/F5 구현 완료 상태 반영. 스키마 통일 결정(§7). Phase 2 검증 전략(§9) 추가 |
| v2.1 | 2026-07-07 | 프롬프트 아키텍처 v3 섹션 추가(§11): Fable-5 역설계 원칙 기반 5개 활성 임상 에이전트 프롬프트 재설계 사양(`docs/ai/prompt_redesign_v3.md` v3.1, REV-002 2026-07-07 non-blocking 종결) + 검증 전략(오프라인 프롬프트 테스트 + Safety Matrix SM-07a/b + VP-001~004 라이브 A/B) 요약 |
| v2.2 | 2026-07-08 | §3(F2) 재정의: **DomainInferenceAgent**(RAG 기반 정신건강 영역/진료과 후보 추론) — 2단계 구조(Stage1 코드검색/Stage2 LLM 1회), 입출력 계약, 프롬프트 방침, 검증 전략(골든 라벨 다중-라벨 사전 등록, n≥2/VP, fabrication=0 하드 게이트, VER-004 유예), 보안 조치(VAL-005 옵션(a), ADR-013) 반영. §9.2 게이트 테이블에 G-D-F2(F2 프로덕션 통합) 명시 행 추가(REV-006 조건 4). 구 temporal_retriever/composite scoring/8-쿼리 플래너는 F4 보류로 재배치(삭제 아님, superseded-for-F2 주석). §1.1/§7/§8/§9.4의 관련 표 정합화. 근거: `discussion.md` PLAN-2026-W28-C, REV-006, ADR-013 (사용자 승인 2026-07-08) |
| v2.3 | 2026-07-08 | §3(F2) 상태 갱신: v1 구현·`EXP-004` llm_only 라이브 배치 결과 반영 — 위험≠도메인 절대 규칙(rule 2) 라이브 위반 확인으로 **EXPERIMENTAL/UNCERTIFIED** 처분(`ADR-014`, `REV-008`) 명시, 프롬프트 문구만으로는 라이브 위반을 막지 못함이 실증됐음을 기록(`VAL-006`). v2 remediation 계획(코드 강제 risk-lexicon evidence filter `src/eval/f2_grounding.py` + 프롬프트 v2, ISS-046 공황 관용구 예외 유지) 추가. §3.8 RAG-arm 게이트 갱신: 본 개발 워크스테이션에서 DB 연결 라이브 검증 완료(conductor 확인, corpus 행수 포함) 반영 — "BLOCKED-awaiting-DB"를 "검증 가능(`EXP-005`에서 RAG arm 실행 예정)"으로 갱신, v2 remediation 게이트 통과 전까지 활성화는 별도 보류(`ADR-014`). 근거: `discussion.md` PLAN-2026-W28-E, ADR-014, REV-008, VAL-006 |
| v2.4 | 2026-07-08 | F2 v2 remediation 완료(`PLAN-2026-W28-E`): `EXP-005` 양 arm(llm_only + RAG, 16런) 라이브 재검증 결과 반영 — **llm_only arm 비인증 해제**(`ADR-015` (1), critic REV-010 채택, 조건부: 상시 수동 taxonomy 감사; REV-008 위반 재발 0/42), **RAG arm은 EXPERIMENTAL 잔류**(`ADR-015` (2), 결함 2건: `chunk_id=` source_id 포맷 과잉거부 ~29%·VP-003 RAG 2/2 출력 실패, `VAL-010` 상시화 미비). §1.1 agent 표/§3.6/§8 API 표/§9.2 G-D 행/§9.4 파이프라인 표의 DomainInferenceAgent 상태 표기를 "설계 확정·구현 착수 중/미구현"에서 현행(구현 완료·llm_only 비인증 해제·RAG EXPERIMENTAL)으로 정합화. RAG arm에 대해서는 어디에도 "인증"/"통과"/"개선" 서술을 쓰지 않는다. 근거: `discussion.md` PLAN-2026-W28-E, REV-009/REV-010, ADR-015; `result.md` EXP-005; `error.md` VAL-006(resolved)/VAL-009(open)/VAL-010(open-narrowed)/BUG-016/BUG-017; `development_report.md` DR-007 |
| v2.5 | 2026-07-09 | F2 RAG-arm remediation (`PLAN-2026-W28-G`) completed: `EXP-006` (1 diagnostic + 16 certification runs) reflected. **`BUG-016` resolved** (confirmed live at n=32, `rejected_unknown_source` 0/32 vs `EXP-005`'s 10/35). **`BUG-017`'s diagnosed truncation mechanism resolved** (0/16 `finish_reason="length"` post-fix, `max_tokens` 1536→4096) — but the certification batch's clean VP-003 RAG n=2 deliverable was **not achieved**: VP-003 RAG stays 0/2 interpretable via a new, distinct, undiagnosed schema-validation-failure mode (tracked as new `BUG-019`), and a previously-clean persona (`VP-001/run1`) newly failed with the identical signature. `VAL-010`'s code mitigation (`risk_assessment` excluded from Stage-1 queries) is applied and confirmed live, but does not resolve the underlying concern for VP-003 (`chief_complaint`/HPI remain risk-worded by persona design, reproduced for a 2nd consecutive batch) — the standing query-content audit continues. Critic `REV-012` ruled, and orchestrator adopted as `ADR-016`: **RAG-arm `EXPERIMENTAL/UNCERTIFIED` status is NOT lifted** (2/3 conditions met, 1/3 not met; no partial/per-persona certification licensed). `llm_only` arm's existing certification (`ADR-015` (1)) is unaffected by this batch. §3 status update + §1.1/§3.6 table cells updated; no "인증"/"통과"/"검증됨" wording used for the RAG arm. Source: `discussion.md` PLAN-2026-W28-G, REV-011, REV-012, ADR-016; `result.md` EXP-006; `error.md` BUG-016(resolved)/BUG-017(open)/BUG-019(open, new)/VAL-010(open); `development_report.md` DR-009 |
| v2.6 | 2026-07-09 | `PLAN-2026-W28-H` completed (Tracks A–D): **Track A — RAG HTTP API permanently out of scope, now and at deployment** (`ADR-017`, `REV-013` §2) — `rag_router` unmounted (RETIRE, not DORMANT), `rag_chat.py` refactored in-process, `NS_RAG_API_KEY` unused; §3.8's S1 status updated, `VAL-005` **structurally resolved** (not merely mitigated). **Track B — new "AI 예상질환" (AI-predicted-disease) entity added** (new §3.9): F2 RAG top-5 disease candidates + `similarity_score` (never `probability`/`confidence`), `is_diagnostic: Literal[False]`, structurally isolated from the 12 canonical clinical slots (§2.3) — isolation evidenced by qa's 9-test adversarial suite (`REV-013` §3 condition 1 met); container built now, live auto-population gated on RAG-arm certification (unchanged `EXPERIMENTAL/UNCERTIFIED`, `ADR-016`). `BUG-019` (RAG-arm certification precondition) diagnosed live (`EXP-007`) and root-cause fixed/code-verified (qa `GATE:PASS`) but stays **open** pending a live clean VP-003/VP-001 RAG n=2 re-verification — no RAG-arm "인증"/"통과"/"검증됨" wording is used. `llm_only` arm's certification (`ADR-015` (1)) unaffected. Source: `discussion.md` PLAN-2026-W28-H, ADR-016, ADR-017, REV-012 §6, REV-013; `result.md` EXP-007; `error.md` BUG-019, VAL-005; `development_report.md` DR-010 |
| v2.7 | 2026-07-09 | Documentation-drift correction (writer, editorial only — no functional/status change): §9.4 pipeline table gained a `continuous_test.py` row (Track C harness, `PLAN-2026-W28-H`, module `apps/ai-server/src/continuous_test.py`) — previously mentioned only in checklist `T1-F0-DEV-011`, absent from the PRD. §3.9 now cites the AI-predicted-disease container's module path (`apps/ai-server/src/schemas/ai_predicted_disease.py`, checklist `T1-F2-DEV-011`). Companion checklist fix (not this document): `T1-F2-VER-012` row corrected from stale `[ ]` to `[~]` to match its own line-267 status-update note (3/4 sub-items complete: `T1-F2-DEV-012`/`VER-013`/`DEV-013`; sole remaining scope is the clean VP-003/VP-001 RAG n=2 re-verification, `ADR-016`). |
| v2.9 | 2026-07-10 | **PR #38 (F1 STT+OCR, Seohyunjho) integration merged** (`feat/f1-stt-ocr-integration`@`5bdd379`, true merge onto Master `411d6a1`, PLAN-2026-W28-N): STT (`POST /ai/stt/transcribe`) and OCR (`POST /ai/ocr/parse`) land as **additive input-modality plumbing** feeding TEXT into the existing, unchanged Safety→Slot→Dialogue turn pipeline (§2.10, new) — the certified pipeline itself carries zero verdict regressions (`result.md` EXP-013, 9/9 EXP-002-comparable safety-matrix scenarios match). §1.1 Agent↔code table and §2.9 F1 API status table updated: InputNormalizer/STT-adapter/OCR-adapter rows move from 대기/미구현 to implemented-as-built, each with its own caveat (InputNormalizer's correction feature is a confirmed 100%-conditional no-op, `BUG-020`; both new routes are unauthenticated, `VAL-012`; the STT live vendor path is declared untested, vendor key unprovisioned). §2.8 gap G6 updated accordingly. No "인증"/"통과"/"certified"/"shippable"/"passed" wording is used for the InputNormalizer correction feature or for the merge's overall safety posture (REV-021 binding). Source: `discussion.md` PLAN-2026-W28-N, REV-021; `result.md` EXP-013; `error.md` BUG-020/BUG-021/VAL-012; `development_report.md` DR-014. |
| v2.10 | 2026-07-12 | **F3 재정의 (§4.1 신설, `PLAN-2026-W28-V`/`ADR-031`, 설계 v1, pre-implementation):** 사용자 지시로 F3의 정의가 갈라진다 — §4 원문이 서술하는 스테이트풀 설문 플래너(`OrchestratorAgent.plan_surveys`/`score_and_check_safety`, 라이브 11-state 채팅 플로우)는 **본 미션에서 변경 없이 유지**되며, "F3 v2.1"로 명명한 **별도·병행하는** 신규 경로가 §4.1에 추가된다: F2의 `ai_predicted_disease.recommended_questionnaire`(및 `recommendation_caveat`)가 지목한 설문 1개만 실행 → item bank 기반 문항 제시 → VP-simulator LLM이 in-persona로 점수 선택(F1 `patient_input_fn` 패턴) → `survey_scorer.py` 재사용 결정론적 채점 → VP별/세션별 원장에 기록해 향후 F5가 소비. Item bank v0: PHQ-9/AUDIT-C만 persona 파일 출처 구성개념 라벨로 populated, GAD-7/PHQ-4/WHO-5는 저장소 전역에 문항 원문·응답 anchor가 부재하여 unpopulated(허구 생성 금지) — v1 item bank는 사용자 결정 대기. 비진단 프레이밍 유지(`similarity_score`/설문 결과 모두 확률·진단 아님, `is_diagnostic: Literal[False]`). 이번 갱신은 **설계·문서 반영만**이며 구현·검증은 이 시점에 미착수(구현은 `PLAN-2026-W28-V` step 5, 별도 디스패치) — "구현 완료"/"검증됨" 서술 없음. 근거: `discussion.md` PLAN-2026-W28-V, ADR-031; `docs/ai/f3_quick_dev_plan.md` |

### 0.3 v1 대비 핵심 변경 요약

| # | 영역 | v1 계획 | v2 as-built / 결정 |
|---|------|---------|-------------------|
| 1 | Slot 스키마 | 13-field `SlotData` (chief_complaint, onset, duration, triggers, sleep, ...) | **12 Standard Clinical Slots**가 canonical (§2.3). `SlotData`와의 정합화는 Phase 2 항목 |
| 2 | Slot 추출 주체 | Dialogue agent가 응답 생성 + slot 추출 겸임 | **역할 분리**: ClinicalSlot(추출 전담), Dialogue(응답 전담), Safety(분류 전담), f1.py(오케스트레이션 전담) |
| 3 | Agent 호출 순서 | Safety ∥ ContextRetrieval 병렬 → Dialogue → ClinicalSlot(optional batch) | 매 턴 **Safety → Slot → Dialogue** 순차 (Slot을 Dialogue보다 먼저 실행하여 최신 slot 기반 질문 생성) |
| 4 | Turn 0 | 미정의 | AI 인사 → 환자 첫 응답에 대해 **Safety + Slot 즉시 실행**, crisis 시 즉시 종료 |
| 5 | Safety 구조 | rule + LLM dual path (개요 수준) | **C 방식 확정**: Rule engine = 1차 스크리닝(부정 문맥 감지 포함) → LLM = 최종 판정, LLM 장애 시 rule 결과 fail-safe |
| 6 | 세션 종료 | 8-15턴 도달 / crisis / handoff 준비 | 질문 가능 슬롯(8개) 전부 수집 시 **자동 종료(handoff ready)** + 반복 감지(2회 연속) 종료 + crisis 종료 |
| 7 | 재진 처리 | prior handoff 주입(개요) | **명시적 follow-up 모드**: `--followup-from`으로만 활성화. `generate_handoff_from_result()` → prior_handoff + prior_slots 주입. 종단 검증의 기반 |
| 8 | 프롬프트 | 상세 지시 중심 | **간결화 확정**: dialogue 228→54줄, safety 208→58줄, clinical_slot 157→67줄. 하드코딩 금지, PromptLoader 로드 |
| 9 | 검증 방법 | VER 항목 나열 | 4VP × Patient LLM(K-EXAONE) 시뮬레이션 체계 확립. Phase 2: **종단 multi-session 프로토콜** (§9) |

### 0.4 개발 범위 / 제외 범위

v1과 동일 (`apps/ai-server/`, `apps/api/`, `docs/ai/`; Task 0/2/3, Frontend, 인프라 제외).

---

## 1. ID 체계 및 Agent 매핑

ID 형식 `T1-Fn-{TYPE}-{SEQ}` 및 기능 번호(F0~F5)는 v1과 동일하다. **ID는 전역적으로 증가하며 재사용하지 않는다.** v2 체크리스트(`checklist_task1.md`)는 v1 ID를 승계하고 Phase 2 신규 항목을 이어 붙인다.

### 1.1 Agent ↔ 코드 매핑 (as-built)

| Agent | 코드 모듈 | 상태 | 소비 기능 |
|---|---|---|---|
| Orchestrator (state machine) | `agents/orchestrator.py` (11-state) | 구현 완료 | F0, 프로덕션 `/ai/chat/respond` |
| F1 Pipeline Orchestrator | `src/f1.py` (경량, LLM 미호출) | 구현 완료 | F1 시뮬레이션/검증 |
| SafetyClassifier | `agents/safety_classifier.py` | 구현 완료 | F1, F3(위험 문항 연동) |
| Dialogue | `agents/dialogue.py` | 구현 완료 | F1 |
| ClinicalSlot | `agents/clinical_slot.py` | 구현 완료 | F1, F3 |
| InputNormalizer | `agents/input_normalizer.py` | **구현 완료 · live-as-of-merge**(PR #38, `feat/f1-stt-ocr-integration`@`5bdd379`, 2026-07-10 — `f1.py`가 모든 환자 입력을 이 agent에 먼저 통과시킴). **Correction 기능은 확인된 100%-conditional no-op**(`BUG-020`, open, major — ISS-039 프롬프트/스키마 불일치, 교정 시도 14/14 fallback, fail-safe는 검증됨). "인증"/"통과" 표현 미사용 | F1 |
| SentimentAnalyzer | `agents/sentiment_analyzer.py` | 구현 완료 | F1(미연동), F4 |
| DomainInferenceAgent | `agents/domain_inference.py` | **구현 완료 · llm_only 경로 비인증 해제**(`ADR-015`, 상시 수동감사 조건부) · **RAG 경로 EXPERIMENTAL 잔류**(§3.8, reaffirmed 2026-07-09 `ADR-016` — `BUG-016` resolved, `BUG-017`'s truncation mechanism resolved, VP-003 RAG clean re-verification NOT MET, tracked as `BUG-019`) | F2 |
| TemporalSummary | `agents/temporal_summary.py` | 구현 완료 | F4 |
| HandoffGenerator | `agents/handoff_generator.py` | 구현 완료 | F5 |
| EvidenceVerifier | `agents/evidence_verifier.py` | 구현 완료 | F5 |
| STT adapter | `adapters/skt_ak_stt.py` + `agents/stt.py` | **구현됨**(PR #38, `feat/f1-stt-ocr-integration`@`5bdd379`) — batch 모드만, streaming은 HTTP 501. **무인증**(`VAL-012`, major, non-blocking). **라이브 벤더 경로는 이 통합 미션에서 미검증**(`SKT_A_X_API_KEY` 비어있음 확인, `result.md` EXP-013 Task 4) | F1 |
| OCR adapter | `adapters/solar_document_parse.py` + `agents/ocr.py` | **구현됨**(PR #38, `feat/f1-stt-ocr-integration`@`5bdd379`). **무인증**(`VAL-012`, major, non-blocking; `UPSTAGE_API_KEY`는 이미 등록되어 있어 STT와 달리 dependency fail-fast는 발현되지 않음). 이 통합 미션에서 라이브 벤더 호출 검증은 수행되지 않음 | F1 |

**이중 오케스트레이션 주의:** F1 검증용 `f1.py`와 프로덕션용 `agents/orchestrator.py`(11-state)가 병존한다. 두 경로의 slot 스키마·세션 종료 조건·coverage 기준 정합화는 Phase 2 항목이다 (§7, §9).

---

## 2. 기능 1-1 (F1): 자율 대화 기반 문진 — As-Built

### 2.1 개요

가상/실제 환자와의 자율 대화를 통해 12 Standard Clinical Slots를 수집하는 멀티에이전트 파이프라인. 2026-07-03 4VP 시뮬레이션은 이슈 0건으로 보고되었으나, **2026-07-06 통합 감사(QA/Critic/Architecture, `development_report.md` DR-001)에서 slot 값의 상당수가 프롬프트 예시 echo(날조)로 확인되어 "안정적 slot 수집 통과" 판정은 무효화되었다.** 아키텍처(역할 분리, 위기 대응 흐름)는 유효하며, Phase 2에서 grounding 수정 후 재검증한다.

**핵심 특징:**
- Patient LLM(K-EXAONE)과 Clinical Agents(Solar Pro3)의 완전 정보 격리
- 매 턴 Safety → Slot → Dialogue 3-agent 협업, 역할 분리 철저
- 질문 가능 슬롯 전부 수집 시 자동 세션 종료 (handoff ready)
- 명시적 follow-up 모드로 재상담(종단) 시나리오 지원

### 2.2 확정 아키텍처 (per-turn)

```
Patient Message
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│                  f1.py (Orchestrator — LLM 미호출)        │
│                                                         │
│  Step 1: SafetyClassifier                               │
│    Rule 스크리닝(부정 문맥 감지) → LLM 최종 판정          │
│    crisis(CTRS 1-2) → CRISIS_RESPONSE(109/119) → 종료    │
│                                                         │
│  Step 2: ClinicalSlot (매 턴, Dialogue보다 먼저)          │
│    12 Standard Slots만 merge (비표준 키 차단)             │
│                                                         │
│  Step 3: Dialogue (최신 filled_slots + safety 결과 사용)  │
│    공감 1문장 + 미수집 슬롯 유도 질문 1개                  │
│                                                         │
│  Step 4: History 갱신 + Coverage 계산 + 종료 판정         │
│    질문 가능 슬롯 완수 → 종료 / 반복 2회 → 종료           │
└─────────────────────────────────────────────────────────┘
```

**역할 분리 원칙 (위반 시 회귀로 간주):**

| 역할 | 담당 | 금지 사항 |
|------|------|----------|
| 위험도 분류 (CTRS) | SafetyClassifier | 응답 생성, 슬롯 추출 |
| 슬롯 추출 | ClinicalSlot | 응답 생성, 위험도 판단 |
| 응답 생성 | Dialogue | 슬롯 추출, 위험도 판단, coverage 계산 |
| 세션 제어·coverage | f1.py | LLM 호출 |

### 2.3 12 Standard Clinical Slots (canonical 스키마)

| No | Slot Key | 수집 방법 | Essential | 질문 가능 |
|----|----------|-----------|:---:|:---:|
| 1 | `encounter_metadata` | System auto | - | X |
| 2 | `chief_complaint` | Dialogue 유도 | O | O |
| 3 | `history_of_present_illness` | Dialogue 유도 | O | O |
| 4 | `past_psychiatric_history` | Dialogue 유도 | - | O |
| 5 | `medical_history` | Dialogue 유도 | - | O |
| 6 | `personal_social_history` | Dialogue 유도 | - | O |
| 7 | `family_history` | Dialogue 유도 | - | O |
| 8 | `substance_use_history` | Dialogue 유도 | - | O |
| 9 | `mental_status_exam` | 관찰 기반 (질문 금지) | O | X |
| 10 | `risk_assessment` | Dialogue 유도 | O | O |
| 11 | `clinical_assessment` | 대화 종료 후 자동 | - | X |
| 12 | `treatment_plan` | 의료진 영역 | - | X |

- **Coverage** = filled essential slots / 5 (`ESSENTIAL_SLOT_KEYS`). 4VP 검증 시 80% (mental_status_exam은 text-only에서 제한적).
- **추출 규칙**: 언급 없으면 null / 환자 표현 보존 / 진단명 금지 / **부정 응답도 유의미한 값으로 수집** ("없어요" → "진단받은 신체 질환 없음") / 비표준 키는 `_KEY_ALIASES` 매핑 후 `ALL_SLOT_KEYS` 필터로 차단.
- 이 12-slot 스키마가 **canonical**이다. F5 `SlotData` 등 타 스키마와의 정합화는 §7 참조.
- **AI 예상질환(AI-predicted-disease) 엔티티는 이 12개 슬롯에 포함되지 않는다** — F2(§3.9, 신규)가 산출하는 별도의 비진단·비임상 필드이며, 구조적으로 격리되어 있다(§3.9 참조). 어떤 clinician 작성 슬롯에도 병합되지 않는다.

### 2.4 Safety 아키텍처 (as-built)

```
Rule Engine (키워드 스크리닝 + 활용형 변형 + 부정 문맥 감지)
     ├── rule_level = none → LLM 독립 분류
     └── rule_level = high/critical → flagged keywords를 LLM에 전달
                                        ▼
                                   LLM 최종 판정 (문맥 우선, 시제 확인,
                                   증상 악화 보고 ≠ 자살 위험)
                                        ▼
                          final = LLM 결과 (LLM 장애 시 Rule 결과 fail-safe)
```

- CTRS 1-2 → crisis protocol: 일반 문진 즉시 중단, 109/119 안내.
- **CTRS 3 + 자살/자해 category → Safety Probe 모드 (v2 신규 설계, ISS-035)**: 즉시 종료 대신 구조화 안전 탐문을 강제 삽입하고, 탐문 응답 재분류 결과에 따라 CTRS 2 승급(위기 종료) 또는 grounded 위험 기록 후 문진 지속. 세션 위험 latch(floor CTRS 3) + handoff 권고 문구 검증 연동. 상세: `development_report.md` DR-002, 체크리스트 T1-F1-DEV-022/023.
- 키워드 사전은 한국어 활용형 변형 포함 (ISS-003/004: "손목을 그었", "약을 많이 먹") 및 복약 순응 표현 오탐 제거 (ISS-013: "약을 먹고 있어요" ≠ 과다복용).
- 위기 키워드 recall 회귀 테스트 유지 (`test_safety_keyword_recall.py`, 13/13 critical).
- 프롬프트 하드코딩 금지 — `PromptLoader`로 `prompts/safety_classifier/v1.system.md` 로드.

### 2.5 세션 수명주기 규칙

1. **Turn 0**: AI 인사 → 환자 첫 응답에 Safety + Slot 즉시 실행. crisis 시 Turn 0 종료.
2. **Crisis**: 어느 턴이든 CTRS 1-2 → `CRISIS_RESPONSE` 반환 + 세션 종료. crisis=True인데 crisis response 없는 케이스 0건이 검증 기준.
3. **자동 종료**: 질문 가능 슬롯 8개 전부 수집 && turn >= 3 → handoff ready 종료. 마지막 턴에서 새 질문 금지(요약 모드).
4. **반복 방지**: 동일 AI 응답 2회 연속 → 세션 종료 + 에러 기록. `_build_slot_context`에 이전 3턴 질문 요약 + 공감 표현 사용 금지 목록 주입.
5. **Safety/Dialogue 실패**: 해당 턴에서 세션 중단 + errors 기록 (fail-closed).

### 2.6 재상담 (Follow-up) 모드 — 종단 데이터 기반

- `--followup-from {VP-ID | conversation.json}`으로만 활성화 (persona의 `visit_type=revisit`만으로는 활성화되지 않음 — 과분류 방지).
- 이전 세션 결과 → `generate_handoff_from_result()` → prior_handoff 텍스트 + prior_slots 주입.
- Patient LLM persona에도 이전 상담 기록을 주입하여 "호전/악화/유지"를 자연스럽게 반영.
- 첫 인사에 이전 주호소 요약 (`_summarize_prior_handoff`) 포함.
- **현재 상태: 구현 완료, 검증 0건.** 종단 검증(F1 follow-up + F4/F5 연계)은 Phase 2 최우선 항목 (§9).

### 2.7 시뮬레이션·산출물 체계

- 실행: `cd apps/ai-server && .venv/bin/python -m src.f1 --persona VP-00N --max-turns 10 [--followup-from VP-00N]`
- 산출물: `docs/ai/simulation_results/{VP-ID}/{VP-ID}_{ts}_conversation.json` + `_report.md` + `_checklist.md`
- Patient LLM: K-EXAONE (`tests/simulation/patient_llm.py`), Clinical: Solar Pro3 (fallback: K-EXAONE → SKT A.X K1)

### 2.8 F1 검증 현황 및 잔여 격차

**2026-07-03 보고 수치 (2026-07-06 감사로 evidence 무효화 — 아래 G0 참조):**

| VP | Turns | Crisis | 보고 Coverage | 감사 후 grounded coverage (추정) |
|----|-------|--------|----------|-------|
| VP-001 (초진 경증) | 3 | No | 80% | ~40% (essential 2/5) |
| VP-002 (첫 상담) | 3 | No | 80% | ~40% |
| VP-003 (초진 중증) | 0 | Yes (T0, CTRS 2) | 80% | 슬롯 근거 2/9 — 0턴 세션이 80%로 보고된 것 자체가 지표 결함 |
| VP-004 (첫 상담) | 3 | No | 80% | ~40% |

유효하게 검증된 것: 위기 감지·109/119 안내·즉시 종료(VP-003 2회 재현), 매 턴 Safety 호출, 비표준 slot 키 0건, 역할 분리 아키텍처.

**격차 목록 (Phase 2 검증 대상, 상세 근거는 development_report.md DR-001):**

| # | 격차 | 심각도 |
|---|------|--------|
| **G0** | **Slot 날조(fabrication)**: clinical_slot 프롬프트 예시 JSON이 최종 slot 값으로 verbatim 유입. VP-003(자살 사고 표현)에 `risk_assessment: "자살/자해 사고 명시적 부인"` 기록 — 안전 치명. 날조 fill이 조기 종료·coverage 80%의 직접 원인 | **critical** |
| G1 | follow-up(재상담) 경로 검증 0건 — 종단 데이터 미수집. followup handoff 생성기 자체 결함 (min-CTRS fallback, 비표준 8-section) | critical |
| G2 | VP당 n=1 단일 런 — 동일 야간 연속 런에서 상반된 risk_assessment 산출 등 불안정성 실증 | major |
| G3 | 3턴 조기 종료 런만 존재 — 장기 세션(10턴+) 품질 미검증 (00:54 VP-004 10턴 런은 4회 반복 루프 포함) | major |
| G4 | 중간 턴 위기 전환, 간접·부정 문맥, CTRS 3+자해사고(VP-004 spec) 파이프라인 수준 검증 없음 | critical |
| G5 | slot 값의 발화 근거(grounding)·persona ground-truth 대비 충실도 정량 평가 없음 | major |
| G6 | STT/OCR 입력 경로 — **2026-07-10 갱신: 구현됨**(PR #38 통합, §2.10 참조)이나 (a) 무인증(`VAL-012`), (b) STT 라이브 벤더 경로 미검증, (c) InputNormalizer correction 기능 no-op(`BUG-020`) 3개 잔여 결함 보유. ISS-011(벤더 계약)은 해소 — SKT A.X/Upstage 어댑터 코드 자체는 이제 존재한다 | major (하향 아님 — 잔여 결함 3건이 severity를 유지시킴) |
| G7 | SentimentAnalyzer가 f1.py 루프에 미연동 (F4 입력 생성 불가) | minor |
| G8 | 검증된 경로(f1.py) ≠ 프로덕션 경로(orchestrator/chat) — 프로덕션 경로는 현재 부팅 불가·slot 누적 불능·구 핫라인(1393) 사용 | critical |

### 2.9 F1 API 상태

| 경로 | 상태 | 비고 |
|------|------|------|
| `python -m src.f1` (CLI 시뮬레이션) | 운영 중 | 검증 표준 경로 |
| `POST /ai/chat/respond` | 구현 (orchestrator 경유) | f1.py와의 동작 정합성 검증 필요 (§7) |
| `POST /ai/stt/transcribe`, `POST /ai/ocr/parse` | **구현됨**(2026-07-10, PR #38 통합) | 라우트·agent·adapter 존재, `main.py`에 마운트됨. 무인증(`VAL-012`); STT는 라이브 벤더 경로 미검증(`SKT_A_X_API_KEY` 비어있음); OCR도 이 미션에서 벤더 호출 검증 없음. 상세: §2.10 |

### 2.10 STT/OCR 입력 경로 — as-built (PR #38 통합, 2026-07-10, `PLAN-2026-W28-N`)

**통합 개요:** `add/f1-stt-and-ocr`(Seohyunjho, 6 commits)가 true merge로 `feat/f1-stt-ocr-integration`@`5bdd379f6eed9f340a9878edd02bbc0f073fd04a`(부모: Master `411d6a1` + PR #38 head `15423baf`)에 통합됐다. 근거: `discussion.md` PLAN-2026-W28-N, REV-021; `result.md` EXP-013; `error.md` BUG-020/BUG-021/VAL-012; `development_report.md` DR-014.

**아키텍처 불변 조건 (binding, ADR-012/ADR-018 — 이 통합은 이를 변경하지 않는다):** STT/OCR/InputNormalizer는 §2.2/§2.4의 기존 Safety→Slot→Dialogue 파이프라인에 **텍스트를 공급하는 부가적(additive) 입력 plumbing**일 뿐이다 — grounding filter, Safety Probe 상태 기계, crisis 처리, `session_ctrs` 등 기존 파이프라인 로직은 이 병합으로 변경되지 않았다. 라이브 실측(`result.md` EXP-013): merge된 `f1.py`에서 실행한 11-scenario safety matrix가 `EXP-002`/`EXP-003` 베이스라인 대비 **비교 가능한 9개 시나리오 전부에서 0건의 verdict 회귀**를 보였다(SM-08b는 이번이 v2의 최초 데이터 포인트로 실패하나, 이는 v2 자체가 ADR-010 rule 5를 구현한 적이 없다는 기존에 알려진 사실의 재확인이며 이 병합이 만든 회귀가 아니다 — `BUG-007`/`ADR-010`/`ADR-012` 계열).

**데이터 흐름 (f1.py, `_run_simulation`):**
1. `audio_inputs`가 주어지면 세션 시작 시점에 STTAgent가 오디오를 일괄 전사한다(batch 모드만; streaming은 미구현, HTTP 501).
2. `ocr_documents`가 주어지면 OCRAgent가 문서를 파싱하고, 결과가 `result.ocr_documents`에 저장되면서 대화 컨텍스트에 system 메시지로 주입된다 — 이 경로는 turn 1부터 진입하며, turn 0의 slot 추출에는 별도 `turn0_history`가 쓰여 OCR 컨텍스트가 배제된다(REV-021 §1 확인).
3. (STT 전사든 직접 텍스트든) **모든 환자 발화는 InputNormalizerAgent로 먼저 수렴한 뒤 Safety/Dialogue로 전달된다** — §2.4의 Safety 아키텍처 자체는 입력 소스와 무관하게 동일하게 작동한다.

**잔여 결함 (병합 자체를 막지 않음, PR 본문/사용자 공지 필수 — 완화 표현 금지):**

| 결함 | 심각도 | 상태 |
|---|---|---|
| `BUG-020` — InputNormalizer correction 기능이 확인된 100%-conditional no-op(ISS-039 프롬프트/스키마 불일치) | major | open |
| `BUG-021` — `.env`의 상대경로 `PROMPTS_BASE_DIR`이 unset-only auto-correction guard를 무언으로 우회, 전 prompt-driven agent가 fallback 프롬프트로 저하 (병합 이전부터 Master 자체에 존재 확인, REV-021) | **critical** | open |
| `VAL-012` — `/ai/stt/transcribe`, `/ai/ocr/parse` 무인증, 유료 벤더 API 프록시(비용/DoS) | major | open, non-blocking |
| STT 라이브 벤더 경로 | — | **미검증으로 명시(declared untested)** — `SKT_A_X_API_KEY` 비어있음 |

**표현 규율(binding, REV-021):** InputNormalizer correction 기능이나 이 병합의 전반적 안전 posture에 대해 "인증"/"통과"/"certified"/"verified"/"shippable"/"passed" 표현을 사용하지 않는다 — 이 통합은 이미 인증된 안전 파이프라인에 대한 회귀 검증(integration-verification gate)이지, 재인증 이벤트가 아니다.

---

## 3. 기능 1-2 (F2): RAG 기반 정신건강 영역/진료과 후보 추론 — DomainInferenceAgent

**상태(당초, `PLAN-2026-W28-C` 승인 시점 기준): 설계 확정, 구현 착수(developer 병행 진행 중 — 본 절 작성 시점 기준 구현 완료 아님). Task 1 잔여 기능 중 유일하게 구현 미착수였던 기능.** — 아래 갱신 참조.

**상태 갱신 (2026-07-08, `PLAN-2026-W28-E` 착수 — v1 결과 및 비인증 처분 반영):** domain_inference v1은 구현이 완료되었고 `llm_only` arm 라이브 배치(`EXP-004`, VP-001~004 n=2, 8런)까지 실행되었다. 그러나 critic 증거 리뷰(`REV-008`)에서 §3.5의 프롬프트 절대 규칙(rule 2, "위험 표현을 domain confidence의 근거로 사용하지 않는다")이 라이브에서 위반된 것이 확인되어 사전 등록된 롤백 트리거가 발동했다(`ADR-014`). **v1은 현재 EXPERIMENTAL/UNCERTIFIED로 코드베이스에 남아 있으며, RAG-arm 활성화와 §9.2 G-D-F2 게이트 진행이 v2 remediation 통과 전까지 차단된다.**

- **위반 내용:** 규칙은 8/8 배치 중 2/8 런(VP-003의 양쪽 run)에서 위반됨(`REV-008`) — VP-003 2/2 라이브 런에서 수동적 자살사고(passive SI) 발화("살고 싶지 않아요" 원문)가 `depression` 도메인의 `evidence[].quote`로 그대로 인용되어 코드 화이트리스트를 통과·채택됨. 엄격 substring 기준 4건, 이 프로젝트 자체의 기존 passive-SI/burdensomeness 어휘 분류(`BUG-007`/`ADR-010`)를 적용하면 ~9-10건(`REV-008`).
- **핵심 교훈(프롬프트만으로는 불충분함이 라이브 입증):** 프롬프트 rule 2는 텍스트로는 항상 존재했고, REV-006 조건 3에 따라 이를 검증할 오프라인 "부정 fixture"(`test_f2_grounding.py::TestRiskNotDomainNegativeFixture`)도 준비되어 있었다. 그러나 REV-007 재검토에서 이 fixture는 갭을 폐쇄하는 테스트가 아니라 갭이 열려 있음을 실증하는 테스트였음이 드러났고(`VAL-006`), EXP-004 라이브 배치에서 그 갭이 실제로 발생했다(`REV-008`) — 이 프로젝트에서 "프롬프트 문구만으로 구조적 보장을 강제"하려다 실패한 네 번째 반복 사례다(`BUG-007`/`BUG-010`/`REV-004` issue #1과 동일 계열).
- **fabrication=0 게이트와는 독립:** §3.7의 근거-화이트리스트 검사(fabrication=0 하드 게이트)는 이 배치에서 위반 없음(`EXP-004`, 0/32 evidence entries) — risk≠domain 규칙 위반은 이와 독립적인 별도의 절대 규칙 위반이다.
- **VP-004 공황 관용구는 별개의 정당한 클래스로 확정:** VP-004의 "죽을 것 같고" 류 공황/응급실 회고 인용은 `anxiety` 도메인의 정당한 근거로 판정되어 제외되었다(`ISS-046` 선례, `REV-008` 항목 (c)) — v2 remediation에서도 이 예외는 유지한다(아래 참조).

**v2 remediation 계획 (`PLAN-2026-W28-E`, 진행 중):** domain_inference v1은 최초 버전이라 되돌릴 이전 안전 버전이 없다(`ADR-014` (2)). 대신 다음 조치로 재검증한다:
1. **코드 강제 risk-lexicon evidence filter** — `src/eval/f2_grounding.py`에 evidence quote가 프로젝트의 passive-SI/자해/burdensomeness 어휘를 포함하면 해당 evidence를 수용 거부(reject)하는 코드 레벨 검사를 추가한다. `rag_chunk` evidence에 이미 적용된 "프롬프트만으로는 불충분 → 코드 레벨 백스톱" 원칙(REV-006 조건 1)을 risk≠domain 규칙에도 동일하게 적용하는 것이다.
2. **프롬프트 v2 개정** — v1은 디스크에 보존, 규칙 문구를 강화한다.
3. **라이브 재검증** n≥8(위반 재발 0 확인) + critic 재심(REV-008 사유 해소 여부, ADR-014 비인증 해제 판정 — 판정 명시 전까지 "인증/통과" 문구 금지).
4. **ISS-046 공황 관용구 예외 유지** — risk-lexicon evidence filter는 공황/응급실 회고 관용구(예: "죽을 것 같고")를 별도 클래스로 취급해 오차단하지 않도록 설계한다(위 VP-004 판정과 동일 기조); 관용구 오차단 여부는 qa/critic 사전리뷰(1g) 항목이다.

**상태 갱신 (2026-07-08 (2), `PLAN-2026-W28-E` 완료 — `ADR-015`):** 위 v2 remediation 계획이 실행 완료됐다. `EXP-005`(양 arm, VP-001~004 n=2, 16런)에서 llm_only arm은 REV-008 위반 재발 0/42(critic REV-010, accepted evidence 42건 전수 재감사)로 확인되어 **비인증 해제**되었다(`ADR-015` (1), 조건부: 매 라이브 배치 상시 수동 taxonomy 감사). top-1/top-3는 7/8(`EXP-004`의 8/8 대비 1건 하락은 필터가 100% 위험-근거였던 VP-003/run2 후보를 정당하게 탈락시킨 결과 — critic이 intended-cost로 프레이밍, 회귀 아님). **RAG arm은 이번 배치가 첫 라이브 가동이었고, EXPERIMENTAL로 잔류한다**(`ADR-015` (2)) — risk≠domain 위반은 없었으나(RAG accepted 인용문 25건 중 taxonomy 매치 0건), 신규 결함 2건(`chunk_id=` 포맷 과잉거부 ~29%, VP-003 RAG 2/2 LLM 출력 실패)과 `VAL-010`(risk_assessment-as-query 채널)의 상시 완화 미비가 EXPERIMENTAL 유지 사유다. 상세: `docs/ai/development_report.md` DR-007.

**Status update (2026-07-09, `PLAN-2026-W28-G` completed — `ADR-016`):** The RAG-arm remediation mission targeted the three defects `ADR-015` (2) named as the certification path. Per critic `REV-012`'s authoritative evidence review of `EXP-006` (17 runs: 1 diagnostic + 16 certification, llm_only + RAG, VP-001~004 n=2 each): **`BUG-016`** (`chunk_id=` source_id prefix echo) is resolved — confirmed live at n=32 (`rejected_unknown_source` 0/32, vs `EXP-005`'s 10/35 ~29%). **`BUG-017`'s diagnosed truncation mechanism** (`max_tokens=1536` ceiling) is resolved — the W4a diagnostic run confirmed it (`finish_reason="length"`, `completion_tokens==1536` exactly), and after the fix (`max_tokens` raised to 4096, single-variable) 0/16 certification-batch runs show `finish_reason="length"`. **But VP-003 RAG remains 0/2 interpretable via a new, distinct, undiagnosed failure mode** (Pydantic schema-validation failure on syntactically-valid JSON, `finish_reason="stop"`, not truncation — tracked as new `BUG-019`), and a previously-clean persona (`VP-001/run1`) newly failed with the identical signature — RAG-arm interpretability moved to **5/8 clean this batch (3/8 LLM-output failures: `VP-001/run1` new + `VP-003` both), down from `EXP-005`'s 6/8 clean / 2/8 failed**. `VAL-010`'s code mitigation (`risk_assessment` excluded from `_STAGE1_QUERY_SLOTS`) is applied and confirmed live, but the underlying concern is not resolved for VP-003: `chief_complaint`/HPI remain risk-worded by persona design and reproduce the same retrieval-bias pattern for a 2nd consecutive batch — VP-003 RAG has never shipped an interpretable result to check, so the standing `retrieval_meta.queries` audit continues on every future batch. The risk≠domain rule held live at n=16 this batch (0/49 accepted quotes match the broader taxonomy, including 14 active-defense interceptions); fabrication remained 0 in both arms (llm_only 0/17, RAG 0/32). **Critic `REV-012` ruling, adopted as `ADR-016`:** "RAG 잔류 EXPERIMENTAL — 2/3 인증조건 충족(BUG-016 해소, 진단된 절단 메커니즘 해소), 1/3 미충족(VP-003 RAG 클린 재검증)." A partial/per-persona certification is explicitly not licensed (`REV-012` §4). The `llm_only` arm's existing certification (`ADR-015` (1)) is unaffected — this batch's llm_only replay (top-1/top-3 7/8, intended-cost, same `VP-003/run2` miss as `EXP-005`) served only as the like-for-like comparison baseline. Detail: `docs/ai/development_report.md` DR-009.

**Status update (2026-07-09, `PLAN-2026-W28-H` completed — Tracks A–D, `ADR-016`/`ADR-017` unaffected for the RAG-arm certification question):** `PLAN-2026-W28-H` continued the F2 RAG-arm work without altering the certification verdict above. `BUG-019` (the sole remaining item on `ADR-016`'s certification path) was diagnosed live: `EXP-007` (4 runs, VP-003/VP-001 RAG) reproduced the schema-validation-failure symptom in 2/4 calls and captured field-level `ValidationError` detail, grounding a root-cause hypothesis (`RetrievedChunk.source_type`'s DB-table-origin value colliding with `DomainEvidence.source_type`'s schema enum, via the prompt's chunk-listing format). Developer implemented a targeted fix (`_normalize_source_type_collision`, coercing the colliding value before Pydantic validation); qa code-verified it (mutation-checked, diff-scope confirmed to 2 files, suite 768 passed) — **`BUG-019` stays open**, pending a live, clean VP-003 (and VP-001) RAG n=2 re-verification passing the secondary taxonomy audit; this diagnostic run does not itself satisfy that condition. The RAG arm remains **EXPERIMENTAL/UNCERTIFIED** (`ADR-016`, unchanged); the `llm_only` arm's certification (`ADR-015` (1)) is unaffected. Separately, this mission permanently descoped the RAG HTTP API (§3.8) and added the non-diagnostic "AI 예상질환" entity (§3.9) — both out of scope for the certification question itself. Detail: `docs/ai/development_report.md` DR-010.

v1 계획(TemporalRetriever agent, composite scoring, 8-쿼리 플래너, `POST /ai/temporal/retrieve`)은 **F2 범위에서 폐기가 아니라 F4(종단 검색)로 재배치한다** — superseded-for-F2 주석 처리이며 삭제하지 않는다(§3.6). F2는 아래 설계로 재정의한다.

### 3.1 명칭 및 범위 결정

- **신규 registry key**: `domain_inference` (agent 명 **DomainInferenceAgent**).
- **신규 라우트**: `POST /ai/domain/infer` (§3.6).
- 명칭 재정의 근거: checklist F2 헤더 자체가 "RAG 기반 정신건강 영역 추론"이므로, 종단/시간축 검색을 함의하던 TemporalRetriever보다 신 명칭이 F2의 원 의도(영역/진료과 후보 추론)에 부합한다.

### 3.2 아키텍처 — 2단계, LLM 1회 호출

```
F1 세션 산출물 (12 slots + CTRS + crisis + is_first_visit)
     │
     ▼
Stage 1: 코드 검색 (LLM 미호출)
  rag/retrieval.py 프리미티브 재사용
  chief_complaint/HPI/risk 슬롯 → rag.qa + case_card top-k (ontology 제외 — 아래 구현 정합 주석 참조)
  DB 실패 시 → mode=llm_only 강등 (PRD v1 §3.3 LLM-only 우선 원칙 승계)
     │
     ▼
Stage 2: DomainInferenceAgent LLM 호출 (1회)
  strategy=benchmarked — Solar Pro3 1차 / K-EXAONE 2차
     │
     ▼
런타임 근거-화이트리스트 검사 (grounding.py의 F2판)
  evidence.source_id ∈ 실제 반환 청크 ∪ F1 발화
  rag_chunk evidence: chunk_ids 멤버십 + quote↔청크 본문 어휘 대조
  (REV-006 조건 1 — source_id 멤버십만으로는 불충분)
```

`f2.py` 검증 파이프라인(f1.py 패턴): 입력 로드 → Stage1 → Stage2 → 근거-화이트리스트 검사 → 산출물(`{VP}_{ts}_domain_inference.json` + report.md, 재현 메타) → 콘솔 요약. **`orchestrator.py`/신규 라우트의 프로덕션 통합은 §9.2 G-D-F2 게이트로 명시적으로 보류**(ISS-029 "검증 경로≠프로덕션 경로" 재발 방지; 스키마 통일 T1-F0-DEV-007 미완이 선행조건).

**구현 정합 주석 (VAL-007, 2026-07-08):** 위 Stage 1 목록은 원 계획(PLAN-2026-W28-C C-2) 대비 실제 구현(`apps/ai-server/src/rag/retrieval.py::retrieve_domain_chunks()`)과 한 가지 차이가 있다 — **ontology 소스는 현재 Stage 1 검색에 포함되지 않는다**(`case_card`/`qa`만 조회). 코드 주석(`retrieval.py:191`)의 근거: ontology의 `follow_up` 그래프는 F2가 아니라 채팅 실시간 근거제시(chat-realtime-grounding) 전용 설계라는 판단. 이 근거 자체는 타당하나, critic(REV-007)이 지적한 대로 이 축소는 계획 검토(critic REV-006)·사용자 승인 단계에서 명시적으로 노출되지 않았다(VAL-007, 문서-구현 drift). 코드 자체는 정상 동작하며 결함이 아니다. 본 항목은 사후 문서 정합화이며, ontology 소스 재도입 여부는 별도 재검토 대상으로 남긴다.

### 3.3 입력 계약

| 구분 | 필드 | 필수 |
|---|---|---|
| 필수 | F1 `final_slots` (12종, §2.3 canonical) | O |
| 필수 | `session_ctrs` | O |
| 필수 | `crisis_triggered` / `crisis_turn` | O |
| 필수 | `is_first_visit` | O |
| 선택 | `turns[].patient_message` | - |
| 선택 | `prior_handoff` | - |
| 선택 | `probe_events` | - |
| 선택 | F3 `scale_scores` | - |

### 3.4 출력 계약

```json
{
  "domain_candidates": [
    {
      "domain": "anxiety | depression | alcohol | substance | trauma | sleep | psychosis | other",
      "confidence": 0.0,
      "evidence": [
        {"source_type": "rag_chunk | utterance", "source_id": "string", "quote": "string"}
      ],
      "recommended_surveys": ["string"]
    }
  ],
  "department_candidates": [
    {"department": "string", "reason": "string", "domain_ref": "string (optional)"}
  ],
  "summary": "string (evidence 밖 신규 임상 주장 금지)",
  "retrieval_meta": {
    "mode": "rag | llm_only",
    "chunks_returned": 0,
    "chunk_ids": ["string"],
    "queries": ["string (optional)"]
  },
  "additional_questions": ["string (optional)"],
  "model_used": "string",
  "prompt_version": "string",
  "latency_ms": 0.0
}
```

- `domain` enum 8종은 v1 정의(`PRD_task1.md:474`)를 승계한다.
- `domain_candidates` ≤ 3개, 후보당 `evidence` ≥ 1개 (빈 배열=스키마 위반).
- `retrieval_meta.chunk_ids`는 **전체 보존**(감사 재현용) — 일부 샘플링 금지.
- `summary`는 `evidence`에 없는 신규 임상 주장을 포함해서는 안 된다(프롬프트 절대 규칙, §3.5).

### 3.5 프롬프트 방침

- v3 12원칙(§11.1) 전면 적용 — 기존 프롬프트의 orphan retrofit이 아니라 **신규 작성**.
- placeholder-only 예시(P7) — handoff_generator급 echo 위험으로 취급.
- 예산: ≤3,000자 / ≤90줄.
- **DR-005 경계 caveat 반영**: 위험 표현(자살/자해 관련 어휘)은 domain confidence의 근거로 사용 금지 — 위험 판정은 Safety 파이프라인 소관이며 F2는 이를 재판정하지 않는다.
- 하한표(calibration floor table) 패턴 미도입 — `BUG-010`(safety v3 과대상향 회귀)의 원인 패턴을 설계 단계에서 회피(REV-006 긍정 소견 (e)).
- 후보 ≤3개.

### 3.6 신규 라우트 / 구 API 처리

| API | 상태 | 비고 |
|---|---|---|
| `POST /ai/domain/infer` | 신규 (검증 파이프라인 산출용) | registry key `domain_inference`. **llm_only 경로는 비인증 해제됨**(`ADR-015`, 2026-07-08, 상시 수동감사 조건부), **RAG 경로는 EXPERIMENTAL**(§3.8, reaffirmed 2026-07-09 `ADR-016` — RAG-arm certification NOT lifted, `BUG-019` new precondition). 프로덕션 통합(orchestrator.py 연동)은 §9.2 G-D-F2 게이트로 보류 |
| `POST /ai/temporal/retrieve` (v1 계획) | **F4 보류 (superseded-for-F2, 삭제 아님)** | composite scoring, 8-쿼리 플래너와 함께 F4(종단 검색) 기능으로 이관 대상. TemporalRetriever 명칭도 F4 문맥에서만 유효 |

### 3.7 검증 전략

**오프라인(5종):** 출력 스키마(후보당 evidence≥1, 빈 배열=위반), 근거-추적성 유닛(fixture 기반 accept/reject), 프롬프트 단정문(placeholder/절대규칙/예산/경계지시), `llm_only` 폴백 경로, department-derives-from-domain.

**라이브(DB 연동):**
- VP-001~004 F1 기록을 입력으로 사용, **n≥2/VP(권장 n≥3)**.
- **골든 라벨 사전 등록(필수 선행조건)**: 페르소나 파일에 domain 필드가 존재하지 않는다(brainstorm 검증됨). `data`가 라이브 실행 **전에** DATASET 항목으로 다중-라벨 매핑을 저작하고(예: VP-001 = {anxiety, sleep} — 페르소나 §2 "불안감과 수면 문제" 직접 병기), `critic`이 승인한다(사후 합리화 차단). 라벨은 페르소나 전문에서 blind 도출하며 `rag_chat.py`의 비공식 태그(`PERSONAS` dict의 단일-라벨 코멘트)는 참고하지 않는다 — 해당 코멘트는 F2 목적으로 검토된 적이 없고 VP-004의 공존 진단(주요우울장애 의심+공황 발작)을 누락하는 등 불완전함이 확인되었다(REV-006 이슈 #2).
- **VER-004(top-1 70%/top-3 90%) 비승계**: "사전 정의 10개 임상 시나리오"가 저장소에 실존하지 않음(grep 0건 확인, REV-006 Summary 긍정 소견 (a)) — 조작화된 적이 없는 v1 초안치이다. 첫 배치는 서술적 보고만 사용한다("n=4×2, top-1 X/8" — 비율 주장 아님). 70%/90%는 임상 검토 시나리오셋 확보 또는 관측 ≥12건 누적 전까지 **유예 목표**로 둔다.
- **레이턴시**: `latency_ms`를 매 런 캡처하고, p95를 v1 SLA(`llm_only` p95<3,000ms, RAG 활성 p95<5,000ms — `PRD_task1.md:497-499` 승계)와 대비하여 **서술 보고**한다(표본이 작아 정식 pass/fail 판정은 licensed되지 않는다).
- **DB 프리플라이트 실패 처리**: 실패 시 RAG-모드 검증 런은 **중단·보고**한다(silent `llm_only` 강등 금지). `llm_only` 런은 별도 라벨로 진행 가능하다.

**하드 게이트:** 근거 요약 grounding 감사 — utterance evidence는 `has_lexical_evidence()` 재사용, rag_chunk evidence는 `chunk_ids` 대조에 더해 **quote↔청크 본문 어휘 대조**(REV-006 조건 1 — source_id 멤버십만으로는 불충분, 실행 산출물에 청크 본문 또는 대조 가능한 텍스트를 보존) — **fabrication = 0**.

**롤백 기준:** fabrication>0 / 위험 표현이 domain confidence 근거로 사용된 사례 / 고아 department → 프롬프트 버전 롤백 + 정직 보고(PLAN-2026-W28/W28-B 규칙 승계).

**게이트 순서:** critic 설계 리뷰(완료, REV-006) → `data` DATASET(골든 라벨) 저작 + critic 승인 → developer 구현 → qa(오프라인 스위트 + rule-by-rule 프롬프트 검사) → DB 연결성 프리플라이트 → experiment-tracker 라이브 → critic 증거 리뷰 → writer DR-006 → filemanager 커밋 2건.

### 3.8 보안 조치 (VAL-005, ADR-013)

developer의 읽기전용 스캔(PLAN-2026-W28-C C-1)에서 3건의 보안 격차가 확인되었고, critic이 그중 S1을 즉시 `VAL-005`로 파일링했다(현재 상태 노출 — 계획 단계 이연 불가 판정). 사용자는 "검증 및 보안 절차는 VAL-005 보안 조치 방향처럼 신경쓰자"고 결정했고(2026-07-08), `ADR-013`이 처분을 확정했다:

| # | 격차 | 처분 (ADR-013) | 상태 |
|---|---|---|---|
| S1 | `rag_chat.py:33` 공인 IP:포트 리터럴 + `:36-42` 환자 UUID 4종 하드코딩 — `POST /ai/rag/grounding` 무인증이라 UUID가 사실상 접근 자격증명. git 이력 2커밋, `origin/Master` 포함 | **옵션 (a) 채택**(2026-07-08): rag 라우터에 env 기반 bearer/API-key 인증 적용(타 라우트 무영향) + `rag_chat.py` 하드코딩 IP/UUID → env/인자화. **갱신(2026-07-09, `PLAN-2026-W28-H` Track A, `ADR-017`): 처분이 인증(mitigation)에서 RETIRE(제거)로 변경됐다** — RAG는 현재·배포시 모두 in-process only이며 HTTP로 서빙할 계획이 없다는 사용자의 영구·범주적 결정에 따라, 완화가 아니라 노출면 자체의 제거를 선택했다(critic `REV-013` §2 판정). **재갱신(2026-07-09, `PLAN-2026-W28-I` TASK 4, `ADR-019`): RETIRE(retired-not-deleted)에서 전면 삭제(FULL DELETION)로 격상됐다** — 사용자 직접 지시("auth.py 파일을 안쓸거면 삭제하면되는거아니냐? RAG API 관련 기능 모두 없애라")에 따라 `src/rag/route.py`/`auth.py`/`tests/rag/test_route_auth.py` 세 파일을 **파일시스템에서 완전히 삭제**했다(retired-not-deleted 상태를 대체, 파일 자체가 트리에 부재 — critic `REV-015` Part B가 정적 코드 증거로 독립 확인) | **구현 완료·검증됨(전면 삭제, 2026-07-09 최신 상태)** — `src/rag/route.py`/`auth.py`/`tests/rag/test_route_auth.py` **삭제됨**(파일 부재, `Glob apps/ai-server/src/rag/*.py` → `embed.py`/`ontology.py`/`crypto.py`/`retrieval.py`만 존재; `Glob apps/ai-server/tests/rag/*.py` → `test_crypto.py`/`test_retrieval.py`만 존재). `main.py`에 `rag_router` 참조 0건, `POST /ai/rag/grounding` → 404(라우트 자체가 존재하지 않음 — 재마운트할 코드가 없음), `/health` → 200, rag-접두 경로 0건 마운트, qa 스위트 760 passed(768에서 삭제된 8개 route-auth 테스트만큼 감소, 그 외 전부 그린). `NS_RAG_API_KEY`/`NS_RAG_DEV_MODE`/`NS_RAG_URL`은 `.env.example`+`.env` 어디에도 없음(grep 0건, 공개 IP 리터럴 포함 제거). `UPSTAGE_API_KEY`(임베딩, 별개 키)는 무영향·필수 유지, in-process RAG core(`retrieval.py`/`embed.py`/`crypto.py`/`ontology.py`)는 무접촉. **`VAL-005`는 구조적으로 해소**(무인증 엔드포인트 자체가 소멸 — 정책적 완화가 아니라 라우트 객체 자체의 부재, RETIRE-언마운트보다 strictly stronger). **역전 시 안전장치(강화됨):** 향후 RAG를 HTTP로 서빙하려면 (a) 영구 descope 번복을 승인하는 신규 ADR + (b) bearer 인증을 재활성이 아니라 **처음부터 재구현**(재활성할 코드 자체가 없음) + (c) 신규 `VAL-005`급 보안 리뷰 — 마운트 전 3가지 모두 필수. **RAG는 개발 단계와 배포 단계 모두 영구 in-process 로컬 workstation 기능이다 — HTTP로 서빙되는 일은 없으며 앞으로도 없다**("현 단계"/"당분간" 류의 hedging 없음). 근거: `discussion.md` ADR-017, ADR-019, REV-013 §2, REV-015 Part B; `error.md` VAL-005; `development_report.md` DR-010 §2, DR-011 §2 |
| S2 | `retrieval.py`의 `_dec()`가 `situation_encrypted`를 실제 복호화하지 않음(`crypto.py`에 decrypt 미구현) — 암호화 바이트가 LLM 프롬프트로 유입 가능 | 본 미션 범위 포함: crypto.py decrypt 구현 + retrieval.py 복호화 적용. `ENCRYPTION_KEY` 부재 시 해당 필드 제외 + 명시 로깅(암호문 LLM 유입 금지) | **구현 완료·검증됨** (`T1-F2-SEC-002`) — `src/rag/crypto.py::decrypt_str`(실 AES-GCM), `retrieval.py::_dec()` 실패 시 필드 제외, `tests/rag/test_crypto.py` 7 cases |
| S3 | `src/rag/` 유닛 테스트 0건 | 본 미션 범위 포함: 모킹 기반 유닛 테스트 신규 | **구현 완료·검증됨** (`T1-F2-SEC-003`) — `tests/rag/` 신규 모킹 테스트 26건 |

**정정 (VAL-007, 2026-07-08):** 위 3건은 이전 버전에서 "구현 대기"로 기재되어 있었으나, 2026-07-08 구현 미션(PLAN-2026-W28-C, `development_report.md` DR-006)에서 실제로 구현·qa GATE:PASS·critic REV-007 확인까지 완료됐다 — 코드는 이미 완성돼 있었고 본 문서의 상태 기재만 갱신이 지연됐던 것을 여기서 정정한다. 위 3건 중 유일하게 미결로 남은 것은 아래 git 이력 정리(옵션 (b))뿐이다.

**미결 (옵션 (b) 미승인):** git 이력 재작성(하드코딩 IP/UUID가 이미 `origin/Master`에 커밋된 상태를 소급 제거)은 **미승인** — 조율된 force-push 결정이 필요하며 미결로 유지한다. 인증 도입 후 위험도는 하락하나(무인증 상태 해소), 이력상 노출 자체는 잔존한다. **갱신(2026-07-09):** Track A RETIRE 처분(위 표 S1 갱신 참조) 이후 라이브 노출면은 완전히 소멸했으나, 이 git 이력 항목 자체는 별개로 여전히 미결이다. **재갱신(2026-07-09, 전면 삭제 이후):** 라우트/인증 코드 자체가 파일시스템에서 삭제되어 라이브 노출 위험은 추가로 하락했으나(재마운트할 코드 자체가 없음), 이 git 이력 항목(과거 커밋에 남은 IP/UUID 리터럴)은 append-only 이력의 성격상 코드 삭제와 무관하게 여전히 별개의 미결 항목이다.

**라이브 검증 게이트 (당초, `PLAN-2026-W28-C`/`ADR-013` 시점 기준):** `DATABASE_URL`이 본 환경에 구성될 때까지 RAG-모드 배치는 BLOCKED-awaiting-DB; `llm_only` arm은 라이브 실행 가능(silent 강등 보고 금지 — REV-006 조건 6).

**갱신 (2026-07-08, `PLAN-2026-W28-E`) — RAG-arm 차단 해제:** 본 개발 워크스테이션에서 외부 포트 개설이 완료되어 DB 연결이 라이브로 검증되었다(conductor 확인: `SELECT 1` OK, pgvector 익스텐션 설치 확인, corpus 행수 `rag.case_card` 1,248 / `rag.qa` 1,789 / `rag.symptom` 40 / `rag.disease` 26 — [`PLAN-2026-W28-E` 기재 conductor 검증치]). 이에 따라 "BLOCKED-awaiting-DB" 상태는 **검증 가능(verifiable)**으로 갱신된다 — `EXP-005`에서 RAG arm 라이브 실행이 예정되어 있다. 단, DB 연결성 확보와 v2 remediation 게이트 통과는 독립적인 조건이다: v2 remediation(§3 상태 갱신 참조)이 qa/critic 게이트를 통과하기 전까지는 RAG-arm 활성화 자체가 `ADR-014` (1)에 의해 별도로 보류된다.

### 3.9 "AI 예상질환" (AI-predicted-disease) 엔티티 — 비진단·구조적 격리·라이브 실채움 SHIPPABLE (v2.8 갱신, `PLAN-2026-W28-K`)

**요구:** F2 RAG top-5 disease 후보 + similarity score를 슬롯 목록에 추가한다. 값은 **결정지원 메타데이터이며 진단이 아니다**(사용자 원문: "AI가 진단하면 안된다는 규정").

**스키마:** `AIPredictedDiseaseCandidate`(disease + `similarity_score`) 목록 + `AIPredictedDiseaseOutput`(`is_diagnostic: Literal[False] = False`, 고정 `disclaimer_ko`) — 모듈: `apps/ai-server/src/schemas/ai_predicted_disease.py`(checklist `T1-F2-DEV-011`). `f2.py`의 **sibling key**로 배선된다 — 기존 `domain_candidates` 출력에 병합되지 않고 나란히 존재한다.

**구조적 격리(§2.3 canonical 12-slot과 별개):** `REV-013` §3 판정 — 브레인스톰 설계 노트(`papers/notes/ai-predicted-disease-hpi-isolation-design.md`)의 3계층(타입/콜그래프/프롬프트) 중 타입·프롬프트 계층은 as-specified로 확인됐으나, `AgentInput.extra`와 `state.conversation_history` 두 채널이 원 설계에서 누락돼 있었다(critic 발견). qa가 이 두 채널을 명시적으로 커버하는 adversarial 테스트(`tests/test_hpi_isolation.py`, 9건, 3 클래스)를 추가로 작성해 전건 통과했고(mutation 검증으로 non-vacuous 확인) — **`REV-013` §3 조건 1이 충족**되어 "구조적으로 격리(structurally isolated)"라는 서술이 이제 licensed된다. 이 서술의 근거는 정확히 이 9개 테스트다(3개 스키마 타입의 typed field + `extra` 버킷 + `conversation_history` append 호출 지점) — 향후 모든 코드 경로에서 절대 누출 불가하다는 전지적 보장이 아니다. **미결(non-blocking):** 설계 노트의 타입 계층(`extra="forbid"` on `SlotData`/`HandoffInput`/`ClinicalSlotOutput`)은 이번 웨이브에 구현되지 않았다 — 9개 테스트는 이것 없이도 전건 통과(mutation 검증됨)하므로 오늘의 격리 주장을 약화하지 않으나, 향후 무관한 우발적 kwarg 버그에 대한 defense-in-depth 항목으로 developer 후속 작업에 남긴다. **Addendum (v2.8, `PLAN-2026-W28-K`):** the qa isolation suite has since been extended and re-run against a genuinely **live-populated** container (real disease name/score/`source_id`/`quote`, not only the Wave-3 synthetic marker) — `TestHPIIsolationPopulatedPath` (mutation-checked, qa `VAL-011` code gate item 1) and, independently, critic's own artifact-level re-derivation on real `EXP-011` shipped candidates (`REV-018` §2). Both confirm zero leakage into `history_of_present_illness` or any other clinical slot on the live-populated path — closing `REV-016`(c) condition 2's own binding requirement that this specific check be run before "structurally isolated" wording could be extended to the populated case.

**라벨링(`REV-013` §4, binding):** 필드명·문서·UI 어디서도 `similarity_score`("유사도 점수") 외 라벨 금지 — `probability`/`확률`/`가능성(%)`/`confidence` 전부 금지. `is_diagnostic=Literal[False]`(타입 자체, 런타임 기본값 아님 — qa가 `model_fields["is_diagnostic"].annotation`으로 확인). top-5 후보 간 softmax 정규화 없음 — 각 `similarity_score`는 독립적이고 `[0,1]` 범위.

**Population state (v2.8, `PLAN-2026-W28-K`): SHIPPABLE, live-populated via path1 (`ADR-020`).** `mode` now transitions `experimental_unpopulated`→`rag_live` on a live run — the RAG arm is certified (`ADR-018`, superseding the `ADR-016` EXPERIMENTAL disposition this section previously cited) and this mission shipped live population on top of that certified arm. Disease candidates are derived **code-side**, from data F2's Stage 1 already retrieved this run — no second retrieval call, no prompt change: each already-retrieved `rag.case_card`/`rag.qa` chunk is matched against the existing symptom-keyword logic (`_detect_symptoms`), then joined against `rag.disease`/`rag.symptom`/`rag.disease_symptom` (the existing 26-disease ontology graph, `_followup`'s query shape, widened per-chunk). Each candidate carries the winning chunk's own retrieval `similarity_score` (never LLM-guessed, never an overlap count), plus `source_id`+`quote` provenance (`ADR-020` condition 2); top-5, ranked by score, never padded; MAX-not-sum aggregation across chunks (no softmax-adjacent drift, `ADR-020`/§3.9 라벨링 above); a legitimate 0-candidate outcome is reported honestly, not treated as an error. Every candidate's evidence is checked against this project's risk-lexicon taxonomy against the **full source-chunk text**, not only the extracted quote — any candidate whose sole matched chunk is risk-lexicon-flagged is DROPPED (not clipped/redacted), mirroring `domain_candidates`' own "no evidence, no candidate" discipline.

**The leak-and-fix arc, reported plainly:** the first live populated-path batch (`EXP-009`, `k=3`) and the k-sweep (`EXP-010`, `k∈{2,3,5}`) both shipped disease candidates citing chunks (`case_card:664`, `case_card:563` — VP-003) that the same run's own `domain_candidates` pipeline independently flagged as risk-lexicon-matched. Root cause: the initial risk-lexicon check tested only a ±40-character quote window around the matched symptom term, not the full chunk. Critic (`REV-017`) ruled this **NOT SHIPPABLE (blocking)** and reopened `VAL-011`. Fix (`f2.py:465`): the check now additionally tests the full chunk text. Re-verification (`EXP-011`, clean, n=2/VP, `k=3`): 0/33 shipped candidates cite a risk-lexicon-flagged chunk; both prior leak chunks are retrieved again this batch but neither is cited or shipped; benign personas still ship legitimate candidate sets (no over-blocking). Critic re-review (`REV-018`) independently re-derived this evidence and ruled the populated path **SHIPPABLE**.

**Mandatory caveats (`REV-018` §2) — every user-facing statement about this entity must carry all five, in substance:**
1. `similarity_score` is a RAG cosine-similarity signal between the retrieved *chunk* and the Stage-1 *query* — NOT a patient-to-disease similarity, NOT a calibrated probability (a two-hop proxy).
2. `VAL-010` (`error.md`) remains **OPEN** — VP-003's `chief_complaint`/HPI queries are risk-worded by persona design, reproducing for a 6th consecutive live batch; this section's shippability ruling does not imply `VAL-010` is resolved.
3. **Single-batch evidence** — one clean re-verification batch (`EXP-011`, n=2/VP, `k=3`) following a documented prior leak on the identical mechanism. The standing secondary taxonomy audit AND the new chunk-level audit continue on every future populated-path batch, unconditionally — not a one-time gate.
4. **Provenance-enforcement fragility** (non-blocking, `VAL-011` qa item 3 / `REV-017` §5): a candidate cannot currently ship without provenance only because of an incidental upstream guarantee elsewhere in `f2.py`, not a designed invariant of the population function itself — adequate to ship today; a hardening follow-up remains open.
5. `is_diagnostic: Literal[False]` — this is a retrieval-derived candidate list, **not a diagnosis**; no diagnosis language on any surface.

**Wording discipline:** the populated path is **shippable** (licensed, `REV-018`) — it is not a new **certification**. The RAG arm's own certification (`ADR-018`) already exists and is confirmed unaffected by Track B (no prompt change, `domain_candidates` shape unchanged). "인증"/"certified" stays reserved for `ADR-018`'s RAG-arm/`llm_only`-arm dispositions; Track B's population is shippable-with-caveats on top of that certified arm.

**Enhancement #4 (evidence-source-type reporting, `ADR-021`):** the code-side half — surfacing `rag_chunk`/`utterance`, `case_card`/`qa` provenance already persisted in the artifact — is shipped, zero prompt change, no re-certification triggered (`REV-016`(a)). The RAG-aware-prompt half remains **deferred**: editing `domain_inference/v2.system.md` would produce a new prompt version that does not inherit `ADR-018`'s certification, and no re-validation batch was run this mission — no license is granted for that half.

**k-sweep (enhancement #1, `EXP-010`):** no `k∈{2,3,5}` value dominates top-1/top-3 (within LLM sampling variance); latency and accepted-evidence volume rise monotonically with `k`; risk-lexicon rejection does not fall with `k`. **Recommendation: keep the certified default `k=3`** — ratified by critic `REV-017` §4.

**Disease-source path (unchanged decision, `ADR-020`):** path1 (chunk-derived, code-side, above) is implemented and shipped. Path2 (`rag.disease` `embedding vector(4096)` + migration `0008_*` + backfill for the existing 26 rows) remains a filed DB-handoff action item, gated on the external DB engineer (`development_report.md` DR-010 §6 item 2, restated DR-012 §8) — not reached this mission. leakage 감사는 `DATASET-005` 애든덤(2026-07-09, `data`) 참조 — 4/6 항목이 design/provenance review로 종결, 2/6 미결(쿼리측 순환성은 F2 자체의 기존 미결 항목을 상속, ontology-graph 경로의 "Ada" 분류체계 출처는 신규 미결, path2 미채택으로 무영향).

근거: `discussion.md` PLAN-2026-W28-K, RES-001, REV-016, ADR-020, ADR-021, REV-017, REV-018; `result.md` EXP-009/EXP-010/EXP-011; `error.md` VAL-011(closed, final)/VAL-010(open); `development_report.md` DR-010 §3/§6, DR-012.

---

## 4. 기능 1-3 (F3): 구조화된 사전문진 설문

> **재정의 고지 (2026-07-12, `PLAN-2026-W28-V`, `ADR-031`) — 아래 원문(v2.0 작성 당시 서술)에 대한 주석, 삭제 아님:** 아래 서술은 실제로는 `OrchestratorAgent.plan_surveys`/`score_and_check_safety`(`src/agents/orchestrator.py:592,638`)로 구현되어 `src/routes/chat.py`의 라이브 11-state 채팅 플로우에 배선되고 `tests/test_survey_safety_integration.py`로 회귀 커버되는 **설문 플래너**를 가리킨다. **이 코드 경로는 본 미션에서 변경되지 않는다** — 아래 서술은 유효한 as-built 기록으로 유지된다. 사용자가 `ADR-031`로 지시한 새 "F3"는 이 플래너를 대체하지 않는다: F2가 이미 추천한 설문 1개만을 실행하는 **별도·병행하는** 제2의 경로이며, 라이브 채팅과는 다른 호출부(오프라인/F2 기반 검증 하네스)를 서비스한다. **superseded되는 것은 오직 "F3라는 라벨이 곧 이 설문 플래너를 뜻한다"는 전제뿐이다** — 신규 경로는 §4.1("F3 v2.1")에 별도 정의한다.

**상태: 구현 완료. Scoring unit test 통과. E2E(F1 대화 → 설문 선택 → 채점 → Safety 연동) 검증은 합성 입력 기반 — 실데이터 E2E는 Phase 2.**

- ClinicalSlot agent: F1과 공유 (12 Standard Slots, §2.3). `POST /ai/slots/extract` 운영.
- Survey Scoring: rule-based 모듈 (PHQ-9, GAD-7, PHQ-4, WHO-5, AUDIT-C), LLM 미사용. `POST /ai/survey/score` 운영. Boundary unit test 통과 (T1-F3-VER-001~002).
- Survey Planner: Orchestrator routing에 통합 (PHQ-4 스크리닝 → subscale 기반 PHQ-9/GAD-7 추가, 음주 표현 → AUDIT-C, CTRS 1-2 → 설문 중단).
- 위험 문항 연동: PHQ-9 문항 9 >= 1 → Safety re-evaluation 트리거 (T1-F3-VER-004 통과).

**v2 유의점:** F1 자율 대화는 척도 점수를 생성하지 않는다. 종단 검증(F4)에 필요한 scale_scores는 **F3 설문 실행을 통해서만 생성**되므로, 종단 프로토콜에 VP별 설문 응답 시뮬레이션(persona의 PHQ-9/GAD-7 기준값 사용)을 포함해야 한다 (§9.3).

### 4.1 재정의: F3 v2.1 — F2 기반 설문 실행 (F2-driven questionnaire administration, `PLAN-2026-W28-V`/`ADR-031`)

**상태: 설계 v1 완료 (pre-implementation) — 구현 전. 어떤 검증·구현 완료 서술도 포함하지 않는다.** 설계 원문: `docs/ai/f3_quick_dev_plan.md`(근거 기록은 `discussion.md` `PLAN-2026-W28-V`/`ADR-031`).

**정의:** F3 v2.1은 F2가 추론한 상위 질환 후보의 `ai_predicted_disease.recommended_questionnaire`(및 `recommendation_caveat`)가 지목한 설문 **1개만**을 실행하는, §4 원문의 설문 플래너와는 **별도·병행하는** 경로다. subscale 기반 추가 설문·음주 표현 트리거·CTRS 기반 중단 등 플래너 로직은 포함하지 않는다(그 로직은 §4 원문이 서술하는 플래너의 소관으로 남는다).

- **트리거 (F2→F3):** F2 산출물(`<vp_id>_<ts>_domain_inference.json`)의 `ai_predicted_disease.recommended_questionnaire`가 `None`이면 "설문 미지시"로 0문항 실행(척도를 임의로 선택하지 않음); 해당 척도의 item bank가 `populated=False`(v0 기준 GAD-7/PHQ-4/WHO-5)면 "item bank 미구축"으로 0문항 실행(loud 로그+아티팩트 기록, 침묵 스킵 아님); 그 외에는 item bank 순서대로 전 문항 실행. **교차참조(`ADR-032`(3)):** 이 트리거가 참조하는 `ai_predicted_disease.candidates[0]`은 `error.md`의 `VAL-014`(RAG 후보 face-validity — VP 간 변별력 저조)가 미결로 플래그한 동일 필드이며, F3의 선택 적합성 판정은 F2 산출물을 있는 그대로(AS-GIVEN) 중계했는지만 확인할 뿐 `VAL-014` 자체를 재판정하지 않는다.
- **실행:** `src/f3.py::administer_survey(scale_name, answer_fn, item_bank, ...)` — 프로덕션 코드 자체는 LLM 호출 0회인 결정론적 엔진이며, VP-simulator LLM(K-EXAONE, harness 측)이 in-persona로 점수를 선택하는 `answer_fn` 주입 지점만 가변(`f1.py`의 `patient_input_fn` 패턴과 동형).
- **채점:** `src/scoring/survey_scorer.py`를 재사용·무변경 — 총점/중증도 밴드는 코드에서 결정론적으로 산출되며 LLM이 산출하지 않는다.
- **기록 (F5 소비 대상):** VP별·세션별 원장(`<persona_id>_session_ledger.json`)에 `"f3"` 하위 객체로 기록되도록 설계됨 — 아티팩트/원장 스키마 상세는 `docs/ai/f3_quick_dev_plan.md` §4/§5.
- **Item bank v0 (허구 생성 금지 원칙 준수):** PHQ-9/AUDIT-C만 persona 파일 출처의 구성개념(construct) 라벨로 v0 populated(`provenance="construct-labels-v0, persona-file-sourced, non-validated"`); GAD-7/PHQ-4/WHO-5는 저장소 전역에 문항 원문·응답 anchor가 부재하여 v0에서 unpopulated로 남는다(`docs/ai/f3_quick_dev_plan.md` §2). v1 item bank(검증된 문항 원문)는 사용자 결정 대기(같은 문서 §2.3).
- **비진단 프레이밍 (유지):** 설문 결과는 의사결정 지원 자료이며, F2의 `similarity_score`와 마찬가지로 어떤 산출물도 확률/진단으로 서술하지 않는다(`is_diagnostic: Literal[False]` 스키마 강제).
- **안전 배선 비변경:** PHQ-9 문항 9 양성은 원장의 `safety_referral` 필드로 **기록만** 되며, `OrchestratorAgent.score_and_check_safety`나 어떤 safety 라우트도 호출하지 않는다 — §4 원문의 위험 문항 연동(트리거)과는 다른, 별도의 기록 전용 필드다.
- **범위 제외 (이번 설계 반영 시점):** safety 재평가 배선, GAD-7/PHQ-4/WHO-5 문항 원문(v1 item bank), `src/`/`tests/` 코드 변경 — 별도 구현 디스패치(`PLAN-2026-W28-V` step 5) 소관이며 본 문서 갱신 시점에는 미착수.

근거: `discussion.md` PLAN-2026-W28-V, ADR-031; `docs/ai/f3_quick_dev_plan.md`.

---

## 5. 기능 1-4 (F4): 종단적 상태 추론

**상태: 구현 완료. 합성 입력 기반 검증 통과 (VP-002 호전 / VP-004 악화 / 초진 unknown / 모순 감지). 실제 F1 세션 연쇄 데이터로는 미검증.**

as-built 반영 사항:
- Direction 판정: **majority vote** (2/3 도메인 개선 → improved), worsened 우선 안전 규칙 유지 (ISS-016 수정).
- all-unknown → `unknown` 반환 (ISS-014 수정: 빈 iterable에 대한 `all()` 함정 제거).
- Sentiment polarity 비교 부동소수점 보정 (ISS-015).
- Plot-ready 시계열 출력 (날짜별 척도 점수 + CTRS + 이벤트).

**Phase 2 핵심**: F1 follow-up 세션 연쇄(§9.3)에서 생성된 **실제** prior/current 데이터(수집 slot 변화, 설문 점수 변화, sentiment 추이)로 direction 판정을 재검증한다. Evidence 필수 원칙(evidence 없는 판정 → unknown) 준수를 EvidenceVerifier 수준에서 확인한다.

---

## 6. 기능 1-5 (F5): Handoff Report 생성

**상태: 구현 완료. 4VP handoff 생성 + EvidenceVerifier 검증 통과 (합성/단일 세션 입력 기반). 12-section 완전성 자동 검증 및 evidence citation coverage 테스트 통과.**

as-built 반영 사항:
- 12-section 템플릿 강제 + `section_completeness` 필드.
- Evidence registry + dangling reference 검증, CTRS-action 일관성 검증.
- 재생성 루프: passed → 반환 / regenerate → 최대 2회 / reject → HTTP 422, 소진 시 `requires_human_review=True`.
- PDF/JSON 듀얼 출력.
- `SlotData` 필드 누락 수정 (ISS-018): history_of_present_illness, psychosocial_context, substance_use, energy 추가.
- Handoff 위험도 = 세션 내 최대 심각도 (risk cap 수정), scale_scores + risk_events 인계 시 데이터 손실 수정 (2026-07 초 merge).

**Phase 2 핵심**: 실제 F1 세션 → (F3 설문) → (F4 종단) → F5 handoff의 **전체 체인 E2E** 검증. Section 9(종단 변화)가 실데이터로 채워지는지, Section 12 evidence가 실제 대화 원문으로 추적되는지 확인 (§9.5).

---

## 7. 스키마 통일 결정 (v2 신규)

**결정: 12 Standard Clinical Slots (§2.3)가 Task 1 전체의 canonical slot 스키마이다.**

근거: F1 검증 통과의 기반 스키마이며, 임상 문진 표준 구조(주호소/현병력/과거력/가족력/사회력/물질사용/MSE/위험평가/평가/계획)와 1:1 대응한다.

파생 조치 (Phase 2 체크리스트 항목으로 관리):

| # | 조치 | 대상 |
|---|------|------|
| S1 | `schemas/handoff.py::SlotData`를 12-slot 기준으로 정합화 (또는 명시적 양방향 매핑 테이블 도입) | F5 |
| S2 | `agents/orchestrator.py` `_build_handoff_input()` 등 프로덕션 경로의 slot 키를 canonical로 통일 | F0 |
| S3 | F2 DomainInferenceAgent 입력 계약(§3.3, 12-slot 기반), F4 TemporalSummaryInput의 slot 참조를 canonical로 통일 | F2, F4 |
| S4 | f1.py ↔ orchestrator.py의 coverage 기준·세션 종료 조건 단일화 | F0, F1 |

레거시 13-field 키(onset, duration, triggers, sleep, ...)는 12-slot 내 서술 값으로 흡수한다 (예: onset/duration → `history_of_present_illness`).

---

## 8. API 명세 종합표 (v2 상태 반영)

| Method | Path | v1 계획 | v2 상태 |
|--------|------|---------|---------|
| POST | `/ai/chat/respond` | 기존 수정 | 구현 (Orchestrator 연동). f1.py와 정합성 검증 필요 |
| POST | `/ai/safety/classify` | 기존 유지 | 구현 (CTRS 필드 포함) |
| POST | `/ai/stt/transcribe` | 신규 | **미구현** (ISS-011) |
| POST | `/ai/ocr/parse` | 신규 | **미구현** (ISS-011) |
| POST | `/ai/slots/extract` | 신규 | 구현 |
| POST | `/ai/survey/score` | 신규 | 구현 (rule-based) |
| POST | `/ai/temporal/retrieve` | 신규 (v1 계획) | **F4 보류** (superseded-for-F2, §3.6 — 삭제 아님) |
| POST | `/ai/domain/infer` | 신규 (v2.2, F2 재정의) | **구현 완료** — llm_only 경로 비인증 해제(`ADR-015`), RAG 경로는 EXPERIMENTAL 잔류(§3.8). 프로덕션 통합은 G-D-F2 보류 |
| POST | `/ai/temporal/summarize` | 신규 | 구현 |
| POST | `/ai/handoff/generate` | 기존 수정 | 구현 (12-section + 검증 루프) |
| POST | `/ai/sentiment/*` | (v1 미정의) | 구현 (utterance/session 모드) |

SLA, Request/Response 스키마 상세는 v1 §2.5, §3.5, §4.5, §5.5, §6.6을 승계한다 (slot 필드는 §7 canonical로 읽는다).

---

## 9. Phase 2 검증 전략 (v2 신규 — 상세는 development_report.md)

### 9.1 원칙

1. **실데이터 연쇄 우선**: 합성 입력 검증(Phase 1)은 필요조건일 뿐이다. Phase 2는 F1 세션 산출물이 F2~F5로 **실제로 흘러가는** 체인을 검증한다.
2. **종단 프로토콜**: 각 VP에 대해 다중 세션(초기 → follow-up ×2)을 실행하여 종단 데이터를 축적하고, 이를 F4/F5/F2 검증의 입력으로 사용한다.
3. **기능별 파이프라인**: f1.py 패턴(CLI 실행, JSON+report+checklist 산출, 재현 가능)을 f2~f5로 확장한다.
4. **정량 기준**: 각 VER 항목은 pass 기준을 수치로 정의한다 (재현성 n>=3, faithfulness 평가, coverage, recall).
5. **다중 관점 QA**: 코드 감사(QA), 검증 타당성 감사(Critic), 아키텍처 정합성 감사를 병행하고 의견을 통합하여 이슈를 확정한다.

### 9.2 검증 게이트

| Gate | 내용 | 통과 조건 |
|------|------|----------|
| **G-0** | **긴급 복구 (Stage 0)** | 서버 부팅 복구(trend_plotter), ISS-020 fix 재적용, safety fail-closed 재수정, 격리 테스트 스위트 복원 — 전체 테스트 green |
| **G-F** | **F1 grounding 재검증** | clinical_slot 프롬프트 grounding 수정 후 slot-근거 자동 감사 통과 (날조 0건), n>=3 재현 |
| G-A | F1 종단 프로토콜 완료 | 4VP × (초기 + follow-up 2회) 세션, slot faithfulness 평가 완료 |
| G-B | Safety 심층 검증 | 중간 턴 위기 전환·부정 문맥·간접 표현·CTRS3+자해 시나리오 파이프라인 레벨 통과 |
| G-C | 스키마 통일 (§7) | S1~S4 완료 + 핫라인 상수 통일 + 회귀 테스트 통과 |
| G-D | 기능별 파이프라인 검증 (f2/f3/f4/f5) | f3/f4/f5 파이프라인 실데이터 통과; F2는 `f2.py` 검증 파이프라인(오프라인 5종 + 라이브 n≥2/VP, §3.7) 통과 — **프로덕션 통합(orchestrator.py 연동, `/ai/domain/infer` 실사용)은 불포함**. **갱신(2026-07-08, `ADR-015`):** F2의 llm_only 경로는 이 조건을 충족(`EXP-005`, 비인증 해제 조건부)했다. RAG 경로는 EXPERIMENTAL로 잔류해 미충족 상태다 |
| **G-D-F2** | **F2 프로덕션 통합 (신규, REV-006 조건 4)** | DomainInferenceAgent가 `orchestrator.py`에 연동되고 `POST /ai/domain/infer`가 실사용 경로로 확인됨. 스키마 통일(T1-F0-DEV-007) 완료 후 착수 |
| G-E | 통합 E2E | F1→F3→F4→F5 전 체인, 4VP, EvidenceVerifier passed |

게이트 순서: G-0 → G-F → (G-A ∥ G-B ∥ G-C) → G-D → G-D-F2 → G-E. **G-0/G-F 통과 전에는 어떤 "pass" 주장도 갱신하지 않는다.** G-D-F2 신설은 REV-006 이슈 #4("G-D가 F2를 지칭한다는 서술이 실제로는 f3/f4/f5만 지칭하고 있어 F2가 dangling 상태"였음)의 해결이다. **잔여 격차(명시적으로 해결하지 않음):** G-E의 E2E 체인 서술(F1→F3→F4→F5)은 F2를 포함하지 않는다 — G-E 체인을 F2까지 확장할지 여부는 별도 결정 사항으로 남긴다.

### 9.3 종단 VP 프로토콜 (요약)

```
세션 S1 (초기):   f1.py --persona VP-00N            → conversation.json + handoff
설문 Q1:         persona 기준값으로 PHQ-9/GAD-7 채점  → scale_scores(t1)
세션 S2 (재상담): f1.py --persona VP-00N --followup-from S1 → 변화 반영 대화
설문 Q2:         변화 반영 응답 채점                  → scale_scores(t2)
세션 S3 (재상담): S2 기반 반복                        → scale_scores(t3)
                          ▼
      VP별 종단 데이터셋: slots(t1..t3), scores(t1..t3), sentiment(t1..t3), handoffs
```

### 9.4 기능별 오케스트레이션 파이프라인 (f1.py 패턴)

| 파이프라인 | 입력 | 호출 체인 | 산출물 |
|-----------|------|----------|--------|
| `f2.py` (구현 완료 — llm_only 비인증 해제·RAG EXPERIMENTAL, §3) | F1 conversation.json + 12-slot + CTRS + is_first_visit | Stage1 코드검색(rag/retrieval.py 재사용) → Stage2 DomainInferenceAgent LLM → 근거-화이트리스트 검사 | domain/department 후보 + evidence + retrieval_meta |
| `f3.py` | F1 slots + persona 설문 기준값 | Survey Planner rule → Scoring → (양성 시) Safety 재평가 | scale_scores JSON + 위험 연동 로그 |
| `f4.py` | 종단 데이터셋 (t1..tN) | SentimentAnalyzer(세션별) → TemporalSummary | direction + evidence + plot_data |
| `f5.py` | F1 slots + F3 scores + F4 summary + risk events | HandoffGenerator → EvidenceVerifier (재생성 루프) | 12-section report + verifier 판정 |
| `continuous_test.py`(Track C 검증 하네스, `PLAN-2026-W28-H`, 모듈: `apps/ai-server/src/continuous_test.py`) | 신규 F1 persona 실행 또는 기존 F1 conversation.json(`--start-from-conversation`) | F1 → F2 체이닝, `STAGE_REGISTRY`로 확장 가능한 스테이지 레지스트리, F3~F6은 명시적 no-op 스텁(구현되는 즉시 자동 편입 — 미구현을 침묵 스킵하지 않음), 자체 DB 프리플라이트로 F2의 silent llm_only 강등을 WARN으로 노출 | 체인 산출물(F1+F2 아티팩트 재사용, 덮어쓰지 않음) + 콘솔 PASS/WARN 로그. `orchestrator.py`/11-state 프로덕션 머신에는 미연동(f1.py/f2.py와 동일하게 검증 전용) |

### 9.5 통합 E2E

`fe2e.py` (또는 f5.py의 `--full-chain` 모드): S1~S3 산출물을 순서대로 F3→F4→F5에 공급하고, 최종 handoff의 Section 9(종단 변화)·Section 12(evidence registry)가 실데이터와 일치하는지 자동 대조한다.

---

## 10. CTRS ↔ RiskLevel 매핑

v1 §13과 동일 (구현 완료: `schemas/common.py`의 `CTRSLevel`, `RISK_TO_CTRS`). CTRS는 숫자가 낮을수록 위험. crisis flow는 CTRS 1-2.

---

## 11. 프롬프트 아키텍처 v3

**상태: 설계 확정(brainstorm A1, critic REV-002 2026-07-07 non-blocking 종결). 프롬프트 파일 작성·구현은 Phase 2 developer(Stage C1, `checklist_task1.md` 신규 항목 T1-F1-DEV-024~028) 소관.**

Claude Fable 5 시스템 프롬프트(소비자 chat 배포판, 약 3,800줄)를 역설계해 이 프로젝트의 소형 한국어 LLM(Solar Pro3/K-EXAONE)에 전이 가능한 설계 원칙을 추출하고, 5개 활성 임상 에이전트 프롬프트를 코드 출력 계약(byte-identical)을 유지한 채 재설계하는 작업이다. 전체 사양의 authoritative source는 `docs/ai/prompt_redesign_v3.md`(v3.1)이며, 아래는 PRD 독자를 위한 요약이다(상세 근거·인용은 원문 참조, 여기서는 중복 서술하지 않는다).

### 11.1 원칙 (Fable-5 역설계 — P1~P12 요약)

`prompt_redesign_v3.md` §1이 정의하는 12개 원칙(P1~P12)은 크게 4갈래로 묶인다:

| 갈래 | 해당 원칙 | 요지 |
|---|---|---|
| 경계·계약형 | P1, P2, P3, P8 | 역할 경계를 단독 절대 문장으로 명시, 출력 계약을 프롬프트 최종 섹션으로 통일, 절대 규칙은 5개 이하로 압축, 지시는 번호화된 우선순위(첫 매치에서 정지)로 배치 |
| 근거주의형 | P4, P5, P11 | 근거 없는 서술은 침묵/null 처리("근거 없으면 침묵" — clinical_slot의 기존 null 원칙과 동일 구조), 불확실성은 명시적 라벨로 표기, 출력 전 자체 점검 |
| 오염 방지형 | P7, P12 | 프롬프트 예시는 명백한 placeholder만 사용(DR-001/ISS-027 echo 재발 방지), 런타임 주입 컨텍스트의 구체값을 정적 프롬프트에 하드코딩하지 않음 |
| 톤·포맷형 | P6, P9, P10 | 단정적 확답 대신 계조적(graduated) 언어, 위기 신호 시 정보 제공 대신 우회 대응(기존 Safety Probe 설계와 철학적으로 동일), 장식적 마크다운 최소화 |

각 원칙의 Fable-5 원문 근거(짧은 발췌)·소형 모델 적용 근거·토큰 예산 지침은 `prompt_redesign_v3.md` §1의 P1~P12 세부 항목을 참조한다.

### 11.2 대상 — 5개 활성 임상 에이전트 (현재 → 목표 버전)

| 에이전트 | 현재 | 목표 | 핵심 변경 (상세: `prompt_redesign_v3.md` §2.x) |
|---|---|---|---|
| safety_classifier | v1 | v2 | 절대 규칙 5개로 압축(ISS-046 관용구 규칙 신규) + v1 핵심 규칙 7개 중 5개 verbatim 보존·2개 표 통합(삭제 0개, REV-002 #2 확인) + ISS-048/050 신규 앵커. I/O 계약(5키) 불변 |
| dialogue | v1 | v2 | 절대 금지 8→6개 통합, "Safety 참고 행동" 섹션 5→1줄 축소(P12 — 런타임 `_build_slot_context`/`safety_context` 주입과의 중복 제거). I/O 계약(`assistant_response`) 불변 |
| clinical_slot | v2 | v3 | 최우선 원칙 5개 hold(내용 불변). risk_assessment ↔ SafetyClassifier 상호참조 노트는 프롬프트에 넣지 않음(REV-002 #3 — `ClinicalSlotInput`이 safety 결과를 받지 않아 모델 지시로는 실행 불가; 조정은 오케스트레이션 코드 레벨 사후 처리로 이관, 본 PRD 범위 밖). I/O 계약(12키) 불변 |
| handoff_generator | v1 | v2 | ctrs_level 출력 지시 삭제(ADR-007 옵션A 확정 — dead instruction, `handoff_generator.py`가 `resp.content`를 JSON 파싱 없이 그대로 사용) + P7 placeholder화 7곳(§6/§8/§9/§12) + evidence citation 반복 지시 3회(§3/§5/§7)→1회 통합. I/O 계약(12개 H2 제목 + `[ev_*]` 토큰) 불변 |
| sentiment_analyzer | v1 | v2 | session 모드 섹션 전체 삭제(코드 확인 결과 LLM 미호출 dead prompt, `_analyze_session()`은 순수 Python 집계) + `turn_index` 예시 필드 제거(코드가 덮어씀) + `evidence_phrase` placeholder화. I/O 계약(5키, utterance 모드만) 불변 |

**고아 프롬프트 제외:** `orchestrator`, `temporal_summary`, `evidence_verifier`(런타임 미로드/rule-based), `temporal_retriever`/`stt`/`ocr`/`prompt_eval`(미구현) 8개는 이번 v3 재설계 범위에서 제외되며 상태만 표기한다 — 근거는 `prompt_redesign_v3.md` §3(코드 확인 완료).

### 11.3 검증 전략

**오프라인 프롬프트 테스트 (Stage C1, developer 구현):** 5개 프롬프트 파일에 대해 placeholder-only 예시, 필수 출력 스키마 키 문자열 존재, 절대 규칙 핵심 문구 존재, char 예산 상한, session 모드 섹션 부재(sentiment), ISS-050 재채점 일관성 문구(safety), v1 핵심 규칙 7개 존치(safety), evidence citation 단일 선언(handoff) — 총 8개 단정문을 자동 검사한다(`prompt_redesign_v3.md` §4.1).

**Safety Matrix (라이브, SM-07a/SM-07b 신설):** 기존 SM-01~06(`development_report.md` DR-003에서 7/7 통과 확인)에 더해 ISS-046 관용구 오탐 방지 시나리오 **SM-07a**(공황/응급실 회고, 자살 의도 없음 — `crisis_triggered==false` 기대)와 그 필수 대조군 **SM-07b**(동일 프레이밍 + 실제 자살 의도 병존 — `crisis_triggered==true` 기대, 오버코렉션/false negative 방지)를 신설한다. SM-01~06 + SM-07a + SM-07b **8개 시나리오 전건 필수 통과**(대조군도 "권장"이 아닌 필수).

**VP-001~004 라이브 A/B (DR-003 베이스라인 대비):** DR-003 베이스라인(2026-07-06, commit 9aea999) — fabrication 0/8 VP 런(n=2/VP), Safety Matrix 7/7, Safety Probe 발동률 100%, SI screen 준수율 75%(목표 100% 미달, ISS-047) — 대비 v3 프롬프트로 VP-001~004 각 **최소 n≥2 세션**(n≥3 권장, DR-003과 동일 표본 이상)을 재실행하고 동일 정의로 fabrication count, grounded_coverage, crisis accuracy, probe rate, CTRS calibration(ISS-046/048/050 재발 여부), 섹션별 evidence citation 첨부율을 재측정한다. n≥2 미만 결과로는 "회귀 없음"/"개선" 문구를 사용하지 않는다.

**ISS-049 정책 고지(ADR-010, ADR-012):** 수동적 자살사고 표현을 첫 발화이든 세션 중 어느 시점이든 즉시 CTRS 2/crisis로 라우팅하도록 **사용자 정책은 확정되었다**(ADR-010, "즉시 대응하자" — ADR-006의 잠정 유지 방침을 대체). 단 이 정책의 첫 구현 시도(safety_classifier v3)는 라이브 검증(EXP-003)에서 SM-04a/SM-04b 프로브 회귀로 롤백되어(ADR-012), 현재 라이브 라우팅은 v2 기준(CTRS 3 → Safety Probe 경유)으로 남아 있다 — v4 재설계 대기 중(DR-005). 본 문서 §11.3의 A/B 비교(DR-003 대비 EXP-002)는 v3 이전, ADR-006 치하에서 수행된 과거 비교이며 소급 수정하지 않는다.

**롤백 기준:** 다음 중 하나라도 관찰되면 버전 핀을 이전 프롬프트(v1/v2)로 즉시 되돌리고 정직하게 보고한다 — (1) fabrication count > 0(어느 하나라도), (2) crisis miss(SM-01~06 + SM-07a/SM-07b 8개 전건 중 하나라도 `crisis_triggered` 기대와 불일치), (3) probe miss(CTRS 3 + 자살/자해 category 조건에서 Safety Probe 미발동). 롤백 시 critic이 독립적으로 원인을 재검토하기 전까지 "개선되었다" 문구를 사용하지 않는다.

**범위 caveat:** 위 A/B는 `f1.py` 시뮬레이션 하네스(검증된 경로)에서 실행되며, 세션 위험도 하한(session risk floor)은 `f1.py`에서만 확인되고 `orchestrator.py`/`routes/`에서는 동일 기능이 확인되지 않았다(기존 gap, ISS-029). 결론은 `f1.py`-검증 경로로 범위를 한정하며, 프로덕션 오케스트레이터 경로로 일반화하려면 별도 확인이 선행되어야 한다.

---

## 부록 A. v1 문서와의 관계

- v1(`PRD_task1.md`)은 원 계획과 상세 API/DB 스키마 정의의 참조 문서로 보존한다.
- 충돌 시 **v2가 우선**한다. 특히 slot 스키마(§2.3, §7), F1 아키텍처(§2), 기능 상태(§3~6)는 v2 기준.
- 이슈 이력은 `docs/ai/backups/issues.md`(ISS-001~018), 세부 해결 내역은 `docs/ai/backups/f1_issue_resolution_report.md` 참조.

*End of Document*
