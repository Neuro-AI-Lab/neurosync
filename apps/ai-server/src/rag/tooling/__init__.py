"""RAG 오프라인 빌드 (CLI 배치, sync psycopg). apps/api 루트에서 실행.

순서:
  1. alembic upgrade head                      # 스키마 (0005_rag_corpus_schema)
  2. python -m src.rag.tooling.load_ontology   # disease/symptom/disease_symptom (데이터셋 불필요)
  3. CASE_DATA_DIR=... python -m src.rag.tooling.load_case_cards
  4. QA_DATA_DIR=...   python -m src.rag.tooling.load_qa
  5. UPSTAGE_API_KEY=... python -m src.rag.tooling.embed_corpus
"""
