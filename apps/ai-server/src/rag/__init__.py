"""RAG 레이어 (apps/api / Platform).

pgvector(postgres)로 정신과 사례·지식·온톨로지를 검색해 grounding을 만들고,
ai-server `/ai/chat/respond` 입력의 `grounding`(shared-contracts)으로 주입한다.
ai-server는 그 grounding을 프롬프트(정신과 EMR 주입)로 활용 — DB는 미접근.

- retrieval.retrieve_grounding(): 런타임 진입점 (async).
- ontology.py: 버킷맵 / 증상 마스터 / 질병 / disease_symptom KG.
- tooling/: 오프라인 빌드 (스키마=alembic 0005, 데이터=로더+임베딩).
"""
