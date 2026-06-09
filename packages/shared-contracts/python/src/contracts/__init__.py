"""Neuro-Sync shared contracts (Python).

5개 AI 인터페이스의 Pydantic 모델 단일 소스.
PRD §0.3 + docs/ai/PRD_ai.md §1 동기 갱신 필수.

- chat: POST /ai/chat/respond
- safety: POST /ai/safety/classify
- stt: POST /ai/stt/transcribe
- ocr: POST /ai/ocr/parse
- handoff: POST /ai/handoff/generate

본 골격은 Phase 1a Day 1~2 부트스트랩에 한정. 실제 스키마는 각 인터페이스 구현 시점에 채운다.
"""

__version__ = "0.1.0"
