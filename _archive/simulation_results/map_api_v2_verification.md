# Map-API 검증 리포트 — 정신건강의학과 전문의 재직 병원 · Crisis 자동 안내

> **Branch**: `add/map-api`
> **Verified at**: 2026-07-10
> **Related PR body**: `docs/ai/pr_description_map_api.md`

---

## 1. 검증된 사실 요약

1. **HIRA `getHospBasisList` 응답에는 `dgsbjtCd`/`dgsbjtCdNm` 필드가 존재하지 않는다** (필터 파라미터로만 작동). 진료과 정보는 별도 서비스 필요.
2. **HIRA MadmDtl 2.8 (`getDgsbjtInfo2.8`) 활용신청 승인 완료**, 현재 키로 진료과별 전문의 수 조회 가능.
3. **Kakao Local `keyword.json`의 `category_name`**은 "의료,건강 > 병원 > 정신건강의학과" 형태로 세분화되어 1차 검증 대체 가능.
4. 병원 검색 결과에서 **실제 정신건강의학과 전문의 0명인 곳(예: 수이비인후과의원, 프리즘의원)은 명시적으로 배제**된다. 응답 places · map.markers · sources.normalized_count 전부 동기화.
5. `_fetch_crisis_facilities()`는 num_of_rows=30 → 필터·검증 통과 결과에서 top-1 skip → top-3 반환.

---

## 2. 4단계 파이프라인 (실측 검증)

```
사용자 좌표 (lat, lng)
        ↓
[1] HIRA getHospBasisList  (dgsbjtCd=03, xPos/yPos, radius)
    응답 필드: yadmNm, addr, telno, clCd/clCdNm, XPos/YPos, ykiho,
              mdept*Cnt, cmdc*Cnt, dety*Cnt, pnursCnt, drTotCnt, distance, ...
    ⚠️ dgsbjtCd/dgsbjtCdNm 필드는 응답에 없음
        ↓
[2] 종별 필터
    ALLOWED_CL_CODES  = {01 상급종합, 11 종합, 21 병원, 29 정신병원, 31 의원}
    EXCLUDED_TYPE_NAMES = {요양병원, 한방병원, 한의원, 치과병원, 치과의원,
                            보건소, 보건지소, 보건진료소}
        ↓
[3] Kakao Local keyword=정신건강의학과, category_group=HP8
    응답 category_name = "의료,건강 > 병원 > 정신건강의학과"
    HIRA place 좌표를 4자리 반올림 격자(~11m) 이웃 3×3(≈33m)로 매칭
    → 1차 specialist_verified=True (fast)
        ↓
[4] HIRA MadmDtlInfoService2.8/getDgsbjtInfo2.8  (per ykiho, concurrency=5, cache)
    응답 item: dgsbjtCd, dgsbjtCdNm, dgsbjtPrSdrCnt
    counts is None (미승인/실패) → Kakao 판정 유지 (specialist_verified=False fallback)
    counts[03] >= 1 → verified=True · count 필드 채움
    counts[03] == 0 → 명시적 drop (places / markers / normalized_count 동기화)
        ↓
[5] 정렬 (스펙 §7)
    key = (not specialist_verified, distance, -count, name)
        ↓
    NearbyResponse
```

---

## 3. 실측 결과 — 페르소나별 반경 5km

| VP | 좌표 | HIRA raw | 종별 통과 | **최종 verified** | clinic / general / psychiatric |
|---|---|---|---|---|---|
| VP-001 (마포) | (37.5807, 126.8898) | 85 | 24 | **18** | 15 / 2 / 1 |
| VP-002 (판교) | (37.4020, 127.1087) | 69 | 30 | **23** | 19 / 3 / 1 |
| VP-003 (관악) | (37.4782, 126.9515) | 139 | 29 | **19** | 10 / 8 / 1 |
| VP-004 (강서) | (37.5510, 126.8495) | 93 | 28 | **20** | 17 / 2 / 1 |

- HIRA raw → 종별 통과: 요양병원·한방·치과 등 제거
- 종별 통과 → 최종 verified: MadmDtl에서 정신과 전문의 == 0인 병원 제거

---

## 4. VP-001 반경 2km 상세 (전문의 표기)

Request: `GET /ai/nearby/hospitals?lat=37.5807&lng=126.8898&radius_km=2&num_of_rows=30`

