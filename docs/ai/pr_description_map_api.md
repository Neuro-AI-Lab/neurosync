# PR: 정신건강의학과 전문의 재직 병원 검색 · Crisis 자동 안내 (HIRA + Kakao)

> **Branch**: `add/map-api` → `Master`
> **Related FR**: FR-011 (Crisis 시 자원 안내)
> **Guide doc**: `docs/ai/api/hira_kakao_map_api_usage_guide.md`

---

## 1. Summary

환자 위치 기반으로 **정신건강의학과 전문의가 실제 재직 중인 의료기관만** 반환하고, F1 Crisis 시 top-3을 자동 안내한다. 단순히 HIRA 진료과목 코드 `03`이 등록된 모든 기관을 노출하지 않는다.

### 4단계 필터 파이프라인
1. **HIRA `getHospBasisList`** (`dgsbjtCd=03`, radius, `xPos/yPos`) — 1차 후보
2. **종별 필터** — 요양병원·한방·치과·보건소 등 제외 (`ALLOWED_CL_CODES`, `EXCLUDED_TYPE_NAMES`)
3. **Kakao Local 카테고리 매칭** — `category_name = "의료,건강 > 병원 > 정신건강의학과"` 좌표 격자로 1차 verified
4. **HIRA `MadmDtlInfoService2.8/getDgsbjtInfo2.8`** — 진료과별 전문의 수 조회. `psychiatry_specialist_count >= 1` 이면 verified, `== 0` 이면 응답에서 명시적 배제

---

## 2. 파일 변경

| 파일 | 변경 |
|---|---|
| `.env` | `HIRA_MADM_DTL_SERVICE_URL` 추가 |
| `src/config.py` | `hira_madm_dtl_service_url` 필드 · Kakao 키 `AliasChoices` · SKT `AliasChoices` |
| `src/adapters/hira_base.py` (신규) | HIRA 공통 클라이언트 (envelope 파싱, 재시도, `HiraApiError`) |
| `src/adapters/hira_hospital.py` (신규) | `getHospBasisList` 클라이언트 (search / search_all) |
| `src/adapters/hira_pharmacy.py` (신규) | `getParmacyBasisList` — 스펙 오타 그대로 유지 |
| `src/adapters/hira_madm_dtl.py` (신규) | `getDgsbjtInfo2.8` — 진료과별 전문의 수. 401/403 시 graceful None |
| `src/adapters/kakao_local.py` (신규) | `search_address()` (geocoding) · `search_keyword()` (category+radius) |
| `src/schemas/nearby.py` (신규) | `Place`, `Marker`, `MapPayload`; `ALLOWED_CL_CODES / EXCLUDED_TYPE_NAMES / PROVIDER_GROUP` 상수; `specialist_verified`, `psychiatry_specialist_count`, `group`, `is_university_hospital_candidate` 필드 |
| `src/agents/nearby_facilities.py` (신규) | 4단계 파이프라인 통합 · Kakao 격자 매칭 · MadmDtl 병렬(5) 검증 + `count==0` drop · marker 재동기화 · 정렬 (`verified > distance > count > name`) |
| `src/routes/nearby.py` (신규) | `GET /ai/nearby/{hospitals,pharmacies}(/report)` · `GET /ai/nearby/ui` (Kakao Map 데모) |
| `src/dependencies.py` | HIRA hospital/pharmacy/madm_dtl · Kakao Local · NearbyFacilitiesAgent DI |
| `src/f1.py` | `PERSONA_LOCATIONS` (VP-001~004 좌표); `F1Result.nearby_psychiatric/patient_lat/patient_lng`; `_fetch_crisis_facilities()` (num_of_rows=30 · top-1 skip · top-3 반환); Crisis 응답에 자동 첨부 |
| `src/main.py` | `nearby_router` mount |
| `docs/ai/api/hira_kakao_map_api_usage_guide.md` | `dgsbjtCd` 응답 필드 부재 실측 note |
| `docs/ai/simulation_results/nearby_smoke/*.json` | 페르소나별 검증 산출물 |
| `tests/smoke_nearby_hira.py, smoke_kakao_local.py, smoke_nearby_personas.py, smoke_psychiatric_personas.py, smoke_crisis_nearby.py` | 5종 smoke 테스트 |

---

## 3. 검증된 API 응답 사실

### 3.1 `getHospBasisList` 응답 필드 (실측)

