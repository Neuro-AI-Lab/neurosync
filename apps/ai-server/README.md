# `apps/ai-server` — AI 서비스 (LLM / Safety / STT / OCR / Handoff)

> **Owner**: AI Research 팀 (단독)
> **언어/프레임워크**: Python 3.12 + FastAPI + LangChain/LangGraph + (vLLM 또는 외부 LLM SDK)
> **PRD**: [`../../docs/ai/PRD_ai.md`](../../docs/ai/PRD_ai.md)
> **계획**: [`../../docs/ai/PLAN_ai.md`](../../docs/ai/PLAN_ai.md)
> **Platform 팀은 본 폴더에 PR 금지** — 인터페이스 변경이 필요하면 `packages/shared-contracts/`로 합의

## 책임 범위

5개 HTTP 인터페이스를 구현한다 (`docs/ai/README.md` §3.1).

| 엔드포인트 | FR | SLA (p95) |
|-----------|-----|-----------|
| `POST /ai/chat/respond` | FR-004 (AI 측) | 첫 토큰 < 800ms |
| `POST /ai/safety/classify` | FR-005, FR-022 | < 1,000ms |
| `POST /ai/stt/transcribe` | FR-033, FR-037 | < 2,000ms |
| `POST /ai/ocr/parse` | FR-009 | < 10s |
| `POST /ai/handoff/generate` | FR-018 | < 30s |

## 본 폴더에서 하지 않는 것

- 인증 검증 — Platform이 보낸 요청은 신뢰 (mTLS 또는 내부 토큰)
- DB 직접 쓰기 — 결과는 HTTP 응답으로만 반환
- 환자 식별정보 처리 — 가명처리된 텍스트만 받는다고 가정
- 감사 로그 작성 — Platform `audit_logs`에 위임

## 디렉토리 구조 (예정)

```
apps/ai-server/
├── pyproject.toml
├── Dockerfile
├── src/
│   ├── chat/         # /ai/chat/respond
│   ├── safety/       # /ai/safety/classify (키워드 + LLM 분류기)
│   ├── stt/          # STT Adapter (A.dot / Whisper / Whisper Local)
│   ├── ocr/          # Upstage Document Parse 클라이언트 + 후처리
│   ├── handoff/      # Handoff Report 생성 + 인용 검증
│   ├── orchestration/  # 멀티 LLM 라우팅 (Post-MVP)
│   ├── prompts/      # 프롬프트 로딩·버전 관리 (docs/ai/prompts와 sync)
│   ├── adapters/     # LLM/STT 벤더 어댑터
│   └── main.py
├── tests/
└── eval/             # docs/ai/eval과 sync — 회귀 테스트
```

## 외부 의존성

- LLM API Key: Claude / GPT / Solar Pro 3 / KT Mi:dm / SKT A.X K1 / LG K-EXAONE (시점별 선택)
- STT: OpenAI Whisper (Phase 1b) → SK A.dot STT (계약 후)
- OCR: Upstage Document Parse
- 트레이싱: LangSmith (또는 자체) — `docs/ai/PRD_ai.md` AI-5 결정 후

## 배포

별도 컨테이너. GPU 노드 또는 외부 LLM API 사용 시 CPU 노드. Platform과 같은 VPC, mTLS 또는 내부 토큰 인증.

`infra/deploy/` (Platform 관리)에 본 서비스 배포 매니페스트 위치. AI 팀은 환경변수·리소스 요구사항을 PR로 제안.
