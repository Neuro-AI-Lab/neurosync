# shared-contracts/python — Pydantic 계약 패키지

apps/api 와 apps/ai-server 양쪽에서 editable install 로 import 한다.

```toml
# apps/api/pyproject.toml
dependencies = [
  "neuro-sync-contracts",
  # ...
]

[tool.uv.sources]
neuro-sync-contracts = { path = "../../packages/shared-contracts/python", editable = true }
```

현재 계약 모듈은 `chat`, `safety`, `stt`, `slots`, `survey`, `survey_plan`, `domain`,
`longitudinal`, `handoff`다. `longitudinal`은 `/ai/temporal/analyze`와
`/ai/handoff/report`, `handoff`는 구조화된 `/ai/handoff/generate` 경계를 정의한다.
`src/contracts/py.typed`를 포함하므로 설치 소비자는 타입 정보를 사용할 수 있다.

계약 변경 시 [`docs/prd/PRD_neuro-sync.md` §0.3](../../../docs/prd/PRD_neuro-sync.md)와
[`docs/ai/PRD_task1_v2.md`](../../../docs/ai/PRD_task1_v2.md)를 함께 갱신하고 Platform·AI
CODEOWNER 리뷰를 모두 받아야 한다.
