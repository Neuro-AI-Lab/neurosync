# 개발 환경 / 협업 아키텍처 가이드

> 대상: 3인 협업 — **A**(ai-server 파이프라인·프롬프트) / **B**(web·mobile) / **C**(api·alembic·DB 스키마)
> 목적: 온보딩 + 트러블슈팅. 각자 이 문서를 읽고 자기 `.env`/연결 설정을 스스로 고칠 수 있어야 한다.
> 원칙: 실 IP·UUID·비밀값은 이 문서에 절대 적지 않는다 — 전부 `<placeholder>`. 실제 값은 각자의 gitignored `.env`에만 있다.
> 모든 구체 사실(포트/서비스명/env 키/경로)은 아래에서 파일 경로와 함께 인용한다 — 이 문서 자체를 소스로 믿지 말고, 코드/설정이 어긋나면 코드가 항상 우선이다.

---

## 목차

1. [서비스 토폴로지](#1-서비스-토폴로지)
2. [협업 seam + 소유 경계](#2-협업-seam--소유-경계)
3. [개발 환경 3-tier](#3-개발-환경-3-tier)
4. [자격증명·보안 표준](#4-자격증명보안-표준)
5. [개발자별 세팅 수정 how-to](#5-개발자별-세팅-수정-how-to)

---

## 1. 서비스 토폴로지

### 1.1 4계층 다이어그램

```
apps/web (Next.js)  ──┐   API_BASE_URL (http/https, :8000)
apps/mobile (Expo)   ─┤──────────────────────────────────►  apps/api (FastAPI, :8000)
                       ┘   EXPO_PUBLIC_API_BASE_URL              │
                                                                  │  DATABASE_URL
                                                                  │  (postgresql+psycopg)
                                            AI_SERVER_URL         │
                                            (http, :8001)         │
                                                  │                │
                                                  ▼                │
                                        apps/ai-server             │
                                        (FastAPI, :8001)           │
                                                  │                │
                                     DATABASE_URL │                │
                                     — RAG 전용,   │                │
                                     api 경유 아님 │                │
                                     (postgresql+asyncpg,          │
                                      ai-server 고유,               │
                                      api와 별개 연결)              │
                                                  ▼                ▼
                                          ┌──────────────────────────┐
                                          │         postgres         │
                                          │        (pgvector)        │
                                          │          :5432           │
                                          └──────────────────────────┘

apps/ai-server ──► 외부 LLM/STT 벤더 (Upstage/Friendli/SKT, UPSTAGE_API_KEY 등)
```

- web/mobile은 `apps/api`만 호출한다. ai-server·DB에 직접 접근하지 않는다(`apps/web/README.md:17-18`, `apps/mobile/README.md:20-21`: "AI는 호출하지 않음... 모든 호출은 Platform API 경유").
- `apps/api` → `apps/ai-server`는 5개 핵심 인터페이스(chat/safety/stt/ocr/handoff, `packages/shared-contracts`가 계약 단일 소스) 경유. `AI_SERVER_URL` 하나의 env 값으로 지정된다(`infra/deploy/docker-compose.yml:41`: `AI_SERVER_URL: http://ai-server:8001`).
- **중요:** postgres에 들어가는 연결점은 하나가 아니라 **둘**이다. `apps/api`가 자신의 `DATABASE_URL`로 접속하고(드라이버 `postgresql+psycopg`, `docker-compose.yml:40`), RAG 기능이 이전되면서 `apps/ai-server`도 **자기 자신의 `DATABASE_URL`**로 postgres에 직접 접속한다(드라이버 `postgresql+asyncpg`, `apps/ai-server/src/config.py:77-79`; 세션메이커 구성은 `apps/ai-server/src/dependencies.py:66-77` `get_sessionmaker()`). api를 경유하지 않는다 — F2의 `retrieve_domain_chunks`(`apps/ai-server/src/f2.py:176-180`)와 `src/rag_chat.py`의 `retrieve_grounding()` 호출이 각각 `get_sessionmaker()`로 직접 DB 세션을 연다. **RAG는 이제 HTTP 라우트로 노출되지 않으며, 앞으로도 노출되지 않는다** — 개발·배포 단계 모두 in-process 전용 기능이며, 구 `src/rag/route.py`/`auth.py`(그리고 `POST /ai/rag/grounding`)는 영구 삭제되었다(`ADR-019`, 2026-07-09 — `main.py`에 라우터 마운트 없음, 파일 자체가 트리에 없음).
  - 참고: `apps/ai-server/src/rag/README.md`와 루트 `README.md:47-59`는 아직 "DB 접근은 apps/api 단독"이라는 예전 아키텍처를 서술하고 있는데, 이는 `apps/ai-server/src/main.py:13-16`의 모듈 docstring("RAG is in-process only, now and at deployment — there is no RAG HTTP API")과 `apps/ai-server/pyproject.toml:15` 주석("RAG 이전 — DB 직접 접속 + 컬럼 암호화")이 보여주는 실제 코드와 어긋난다. 이 문서는 코드 기준(현재: ai-server도 DB 직접 접속, RAG는 in-process 전용)으로 작성했다 — 두 README는 이 미션의 쓰기 범위 밖이라 고치지 않았다.

### 1.2 "DB를 다른 워크스테이션으로 옮겨도 연결문자열만 바꾸면 된다"의 성립 조건

이 원칙은 이 프로젝트가 지키기로 한 규율("모든 서비스 간 연결은 env DSN/URL 단일 지점 — 코드/이미지에 호스트·자격증명 하드코딩 금지")이 실제로 지켜질 때만 성립한다. 구체적으로 4가지 조건이 필요하다.

1. **코드에 호스트/자격증명이 하드코딩되어 있지 않아야 한다.** 과거 한 번 이 규율이 깨진 적이 있다 — `rag_chat.py`가 접속 정보를 파일에 직접 박아 넣었던 사례(§4에서 상술). 지금은 고쳐졌지만, 새 코드를 짤 때마다 이 조건이 다시 깨지지 않는지가 첫 번째 전제다.
2. **연결점이 하나가 아니라 둘이라는 것을 알아야 한다.** §1.1에서 본 대로 postgres를 바라보는 `DATABASE_URL`은 `apps/api`용과 `apps/ai-server`용이 독립적으로 존재한다. DB를 옮기면 이 둘을 **모두** 바꿔야 한다 — 하나만 바꾸면 나머지 서비스는 옛 위치를 계속 바라본다.
3. **네트워크로 실제 도달 가능해야 한다.** compose의 서비스 DNS(`postgres`, `ai-server` 등)는 compose 네트워크 안에서만 풀린다. 워크스테이션을 진짜로 옮기는 경우, 대상 호스트의 포트가 열려 있거나(현재는 아님 — 아래 참고) SSH 터널이 필요하다.
4. **DB 이미지 자체가 연결문자열을 따라가지 않는다.** postgres 이미지는 반드시 `pgvector/pgvector:pg16`이어야 한다 — 일반 `postgres` 이미지면 `rag` 스키마를 만드는 alembic 0005 마이그레이션이 `CREATE EXTENSION vector`에서 실패한다(`docker-compose.yml:16` 주석; `infra/deploy/k8s/postgres/postgres.yaml:1-4,44`). 연결문자열만 바꿔서 "다른 DB"를 가리키게 해도, 그 DB가 pgvector 확장을 가진 인스턴스가 아니면 RAG 관련 기능은 깨진다.

**현재 상태(보완사항):** `infra/deploy/docker-compose.yml`의 `ai-server` 서비스 environment 블록에는 `LOG_LEVEL: info` 하나만 있고 `DATABASE_URL`이 없다(`docker-compose.yml:58-59`, `api` 서비스의 `:40`과 대조). 즉 `docker compose up ai-server`로 띄우면 ai-server는 `.env`도 compose env도 없이 `config.py`의 내장 기본값 `postgresql+asyncpg://neurosync:dev@localhost:5432/neurosync`(`config.py:78`)로 접속을 시도한다. 이 기본값은 ai-server가 **컨테이너가 아니라 호스트에서 직접 실행되고, postgres가 그 호스트의 `127.0.0.1:5432`(compose가 바인딩하는 위치, `docker-compose.yml:22-23`)에 떠 있을 때만** 우연히 맞아떨어진다 — 이것이 지금까지 "ai-server와 DB가 같은 워크스테이션에 있어야만 동작"했던 정확한 메커니즘이다. §3의 Shared-Dev tier가 이 결합을 푸는 해법이다.

부수적으로 하나 더: `apps/ai-server`의 Dockerfile(`Dockerfile:15-19`, `COPY` 대상: `packages/shared-contracts/python`, `pyproject.toml`, `src`, `tests`)과 compose의 volume 마운트(`docker-compose.yml:62-64`, `src`/`tests`만 마운트)는 둘 다 `docs/`를 포함하지 않는다. `PROMPTS_BASE_DIR`의 기본값(`docs/ai/prompts`, `config.py:71-74`)과 F2 산출물 경로(`docs/ai/simulation_results/`)는 이 때문에 컨테이너화된 ai-server 안에서는 접근 불가능하다 — §5-A 트러블슈팅 참고.

---

## 2. 협업 seam + 소유 경계

### 2.1 `packages/shared-contracts` — 계약 단일 소스

```
packages/shared-contracts/
├── python/    # Pydantic 모델 — apps/api·apps/ai-server 양쪽이 import (편집가능 설치, Dockerfile:15,21-22)
└── typescript/ # apps/web·apps/mobile이 쓰는 응답 타입
```

5개 AI 인터페이스(`chat`, `safety`, `stt`, `ocr`, `handoff`)의 입출력 스키마가 여기서 한 번만 정의된다(`packages/shared-contracts/README.md:33-41`). `apps/api`와 `apps/ai-server`는 이 패키지를 각자 pin해서 쓴다(`apps/ai-server/pyproject.toml:12,32-33`: `neuro-sync-contracts`를 `../../packages/shared-contracts/python`에서 editable로 설치).

### 2.2 소유 경계

| 영역 | 담당 | 코드/문서 경로 | CODEOWNERS |
|:--|:--|:--|:--|
| ai-server 파이프라인·에이전트·프롬프트 | **A** | `apps/ai-server/src/{agents,routes,f1.py,f2.py,...}`, `docs/ai/prompts/` | `@ai-team` (`.github/CODEOWNERS:22`) |
| web 대시보드 | **B** | `apps/web` | `@platform-team` (`:18`) |
| mobile 앱 | **B** | `apps/mobile` | `@platform-team` (`:17`) |
| api 백엔드·alembic·DB 스키마 | **C** | `apps/api/{src,alembic}` | `@platform-team` (`:16`) |
| RAG 코퍼스 적재/임베딩 tooling | 코드 소유 A, 실무 운영 C | `apps/ai-server/src/rag/tooling/` | `@ai-team` |
| shared-contracts | 공동 | `packages/shared-contracts/` | `@platform-team @ai-team` (`:25`) |

한 가지 어긋나 보이는 지점을 미리 밝힌다: CODEOWNERS는 팀을 `@platform-team`(api+web+mobile)과 `@ai-team`(ai-server) 둘로만 나눈다 — 이 문서가 쓰는 B/C 구분은 그 안에서 3인이 실무를 나눈 것이지 CODEOWNERS가 강제하는 경계가 아니다. 또한 코퍼스 적재 스크립트(`rag/tooling/*.py`)는 물리적으로 `apps/ai-server/` 밑(A 소유 디렉터리)에 있지만, DB 스키마·데이터와 맞물려 있어 실제로는 C가 돌리는 경우가 많다 — 이 스크립트를 고칠 때는 A에게 알린다.

### 2.3 누가 무엇을 노출/소비하는가

- **A**는 5개 핵심 인터페이스 + `/ai/domain/infer`(`apps/ai-server/src/main.py:44-53`)를 HTTP로 노출한다. RAG에는 HTTP 라우트가 없다 — 개발·배포 단계 모두 in-process 전용 기능이다(`ADR-019`, §4 참고). postgres(RAG 전용, §1.1)와 외부 LLM 벤더를 소비한다.
- **C**는 REST/WS 게이트웨이(`apps/api`)를 노출한다. A의 5개 인터페이스(`AI_SERVER_URL` 경유), postgres(자신의 `DATABASE_URL`)를 소비한다. `apps/api/README.md:6`: "AI 팀은 본 폴더에 PR 금지" — 인터페이스 변경은 `packages/shared-contracts`로.
- **B**는 C가 노출한 REST/WS API만 소비한다. `apps/ai-server/README.md:7`도 대칭으로 "Platform 팀은 본 폴더에 PR 금지"라고 못박는다.

### 2.4 계약 변경 워크플로

`packages/shared-contracts/README.md:43-49`에 정의된 절차 — **계약이 먼저, 각자 구현은 그다음**:

1. PR 작성 (양 팀이 필요로 하는 변경 시점에)
2. CODEOWNERS가 Platform+AI 리뷰어를 자동 할당(`:25`)
3. 같은 PR 또는 연결된 PR로 양쪽 PRD(`docs/prd/PRD_neuro-sync.md` §0.3 + `docs/ai/PRD_ai.md` §1) 동반 갱신
4. 두 팀 모두 approve 후 머지
5. 머지 후 `apps/api`와 `apps/ai-server` 양쪽이 pin된 버전을 올린다

---

## 3. 개발 환경 3-tier

| Tier | 구성 | 장점 | 단점 | 언제 |
|:--|:--|:--|:--|:--|
| **Local** | 개발자별 `docker compose -f infra/deploy/docker-compose.yml up -d postgres` + `make dev-py`(api/ai-server를 호스트에서 직접 uvicorn, `Makefile:35-38`) + `pnpm turbo run dev`(web/mobile) — 각자 워크스테이션에 완전한 스택 | 완전 격리, 오프라인 가능, 남의 변경에 영향받지 않음 | 코퍼스 원본 데이터(`CASE_DATA_DIR`/`QA_DATA_DIR`)는 레포에 없어 각자 재현 필요; 리소스 소모 | 기능 개발·단위 테스트 |
| **Shared-Dev** | 공용 호스트 1대에 postgres+ai-server를 상시 기동, 각자 로컬 web/mobile/api는 원격 `DATABASE_URL`/`AI_SERVER_URL`로 지정(§5의 전환 절차) | **현재의 "같은 워크스테이션 결합" 문제를 해소하는 tier** — DB·코퍼스·ai-server를 한 곳에서만 세팅해 3인이 공유; 스키마 변경도 한 곳에서만 `alembic upgrade head` | 동시 스키마 변경 충돌(누가 언제 마이그레이션을 돌렸는지 조율 필요); DB/ai-server 포트를 공인망에 직접 열지 않으므로 SSH 터널이 필수(§4) | 통합 테스트, B/C가 A의 최신 ai-server를 붙여볼 때 |
| **Staging-Prod** | k8s(`infra/deploy/k8s/`) — postgres는 headless Service(`clusterIP: None`, 클러스터 내부에서만 5432, `postgres.yaml:11-20`) + StatefulSet, 자격증명은 Secret `ns-db-credentials`(KMS, `:50-52`); 운영은 관리형 DB(RDS/CloudSQL) 검토 권고(`postgres.yaml:8`) | 프로덕션 동등 검증 | 배포 파이프라인·클러스터 권한 필요 | 배포 전 최종 검증 |

**현재 "같은 워크스테이션 결합" 문제의 해법 = Shared-Dev tier.** §1.2에서 확인했듯, 지금은 compose가 ai-server에 `DATABASE_URL`을 배선하지 않아서 postgres와 ai-server가 물리적으로 같은 워크스테이션에 있을 때만 기본값이 우연히 맞는다. 공용 호스트 하나에 postgres+ai-server를 항상 띄워 두고, 각자의 로컬 api/web/mobile이 그 호스트를 `DATABASE_URL`/`AI_SERVER_URL` 한 줄로 가리키게 하면, "내 워크스테이션"과 "DB/ai-server가 실제로 있는 곳"이 분리된다.

---

## 4. 자격증명·보안 표준

- **비밀은 코드/이미지에 절대 넣지 않는다** — env var 또는 secret manager로만 주입한다. k8s는 Secret `ns-db-credentials`(KMS 참조, `infra/deploy/k8s/postgres/postgres.yaml:50-52`)를 쓴다. 로컬은 `.env` 파일이다.
- **`.env`는 gitignore되어 있다.** 확인: `.gitignore:46-49` — `.env`, `.env.*` 패턴을 무시하되 `!.env.example`만 예외로 살려서 커밋한다. 즉 `apps/ai-server/.env.example`, `apps/api/.env.example`은 **키 이름과 용도만** 적은 템플릿이고, 실제 값은 각자의 `apps/*/​.env`(둘 다 gitignored)에만 채운다.
- **내부 서비스 간 인증 사례 — RAG 라우터는 이제 존재하지 않는다(과거형 교훈).** `apps/ai-server`의 5개 핵심 인터페이스는 기본적으로 "Platform(api)이 보낸 요청을 신뢰"하는 모델이다(`apps/ai-server/README.md:23`: "인증 검증 — Platform이 보낸 요청은 신뢰(mTLS 또는 내부 토큰)"). 과거 `POST /ai/rag/grounding`이 실제로 외부에서 무인증으로 도달 가능했던 사건이 있었다(§4 반면교사 참고, `VAL-005`). 한동안 이 라우터에만 bearer 인증(`NS_RAG_API_KEY`, fail-closed 기본값)을 추가해 완화했으나, RAG를 영구·범주적으로 in-process 전용 기능으로 확정하면서(사용자 결정, `ADR-017`→`ADR-019`, 2026-07-09) 이 라우트와 인증 코드 자체를 **전면 삭제**했다 — `apps/ai-server/src/rag/route.py`와 `auth.py` 두 파일이 더 이상 트리에 존재하지 않고(`main.py`에 라우터 마운트도 없음, `git status`로 확인 가능), `NS_RAG_API_KEY`/`NS_RAG_DEV_MODE` env 키도 더 이상 쓰이지 않는다(`.env.example`에서도 제거됨). **현재는 이 인터페이스 자체가 존재하지 않으므로 별도 인증 설정이 필요 없다** — RAG는 F2의 `retrieve_domain_chunks`(`f2.py:176-180`)와 `rag_chat.py`의 `retrieve_grounding()`처럼 DB 세션을 직접 여는 in-process 호출로만 소비된다.
- **DB 포트를 공인망에 직접 열지 않는다.** postgres는 compose에서 `127.0.0.1:5432`로 호스트 로컬 바인딩만 한다(`docker-compose.yml:22-23`). k8s에서는 `clusterIP: None`인 headless Service라 클러스터 내부에서만 5432가 열린다(`postgres.yaml:11-20`). 원격 DB에 접속해야 하면 SSH 터널을 쓰거나(§5), `apps/api`를 경유한다 — DB로 직접 향하는 새 공인 접속 경로를 만들지 않는다.
- **`ENCRYPTION_KEY`는 api와 ai-server가 반드시 같은 값이어야 한다.** `apps/ai-server/src/config.py:81-83`: "AES-256-GCM 키(base64-urlsafe 32B). **api와 동일 값**이어야 앱이 복호화 가능." 다르거나 미설정이면 조용히 깨지는 대신 명시적으로 실패한다 — 암호화된 필드는 복호화 없이 응답에서 제외되고 로그가 남는다(`apps/ai-server/.env.example:33`; `retrieval.py`의 `_dec()` 실패 처리).
- **반면교사 (VAL-005급 재발 방지).** 과거 이 저장소의 한 테스트 클라이언트 스크립트(`rag_chat.py`)가 접속 대상 주소와 환자 식별자를 코드에 직접 박아 넣은 적이 있었다. 당시 해당 HTTP 엔드포인트(`POST /ai/rag/grounding`)가 무인증이었기 때문에, 코드에 박힌 그 식별자가 사실상 접근 자격증명처럼 작동한 셈이었다 — critic 검토에서 지적됐다(`VAL-005`). 그 스크립트는 이후 접속 정보를 전부 env var로만 받도록 고쳐졌고, 한동안 해당 엔드포인트에 위에서 설명한 bearer 인증도 추가됐었다 — 그러나 최종적으로는 완화가 아니라 **라이브 노출면 자체의 영구 삭제**로 귀결됐다: RAG를 개발·배포 단계 모두 in-process 전용 기능으로 확정하면서(`ADR-019`, 2026-07-09) 해당 라우트/인증 코드가 트리에서 완전히 제거되었고, `rag_chat.py`도 이제 HTTP 클라이언트가 아니라 `retrieve_grounding()`을 직접 호출하는 in-process 스크립트다(`rag_chat.py:1-20` 모듈 docstring 참고). 이 문서가 모든 예시에 `<placeholder>`만 쓰는 이유가 이 사례다 — 실 IP·UUID·비밀값을 문서나 스크립트에 직접 적지 않는다.

---

## 5. 개발자별 세팅 수정 how-to

### 5.1 개발자 A (ai-server 파이프라인/프롬프트)

**(a) 워크스테이션에 두는 것**
- `apps/ai-server/.env` (`.env.example`을 복사해 값 채움, gitignored)
- Python 3.12 + `uv` (`cd apps/ai-server && uv sync`)
- Local tier라면 `docker compose -f infra/deploy/docker-compose.yml up -d postgres`
- `docs/ai/prompts/`, `docs/ai/simulation_results/`가 레포 루트 기준 상대경로로 실제 파일시스템에 있어야 함 — ai-server를 컨테이너로(`docker compose up ai-server`) 띄우면 이 두 경로가 이미지에도 볼륨마운트에도 없다(§1.2 참고). 로컬 개발은 `make dev-py`로 호스트에서 직접 띄우는 편이 안전하다 — 단, `Makefile:38`의 ai-server 줄은 `cd apps/ai-server && uv run uvicorn src.main:app --reload --port 8001`이다. **레포 루트에서가 아니라 `apps/ai-server`로 cd한 뒤 uvicorn이 뜬다** (BUG-013 — 이 문서가 과거 "레포 루트에서 실행"이라고 서술했던 것은 오기였다). 이 cwd 차이 때문에 `PROMPTS_BASE_DIR`의 기본값이 깨진다 — 아래 (b)를 반드시 읽고 `.env`에 절대경로로 설정한다.

**(b) `.env` 키 예시** (`apps/ai-server/.env.example`이 정본 — 아래는 그 키에 placeholder 값만 채운 예시)

```
UPSTAGE_API_KEY=<upstage-key>
LG_K_EXAONE_API_KEY=<friendli-key>
LG_K_EXAONE_ENDPOINT_ID=<friendli-endpoint-id>
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<db-host>:5432/neurosync
ENCRYPTION_KEY=<32byte-base64-urlsafe-key-must-match-apps-api>
PROMPTS_BASE_DIR=<repo-root-absolute-path>/docs/ai/prompts
LOG_LEVEL=INFO
DEBUG=false
```

`NS_RAG_API_KEY`/`NS_RAG_DEV_MODE`는 더 이상 존재하는 env 키가 아니다 — RAG HTTP 라우트/인증 코드 자체가 영구 삭제되었으므로(`ADR-019`, §4 참고) `.env.example`에서도 제거되었다.

`PROMPTS_BASE_DIR`을 비워둬도 되는 경우는 **검증 파이프라인 CLI**(`f1.py`/`f2.py`/`safety_matrix.py`)를 직접 실행할 때뿐이다 — 이 세 스크립트는 실행 시 이 값을 `PROJECT_ROOT` 기준 절대경로로 자동 보정한다(`f1.py:1341-1342`, `f2.py:473-474`, `safety_matrix.py:270-271`).

**하지만 uvicorn으로 띄우는 FastAPI 앱 자체(`src.main:app`)는 그런 보정을 하지 않는다.** `resolve_prompts_dir()`(`config.py:96-98`)는 `prompts_base_dir`(기본값 `docs/ai/prompts`)을 그대로 `Path()`로 감싸 프로세스의 현재 cwd 기준 상대경로로 해석할 뿐이다. `make dev-py`(§5.1a — `Makefile:38`: `cd apps/ai-server && uv run uvicorn src.main:app --reload --port 8001`)로 띄우면 cwd가 `apps/ai-server`이므로 이 기본값은 존재하지 않는 `apps/ai-server/docs/ai/prompts`를 가리키게 된다. 실패는 즉시 드러나지 않는다 — 서버 기동과 `/health`는 정상으로 보이고, 프롬프트를 쓰는 엔드포인트(예: `/ai/chat/respond`)를 실제로 호출하는 순간에만 지연된 `FileNotFoundError`가 난다(BUG-013).

**따라서 `make dev-py`로 (또는 `apps/ai-server`가 cwd인 채로) uvicorn을 띄울 때는 `PROMPTS_BASE_DIR`를 반드시 레포 루트 기준 절대경로로 `.env`에 설정한다** — 위 (b) 예시 코드블록의 값이 바로 이 경우이며, 이때는 비워두면 안 된다:

```
PROMPTS_BASE_DIR=<repo-root-absolute-path>/docs/ai/prompts
```

요약하면 "검증 파이프라인 CLI는 자동 보정, uvicorn 서버 경로는 보정 없음" — `PROMPTS_BASE_DIR`을 비워둬도 되는지는 어느 쪽을 띄우느냐에 달려 있다.

**(c) Local ↔ Shared-Dev 전환**

Local(기본값, `DATABASE_URL` 미설정 → `config.py`의 내장 기본값이 `localhost:5432`를 가리킴, 즉 postgres가 같은 워크스테이션에 있어야 함)에서 Shared-Dev로 바꾸려면 `.env` 한 줄을 교체한다:

```
# 변경 전 (Local)
# DATABASE_URL 자체가 없음 → config.py 기본값 사용 (postgres가 같은 호스트에 있어야 함)

# 변경 후 (Shared-Dev, SSH 터널 경유)
DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/neurosync
```

그리고 별도 터미널에서 터널을 연다 (DATABASE_URL의 host:port가 터널의 로컬 쪽과 정확히 일치해야 함):

```
ssh -N -L 5432:localhost:5432 <user>@<shared-dev-host>
```

B/C가 A의 ai-server를 Shared-Dev로 공유해서 쓰게 하려면, 그쪽에서 `AI_SERVER_URL=http://<shared-dev-host>:8001` 한 줄만 바꾸면 된다 — 단 8001 포트도 공인망에 열려 있지 않다면 마찬가지로 터널 대상이다.

**(d) 스키마 변경 워크플로**

A는 alembic을 직접 실행하지 않는다(C 소관, `apps/api/alembic/`). 다만 A의 RAG 코드가 참조하는 `rag.*` 테이블이 바뀌면: C가 새 alembic revision을 만들고 병합 → A는 자기 로컬(또는 Shared-Dev, C가 대표 실행 후 공지)에서 `cd apps/api && alembic upgrade head`를 실행해야 코드가 기대하는 스키마와 실제 DB가 맞는다. postgres 이미지가 `pgvector/pgvector:pg16`이 아니면 alembic 0005(`CREATE EXTENSION vector`)부터 실패한다 — 이미지는 절대 바꾸지 않는다.

---

### 5.2 개발자 B (web·mobile)

**(a) 워크스테이션에 두는 것**
- `apps/web`(Next.js) — `pnpm install` 후 `pnpm --filter web dev`
- `apps/mobile`(Expo/RN)
- DB나 ai-server를 설치할 필요 없음 — B는 `apps/api` 하나만 바라본다(`apps/web/README.md:17-18`, `apps/mobile/README.md:20-21`).

**(b) env 키**

web (`apps/web/.env.local`, Next.js 관례 — `apps/web/lib/config.ts:9`가 읽음):
```
API_BASE_URL=http://localhost:8000
```
프로덕션 빌드는 반드시 `https://`여야 한다 — 아니면 첫 요청에서 런타임 에러(`lib/config.ts:19-31` `assertProductionTLS`).

mobile (Expo — `EXPO_PUBLIC_*`만 번들에 인라인됨, `apps/mobile/lib/config.ts`):
```
EXPO_PUBLIC_API_BASE_URL=http://<host>:8000
EXPO_PUBLIC_WS_BASE_URL=ws://<host>:8000
EXPO_PUBLIC_MOCK=1
```
값을 아예 안 주면 iOS 시뮬레이터는 `localhost:8000`, Android 에뮬레이터는 자동으로 `10.0.2.2:8000`으로 대체된다(`lib/config.ts:21-26`). `EXPO_PUBLIC_MOCK=1`은 API/DB 없이 오프라인 목업으로 개발할 때 쓴다(`lib/config.ts:44-49`) — 프로덕션 빌드에서는 강제로 꺼진다(`:51-58`).

**(c) Local ↔ Shared-Dev 전환**

B는 DB나 ai-server를 신경 쓸 필요가 없다 — `apps/api` 주소 한 줄만 바꾼다.
```
# Local
API_BASE_URL=http://localhost:8000
# Shared-Dev (C가 공용 api를 띄운 경우)
API_BASE_URL=http://<shared-dev-host>:8000
```
mobile도 `EXPO_PUBLIC_API_BASE_URL`/`EXPO_PUBLIC_WS_BASE_URL` 두 줄만 같은 방식으로 바꾼다. api 포트가 공인망에 없다면:
```
ssh -N -L 8000:localhost:8000 <user>@<shared-dev-host>
```
터널을 열고 URL은 `localhost:8000`으로 둔다.

**(d) 스키마 변경 워크플로**

B는 alembic을 직접 실행하지 않는다. B가 영향받는 것은 `packages/shared-contracts/typescript`의 타입뿐이다 — C/A가 `packages/shared-contracts`를 갱신·머지하면 최신 버전을 받아 타입 에러가 나는 지점만 고친다(§2.4 "계약이 먼저" 절차).

---

### 5.3 개발자 C (apps/api·alembic·rag tooling 실무·DB 스키마)

**(a) 워크스테이션에 두는 것**
- `apps/api/.env` (`.env.example` 복사)
- postgres (Local이면 `docker compose -f infra/deploy/docker-compose.yml up -d postgres`)
- `cd apps/api && uv sync`
- C는 alembic 마이그레이션의 실질 소유자이며, `apps/ai-server/src/rag/tooling/`의 코퍼스 적재 스크립트(`load_ontology.py`/`load_case_cards.py`/`load_qa.py`/`embed_corpus.py`/`load_simulations.py`)도 실무상 C가 돌리는 경우가 많다 — 코드 경로 자체는 CODEOWNERS상 A(`@ai-team`) 소관이므로 수정 시 A에게 공유한다.

**(b) env 키** (`apps/api/.env.example`이 정본)
```
DATABASE_URL=postgresql+psycopg://<user>:<password>@<db-host>:5432/neurosync
JWT_SECRET_KEY=<random-48byte-urlsafe>
ENCRYPTION_KEY=<32byte-base64-urlsafe-key-must-match-apps-ai-server>
AI_SERVER_URL=http://localhost:8001
```
`api`는 동기 `psycopg` 드라이버, `ai-server`는 비동기 `asyncpg` 드라이버를 쓴다 — 접두사(`postgresql+psycopg` vs `postgresql+asyncpg`)가 다르다는 점에 주의(`docker-compose.yml:40` vs `config.py:78`).

**(c) Local ↔ Shared-Dev 전환**

C가 Shared-Dev 호스트의 DB를 세팅하는 당사자일 가능성이 높다. 다른 두 사람과 같은 패턴으로 `DATABASE_URL`의 host를 바꾸되, DB 포트는 공인망에 열지 않으므로(§4) 보통 SSH 터널을 쓴다:
```
ssh -N -L 5432:localhost:5432 <user>@<shared-dev-host>
```
`.env`의 `DATABASE_URL`은 `@localhost:5432`를 유지한다(터널이 로컬 5432를 원격 5432로 전달하므로).

**(d) 스키마 변경 워크플로 (C가 시작점)**

1. 스키마 변화가 API 계약에 드러난다면(새 필드/타입) `packages/shared-contracts/python`을 먼저 바꾼다 — §2.4 절차(PR → CODEOWNERS 자동 리뷰어(A+C) → 양쪽 PRD 갱신 → 승인 → 양쪽 pin 갱신).
2. `apps/api/alembic/versions/`에 새 revision을 추가한다(현재 최신 `0007_session_insights_slots.py`).
3. `alembic upgrade head`는 Local이면 각자 실행, Shared-Dev면 **대표 1인만** 실행하고 팀에 공지한다(동시 실행 충돌 방지).
4. `rag.*` 스키마를 건드리면 postgres 이미지가 여전히 `pgvector/pgvector:pg16`인지 재확인한다(plain postgres 이미지면 0005부터 실패).
5. A가 자기 환경(Local 또는 Shared-Dev)에서도 같은 `alembic upgrade head`가 반영됐는지 확인해야 ai-server 코드가 기대하는 스키마와 실제 DB가 맞는다.

---

### 5.4 공통 트러블슈팅

| 증상 | 원인 | 해법 |
|:--|:--|:--|
| 연결 거부 (`Connection refused` / `ECONNREFUSED` on 5432) | `DATABASE_URL`의 host/port가 실제 postgres 위치와 다름; postgres 컨테이너 미기동/unhealthy; Shared-Dev인데 SSH 터널 미연결; postgres는 `127.0.0.1` 호스트로컬 바인딩이라 터널 없이 원격 접근 자체가 불가능(`docker-compose.yml:22-23`) | `docker compose ps`로 postgres `healthy` 확인; SSH 터널 프로세스가 살아있는지 확인; `DATABASE_URL`의 host:port가 터널의 로컬 포트와 정확히 일치하는지 확인 |
| 복호화 실패 / 응답에서 암호화 필드가 통째로 빠짐 | `ENCRYPTION_KEY`가 api와 ai-server에서 다르거나 한쪽만 미설정 | 두 서비스의 `.env`에 **동일한** 32바이트 base64-urlsafe `ENCRYPTION_KEY` 값을 넣는다(`config.py:81-83`); 실패해도 서버는 죽지 않고 해당 필드만 제외되며 로그가 남으므로 로그를 먼저 확인 |
| alembic 0005 이후 마이그레이션 실패 (`vector` extension/type 관련 에러) | postgres 이미지가 `pgvector/pgvector:pg16`이 아니라 plain `postgres` 이미지 | compose/k8s 매니페스트의 이미지가 `pgvector/pgvector:pg16`인지 확인 후 볼륨을 재생성하고 `alembic upgrade head` 재실행 |
| 컨테이너로 띄운 ai-server가 프롬프트를 못 찾거나 F2 산출물을 못 씀 | `docs/ai/prompts`, `docs/ai/simulation_results`가 Dockerfile에도 compose volume에도 없음(§1.2) | 컨테이너 대신 `make dev-py`로 호스트에서 직접 실행하거나, `PROMPTS_BASE_DIR`을 절대경로로 명시 |
| 프롬프트 엔드포인트에서 `FileNotFoundError` (서버 기동·`/health`는 정상) | `make dev-py`는 cwd가 `apps/ai-server`인데 `PROMPTS_BASE_DIR` 기본값은 그 cwd 기준 상대경로(§5.1b) | `.env`에 `PROMPTS_BASE_DIR`을 레포 루트 기준 절대경로로 설정 (BUG-013) |

---

*이 문서에 인용된 모든 사실은 파일 경로/줄번호로 소스가 달려 있다. 코드가 바뀌면 이 문서보다 코드가 우선이며, 문서 갱신은 다음 세션의 몫이다.*