```
yadmNm, addr, telno, clCd, clCdNm, sidoCd/sgguCd, XPos, YPos, ykiho,
mdeptGdrCnt, mdeptResdntCnt, mdeptSdrCnt, cmdcGdrCnt, detyGdrCnt, pnursCnt,
drTotCnt, distance, hospUrl, postNo
```

- ⚠️ **응답에 `dgsbjtCd`/`dgsbjtCdNm` 필드는 존재하지 않는다.** `dgsbjtCd`는 요청 파라미터로만 작동하는 필터. 응답 각 item에는 "이 병원의 진료과 코드"가 담기지 않는다.
- 우리는 필터 사실을 근거로 `subject_code="03"`, `subject_name="정신건강의학과"` 태그를 후처리에서 부여한다.

### 3.2 `MadmDtlInfoService2.8/getDgsbjtInfo2.8` 응답 필드 (실측 · 승인 완료)

양지병원 ykiho probe 결과:
```
{'01': 23, '02': 5, '03': 1, '04': 11, '05': 4, '06': 3, '07': 0,
 '09': 3, '10': 3, '11': 4, '13': 1, '15': 2, '16': 8, '18': 2,
 '19': 1, '21': 1, '23': 3, '24': 11, '25': 1, '59': 0, '61': 0}
```

- 응답 item 필드: `dgsbjtCd`, `dgsbjtCdNm`, `dgsbjtPrSdrCnt` (진료과별 전문의 수)
- 이 병원의 정신건강의학과 전문의 수 = **1명**

### 3.3 Kakao Local `keyword.json` 응답 필드

`category_name` 값이 "의료,건강 > 병원 > 정신건강의학과" 형태로 세분화되어 정신과 전문 여부 판별에 사용 가능. VP-001 마포 반경 5km에 카테고리 정확히 일치하는 47개 문서 확보.

### 3.4 HIRA 서브서비스 접근 상태

- ✅ `hospInfoServicev2/getHospBasisList` — 200 OK
- ✅ `pharmacyInfoService/getParmacyBasisList` — 200 OK
- ✅ `MadmDtlInfoService2.8/getDgsbjtInfo2.8` — 200 OK (활용신청 승인 완료)
- ❌ `MadmDtlInfoService2/getDgsbjtInfo2` — 500 (구버전)
- ❌ `MadmDtlInfoService2.7/getDgsbjtInfo2.7` — 403 (미구독)

---

## 4. 페르소나별 실측 결과 (반경 5km)

| VP | 좌표 | HIRA raw | 종별 필터 | 최종 verified | clinic / general / psychiatric |
|---|---|---|---|---|---|
| VP-001 (마포) | (37.5807, 126.8898) | **85** | 24 | **18** | 15 / 2 / 1 |
| VP-002 (판교) | (37.4020, 127.1087) | **69** | 30 | **23** | 19 / 3 / 1 |
| VP-003 (관악) | (37.4782, 126.9515) | **139** | 29 | **19** | 10 / 8 / 1 |
| VP-004 (강서) | (37.5510, 126.8495) | **93** | 28 | **20** | 17 / 2 / 1 |

- **HIRA raw → 최종**: 요양병원·한방·치과 제거 (종별 필터) + 실 정신과 전문의 0명 병원 제거 (MadmDtl).
- 3그룹 분류(`Place.group`)는 UI에서 clinic / generalHospital / psychiatricHospital로 분리 표시 가능.

---

## 5. VP-001 반경 2km 상세 (진료과별 전문의 표기 실증)

Request: `GET /ai/nearby/hospitals?lat=37.5807&lng=126.8898&radius_km=2&num_of_rows=30`

| # | 병원 | 거리 | 종별 | 진료과 전문의 (MadmDtl 실측) |
|---|---|---|---|---|
| 1 | 상암정신건강의학과의원 | 0.098km | 의원 | 🧠 정신건강의학과 **2명** |
| 2 | 도우정신건강의학과의원 | 0.151km | 의원 | 🧠 정신건강의학과 **2명** |
| 3 | 온유정신건강의학과의원 | 0.369km | 의원 | 🧠 정신건강의학과 **2명** |
| 4 | 민정신건강의학과의원 | 0.840km | 의원 | 🧠 정신건강의학과 **1명** |
| 5 | 사람과생각정신건강의학과의원 | 0.989km | 의원 | 🧠 정신건강의학과 **1명** |

### 응답에서 명시적으로 배제된 곳 (MadmDtl에서 정신과 전문의 0명 확인)
- **수이비인후과의원** (0.58km) — 이비인후과 1명
- **프리즘의원** (1.03km) — 내과 1명

