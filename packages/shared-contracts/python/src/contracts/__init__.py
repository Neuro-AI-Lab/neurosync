"""Neuro-Sync shared contracts (Python).

AI 인터페이스의 Pydantic 모델 단일 소스.
PRD §0.3 + docs/ai/PRD_ai.md §1 동기 갱신 필수.

Phase 1:
- chat: POST /ai/chat/respond
- safety: POST /ai/safety/classify
- stt: POST /ai/stt/transcribe
- ocr: POST /ai/ocr/parse
- handoff: POST /ai/handoff/generate

v3 추가 (PRD_frontend_v3 §6-A / 미결 #8):
- survey: POST /ai/survey/score      — 결정론적 채점 5종 (FR-040)
- domain: POST /ai/domain/infer      — F2 도메인 추정, Stage 2 전용 (FR-039)
- slots:  POST /ai/slots/extract     — F1 임상 슬롯 추출
"""

__version__ = "0.1.0"