Response counter:
```json
{
  "sources": {
    "hospital": {"total_count": 8, "normalized_count": 5}
  }
}
```

### 응답에 포함된 병원 (5)

| # | 병원 | 거리 | 종별 | 정신과 전문의 |
|---|---|---|---|---|
| 1 | 상암정신건강의학과의원 | 0.098km | 의원 | **2명** |
| 2 | 도우정신건강의학과의원 | 0.151km | 의원 | **2명** |
| 3 | 온유정신건강의학과의원 | 0.369km | 의원 | **2명** |
| 4 | 민정신건강의학과의원 | 0.840km | 의원 | **1명** |
| 5 | 사람과생각정신건강의학과의원 | 0.989km | 의원 | **1명** |

### 응답에서 배제된 병원 (2) — MadmDtl 실측 결과

- **수이비인후과의원** (0.58km) — 이비인후과 1명, 정신건강의학과 0명
- **프리즘의원** (1.03km) — 내과 1명, 정신건강의학과 0명

두 병원 모두 HIRA `dgsbjtCd=03` 필터에는 잡히지만 (등록 이력 기준), MadmDtl 실측 진료과별 전문의 수는 정신과 0명. Agent가 응답 `places` 배열과 `map.markers`에서 삭제. UI 지도에도 표시되지 않는다.

---

## 5. Crisis smoke 실측 (canned utterances)

### VP-003 (박민수 · 관악) — Turn 2 crisis
```
📍 가까운 정신건강의학과:
1. 의료법인서울효천의료재단 에이치플러스양지병원 (1.8km) · ☎ 02-1877-8875   [정신과 전문의 1명, 종합병원]
2. 강신경정신과의원 (2.0km) · ☎ 02-871-7121                                  [정신과 전문의 1명, 의원]
3. 개운정신건강의학과의원 (2.9km) · ☎ 02-534-5568                            [정신과 전문의 1명, 의원]
```
- top-1 skip 대상: 나눔정신건강의학과의원 (0.33km, 정신과 전문의 1명)

### VP-004 (최하은 · 강서) — Turn 2 crisis
```
📍 가까운 정신건강의학과:
1. 이화여자대학교의과대학부속서울병원 (1.4km) · ☎ 1522-7000                [정신과 전문의 4명, 종합병원]
2. 가족사랑정신과의원 (1.4km) · ☎ 02-3663-5956                             [정신과 전문의 1명, 의원]
3. 마음과정신건강의학과의원 (1.4km) · ☎ 02-2697-8575                       [정신과 전문의 1명, 의원]
```
- top-1 skip 대상: 마음의지도정신건강의학과의원 (1.25km, 정신과 전문의 1명)

산출물: `docs/ai/simulation_results/nearby_smoke/crisis_nearby.json`

---

## 6. Kakao Local 카테고리 매칭 실측 (VP-001 마포 반경 5km)

`GET https://dapi.kakao.com/v2/local/search/keyword.json`
```
query=정신건강의학과
category_group_code=HP8
x=126.8898, y=37.5807, radius=5000, sort=distance
```

결과: `meta.total_count = 47`. 각 document의 `category_name = "의료,건강 > 병원 > 정신건강의학과"`. 상위 8개 실제 결과:
1. 상암정신건강의학과의원 — 0.10km
2. 도우정신건강의학과의원 — 0.14km
3. 온유정신건강의학과의원 — 0.38km
4. 민 정신건강의학과의원 — 0.84km
5. 사람과생각정신건강의학과의원 — 0.99km
6. 연세인정신건강의학과의원 — 2.02km
7. 한혜성 조이의원 — 2.27km (category=정신건강의학과)
8. 좋은정신건강의학과의원 — 2.47km

---

## 7. HIRA 서브서비스 접근 상태 (실측 · 2026-07-10)

| Endpoint | 상태 | 비고 |
|---|---|---|
| `hospInfoServicev2/getHospBasisList` | ✅ 200 | 병원 기본 정보 |
| `pharmacyInfoService/getParmacyBasisList` | ✅ 200 | 약국 정보 · 스펙 오타(Parmacy) 그대로 |
| `MadmDtlInfoService2.8/getDgsbjtInfo2.8` | ✅ 200 | **활용신청 승인 완료** — 진료과별 전문의 수 |
| `MadmDtlInfoService2.7/getDgsbjtInfo2.7` | ❌ 403 | 구버전 미구독 |
| `MadmDtlInfoService2/getDgsbjtInfo2` | ❌ 500 | 구버전 |
| `hospInfoServicev2/getDgsbjtInfo(2)` | ❌ 404 | 존재하지 않음 |

