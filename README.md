# Neuro-Sync — 정신과 사전 진료 Handoff 시스템

> AI 챔피언 대회 출품 · Korean PIPA + 의료법 + 자살예방법 기반 PoC/파일럿

## 워크스페이스 분리

본 프로젝트는 **Platform 팀**과 **AI Research 팀**이 분리된 워크스페이스에서 병행 작업한다.
경계 정책은 [`docs/prd/PRD_neuro-sync.md` §0 Ownership Matrix](./docs/prd/PRD_neuro-sync.md)와 [`.github/CODEOWNERS`](./.github/CODEOWNERS)가 단일 소스.

```
neuro-sync/
├── docs/
│   ├── prd/PRD_neuro-sync.md        Platform 마스터 PRD
│   ├── todo_plan/PLAN_neuro-sync.md Platform 마스터 PLAN
│   └── ai/                          🤖 AI Research 워크스페이스
│       ├── README.md                AI 진입점 + Boundary Contract
│       ├── PRD_ai.md                AI 도메인 PRD
│       ├── PLAN_ai.md               AI 팀 계획
│       ├── AI_API_가이드.md         5종 벤더 가이드
│       ├── orchestration/ prompts/ safety_guard/ stt/ ocr/ eval/
├── apps/
│   ├── api/                         Platform — FastAPI 백엔드 (Auth/DB/WS/Workers)
│   ├── ai-server/                   🤖 AI — FastAPI AI 서비스 (5개 인터페이스)
│   ├── mobile/                      Platform — React Native (환자 앱)
│   └── web/                         Platform — Next.js (의료진 대시보드)
├── packages/
│   └── shared-contracts/            ⚖️ 공유 — Pydantic + TypeScript 인터페이스 스키마
├── infra/                           Platform — 배포/CI/시크릿
├── tools/                           공유 dev 스크립트
├── references/                      원본 자료 (read-only)
└── .github/CODEOWNERS               자동 리뷰어 할당
```

## 팀별 진입점

### Platform 팀
1. [`docs/prd/PRD_neuro-sync.md`](./docs/prd/PRD_neuro-sync.md) — 마스터 PRD
2. [`docs/todo_plan/PLAN_neuro-sync.md`](./docs/todo_plan/PLAN_neuro-sync.md) — 마스터 PLAN
3. `apps/api/`, `apps/mobile/`, `apps/web/`, `infra/`

### AI Research 팀
1. [`docs/ai/README.md`](./docs/ai/README.md) — AI 워크스페이스 진입점
2. [`docs/ai/PRD_ai.md`](./docs/ai/PRD_ai.md) — AI 도메인 PRD
3. [`docs/ai/PLAN_ai.md`](./docs/ai/PLAN_ai.md) — AI 팀 계획
4. `apps/ai-server/`

## 통신 아키텍처

```
Mobile / Web ──HTTPS──> apps/api ──HTTP(internal)──> apps/ai-server ──> 외부 LLM/STT/OCR
                              │
                              ├──> PostgreSQL (Platform 단독 소유)
                              ├──> Redis (Celery)
                              └──> S3 SSE-KMS (오디오·문서)
```

- 모바일/웹은 **Platform API만** 호출 (AI 서버 직접 접근 금지)
- AI 서버는 **DB 직접 접근 금지** — 결과는 HTTP 응답으로만 반환
- 5개 AI 인터페이스 스키마는 `packages/shared-contracts/`가 단일 소스

## 인터페이스 변경 절차

`packages/shared-contracts/` 변경 시:
1. CODEOWNERS에 따라 양 팀 리뷰어 자동 할당
2. [`docs/prd/PRD_neuro-sync.md` §0.3](./docs/prd/PRD_neuro-sync.md) + [`docs/ai/PRD_ai.md` §1](./docs/ai/PRD_ai.md) 동시 갱신
3. 양 팀 approve 후 머지
4. `apps/api`·`apps/ai-server`가 버전 업데이트

## 현재 단계

**Phase 0 차단 게이트** — 코드 작성 전 (마스터 PLAN 참조). 본 README는 진입 직전 골격.
