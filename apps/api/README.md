# `apps/api` — Platform API 서버

> **Owner**: Platform 팀 (단독)
> **언어/프레임워크**: Python 3.12 + FastAPI + SQLAlchemy/SQLModel + Celery
> **PRD**: [`../../docs/prd/PRD_neuro-sync.md`](../../docs/prd/PRD_neuro-sync.md) 전체 (특히 §5.1, §5.2, §5.3 Platform 블록)
> **AI 팀은 본 폴더에 PR 금지** — 인터페이스 contract 변경이 필요하면 `packages/shared-contracts/`로 합의

## 책임 범위

- 인증/RBAC/RLS/2FA/세션 (FR-001, FR-015, FR-026, FR-027, FR-031)
- DB 스키마·마이그레이션 (Alembic) — 마스터 PRD §5.2
- REST/WebSocket 게이트웨이 — 마스터 PRD §5.1
- 동의 수집 흐름·감사 로그 작성 (FR-023, FR-030)
- 파일 업로드 보안 검증 (FR-028) + S3 SSE-KMS
- 가명처리·삭제 처리 (FR-029)
- 알림 (이메일/SMS/푸시) (FR-014, FR-024)
- Celery 워커 (리포트 생성 큐, 48h 오디오 폐기 잡 — FR-036)
- **AI 서비스 호출 (HTTP 클라이언트)** — `apps/ai-server`의 5개 인터페이스 소비

## 본 폴더에서 하지 않는 것

- LLM 호출, 프롬프트 작성, Safety 분류 모델 — **`apps/ai-server` 책임**
- STT 어댑터, OCR Document Parse 호출 — **`apps/ai-server` 책임**
- Handoff Report 생성 프롬프트 — **`apps/ai-server` 책임**

## AI 서비스와의 통신

AI 서버는 별도 프로세스(같은 K8s 클러스터 또는 별도 GPU 노드). HTTP 호출:

```python
# 예시 — Platform → AI 서버
async with httpx.AsyncClient() as client:
    resp = await client.post(
        f"{AI_SERVER_URL}/ai/safety/classify",
        json={"message": pseudonymized_text, "prev_context": [...]},
        timeout=2.0,
    )
```

5개 인터페이스 시그니처는 `packages/shared-contracts/python/`의 Pydantic 모델 단일 소스.

## 디렉토리 구조 (예정)

```
apps/api/
├── pyproject.toml
├── src/
│   ├── auth/         # 인증·동의
│   ├── db/           # 모델·마이그레이션
│   ├── routes/       # REST 엔드포인트
│   ├── ws/           # WebSocket 게이트웨이
│   ├── ai_client/    # AI 서버 HTTP 클라이언트
│   ├── workers/      # Celery 태스크
│   ├── security/     # 암호화·감사 로그
│   └── main.py
├── tests/
└── alembic/          # DB 마이그레이션
```
