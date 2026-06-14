# Task Plan: neuro-sync

> **Generated from**: docs/prd/PRD_neuro-sync.md (v1.4)
> **Created**: 2026-06-02 / **Updated**: 2026-06-04 (8주 데모 일정 재구성)
> **Status**: Phase 1a in-progress (D-Day 2026-07-31)
> **Scale Grade**: Startup (PoC/파일럿)
> **전제**: 제안서 단계에서 비개발 의사결정(법률·라이선스·자문의·LLM 선정·LOI·라벨링·임계값) 완료. 본 PLAN은 **순수 개발**만 다룬다.

## Execution Config

| Option | Value | Description |
|--------|-------|-------------|
| `auto_commit` | true | 완료 시 자동 커밋 |
| `commit_per_phase` | true | Phase별 중간 커밋 (의료 도메인 안전성 추적용) |
| `quality_gate` | true | /auto-commit 품질 검사 |
| `security_review` | true | 민감정보 다루므로 보안 리뷰 필수 |

## Phases

### Phase 1a: Auth + 안전 코어 (3주, 2026-06-04 ~ 2026-06-24, 인력: BE1+FE1+AI1)

> **목표**: 인증·위험 감지·응급 라우팅·의료진 대시보드 read-only.
> **Gate (W3)**: Safety Guard p95 < 1,000ms + 안전/위험 케이스 5건 통과.

#### 1a.0 환경 셋업 (Day 1~2)
- [ ] 모노레포 구조 적용 (apps/api, apps/mobile, apps/web, apps/ai-server 진입)
- [ ] 백엔드: FastAPI + Python 3.12 + uv 셋업
- [ ] 모바일: React Native (Expo) + TypeScript
- [ ] 웹: Next.js 16 + TypeScript + Tailwind
- [ ] PostgreSQL 16 + pgvector + Redis 로컬 Docker 컴포즈
- [ ] 환경변수 관리 (`.env.example`, secrets: 1Password/Doppler)
- [ ] GitHub Actions CI 기본 (lint + test) — Platform + AI 별도 파이프라인

#### 1a.1 인증 & 권한 (FR-001, FR-002, FR-015, FR-023, FR-026)
- [ ] DB 스키마: `users`, `patient_profiles`, `consent_snapshots`, `organizations`, `audit_logs`, `clinician_sessions`
- [ ] AES-256 컬럼 암호화 (이름/연락처/비상연락처)
- [ ] **Argon2id 비밀번호 해시**
- [ ] `POST /api/v1/auth/register` — 4개 동의 분리 (만 14세 미만 분기는 Phase 2)
- [ ] `POST /api/v1/auth/login` — Rate limit + 5회 실패 15분 잠금
- [ ] JWT (15분) + Refresh token (7일, 환자)
- [ ] RBAC + RLS 정책 (5개 Role)
- [ ] 감사 로그 미들웨어 (모든 환자 데이터 접근 기록) — hash chain은 Phase 2
- [ ] 모바일 회원가입/로그인 화면 (`/onboarding`, `/login`, `/register`)
- [ ] 웹 의료진 로그인 화면 (2FA는 Phase 2)

#### 1a.2 환자 홈 + 세션 (FR-003, FR-013)
- [ ] DB: `sessions`
- [ ] `POST /api/v1/sessions`, `GET /api/v1/sessions/current`
- [ ] 모바일 `/home`

#### 1a.3 WebSocket 채팅 + 위험 감지 (FR-004, FR-005, FR-011, FR-022) 🔴 안전 핵심
- [ ] DB: `messages` (암호화), `risk_events`
- [ ] **WebSocket 인증 (`auth:connect` 초기 프레임만, URL query 금지)**
- [ ] Origin 화이트리스트 + idempotencyKey 검증
- [ ] 단일 LLM 어댑터 + 스트리밍 (`apps/ai-server`의 `/ai/chat/respond` 소비)
- [ ] **Safety Guard 모듈** (`apps/ai-server`의 `/ai/safety/classify`): 키워드 사전 + LLM 분류 병렬, 키워드 결과 우선 차단 fallback
- [ ] 위험 등급 분류 (low/medium/high/critical)
- [ ] WebSocket `risk:detected` 이벤트
- [ ] 모바일 `/emergency` 강제 전환 (119/1393 버튼, 안전 확인 질문)
- [ ] **위험 통보 흐름** (FR-026): 데모는 **시뮬레이션 알림만** (실 SMS 미발송)
- [ ] Safety latency p95 < 1,000ms 측정

