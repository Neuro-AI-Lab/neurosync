# PHR Sample Data (페르소나별 익명화 샘플)

**⚠️ 실 개인정보 저장 금지**. 이 디렉터리에는 페르소나 시뮬레이션용 fake 데이터만 커밋한다.

## 파일 명명

```
VP-{001-004}_medications.json    # MedicationDispense + Medication + Patient
VP-{001-004}_visits.json         # ExplanationOfBenefit + Patient
```

## 포맷

`myhealthway.go.kr` 계열 PHR (FHIR R4 커스텀 프로파일)의 실 샘플 스키마를 그대로 사용.
- 컨테이너: `{ "publicData": [...], "medicalData": [], "healthData": {...} }`
- Meta profile: `https://simplifier.net/myhealthway/StructureDefinition/Public*`
- 코드체계:
  - 약품: KDCode (`https://biz.kpis.or.kr/CodeSystem/kdcode`)
  - 성분: HIRA (`https://www.hira.or.kr`)

## 페르소나별 임상 시나리오 요약

| VP | 프로파일 | 정신과 약 | 진료 이력 특징 |
|---|---|---|---|
| VP-001 | 28F 초진 경증 (F41.9 불안, F51.0 불면) | **없음** | 이비인후과·내과 방문 |
| VP-002 | 35M 재진 경증 (F32.0 경도 우울) | 에스시탈로프람 10mg · 3개월 | 정신건강의학과 재진 3회 |
| VP-003 | 42M 초진 중증 (F32.2) | **없음** (첫 방문) | 내과·응급실 방문 |
| VP-004 | 29F 재진 중증 (F32.2 + F41.0 공황) | SSRI + BENZO + Z-drug 병용 6개월 | 정신건강의학과 · 응급실 |

## 익명화 원칙 (모두 준수됨)

- 성명: 페르소나명 (김서연/이준호/박민수/최하은) — 가상 인물
- 주민번호: 뒷자리 6자리 전체 마스킹 (`0000000******`)
- MHID: 임의 8자리 정수
- 요양기관명·주소: 페르소나 좌표 부근 실 병원/약국명 사용 (map-api 검증 리스트) — 개인 식별 불가
- 조제일·진료일: 2025-09 ~ 2026-06 임의 분포

## 향후 확장

- Phase 1 파서가 이 샘플들을 로드 · 파싱 정합성 검증 대상.
- 새 페르소나 추가 시 이 형식·명명 규칙 유지.
