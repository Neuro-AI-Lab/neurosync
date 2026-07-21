# `apps/ai-server` — AI 서비스 (LLM / Safety / STT / OCR / Handoff)

> **Owner**: AI Research 팀 (단독)
> **언어/프레임워크**: Python 3.12 + FastAPI + LangChain/LangGraph + (vLLM 또는 외부 LLM SDK)
> **PRD**: [`../../docs/ai/PRD_task1_v2.md`](../../docs/ai/PRD_task1_v2.md)
> **계획**: [`../../docs/AI_master_plan.md`](../../docs/AI_master_plan.md)
> **Platform 팀은 본 폴더에 PR 금지** — 인터페이스 변경이 필요하면 `packages/shared-contracts/`로 합의

## 책임 범위

현재 마운트된 전체 인터페이스의 실행 기준은 [`src/main.py`](src/main.py)다. 아래 표는 주요 POST
route를 요약하며, `/ai/nearby/*` GET route도 `src/main.py`에서 마운트한다.

| 엔드포인트 | FR | SLA (p95) |
|-----------|-----|-----------|
| `POST /ai/chat/respond` | FR-004 (AI 측) | 첫 토큰 < 800ms |
| `POST /ai/safety/classify` | FR-005, FR-022 | < 1,000ms |
| `POST /ai/stt/transcribe` | FR-033, FR-037 | < 2,000ms |
| `POST /ai/ocr/parse` | FR-009 | < 10s |
| `POST /ai/handoff/generate` | FR-018 | < 30s |
| `POST /ai/handoff/report` | F4+F5 stateless export | 입력 크기·PDF 옵션에 따름 |
| `POST /ai/slots/extract` | F1 임상 슬롯 | 모델 설정에 따름 |
| `POST /ai/survey/score`, `/plan` | F3 채점·계획 | score는 zero-LLM |
| `POST /ai/domain/infer` | F2 영역 추론 | 모델 설정에 따름 |
| `POST /ai/temporal/summarize`, `/analyze` | F4 종단 분석 | analyze는 zero-LLM |
| `POST /ai/sentiment/utterance`, `/session` | 감정 분석 | 모델 설정에 따름 |

## 본 폴더에서 하지 않는 것

- 인증 검증 — Platform이 보낸 요청은 신뢰 (mTLS 또는 내부 토큰)
- DB 직접 쓰기 — 결과는 HTTP 응답으로만 반환
- 환자 식별정보 처리 — 가명처리된 텍스트만 받는다고 가정
- 감사 로그 작성 — Platform `audit_logs`에 위임

## 디렉토리 구조

```
apps/ai-server/
├── pyproject.toml
├── Dockerfile
├── src/
│   ├── agents/       # LLM·rule-based agent
│   ├── adapters/     # LLM/STT 벤더 어댑터
│   ├── routes/       # FastAPI route
│   ├── routing/      # 모델 선택·fallback
│   ├── schemas/      # AI 서버 로컬 schema
│   ├── services/     # Handoff/F4/F5 변환·export 경계
│   ├── eval/         # 평가 코드
│   ├── prompts/      # 프롬프트 로딩·버전 관리
│   ├── rag/          # in-process RAG
│   └── main.py       # 마운트된 route의 실행 기준
├── tests/
└── assets/           # F5 PDF 폰트 등 runtime asset
```

## 외부 의존성

- LLM API Key: Claude / GPT / Solar Pro 3 / KT Mi:dm / SKT A.X K1 / LG K-EXAONE (시점별 선택)
- STT: OpenAI Whisper (Phase 1b) → SK A.dot STT (계약 후)
- OCR: Upstage Document Parse
- 트레이싱 정책: [`../../docs/ai/PRD_task1_v2.md`](../../docs/ai/PRD_task1_v2.md)의 현재 구현·검증 상태를 따른다.

## 배포

별도 컨테이너. GPU 노드 또는 외부 LLM API 사용 시 CPU 노드. Platform과 같은 VPC, mTLS 또는 내부 토큰 인증.

`infra/deploy/` (Platform 관리)에 본 서비스 배포 매니페스트 위치. AI 팀은 환경변수·리소스 요구사항을 PR로 제안.