#### 1a.4 의료진 대시보드 read-only (FR-016, FR-021)
- [ ] `GET /api/v1/clinician/patients` (페이지네이션, 위험 정렬)
- [ ] 웹 `/dashboard` 환자 목록 + 위험 플래그

**Phase 1a Deliverable**: 인증 + 위험 감지 + 응급 라우팅 + 대시보드 read-only

---

### Phase 1b: 문진 + Handoff + STT (4주, 2026-06-25 ~ 2026-07-22)

> **목표**: PHQ-9/GAD-7 + AI 채팅 + Handoff 리포트 + 의료진 상세 + 음성 입력 (Whisper 모드).
> **Gate (W7)**: 가상 페르소나 3건으로 채팅→문진→Handoff 풀 시나리오 통과.

#### 1b.1 표준 문진 (FR-006, FR-007)
- [x] DB: `questionnaire_results` (alembic 0003)
- [x] PHQ-9 9문항
- [x] GAD-7 7문항
- [x] `POST /api/v1/sessions/:id/questionnaires`
- [x] 총점 자동 계산 + severity 분류 (참고용)
- [x] 모바일 `/intake/phq9`, `/intake/gad7`

#### 1b.2 AI 사전 문진 채팅 본격 운영 (FR-004)
- [ ] 프롬프트 시스템 메시지 (진단 금지, 구조화 수집 가이드) — `apps/ai-server/src/prompts/chat/`
- [ ] 대화 진행률 계산 로직 (수집 항목 13개 기준)
- [ ] 모바일 `/intake/chat` 화면 (스트리밍 UX)

#### 1b.3 문진 제출 + Handoff 리포트 (FR-010, FR-018)
- [x] DB: `handoff_reports` (alembic 0003, 상태 추적 generating/ready/failed)
- [x] `POST /api/v1/sessions/:id/submit` (202, 세션 freeze + 리포트 row 생성)
- [x] 비동기 리포트 생성 작업 → `apps/ai-server`의 `/ai/handoff/generate` 호출
      (**Demo는 FastAPI BackgroundTasks**, seam = `generate_report_task`; Celery 스왑은 Phase 후속)
- [ ] LLM 프롬프트: 환자 발화 → 구조화 JSON (주호소, 현병력, 증상 등 13항목) — **AI팀 (ai-server)**
- [x] **원문 근거 인용 계약** (`contracts.handoff.Citation`, field별 source_message_id) — 생성 검증은 AI팀
- [x] `GET /api/v1/sessions/:id/report` (의료진, 문진점수·위험신호는 항상 서버 조합)
- [x] 모바일 `/intake/submit` (제출 전 안내문구 FR-010)
- [ ] 모바일 `/report/status` (환자용 리포트 상태 화면 — 후속)

#### 1b.4 의료진 환자 상세 + 리포트 뷰 (FR-017)
- [x] `GET /api/v1/clinician/patients/:id` (Phase 1a 완료)
- [x] 웹 `/dashboard/patients/:id/sessions/:id` Handoff 리포트 뷰 (HandoffReportView)
- [x] 위험 신호 강조 표시 + 원문 근거 표시 (narrative.evidence)

#### 1b.x 위험 이벤트 확인 (FR-011, FR-022) — 추가 슬라이스
- [x] DB: `risk_events.alone_status`, `acknowledged_at` (alembic 0003)
- [x] `PATCH /api/v1/risk_events/:id` (환자 본인, aloneStatus 기록)
- [x] `risk:detected` payload에 `riskEventId` 추가 + 모바일 `/emergency` "혼자 계신가요?" 활성화

#### 1b.5 STT (Whisper 모드) (FR-033, FR-034, FR-035, FR-036, FR-037)
- [ ] DB: `audio_recordings`, `stt_transcriptions`, `messages.input_modality` 컬럼
- [ ] `consent_snapshots`에 음성 동의 컬럼 추가 + 회원가입/설정에서 옵트인 UX (FR-034)
- [ ] `POST /api/v1/stt/transcribe` (multipart) — `apps/ai-server`의 `/ai/stt/transcribe` 호출
- [ ] **STT Adapter v1**: A.dot 어댑터는 스텁만, **Whisper(OpenAI 또는 self-hosted) 구현이 데모 경로**
- [ ] **48시간 자동 폐기 잡** (Celery Beat) — FR-036
- [ ] 모바일 마이크 권한 + Push-to-Talk UI (파형/경과시간/취소)
- [ ] 변환 결과를 입력창에 자동 채움 + 사용자 명시적 전송 (FR-035)
- [ ] 신뢰도 < 0.6 또는 실패 시 키보드 폴백 자동 전환 (FR-037)

