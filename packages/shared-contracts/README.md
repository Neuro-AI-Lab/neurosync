# `packages/shared-contracts` — Platform ↔ AI 인터페이스 스키마

> **Owner**: Platform 팀 + AI Research 팀 **공동 소유** (CODEOWNERS)
> **변경 규칙**: 양 팀 리뷰 모두 통과해야 머지 — 인터페이스 contract 변경은 양 PRD(`docs/prd/PRD_neuro-sync.md` §0.3 + `docs/ai/PRD_ai.md` §1) 동시 갱신 필수

## 목적

마스터 PRD §0.3에서 정의한 **5개 AI 인터페이스**의 입출력 스키마를 단일 소스로 관리.
- `apps/api`(Platform)와 `apps/ai-server`(AI)가 동일 스키마를 import하여 contract drift 방지
- 모바일/웹은 TypeScript 버전을 통해 API 응답 타입 안전 보장

## 구조

```
packages/shared-contracts/
├── python/                 # Pydantic 모델 (apps/api·apps/ai-server 양쪽 import)
│   ├── pyproject.toml
│   └── src/contracts/
│       ├── chat.py         # /ai/chat/respond
│       ├── safety.py       # /ai/safety/classify
│       ├── stt.py          # /ai/stt/transcribe
│       ├── ocr.py          # /ai/ocr/parse
│       └── handoff.py      # /ai/handoff/generate
└── typescript/             # apps/mobile·apps/web에서 사용 (Platform API 응답 타입)
    ├── package.json
    └── src/
        ├── auth.ts
        ├── session.ts
        ├── report.ts
        └── ...
```

## 5개 AI 인터페이스 시그니처 (단일 소스)

| 인터페이스 | 입력 | 출력 |
|-----------|------|------|
| `POST /ai/chat/respond` | `ChatRequest` | `ChatResponse` (stream) |
| `POST /ai/safety/classify` | `SafetyRequest` | `SafetyResponse` |
| `POST /ai/stt/transcribe` | `STTRequest` (multipart) | `STTResponse` |
| `POST /ai/ocr/parse` | `OCRRequest` | `OCRResponse` |
| `POST /ai/handoff/generate` | `HandoffRequest` | `HandoffResponse` |

## 변경 절차

1. PR 작성 (양 팀 변경 시점에)
2. CODEOWNERS에 따라 Platform 팀 + AI 팀 리뷰어 자동 할당
3. 양 팀 PRD 갱신을 같은 PR 또는 연결된 PR로 동반
4. 두 팀 모두 approve 후 머지
5. 머지 후 `apps/api`와 `apps/ai-server` 양쪽이 pin된 버전 업데이트