**MadmDtl 2.8 probe 응답 예시 (양지병원 ykiho)**:
```
{'01': 23, '02': 5, '03': 1, '04': 11, '05': 4, '06': 3, '07': 0,
 '09': 3, '10': 3, '11': 4, '13': 1, '15': 2, '16': 8, '18': 2,
 '19': 1, '21': 1, '23': 3, '24': 11, '25': 1, '59': 0, '61': 0}
```

---

## 8. 재현 명령

```bash
cd apps/ai-server

# Boot + lint (모두 통과)
.venv/bin/python -c "from src.main import app; print(len(app.routes))"   # 22
.venv/bin/ruff check src tests                                             # All checks passed!

# 페르소나별 5km 결과 (§3 표 재현)
.venv/bin/python -c "
import asyncio, os
from dotenv import load_dotenv; load_dotenv('.env')
os.environ['PROMPTS_BASE_DIR'] = '../../docs/ai/prompts'
from src.dependencies import get_nearby_agent
from src.schemas.nearby import NearbySearchInput
from src.f1 import PERSONA_LOCATIONS
async def m():
    a = get_nearby_agent()
    for vp,(lat,lng) in PERSONA_LOCATIONS.items():
        r = await a.search(NearbySearchInput(session_id=vp, entity_type='hospital',
            lat=lat, lng=lng, radius_km=5, num_of_rows=30))
        print(f'{vp}: hira={r.sources[\"hospital\"].total_count} → final={len(r.places)}')
asyncio.run(m())
"

# VP-001 2km 실측 (§4 표)
curl "http://localhost:8080/ai/nearby/hospitals?lat=37.5807&lng=126.8898&radius_km=2&num_of_rows=30"

# Crisis smoke (§5)
.venv/bin/python -m tests.smoke_crisis_nearby

# UI (localhost:8080 필수 — Kakao SDK 도메인 제약)
PROMPTS_BASE_DIR=../../docs/ai/prompts \
  .venv/bin/uvicorn src.main:app --host 127.0.0.1 --port 8080
# 브라우저: http://localhost:8080/ai/nearby/ui
```

---

## 9. 산출물

- `docs/ai/simulation_results/nearby_smoke/crisis_nearby.json` — Crisis + Nearby 캔드 결과
- `docs/ai/simulation_results/nearby_smoke/personas_nearby.json` — 페르소나 5km 상세
- `docs/ai/simulation_results/nearby_smoke/psychiatric_personas.json` — 진료과 필터 적용 결과
- `docs/ai/simulation_results/nearby_smoke/kakao_local_smoke.json` — Kakao ↔ HIRA 좌표 교차 검증
- `docs/ai/simulation_results/nearby_smoke/hospitals_smoke.json`, `pharmacies_smoke.json` — HIRA 기본 검증
- 본 리포트 · `docs/ai/pr_description_map_api.md` (PR body)

---

## 10. 제한 사항 (검증된 사실)

- **HIRA MadmDtl 응답 지연**: 병원 20~30개 검증 시 총 4~13초 (concurrency=5, HIRA 개별 응답 1~2초). ykiho 단위 프로세스 내 dict 캐시로 재조회 절약.
- **Kakao Map SDK 도메인 제약**: `/ai/nearby/ui`는 `localhost:8080`으로만 접근 가능. 다른 포트/`127.0.0.1`은 401.
- **캐시 정책 미도입**: 스펙 §12의 24h/7d 캐시는 프로세스 dict 이상 미구현. Redis 등 외부 캐시 도입은 향후 작업.
- **특수진료병원정보서비스** (부가 태그용) 미연동. 이번 스코프 밖.
- **MadmDtl 미구독 환경 fallback**: 어댑터가 401/403 응답을 감지하면 `specialist_verified=false`, `count=None`로 폴백. 이 경우 이비인후과의원 등이 응답에 남을 수 있다.
