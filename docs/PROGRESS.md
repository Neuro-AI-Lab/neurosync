# Neuro-Sync 개발 진행 현황

> **작성일**: 2026-06-18 · **데모 D-Day**: 2026-07-31
> **소스**: [PRD](prd/PRD_neuro-sync.md) · [PLAN](todo_plan/PLAN_neuro-sync.md) · [AI PRD](ai/PRD_ai.md)
> 본 문서는 머지된 작업 기준의 스냅샷이다. 세부 체크리스트는 PLAN을 따른다.

## 1. 개요

**Neuro-Sync** — 정신건강의학과 진료 전 사전 문진/핸드오프 시스템 (PoC/파일럿).
환자가 진료 전 AI 채팅 + 표준 문진(PHQ-9/GAD-7)으로 증상을 정리하면, 의료진이 5초 내 판독 가능한
**구조화 Handoff 리포트**로 변환한다. 실시간 자살/자해 위험 감지 + 응급 라우팅(119/1393)을 포함한다.

- **법적 기반**: 개인정보보호법(PIPA) + 의료법 + 자살예방법 §13/§14
- **규모**: Startup (2~5개 의원, 1~5K DAU 가정)
- **현재 단계**: **Phase 1b 플랫폼 거의 완료** + 데모 준비 진행 중. AI 서버 통합이 남은 핵심.

## 2. 아키텍처

```
Platform Team (BE/FE)              AI Research Team (LLM/Safety/STT)
  apps/api      FastAPI            apps/ai-server   FastAPI
  apps/mobile   React Native/Expo    └ contracts/   (shared-contracts 단일 계약)
  apps/web      Next.js 15           └ src/rag/     pgvector RAG (apps/api 내)
```

| 앱 | 스택 | 역할 |
|----|------|------|
| `apps/api` | FastAPI · SQLAlchemy 2.0(async) · asyncpg · Alembic | 플랫폼 API + WebSocket 게이트웨이 + AI 서버 프록시 |
| `apps/mobile` | React Native 0.76 · Expo SDK 52 · expo-router · Zustand | 환자 앱 |
| `apps/web` | Next.js 15 · React 18.3.1 · Tailwind · RSC | 의료진 대시보드 |
| `apps/ai-server` | FastAPI · Pydantic | AI 추론(LLM/Safety/STT/Handoff) — **통합 대기** |
| `packages/shared-contracts` | Pydantic + TypeScript | API↔AI 단일 계약 |

- **DB**: PostgreSQL 16 + pgvector · **패키지**: pnpm + uv · **CI**: GitHub Actions(Platform/AI 분리)
- **보안**: AES-256-GCM 컬럼 암호화(AAD 바인딩) · Argon2id · JWT(iss/aud/jti) · RBAC · 모든 민감접근 audit_logs

## 3. 진행 현황 요약

| 영역 | 상태 |
|------|------|
| **Phase 1a** (인증·안전·응급·대시보드) | ✅ 완료 |
| **Phase 1b 플랫폼** (문진·Handoff·채팅·STT 배관) | ✅ 완료 |
| **RAG 검색 계층** (pgvector grounding) | ✅ 완료 |
| **모바일 데모 화면** + 오프라인 MOCK | ✅ 완료 |
| **데모 준비** (시드·폐기 스케줄러·테스트) | ✅ 완료 |
| **AI 서버 프로덕션** (실제 LLM/Safety/STT/Handoff) | 🔴 미머지 (`feat/ai-server-production-modules`) |
| **통합 E2E** (실제 AI로 풀 시나리오) | ⏸️ AI 서버 머지 후 |

## 4. 머지된 PR 전체

