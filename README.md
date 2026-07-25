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
│   ├── AI_master_plan.md            AI 전체 개발 계획
│   └── ai/                          🤖 AI Research 워크스페이스
│       ├── PRD_task1_v2.md          Task 1 활성 AI PRD
│       ├── checklist_task1.md       Task 1 개발·검증 체크리스트
│       └── agents/ prompts/ api/ personas/
├── apps/
│   ├── api/                         Platform — FastAPI 백엔드 (Auth/DB/WS/Workers)
│   ├── ai-server/                   🤖 AI — FastAPI AI 서비스
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
1. [`docs/AI_master_plan.md`](./docs/AI_master_plan.md) — AI 전체 개발 계획
2. [`docs/ai/PRD_task1_v2.md`](./docs/ai/PRD_task1_v2.md) — Task 1 활성 AI PRD
3. [`docs/ai/checklist_task1.md`](./docs/ai/checklist_task1.md) — Task 1 개발·검증 체크리스트
4. `apps/ai-server/`

## 통신 아키텍처

```
Mobile / Web ──HTTPS──> apps/api ──HTTP(internal)──> apps/ai-server ──> 외부 LLM/STT/OCR
                              │
                              ├──> PostgreSQL (Platform 단독 소유)
                              └──> S3 SSE-KMS (오디오·문서)
```

- 모바일/웹은 **Platform API만** 호출 (AI 서버 직접 접근 금지)
- AI 서버는 **DB 직접 접근 금지** — 결과는 HTTP 응답으로만 반환
- Platform↔AI 공유 스키마는 `packages/shared-contracts/`가 단일 소스다. 실제 마운트된 AI 서버
  엔드포인트 목록은 [`apps/ai-server/src/main.py`](./apps/ai-server/src/main.py)를 기준으로 한다.

## 인터페이스 변경 절차

`packages/shared-contracts/` 변경 시:
1. CODEOWNERS에 따라 양 팀 리뷰어 자동 할당
2. [`docs/prd/PRD_neuro-sync.md` §0.3](./docs/prd/PRD_neuro-sync.md) +
   [`docs/ai/PRD_task1_v2.md`](./docs/ai/PRD_task1_v2.md) 동시 갱신
3. 양 팀 approve 후 머지
4. `apps/api`·`apps/ai-server`가 버전 업데이트

현재 변경도 이 절차의 예외가 아니다. Platform·AI CODEOWNER 승인은 PR 리뷰에서 받아야 하며,
이 문서 갱신 자체가 승인을 획득했다는 뜻은 아니다.

## 현재 단계

현재 구현·검증 상태는 [`docs/ai/PRD_task1_v2.md`](./docs/ai/PRD_task1_v2.md)와 기능별 체크리스트를
기준으로 확인한다. 과거 Phase 표나 완료 표시는 해당 문서에 기록된 증거 범위 안에서만 해석한다.