**Phase 1b Deliverable**: 환자 앱(iOS or Android 1개) + 의료진 웹 + AI 서버 통합 + Whisper STT 가동.

---

### Demo Polish (1주, 2026-07-23 ~ 2026-07-31)

> **목표**: 데모 발표·시연 준비 완료.

- [ ] 가상 페르소나 시드 데이터 3~5명 (위험·일반 혼합)
- [ ] 데모 시나리오 스크립트 + 진행 가이드
- [ ] UX 다듬기 (에러/로딩/empty 마이크로카피)
- [ ] 데모 영상 백업 녹화 (라이브 실패 대비)
- [ ] 발표 자료
- [ ] 격리 데모 환경 안정화 (외부 LLM/STT API rate limit·캐시 검증)
- [ ] 통합 회귀 테스트 (Safety 5건 + 풀 시나리오 3건)

**Demo Deliverable (D-Day 2026-07-31)**: 환자 모바일 + 의료진 웹 + AI 서버 통합 데모.

---

### Phase 2: 보안·컴플라이언스 강화 + OCR + 알림 (Post-demo, 3~4개월)

#### 2.1 보안·컴플라이언스 강화 (데모에서 미룬 항목)
- [ ] 만 14세 미만 법정대리인 동의 분기 — FR-027 + 휴대폰 본인인증
- [ ] 의료진 2FA (TOTP) + idle 15분 세션 타임아웃 — FR-031
- [ ] **감사 로그 hash chain** + UPDATE/DELETE 트리거 + super_admin 메타 audit — FR-030
- [ ] 위험 트리거 컨텍스트 보존 (전 5턴 + 후 3턴) — FR-032
- [ ] 회원 탈퇴/가명처리 — FR-029
- [ ] 위험 통보 실 SMS 발송 (Toast/Aligo) + 다단계 등급 — FR-026

#### 2.2 문서 업로드 + OCR (FR-008, FR-009, FR-028)
- [ ] DB: `documents`
- [ ] S3 + SSE-KMS + Presigned URL (5분)
- [ ] `POST /api/v1/sessions/:id/documents` (multipart)
- [ ] **FR-028 보안 검증**: MIME 화이트리스트 + 매직넘버 + 파일명 새니타이즈 + ClamAV + 20MB 제한
- [ ] Upstage Document Parse 통합 — `apps/ai-server`의 `/ai/ocr/parse`
- [ ] OCR 텍스트 → Handoff 리포트 "업로드 문서 요약" 자동 반영
- [ ] 모바일 `/intake/documents` (카메라/갤러리/PDF)

#### 2.3 리포트 PDF + EMR 텍스트 (FR-019, FR-020)
- [ ] `GET /api/v1/sessions/:id/report/pdf` (ReportLab 또는 wkhtmltopdf)
- [ ] `GET /api/v1/sessions/:id/report/emr-text`
- [ ] 웹 다운로드 + 클립보드 복사 버튼

#### 2.4 병원 검색 + 알림 (FR-012, FR-014)
- [ ] DB: `hospitals` (정적 시드 데이터, 서울/경기 정신과 100~200개)
- [ ] `GET /api/v1/hospitals/search` + 모바일 `/hospitals`
- [ ] 앱 내 알림 센터 + 이메일(Resend/SES) + SMS(Toast/Aligo)

#### 2.5 STT Primary 스왑 (A.dot 계약 후)
- [ ] A.dot 어댑터 구현 + 인증
- [ ] 환경변수만 교체로 무중단 전환

**Phase 2 Deliverable**: 파일럿 1~2 의원 시범 도입 가능 수준

---

### Phase 3: 품질 + 확장 (5~6주)

- [ ] **임상 자문단 5명 대상 Handoff 리포트 블라인드 테스트** (목표 만족도 85%)
- [ ] 프롬프트 튜닝 + Few-shot 예시 추가
- [ ] (선택) 다중 LLM 오케스트레이션: LangGraph 기반
  - [ ] Orchestrator (K-EXAONE 또는 GPT-4)
  - [ ] Dialogue Agent (Solar Pro 3)
  - [ ] RAG Agent (A.X K1 + pgvector)
  - [ ] Safety Agent (Mi:dm K 2.0)