| PR | 슬라이스 | FR |
|----|----------|-----|
| #1·#2 | 모노레포 부트스트랩 + 화면정의서 | — |
| #3 | Phase 1a 인증 | FR-001/002/015/026 |
| #4 | 안전 파이프라인 E2E (WS + Safety + RiskEvent) | FR-004/005/022 |
| #5 | 모바일 환자앱 (로그인→홈→채팅→응급) | FR-001/003/004/005/011 |
| #6 | 웹 의료진 대시보드 (read-only) | FR-015/016/017 |
| **#7** | **PHQ-9/GAD-7 + Handoff 배관 + risk PATCH** | FR-006/007/010/011/017/018/022 |
| **#8** | **AI 채팅 턴 + 진행률 (WebSocket)** | FR-004 |
| #9 | pgvector RAG 검색 계층 + grounding 계약 | (RAG) |
| #10 | 모바일 데모 화면 + 오프라인 MOCK | FR-013 외 |
| **#11** | **STT 음성입력 플랫폼** (transcribe·동의·48h 폐기) | FR-033~037 |
| **#12** | RAG 린트 수정 (Python CI 복구) | — |
| **#13** | 데모 준비 (시드·폐기 스케줄러·음성동의 토글·웹 테스트) | — |

> 굵게 표시한 #7·#8·#11·#12·#13이 이번 작업 세션 산출물.

## 5. 기능별 구현 상세 (플랫폼)

### 인증·권한 (FR-001/002/015/026)
- `POST /auth/register`(4-동의 분리 + 음성동의 옵트인) · `/login`(5회 실패 15분 잠금) · `/refresh`
- Argon2id(64MB/3) · AES-256-GCM(이름/연락처/비상연락처) · JWT 하드닝 · 5개 Role RBAC

### 세션·안전 (FR-003/004/005/011/022)
- `POST /sessions` + `WS /sessions/:id/chat` (C-7 핸드셰이크: 토큰 auth:connect 프레임만, Origin 화이트리스트, idempotencyKey LRU)
- 모든 유저 메시지 → `/ai/safety/classify` → 위험 등급. HIGH/CRITICAL → `risk:detected`(대화 중단), 동의 기반 `/emergency` vs `/self_hotline`
- 분류기 다운 시 보수적 MEDIUM fallback (침묵 금지)
- `PATCH /risk_events/:id` — 환자 "혼자 계신가요?" 응답(aloneStatus) 기록

### AI 채팅 진행률 (FR-004)
- 비위험 턴 → `/ai/chat/respond` → AI 메시지 저장(암호화) + `ai:complete`(progress 포함) 전송
- `sessions.progress_ratio/collected_items` 저장 · 모바일 진행률 바(70%+ 문진 안내)
- 토큰 스트리밍(`ai:token`)은 ai-server SSE 지원 시 후속

### 표준 문진 (FR-006/007)
- `POST /sessions/:id/questionnaires` — PHQ-9(0-27)/GAD-7(0-21) 채점 + severity 분류 · 모바일 phq9/gad7 화면

### Handoff 리포트 (FR-010/017/018)
- `POST /sessions/:id/submit`(202, 세션 freeze + BackgroundTasks 생성) · `GET /sessions/:id/report`(의료진)
- 문진점수·위험신호는 생성 상태와 무관하게 항상 서버 조합 · 웹 `HandoffReportView` 렌더링
- 원문 근거 인용 계약(`contracts.handoff.Citation`)

### STT 음성입력 (FR-033~037)
- `POST /stt/transcribe`(multipart) — 음성동의 게이트(403) · 매직넘버+2MB 검증 · 변환텍스트 AAD 암호화 · 자동전송 금지(FR-035) · 신뢰도<0.6→422(FR-037)
- `POST /consent/voice` 토글(가입+설정) · **48h 자동폐기**(lifespan 스케줄러 + `scripts/purge_audio.py`)
- 모바일 Push-to-Talk 녹음 UI는 `expo-av` 필요 → 미구현

### 의료진 대시보드 (FR-015/016/017)
- `GET /clinician/patients`(위험 정렬) · `/patients/:id` · `/sessions/:id` — PII 복호화 + 읽기마다 audit

## 6. DB 스키마 (Alembic)

