# `src/rag/` — RAG 검색 엔진 (apps/api)

정신과 사례·지식·온톨로지를 **pgvector**로 검색해 grounding 4슬롯을 만들고,
`ai-server`의 `/ai/chat/respond` 입력(`grounding`, shared-contracts)으로 주입한다.

## 왜 apps/api 인가 (아키텍처)
루트 README 통신도: **`apps/api` → PostgreSQL** (DB 접근은 apps/api 단독).
`ai-server`는 무DB 순수함수 → pgvector를 못 봄. 그래서 **RAG 검색은 apps/api**,
결과(grounding)를 HTTP로 ai-server에 전달 (docs/ai §3.2 "Platform이 context를 먹임").

```
사용자 발화 → [apps/api WS] services/chat.respond
   → rag.retrieval.retrieve_grounding(db, 발화, patient_id)   # pgvector 검색
   → ChatRequest(grounding=...) → ai_client → [ai-server] chat/prompt 주입 → LLM
   → 응답 저장
```

## 구성
```
src/rag/
├── retrieval.py     ⭐ async retrieve_grounding() → shared-contracts Grounding 반환
├── ontology.py      버킷맵(67)·증상 마스터(40)·질병(26)·disease_symptom KG
├── embed.py         Upstage solar 임베딩 (passage/query 4096, EMBED_DUMMY 지원)
├── bucket_map.md / unmapped_report.md   근거 문서
└── tooling/         오프라인 빌드 (sync psycopg, CLI)
    ├── load_ontology.py     disease/symptom/disease_symptom (데이터셋 불필요)
    ├── load_case_cards.py   심리상담 사례 (CASE_DATA_DIR)
    ├── load_qa.py           정신과 QA (QA_DATA_DIR)
    └── embed_corpus.py      임베딩 (UPSTAGE_API_KEY, 증분)
```
연관:
- 스키마: `apps/api/alembic/versions/0005_rag_corpus_schema.py` (rag.* + pgvector)
- 인터페이스: `packages/shared-contracts/.../chat.py` 의 `Grounding`
- 주입: `apps/ai-server/src/chat/prompt.py`
- 인프라: `infra/deploy/docker-compose.yml`(pgvector) · `infra/deploy/k8s/postgres/`

## 로컬 실행
```bash
export POSTGRES_PASSWORD=dev
docker compose -f infra/deploy/docker-compose.yml up -d postgres   # pgvector

cd apps/api
alembic upgrade head                                  # → rag 스키마(0005)
python -m src.rag.tooling.load_ontology               # disease26/symptom40/엣지169
CASE_DATA_DIR=/path/16.심리상담.../1.데이터 python -m src.rag.tooling.load_case_cards
QA_DATA_DIR=/path/08.전문_의학지식.../1.데이터  python -m src.rag.tooling.load_qa
UPSTAGE_API_KEY=up_... python -m src.rag.tooling.embed_corpus      # EMBED_DUMMY=1 가능
```

## 환경변수
| 변수 | 용도 |
|---|---|
| `DATABASE_URL` | 연결 (드라이버 접두 자동 제거) |
| `UPSTAGE_API_KEY` | 임베딩 (없으면 더미). AI팀 시크릿 — Secret Manager 등록 |
| `EMBED_DUMMY=1` | 키 없이 배관 테스트 |
| `CASE_DATA_DIR`/`QA_DATA_DIR` | 데이터셋 경로 (레포 미포함) |

## 후속 (TODO)
- `retrieval._detect_symptoms` 키워드 매칭 → ai-server 구조화 추출(40 플래그)로 교체.
- disease_symptom 후속질문에 specificity(변별자질) 가중 — MedRAG 변별 KG 방향.
- 코퍼스 데이터 배포: pg_dump seed 아티팩트 또는 seed Job (이미지에 데이터 미포함).