- [ ] 시계열 RAG: 과거 세션 비교 ("지난 방문 대비 변화")
- [ ] 심평원 Open API 연동 (병원 정보 자동 갱신)
- [ ] 푸시 알림 (FCM Android + APNs iOS)
- [ ] Latency 최적화 (병렬 호출, 캐싱, p95 < 2s 보장)

**Phase 3 Deliverable**: 파일럿 3~5 의원, 실 환자 운영

---

### Phase 4: 컴플라이언스 + 상용화 (4주)

- [ ] 외부 침투 테스트 (전문 업체)
- [ ] 취약점 패치 + 보고서
- [ ] ISMS-P 준비 (선택적, 자문 후 결정)
- [ ] HL7 FHIR 부분 호환 (Patient, Observation, Condition 리소스)
- [ ] EMR 연동 SDK (유비케어/비트컴퓨터 검토)
- [ ] 의료진 운영 매뉴얼 + SLA 계약서 템플릿
- [ ] B2B 구독 결제 (Toss Payments)
- [ ] 운영 모니터링 (Sentry, Datadog or Grafana)
- [ ] On-call 체계 + Runbook

**Phase 4 Deliverable**: 상용 GA 출시

---

## Progress

| Metric | Value |
|--------|-------|
| Total Phases | 4 (Phase 1a / 1b / Demo Polish / Phase 2~4 post-demo) |
| Current Phase | Phase 1a (시작) |
| Status | in-progress |
| **Demo D-Day** | **2026-07-31** |

## Execution Log

| Timestamp | Phase | Task | Status |
|-----------|-------|------|--------|
| 2026-06-02 | - | PRD v1.0 & Plan v1.0 생성 | completed |
| 2026-06-02 | - | prd-reviewer: Critical 8건 식별 (BLOCKED) | completed |
| 2026-06-02 | - | PRD v1.1 & Plan v1.1: Critical 8건 반영 + FR-026~032 추가 | completed |
| 2026-06-04 | - | PRD v1.2: STT(FR-033~037) 통합 | completed |
| 2026-06-04 | - | PRD v1.3 & 워크스페이스 분리: Ownership Matrix + AI Research 독립 | completed |
| 2026-06-04 | - | PRD v1.4 & PLAN: 8주 데모 일정 재구성, Phase 0 제거 (제안서 단계 완료 항목 분리) | completed |
| 2026-06-04 | Phase 1a | 환경 셋업 시작 | pending |
| 2026-06-14 | Phase 1b | 1b.1 표준 문진(PHQ-9/GAD-7) — DB+API+채점+모바일 화면 | completed |
| 2026-06-14 | Phase 1b | 1b.3/1b.4 Handoff 배관 — submit/report API(BackgroundTasks)+계약+웹 리포트 뷰 | completed |
| 2026-06-14 | Phase 1b | 1b.x 위험 이벤트 확인 PATCH + 모바일 응급화면 활성화 (FR-011/022) | completed |

## Critical Path (Demo)

1. **CI/CD + DB 스키마 + Auth** (W1) — 다른 모든 기능의 기반
2. **WebSocket 채팅 + Safety Guard** (W2~W3) — 안전 직결, latency p95 < 1,000ms
3. **AI 채팅·문진·Handoff 리포트** (W4~W6) — 핵심 가치 시연
4. **STT (Whisper 모드)** (W6~W7) — 음성 입력 데모 차별화
5. **Demo Polish** (W8) — 시나리오·UX·발표 자료

## Open Decisions (개발 단계)

> 제안서 단계에서 결정된 항목(법률·LLM·라이선스·자문의·LOI·라벨링·임계값 등)은 제외.

| # | 결정 | 시점 | 담당 |
|---|------|------|------|
| 1 | STT 신뢰도 폴백 임계값 (잠정 0.6) | Phase 1b 종료 전 | AI 팀 |
| 2 | SK A.dot STT API 발급/단가/계약 (FR-033 Primary) | Phase 2 — 데모는 Whisper로 | Platform 법무 + AI |
| 3 | STT 외부 위탁 시 국내 데이터 잔류 조건 | A.dot 도입 직전 (Phase 2) | Platform 법무 |
| 4 | MVP 우선 모바일 플랫폼 (iOS or Android) | Phase 1a 종료 전 | Platform |
| 5 | 데이터 이동권 (타 병원 export) | Phase 4 (Post-MVP) | - |
