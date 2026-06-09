# shared-contracts/python — Pydantic 골격

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

5개 AI 인터페이스 스키마는 각각 `src/contracts/{chat,safety,stt,ocr,handoff}.py` 로 분리할 예정.
Phase 1a Day 1~2 는 패키지 골격만.
