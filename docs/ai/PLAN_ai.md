# Neuro-Sync AI 팀 작업 계획

> **Owner**: AI Research 팀
> **Parent**: [`../todo_plan/PLAN_neuro-sync.md`](../todo_plan/PLAN_neuro-sync.md) (마스터 PLAN v1.4 — 8주 데모 일정)
> **참조**: [`PRD_ai.md`](./PRD_ai.md)
> **AI ↔ Platform 경계**: [`README.md`](./README.md) §3
> **Demo D-Day**: **2026-07-31**
> **전제**: 제안서 단계에서 MVP LLM 선정·라벨링 전략·자문의·임계값 등 비개발 의사결정 완료. 본 PLAN은 **순수 개발만** 다룬다.

본 계획은 AI 팀 단독 작업분만 다룬다. Platform 작업분은 마스터 PLAN 참조.

---

## Phase 1a: Safety 코어 (3주, 2026-06-04 ~ 2026-06-24, Platform Phase 1a 병행)

> Platform Phase 1a 산출물(Auth/RBAC/WebSocket 인증/Audit 인프라)을 입력으로 받음.

- [ ] **`apps/ai-server` 부트스트랩** — FastAPI + Dockerfile + CI 파이프라인 (Day 1~2)
- [ ] **`POST /ai/safety/classify` 인터페이스 구현** (README.md §3.1, 마스터 PRD §0.3)
- [ ] **Safety Guard 모듈 v1**
  - 키워드 사전 매칭 (Aho-Corasick, ~50ms) — 제안서 단계 자살 은어 사전 시드
  - LLM 분류기 (제안서 선정 MVP LLM, ~600ms)
  - 병렬 호출 + 빠른 결과 우선 라우팅
  - 산출물: `safety_guard/spec_v1.md` + `apps/ai-server/src/safety/`
- [ ] **위험 등급 페이로드 정의** (Platform과 합의)
- [ ] **Safety Guard 회귀 테스트셋 v1** (제안서 라벨 데이터 import) — `eval/safety_guard/regression_v1.jsonl`
- [ ] **AI 호출 트레이싱·관측 셋업** (LangSmith 또는 자체)
- [ ] **`POST /ai/chat/respond` 인터페이스 스켈레톤** (Phase 1b에서 본격 구현 예정)

**Phase 1a Gate (W3 종료)**: `/ai/safety/classify` p95 < 1,000ms + 안전/위험 케이스 5건 통과.

---

## Phase 1b: 채팅 + Handoff + STT (4주, 2026-06-25 ~ 2026-07-22, Platform Phase 1b 병행)

- [ ] **`POST /ai/chat/respond` 본격 구현** (FR-004)
  - 시스템 프롬프트 v1 (`prompts/chat/system_v1.md`)
  - 후속 질문 생성 (`prompts/chat/followup_v1.md`)
  - 스트리밍 토큰 반환
  - 첫 토큰 p95 < 800ms 검증
- [ ] **`POST /ai/handoff/generate`** (FR-018)
  - Markdown 생성 + 원문 근거 인용 자동 검증 (인용 누락 시 reject + 재생성)
  - 산출물: `prompts/handoff/v1.md`, `eval/handoff/citation_check.md`
- [ ] **`POST /ai/stt/transcribe` (Whisper 모드)** (FR-033, FR-035, FR-037)
  - STT Adapter 인터페이스 구현 (Whisper API + self-hosted Whisper Large-V3)
  - A.dot 어댑터는 **스텁만** (Phase 2 계약 후 본격)
  - 신뢰도 임계값 0.6 (잠정), 폴백 응답 코드 정의
  - 산출물: `stt/adapter_v1.md` + `apps/ai-server/src/stt/`
- [ ] **Handoff Report 의사 만족도 사전 검증 (선택)**
  - 합성 케이스 10건 자체 평가 (제안서 단계 자문의 일정 가능 시 실 자문)

**Phase 1b Gate (W7 종료)**: 가상 페르소나 3건으로 채팅 → 문진 → Handoff 시나리오 통과.

---

## Demo Polish (1주, 2026-07-23 ~ 2026-07-31, Platform 병행)

