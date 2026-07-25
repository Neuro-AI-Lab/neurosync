# `packages/shared-contracts` — Platform ↔ AI 인터페이스 스키마

> **Owner**: Platform 팀 + AI Research 팀 **공동 소유** (CODEOWNERS)
> **변경 규칙**: 양 팀 리뷰 모두 통과해야 머지 — 인터페이스 contract 변경은
> [`docs/prd/PRD_neuro-sync.md` §0.3](../../docs/prd/PRD_neuro-sync.md)와
> [`docs/ai/PRD_task1_v2.md`](../../docs/ai/PRD_task1_v2.md)를 함께 갱신해야 한다.

## 목적

마스터 PRD §0.3에서 정의한 Platform↔AI 입출력 스키마를 단일 소스로 관리한다.
- 양 앱이 공유 모델을 채택한 경계에서 동일 스키마를 import해 contract drift를 방지한다. 현재 route
  adoption 상태는 아래 인벤토리에 별도로 표시한다.
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
│       ├── slots.py        # /ai/slots/extract
│       ├── survey.py       # /ai/survey/score
│       ├── survey_plan.py  # /ai/survey/plan
│       ├── domain.py       # /ai/domain/infer
│       ├── longitudinal.py # /ai/temporal/analyze + /ai/handoff/report
│       ├── handoff.py      # /ai/handoff/generate
│       └── py.typed        # PEP 561 typing marker
└── typescript/             # apps/mobile·apps/web에서 사용 (Platform API 응답 타입)
    ├── package.json
    └── src/
        ├── auth.ts
        ├── session.ts
        ├── report.ts
        └── ...
```

## Python 계약 인벤토리

| 인터페이스 | 입력 | 출력 |
|-----------|------|------|
| `POST /ai/chat/respond` | `ChatRequest` | `ChatResponse` (non-streaming full reply) |
| `POST /ai/safety/classify` | `SafetyRequest` | `SafetyResponse` |
| `POST /ai/stt/transcribe` | `STTRequest` (base64 audio) | `STTResponse` |
| `POST /ai/slots/extract` | `SlotsExtractRequest` | `SlotsExtractResponse` |
| `POST /ai/survey/score` | `SurveyScoreRequest` | `SurveyScoreResponse` |
| `POST /ai/survey/plan` | `SurveyPlanRequest` | `SurveyPlanResponse` |
| `POST /ai/domain/infer` | `DomainInferRequest` | `DomainInferResponse` |
| `POST /ai/temporal/analyze` | `TemporalAnalyzeRequest` | AI 서버 `LongitudinalAnalysisOutput` |
| `POST /ai/handoff/generate` | `HandoffRequest` | `HandoffResponse` |
| `POST /ai/handoff/report` | `HandoffReportRequest` | `HandoffReportResponse` |

이 표는 패키지에 출하된 계약 모델의 인벤토리다. 일부 기존 라우트는 아직 `apps/ai-server/src/schemas/`
모델을 사용한다. 실제 마운트된 전체 엔드포인트는
[`apps/ai-server/src/main.py`](../../apps/ai-server/src/main.py)가 기준이다.

### Handoff 계약 주의사항

- `/ai/handoff/generate`는 구조화된 공식 `HandoffRequest`/`HandoffResponse` 경계다. 채워진 scalar와
  `sleep_appetite_activity` leaf마다 해당 field 인용이 필요하고, `symptoms[i]`, `triggers[i]`,
  `clinician_attention[i]`는 항목별 zero-based target이 필요하다. metadata·container·빈 target은
  인용 대상이 아니다.
- `Citation`은 대화 `message_id`만 가리킬 수 있다. 문서 source ID가 계약에 추가되기 전까지
  `documents_summary`는 빈 배열이어야 한다.
- AI 서버는 설정된 primary→secondary→fallback 순서로 최대 세 번 시도한다. transport 실패나 계약
  불일치는 해당 tier의 실패로 기록하고, JSON·공식 응답·인용 검증을 모두 통과한 뒤에만 성공으로
  기록한다.
- `/ai/handoff/report`의 A8 호환 경계는 `narrative_enabled=false`, `narrative_text=null`뿐이다.
  과거에 수용되던 `true/null`, `true/text`, `false/text` 조합은 이제 422로 거부된다. 이 메모는 현재
  동작의 migration 안내이며 별도 semver·deprecation 정책을 만들지 않는다.

## 변경 절차

1. PR 작성 (양 팀 변경 시점에)
2. CODEOWNERS에 따라 Platform 팀 + AI 팀 리뷰어 자동 할당
3. 양 팀 PRD 갱신을 같은 PR 또는 연결된 PR로 동반
4. 두 팀 모두 approve 후 머지
5. 머지 후 `apps/api`와 `apps/ai-server` 양쪽이 pin된 버전 업데이트

현재 변경에 대한 Platform·AI CODEOWNER 승인은 아직 획득된 것으로 간주하지 않는다. PR 리뷰에서
두 owner의 승인이 남아 있다.
