"""Neuro-Sync shared contracts (Python).

AI 인터페이스의 Pydantic 모델 단일 소스.
docs/prd/PRD_neuro-sync.md §0.3 + docs/ai/PRD_task1_v2.md 동기 갱신 필수.

계약 모듈:
- chat: POST /ai/chat/respond
- safety: POST /ai/safety/classify
- stt: POST /ai/stt/transcribe
- slots: POST /ai/slots/extract
- survey: POST /ai/survey/score
- survey_plan: POST /ai/survey/plan
- domain: POST /ai/domain/infer
- longitudinal: POST /ai/temporal/analyze + POST /ai/handoff/report
- handoff: POST /ai/handoff/generate
"""

__version__ = "0.1.0"