두 병원 모두 HIRA `dgsbjtCd=03` 필터엔 포함(등록 이력 기준)됐지만, MadmDtl 현행 인력 조회에서 정신과 전문의 0명 확인 → agent가 응답 `places` 및 `map.markers`에서 삭제. UI 지도에도 표시되지 않는다.

### 응답 카운터 (`sources.hospital`)
```json
{"total_count": 8, "normalized_count": 5}
```
`total_count`(HIRA raw) vs `normalized_count`(필터·검증 통과) 격차가 소비자에게 투명하게 노출된다.

---

## 6. Crisis 통합 (F1)

### 6.1 좌표 · 실행 흐름
`f1.py`의 `PERSONA_LOCATIONS`에 VP-001~004의 임의 좌표 등록. `F1Pipeline.run_session(patient_lat, patient_lng)` 인자로 사용. Crisis 발동 시 `_fetch_crisis_facilities()`가:
1. Agent 검색 (`num_of_rows=30`, 반경 5km · psychiatric-only 강제 · MadmDtl 검증)
2. **최근접 1곳(top-1)은 의도적 스킵**: HIRA + verified 정렬 후 index 0을 제외한 다음 3곳 반환 (대형 종합병원 top-1이 나올 경우 접근성 완충)
3. AI 응답에 자동 첨부: `109/119 안내 + 근처 정신건강의학과 top-3`

### 6.2 Crisis smoke 실측 (canned utterances)

**VP-003 (관악)** — Turn 2 crisis
```
📍 가까운 정신건강의학과:
1. 의료법인서울효천의료재단 에이치플러스양지병원 (1.8km) · ☎ 02-1877-8875   [정신과 전문의 1명, 종합병원]
2. 강신경정신과의원 (2.0km) · ☎ 02-871-7121                                  [정신과 전문의 1명, 의원]
3. 개운정신건강의학과의원 (2.9km) · ☎ 02-534-5568                            [정신과 전문의 1명, 의원]
```
(top-1 skip 대상 = 나눔정신건강의학과의원 0.33km, 정신과 전문의 1명)

**VP-004 (강서)** — Turn 2 crisis
```
📍 가까운 정신건강의학과:
1. 이화여자대학교의과대학부속서울병원 (1.4km) · ☎ 1522-7000                [정신과 전문의 4명, 종합병원]
2. 가족사랑정신과의원 (1.4km) · ☎ 02-3663-5956                             [정신과 전문의 1명, 의원]
3. 마음과정신건강의학과의원 (1.4km) · ☎ 02-2697-8575                       [정신과 전문의 1명, 의원]
```
(top-1 skip 대상 = 마음의지도정신건강의학과의원 1.25km, 정신과 전문의 1명)

### 6.3 음성(STT) 입력에서도 동일 동작
`add/f1-stt-and-ocr` 브랜치 병합 상태에서 mp3(VP-003 2개, VP-004 3개) 입력으로 F1 실행 → STT → Safety → Crisis → Nearby 자동 첨부 흐름 재현됨. 텍스트/음성 파이프라인 결과 동일.

---

## 7. 검증 명령 (재현)

```bash
cd apps/ai-server

# 1. Boot + lint
.venv/bin/python -c "from src.main import app; print(len(app.routes), 'routes')"   # 22
.venv/bin/ruff check src tests                                                       # All checks passed!

# 2. REST 실측 (필터·검증 통과 place만 반환)
curl "http://localhost:8080/ai/nearby/hospitals?lat=37.5807&lng=126.8898&radius_km=2&num_of_rows=30"

# 3. Crisis smoke (canned)
.venv/bin/python -m tests.smoke_crisis_nearby

# 4. UI (Kakao Map SDK 도메인 제약 — 반드시 localhost:8080)
PROMPTS_BASE_DIR=../../docs/ai/prompts \
  .venv/bin/uvicorn src.main:app --host 127.0.0.1 --port 8080
# 브라우저: http://localhost:8080/ai/nearby/ui
```

---

## 8. 명세 준수 (`docs/ai/api/hira_kakao_map_api_usage_guide.md` + 사용자 요구 스펙)