- [ ] 프롬프트 마지막 튜닝 (가상 페르소나 3~5건 회귀)
- [ ] Safety 임계값 미세 조정 (Precision/Recall trade-off)
- [ ] 데모용 격리 환경에서 토큰 사용량·외부 API rate limit 점검
- [ ] AI 메트릭 대시보드 스크린샷 (발표 자료용)

---

## Phase 2: 안전 강화 + 멀티 LLM 준비 + OCR (Post-demo, 3~4개월, Platform Phase 2 병행)

- [ ] **`POST /ai/ocr/parse`** (FR-009)
  - Upstage Document Parse 통합 + 의료 용어 후처리 v1
  - 산출물: `ocr/integration_spec.md`
- [ ] **Safety Guard Recall ≥ 95% 달성**
  - 라벨 데이터셋 v2 (파일럿 데이터 가명처리 반영)
  - Cohen's κ ≥ 0.7 (자문의 2명, 분기별)
- [ ] **STT 벤더 비교 리포트**
  - 의료 한국어 발화 100건 자체 녹음
  - A.dot vs Whisper API vs Whisper Local 정확도/지연/비용
  - 산출물: `stt/vendor_eval_v1.md`
- [ ] **A.dot STT Primary 스왑** (계약 체결 시) — 환경변수만 교체
- [ ] **LG K-EXAONE 2차수 통합 준비** (출시 시점에 맞춰)
  - FriendliAI API 연동, Hybrid Reasoning 채팅·Handoff PoC
  - 산출물: `orchestration/exaone_integration.md`
- [ ] **SK A.X K1 Agentic Orchestrator PoC**
  - 산출물: `orchestration/axk1_router.md`
- [ ] **KT Mi:dm K 2.0 자가호스팅 PoC** (PHI 격리 RAG, vLLM)
  - 산출물: `orchestration/midm_rag.md`
- [ ] **Hallucination 검출 자동화** — `eval/handoff/hallucination_detector.md`

**Phase 2 AI Deliverable**: Safety Recall ≥ 95% + OCR 가동 + 멀티 LLM PoC + 파일럿 AI 메트릭 확보.

---

## Phase 3: 멀티 LLM 본격 도입 + 품질 고도화 (5~6개월)

- [ ] 오케스트레이션 정식 도입 (PRD_ai §2.2)
- [ ] NC AI VARCO 평가 (환자 교육 자산)
- [ ] AI 메트릭 대시보드 v1
- [ ] 프롬프트 A/B 테스트 인프라

---

## Phase 4: 상용 운영 (Post-MVP)

- [ ] 다국어 확장 (K-EXAONE 6개국어)
- [ ] 자가호스팅 LLM 전환 검토
- [ ] 임상 도메인 미세조정

---

## AI 팀 의존성 표

| 의존성 | 출처 | 영향받는 AI task |
|--------|------|-----------------|
| Auth/RBAC/WebSocket 인증 | Platform Phase 1a | `/ai/chat/respond` 호출 인증 |
| `audit_logs` 인프라 + AI 호출 추적 | Platform Phase 1a | AI 호출 감사 기록 |
| 파일 저장(S3 SSE-KMS) presigned URL | Platform Phase 1b/2 | OCR/STT 원본 가져오기 |
| `messages` / `risk_events` / `audio_recordings` 스키마 | Platform Phase 1a/1b | AI 응답 저장 인터페이스 |
| LG K-EXAONE 2차수 출시 | 외부 (2026-06) | Phase 2 멀티 LLM 진입 |
| SK A.X K1 API Key | 외부 (대회 본선 전) | Phase 2 Agentic Orchestrator PoC |
| SK A.dot STT 계약 | Platform 법무 + AI | Phase 2 STT Primary 스왑 |

---

## Changelog

- **v1.1 (2026-06-04)**: 마스터 PLAN v1.4 (8주 데모 일정)에 맞춰 재구성. Phase 0(LLM PoC·라벨링 가이드 등)은 제안서 단계 완료로 제거. Phase 1a/1b/Demo Polish 일자 명시. STT는 Whisper 모드로 데모, A.dot은 Phase 2. OCR는 Phase 2.
- **v1.0 (2026-06-04)**: 마스터 PLAN v1.1에서 AI 영역 추출, AI 팀 단독 계획으로 분리.
