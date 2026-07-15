# 정신과 약물 분류 — 근거 및 데이터 소스

> 작성: 2026-07-13 · 담당: AI Research
> 관련 코드: `apps/ai-server/src/data/psychotropic_classification.py`,
> `src/adapters/hira_drug_efficacy.py`, `src/data/hira_efficacy_cache.{py,json}`

## 1. 배경 — 왜 바꿨나

초기 구현(`psychotropic_ingredients.py`, 삭제됨)은 정신과 약물 성분명 약 40종을
**하드코딩한 화이트리스트**로 판정했다. 이 목록은 임상 레퍼런스 없이 임의로 작성된
값이라 (a) 근거를 댈 수 없고 (b) 누락·오분류를 검증할 수 없었다.

→ 판정 기준을 **건강보험심사평가원(HIRA) 공식 약효분류번호**로 전면 대체했다.

## 2. 데이터 소스 (검증 완료)

**건강보험심사평가원 「의약품성분약효정보조회서비스」**
- 공공데이터포털: https://www.data.go.kr/data/15021027/openapi.do
- Endpoint: `GET https://apis.data.go.kr/B551182/msupCmpnMeftInfoService/getMajorCmpnNmCdList`
- 인증: `ServiceKey` (기존 `HIRA_SERVICE_KEY` 공유 — 승인 완료, `resultCode:00` 확인)
- 입력: `gnlNmCd`(일반명코드) · `gnlNm`(일반명) · `meftDivNo`(약효분류번호)
- 출력: `meftDivNo`(약효분류번호) · `divNm`(분류명) · `gnlNm` · 제형/투여경로/함량 등

PHR(마이헬스웨이) `MedicationDispense`의 성분코드(`Substance.code`, system
`hira.or.kr`)가 곧 이 API의 `gnlNmCd`와 동일 포맷이라 **별도 매핑 없이** 조회 가능.
(예: escitalopram `474802ATB`)

## 3. 정신과 판정 규칙

| meftDivNo | divNm | PsychotropicClass | 정신과? |
|---|---|---|---|
| 117 | 정신신경용제 | `PSYCHONEUROTIC` | ✅ |
| 112 | 최면진정제 | `SEDATIVE_HYPNOTIC` | ✅ |
| 그 외 | — | `NON_PSYCHIATRIC` | ✗ |
| (미조회) | — | `UNKNOWN` | ✗ (단정 안 함) |

`PSYCHIATRIC_EFFICACY_CODES = {112, 117}`

### 실측 근거 (API 응답)
- escitalopram(474802ATB)·sertraline(227001ATB)·**alprazolam(105502ATB)** → 모두 **117 정신신경용제**
  - ⚠️ 국내 KFDA 분류에서 항불안제(benzodiazepine, alprazolam 등)는 112가 아니라 **117**이다.
- acetaminophen→114 해열·진통·소염제 / mosapride→239 소화기 / amlodipine→214 혈압강하제 (전부 비정신과)

## 4. 런타임 흐름 (`PatientHistoryAgent`)

1. **로컬 캐시** `hira_efficacy_cache.json` 조회 (오프라인·테스트 동작, 지연 0)
2. 캐시 miss & 어댑터 주입 시 → HIRA API 실시간 조회
3. 둘 다 실패 → `UNKNOWN` (정신과로 단정하지 않음, 보수적 fallback)

캐시는 임의 값이 아니라 **API 응답 스냅샷**이며 재생성 가능:
```
cd apps/ai-server
python -m src.data.build_efficacy_cache            # 샘플 코드 자동 수집
python -m src.data.build_efficacy_cache --code 474802ATB   # 특정 코드 추가
```

## 5. 한계

- **세분류 불가**: 약효분류번호는 SSRI/SNRI/TCA/항불안제/항정신병약을 모두 117로 묶는다.
  세분류(예: N06AB SSRI)가 필요하면 ATC 코드 소스(HIRA ATC 매핑 목록 15118958 또는
  식약처 묶음의약품정보서비스 15063908)를 추가 도입해야 한다.
- **항전간제(113) 제외**: 라모트리진·발프로에이트 등은 기분안정제로도 쓰이나
  순수 뇌전증과 구분 불가하여 정신과 판정에서 기본 제외(오탐 방지). 필요 시 재검토.
- **KDCode(biz.kpis.or.kr)**: 샘플 PHR의 제품코드(`kd_code`)는 별도 검증 대상.
  분류에는 성분코드(`hira_ingredient_code`)만 사용하므로 판정에 영향 없음.

## 6. 부수 발견 — 샘플 데이터 성분코드 교정

검증 과정에서 VP-001~004 샘플 PHR의 HIRA 성분코드 14건이 모두 **조작된 값**임을
확인하고 실제 코드로 교정했다 (예: escitalopram `245801ATB`→`474802ATB`;
`245801ATB`는 실제로는 ubidecarenone 강심제). 용량별 구분 적용
(escitalopram 10mg→`474802ATB`, 20mg→`474803ATB`).