- ✅ **§3.2 종별 필터**: `ALLOWED_CL_CODES = {01, 11, 21, 29, 31}`, `EXCLUDED_TYPE_NAMES` 요양·한방·치과·보건소
- ✅ **§4 전문의 검증**: MadmDtl 2.8 조회 `psychiatry_specialist_count >= 1`이면 verified · 0이면 응답 배제. 조회 실패는 `specialist_verified=false`로 fallback
- ✅ **§6 3그룹 분류**: `Place.group ∈ {clinic, generalHospital, psychiatricHospital}` 필드로 노출
- ✅ **§7 정렬**: `verified 우선 → distance → -count → name`
- ✅ **§10 나열 정보 범위**: name, type, distance, phone, address, subject count · 예약 확정 정보는 포함하지 않음
- ✅ **§11 예외 처리**: HIRA 타임아웃/500 재시도 (지수 백오프) · MadmDtl 401/403 흡수 · items 단일/배열/누락 모두 파싱 · `distance` 문자열 파싱
- ✅ **좌표 sanity**: KR 범위 (lat 30-45, lng 120-135) 밖 필터 아웃
- ✅ **개인정보 안전 필드**: `emergency_available`, `open_now` — 데이터 없으면 `null` (`true` 로 절대 추정 금지)

### 미구현 (범위 밖 · 스펙 §12 등)
- 캐시 정책 (병원 기본정보 24h · 코드 정보 7d): 프로세스 내 dict 캐시만 존재. Redis 등 외부 캐시 미도입.
- 특수진료병원정보서비스(`getPatMedInfo`) 연동: 태그 부가 정보로만 사용될 예정, 이번 스코프 밖.
- 병원코드정보서비스와 동기화 스크립트: 코드 하드코딩 → 향후 자동 동기화 예정.

---

## 9. Known Issues

1. **HIRA MadmDtl 응답 지연**: 병원 20~30개 검증 시 총 4~13초 (concurrency=5, HIRA 개별 응답 1~2초). 프로세스 내 ykiho 캐시로 재조회 절약하지만 초기 요청은 최대 지연 가능.
2. **Kakao Map SDK 도메인 제약**: `/ai/nearby/ui` HTML은 `localhost:8080`으로만 접근 가능 (Kakao 개발자 콘솔에 등록된 도메인). `127.0.0.1` 또는 다른 포트로 접속 시 지도 SDK 401.
3. **top-1 skip 논리**: 검증 도입 후 top-1이 실제 정신과 전문의 있는 곳으로 나오는 경우가 많아, skip이 유용한 정보를 버릴 수 있음. 사용자 UX 결정에 따라 향후 제거/조정 가능.
4. **HIRA MadmDtl 미구독 환경**: 어댑터가 401/403을 감지하면 `psychiatry_specialist_count=None`, `specialist_verified=False (Kakao 판정 유지)`로 폴백. 이 경우 이비인후과의원 등이 응답에 남을 수 있음.

---

## 10. Test plan

- [ ] `.venv/bin/python -m tests.smoke_nearby_hira` — 서울시청 반경 1km 병원/약국 (HIRA envelope 파싱 정합)
- [ ] `.venv/bin/python -m tests.smoke_kakao_local` — Kakao Local geocoding ↔ HIRA 좌표 교차 검증
- [ ] `.venv/bin/python -m tests.smoke_psychiatric_personas` — dgsbjtCd=03 페르소나별 정신과 카운트
- [ ] `.venv/bin/python -m tests.smoke_crisis_nearby` — Crisis + Nearby 통합 (canned)
- [ ] `curl "http://localhost:8080/ai/nearby/hospitals?lat=37.5807&lng=126.8898&radius_km=2&num_of_rows=30"` — VP-001 2km · 5개 verified places 확인
- [ ] `uv run uvicorn src.main:app --port 8080` + 브라우저 `http://localhost:8080/ai/nearby/ui` — 페르소나 선택 → 지도 마커 verified 병원만 표시 확인
- [ ] `.venv/bin/python -m src.f1 --persona VP-003 --max-turns 5 --audio-vp-default` — 음성 crisis + nearby (add/f1-stt-and-ocr 병합 상태)
- [ ] `uv run ruff check src tests` → All checks passed!
- [ ] `.venv/bin/python -c "from src.main import app; assert len(app.routes) == 22"`

---

## 11. Notes

- `add/f1-stt-and-ocr` 로컬 병합됨(commit `999975e`) → mp3 crisis 흐름 검증 목적. PR #38이 먼저 병합되면 이 PR은 rebase 없이 clean merge 가능.
- Master 직접 커밋 없음. 팀 규정 준수.
- `.env`는 커밋하지 않음. `HIRA_MADM_DTL_SERVICE_URL`은 default 값이 config에도 있어 없이도 동작.

---

## 12. PR 재생성 명령

```bash
gh pr edit 42 --body-file docs/ai/pr_description_map_api.md
```