| 마이그레이션 | 테이블 |
|------|------|
| 0001 | organizations, users, patient_profiles, consent_snapshots, audit_logs |
| 0002 | sessions, messages, risk_events |
| 0003 | questionnaire_results, handoff_reports, risk_events.alone_status/acknowledged_at |
| 0004 | sessions.progress_ratio/collected_items |
| 0005 | rag.* (pgvector 코퍼스) |
| 0006 | audio_recordings, stt_transcriptions, consent_snapshots.voice |

## 7. AI 계약 (`packages/shared-contracts`)

| 계약 | 인터페이스 | 상태 |
|------|-----------|------|
| `safety.py` | `POST /ai/safety/classify` | ✅ |
| `chat.py` | `POST /ai/chat/respond` (+ RAG `Grounding`) | ✅ |
| `handoff.py` | `POST /ai/handoff/generate` (+ `Citation`) | ✅ |
| `stt.py` | `POST /ai/stt/transcribe` (벤더 폴백체인) | ✅ |

> 플랫폼은 4개 계약을 모두 소비할 준비 완료. **AI 서버(`apps/ai-server`)가 이 계약 형태로 응답해야 실연결됨** — §9 참고.

## 8. 데모 실행 가이드

```bash
# 1. 인프라
docker compose -f infra/deploy/docker-compose.yml up -d postgres redis
# 2. 마이그레이션
cd apps/api && uv run alembic upgrade head
# 3. 시드 (의료진 1 + 환자 4 페르소나)
uv run python -m scripts.seed_demo
# 4. 서버
uv run uvicorn src.main:app --port 8000        # api
cd ../web && pnpm dev                            # 의료진 대시보드 :3000
cd ../mobile && pnpm dev                         # 환자 앱 (Expo)
```

**데모 계정** (pw: `Demo!Password-2026`)
- 의료진: `clinician@neurosync.demo`
- 환자: `minjun@demo`(경증) · `seoyeon@demo`(중등도) · `jiho@demo`(중증/위험) · `yujin@demo`(불안형)

> 모바일은 오프라인 **MOCK 모드** 지원 → 백엔드 없이도 화면 시연 가능.

## 9. 남은 작업

### 🔴 최우선 — AI 서버 통합
`feat/ai-server-production-modules` (미머지, 7 ahead/3 behind):
- 실제 멀티벤더 LLM 어댑터(Solar Pro3·K-EXAONE·A.X K1) + 에이전트(safety/handoff/evidence) + 라우팅
- **⚠️ 계약 불일치**: ai-server가 자체 `schemas/`(예: `DialogueOutput`)를 쓰고 공유 `contracts/`를 안 씀.
  머지 전 `contracts/{chat,safety,handoff,stt}`와 정합 필요.
- 작업: 계약 정합 → 최신 Master 동기화 → PR → 머지 → **통합 E2E**(채팅→문진→Handoff 실제 AI)

### 🟢 Phase 1b 마무리
- 모바일 Push-to-Talk 녹음 UI (`expo-av`) → `/stt/transcribe` 연결
- 채팅 토큰 스트리밍 `ai:token` (ai-server SSE)

### ⚪ Demo Polish (W8)
- 데모 시나리오 스크립트 · UX 마이크로카피 · 통합 회귀 테스트(Safety 5 + 시나리오 3) · 격리 데모 환경

### ⏸️ Phase 2 (데모 제외)
의료진 org-scoping(RLS) · 2FA · 감사로그 hash chain · OCR/문서 실구현 · 병원검색 실데이터 · PDF/EMR export · 알림(SMS/이메일) · 보호자 KYC

## 10. 알려진 후속 (코드 리뷰 산출)

- **의료진 org-scoping 부재** (Major, 선행 갭): 어떤 의료진이든 임의 세션/리포트 조회 가능 → 임상의 GA 전 조직 스코핑 필요 (Phase 2)
- 채팅 M-1(재접속 시 대화 복원), M-2(progress 정합성 로깅) · handoff bg-task 실패경로 테스트 · `modelUsed` 클라이언트 노출 제거
- RAG 데이터(`ontology.py`)는 ruff format 정규화 완료
