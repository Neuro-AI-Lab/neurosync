# `docs/ai/` — AI Research 팀 워크스페이스

> **Owner**: AI Research 팀 (LLM / Orchestration / Safety / STT / OCR)
> **Sister workspace**: Platform 팀(BE/FE/Infra/Security)은 `docs/prd/PRD_neuro-sync.md` 마스터 PRD + 루트 코드 트리에서 작업
> **공유 자료**: 프로젝트 루트 `references/*.pdf`(원본 PDF) — read-only

---

## 1. 책임 범위

AI 팀이 단독 소유하는 영역:

| 영역 | 담당 FR | 산출물 위치 |
|------|---------|------------|
| **멀티 LLM 오케스트레이션** (K-EXAONE / Solar Pro 3 / A.X K1 / Mi:dm) | FR-018 (Handoff Report 생성) | `orchestration/` |
| **프롬프트 라이브러리** (시스템 프롬프트, 임상 요약, 후속 질문 생성) | FR-004, FR-018 | `prompts/` |
| **Safety Guard** (위험 발화 실시간 감지: 키워드 + LLM 분류) | FR-005, FR-011, FR-022, FR-032 | `safety_guard/` |
| **STT 어댑터** (SK A.dot STT Primary / Whisper Fallback) | FR-033, FR-035, FR-037 | `stt/` |
| **OCR 파이프라인** (Upstage Document Parse 통합 + 후처리) | FR-009 | `ocr/` |
| **AI 평가** (Recall ≥95%, Precision ≥80%, Cohen's κ ≥0.7, BLEU/ROUGE 등) | §7 Success Metrics 중 AI 지표 | `eval/` |

AI 팀이 **건드리지 않는** 영역 (Platform 담당):
- Auth / RBAC / RLS / 2FA / 세션 타임아웃
- DB 스키마 (단, AI 결과를 저장하는 컬럼 추가 요청은 PR로 제안)
- API 서버 라우팅 / WebSocket 전송 / Rate Limiting
- 모바일 앱 UI / Next.js 대시보드 UI
- 동의 수집 UX / 감사 로그 인프라 / 파일 업로드 보안
- 가명처리 / 데이터 삭제 / 컴플라이언스

---

## 2. 폴더 구조

### 2.1 AI 팀 문서 워크스페이스

```
docs/ai/
├── README.md              # ← 본 문서 (진입점)
├── PRD_ai.md              # AI 도메인 PRD (마스터 PRD의 AI 영역 상세화)
├── PLAN_ai.md             # AI 팀 작업 계획
├── AI_API_가이드.md       # 5개 벤더 LLM/API 통합 가이드 (KT/LG/NC/SKT/Upstage)
├── orchestration/         # 멀티 LLM 라우팅·플로우 설계
├── prompts/               # 프롬프트 버전 관리 (system, summarize, follow-up, eval)
├── safety_guard/          # 위험 감지 모듈: 라벨 데이터, 임계값, 모델 카드
├── stt/                   # STT 어댑터 구현 사양, 벤더 비교 리포트
├── ocr/                   # Document Parse 호출·후처리 사양
└── eval/                  # 테스트셋, 메트릭, 회귀 테스트 결과
```

### 2.2 AI 팀 코드 워크스페이스

```
apps/ai-server/            # ← AI 팀 단독 — 5개 인터페이스 구현
├── README.md              # apps/ai-server 진입점 (책임 범위·디렉토리·시크릿)
├── pyproject.toml
├── Dockerfile
├── src/
│   ├── chat/              # /ai/chat/respond
│   ├── safety/            # /ai/safety/classify
│   ├── stt/               # STT Adapter (A.dot / Whisper / Whisper Local)
│   ├── ocr/               # Upstage Document Parse 통합
│   ├── handoff/           # Handoff Report 생성 + 인용 검증
│   ├── orchestration/     # Post-MVP 멀티 LLM
│   ├── prompts/           # docs/ai/prompts와 sync
│   ├── adapters/          # LLM/STT 벤더 어댑터
│   └── main.py
├── tests/
└── eval/                  # docs/ai/eval과 sync
```

### 2.3 공유 영역 (양 팀 리뷰 필수)

```
packages/shared-contracts/  # 5개 인터페이스 Pydantic + TS 스키마 (단일 소스)
├── python/                # apps/api·apps/ai-server 양쪽 import
└── typescript/            # apps/mobile·apps/web에서 사용
```

---

## 3. Platform ↔ AI 인터페이스 Contract

AI는 **순수 함수형 서비스**로 동작한다. Platform이 입력을 주면 AI가 출력을 반환한다. AI는 DB·인증·세션을 직접 다루지 않는다.

### 3.1 AI가 제공하는 인터페이스

| 인터페이스 | 입력 | 출력 | SLA |
|-----------|------|------|-----|
| **`POST /ai/chat/respond`** | `{messages, sessionContext}` | `{text(stream), tokens, modelUsed, latencyMs}` | 첫 토큰 < 800ms (p95) |
| **`POST /ai/safety/classify`** | `{message, prevContext}` | `{risk_level: low/medium/high/critical, evidence, confidence}` | < 1,000ms (p95) — FR-005 핵심 SLA |
| **`POST /ai/stt/transcribe`** | `{audio(opus/pcm), lang, prevContext}` | `{text, confidence, vendor, fallback_chain}` | < 2,000ms (p95) — FR-033 |
| **`POST /ai/ocr/parse`** | `{file_url(s3), doc_type}` | `{text, structured_blocks, confidence}` | < 10s (p95) — FR-009 |
| **`POST /ai/handoff/generate`** | `{session_id, messages, phq9, gad7, doc_texts, risk_events}` | `{report_markdown, citations[{section, message_id}], model_used}` | < 30s (p95) — FR-018 |

### 3.2 Platform이 제공하는 인터페이스

| 인터페이스 | 제공 데이터 | 사용처 |
|-----------|-----------|--------|
| Auth context (JWT decoded) | `{user_id, role, org_id, consents}` | AI 응답 필터링, 동의 확인 |
| Message history | `messages[]` (가명처리된 텍스트) | LLM 컨텍스트 입력 |
| File storage (S3 SSE-KMS) | `presigned_url` | OCR / STT 원본 가져오기 |
| Audit log writer | `audit_log.write(actor, action, target)` | AI 호출도 감사 대상 |
| Consent verification | `consents.voice / consents.sensitive` | STT/LLM 호출 전 사전 확인 |

### 3.3 데이터 격리 원칙

- **PHI 마스킹 책임**: Platform이 LLM 호출 전 가명처리 완료된 텍스트만 전달. AI 팀은 입력 데이터에 직접식별자(이름/주민번호/연락처)가 없다고 신뢰.
- **DB 직접 접근 금지**: AI 서비스는 PostgreSQL에 직접 쓰지 않음. 결과는 응답으로만 반환, Platform이 저장.
- **외부 LLM 호출**: AI 팀 책임. 단, 벤더별 위·수탁 계약·국내 데이터 잔류 확인은 Platform 법무 협업.
- **로그**: AI 호출 로그(모델/지연/토큰/오류)는 AI 팀이 자체 관측. 사용자 식별 로그(`audit_logs`)는 Platform이 작성.

---

## 4. 작업 규칙

1. **AI 팀이 수정 가능 (단독)**:
   - `docs/ai/**` 전체
   - `apps/ai-server/**` 전체
   - 마스터 PRD `§3` FR 표의 Owner=AI 행 텍스트, §5.3 Architecture Diagram의 AI 블록
2. **AI 팀이 수정 가능 (공유 — 양 팀 리뷰)**:
   - `packages/shared-contracts/**` (인터페이스 스키마)
   - 마스터 PRD `§0.3` 인터페이스 contract 표
3. **AI 팀이 수정 금지**:
   - `apps/api/`, `apps/mobile/`, `apps/web/`, `infra/`
   - 마스터 PRD의 Auth/DB/Security/Consent 섹션
   - `docs/todo_plan/PLAN_neuro-sync.md`의 Platform task
4. **인터페이스 변경 시**: `packages/shared-contracts/` PR + 마스터 PRD §0.3 갱신 + 본 PRD_ai 갱신을 같은 PR로 묶음.
5. **벤더 라이선스/계약 정보**: `AI_API_가이드.md`에 최신 상태 반영. Platform 법무 검토 결과는 마스터 PRD §4.5에서 가져옴.
6. **AI 평가 데이터셋**: `eval/` 폴더. 환자 실제 데이터는 가명처리된 derivative만 사용, 원본 절대 금지.
7. **AI 시크릿 (LLM/STT/OCR Key)**: AI 팀이 발급, [`infra/`](../../infra/README.md) Secret Manager에 등록 PR로 요청.

---

## 5. 진행 중인 결정 (AI 팀 책임 Open Questions)

마스터 PRD §8.2와 별도로, AI 팀이 단독 결정해야 할 Open Question은 `PRD_ai.md` §8에서 관리.

대표:
- MVP 단일 LLM 선택 (Claude / GPT / Solar Pro 3 / Mi:dm)
- Safety Guard 위험 임계값 (정신과 자문의와 협업 필요 → Platform Phase 0와 연계)
- STT Primary 채택 시점 (A.dot 계약 종속, Platform과 공동)
- 멀티 LLM 도입 시점 (Phase 2 vs 3)

---

## 6. 관련 문서

- **마스터 PRD** (Platform 주도): [`../prd/PRD_neuro-sync.md`](../prd/PRD_neuro-sync.md)
- **마스터 PLAN** (Platform 주도): [`../todo_plan/PLAN_neuro-sync.md`](../todo_plan/PLAN_neuro-sync.md)
- **AI PRD**: [`PRD_ai.md`](./PRD_ai.md)
- **AI PLAN**: [`PLAN_ai.md`](./PLAN_ai.md)
- **AI API 가이드**: [`AI_API_가이드.md`](./AI_API_가이드.md)
- **원본 PDF**: 프로젝트 루트 `references/*.pdf` (read-only)
