# `tools/` — 공유 개발 스크립트

> **Owner**: Platform 팀 주도, 양 팀 기여 가능

dev 환경 셋업, 데이터 마이그레이션, OCR/STT 합성 데이터 생성 등 한쪽 팀에 속하지 않는 유틸 스크립트.

## 예정 항목

- `tools/dev-setup.sh` — 신규 개발자 로컬 셋업
- `tools/seed-db.py` — 개발 DB 시드 (Platform)
- `tools/synth-safety-labels.py` — Safety 합성 데이터 생성 (AI)
- `tools/pdf-to-png.sh` — references PDF → PNG 변환 (이미 사용한 워크플로)
