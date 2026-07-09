# PR: HIRA + Kakao Map 기반 근처 병원/약국 검색 + Crisis 자동 안내

> **Branch**: `add/map-api` → `Master`
> **PRD reference**: FR-011 (Crisis 시 자원 안내) · Task1 F1 확장
> **Guide doc**: `docs/ai/api/hira_kakao_map_api_usage_guide.md`

---

## 1. Summary

환자 위치 기반으로 **HIRA(건강보험심사평가원) 병원/약국을 실시간 검색**하고 **Kakao Map으로 시각화**하는 기능을 추가. 특히 F1 파이프라인에서 **Crisis 발동 시 근처 정신건강의학과 top-3을 자동 첨부**하여 자살예방상담전화(109) 안내와 함께 즉시 접근 가능한 오프라인 자원을 제시.

**변경 규모** (map-api 자체): 32 files, +10,309 / -5 lines
**병합 포함** (add/f1-stt-and-ocr 로컬 병합 후 음성 crisis 검증까지 포함): 135 files, +30,381 / -70 lines

---

## 2. 왜 필요한가

- **FR-011 (Crisis 시 자원 안내)**: 자살/자해 위기 상황에서 109/119 안내만으로는 부족. 물리적으로 도달 가능한 정신건강의학과가 필요.
- **환자 컨텍스트 활용**: 페르소나별 실제 거주지 좌표 (관악구/강서구/성남/영등포 등)를 활용해 "여기서 가장 가까운 정신과 3곳" 즉시 안내.
- **재사용 가능한 자원 검색 인프라**: F2 handoff 이후에도, 사후 관리(추후 방문 병원/약국 안내)에 활용 가능.

---

## 3. 아키텍처

```
사용자 좌표 (lat, lng)
      ↓
┌──────────────────────────────────────────────┐
│ NearbyFacilitiesAgent                        │
│   ├─ HiraHospitalAdapter  (dgsbjtCd=03 등)   │  ← HIRA Open API
│   ├─ HiraPharmacyAdapter                    │  ← HIRA Open API
│   └─ KakaoLocalAdapter (선택)               │  ← 주소 → 좌표 보정
│                                              │
│  결과: Place[] (name, dist_km, phone, ...)   │
│        + MapPayload (Kakao markers)          │
└──────────────────────────────────────────────┘
      ↓                    ↓                    ↓
GET /ai/nearby/…    /ai/nearby/ui         F1 Crisis Handler
  (JSON API)         (Kakao Map 데모)     (dgsbjtCd=03 top-3
                                          → AI 응답에 자동 첨부)
```

---

## 4. 신규 파일 상세

### 4.1 어댑터 (Adapters)

#### `src/adapters/hira_base.py` (218 lines) 🆕
**역할**: HIRA Open API 공통 클라이언트 (병원/약국 어댑터 상속용).

**주요 기능**:
- ServiceKey 인증 (backend only, client 노출 금지)
- `_fetch_page()`: 429/5xx 지수 백오프 재시도 (2s → 4s → 8s, 최대 3회)
- `parse_envelope()`: `items` array/single object/missing 3가지 케이스 모두 처리
- `check_success()`: `resultCode != '00'` 시 `HiraApiError` 발생

#### `src/adapters/hira_hospital.py` (144 lines) 🆕
**엔드포인트**: `https://apis.data.go.kr/B551182/hospInfoServicev2`
- `search(lat, lng, radius_m, subject_code=None, hospital_type_code=None, ...)`
- `search_all()`: 다중 페이지 자동 집계 (max_pages, truncated 플래그)
- **핵심 필터**: `dgsbjtCd=03` (정신건강의학과)

#### `src/adapters/hira_pharmacy.py` (125 lines) 🆕
**엔드포인트**: `https://apis.data.go.kr/B551182/pharmacyInfoService`
- Operation: `getParmacyBasisList` (**HIRA 공식 스펙 오타 그대로 유지** — 그대로 안 쓰면 400)

#### `src/adapters/kakao_local.py` (157 lines) 🆕
**엔드포인트**: `https://dapi.kakao.com/v2/local/search/address.json`
- `search_address(query)` / `geocode(query) → (lat, lng)`
- Auth: `Authorization: KakaoAK {rest_api_key}`
- HIRA 좌표 교차 검증용 (0~51m 오차로 실측 일치)

### 4.2 에이전트 (Agent)

#### `src/agents/nearby_facilities.py` (354 lines) 🆕

**핵심 클래스**:
```python
class NearbyFacilitiesAgent:
    async def search(kind: Literal["hospital","pharmacy"], lat, lng, ...) -> list[Place]
    async def report(...) -> MapPayload
```

**주요 로직**:
- `_normalize_hira_item()`: HIRA raw item → 표준 `Place` (XPos → lng, YPos → lat 매핑 문서화)
- `_haversine_km()`: 좌표 → 거리 계산 (반경 필터링 · 정렬)
- **KR 좌표 sanity check**: lat 30-45, lng 120-135 밖이면 필터 아웃 (HIRA 오데이터 방어)
- **개인정보 안전 필드**: `emergency_available`, `open_now` → 데이터 없으면 `null` (절대 `True`로 추정 금지)
- Kakao Map 마커 페이로드 (색깔, 라벨, 클릭 URL) 자동 생성

### 4.3 스키마 (Pydantic Schemas)

#### `src/schemas/nearby.py` (210 lines) 🆕

**주요 클래스**:
- `Place` — `name, address, phone, kind, distance_km, lat, lng, dept_codes, emergency_available, open_now`
- `Marker` — Kakao Map 마커 (color, label, click URL 포함)
- `MapPayload` — `center, zoom, markers[], list_items[]`
- `SourceMeta` — HIRA vs Kakao 출처 표기 (`data_provenance`)

### 4.4 라우트 (FastAPI Routes)

#### `src/routes/nearby.py` (529 lines) 🆕

**엔드포인트**:
| Method | Path | 설명 |
|---|---|---|
| GET | `/ai/nearby/hospitals` | HIRA 병원 검색 (반경, 진료과, 유형 필터) |
| GET | `/ai/nearby/hospitals/report` | Kakao Map 페이로드 포함 |
| GET | `/ai/nearby/pharmacies` | HIRA 약국 검색 |
| GET | `/ai/nearby/pharmacies/report` | Kakao Map 페이로드 포함 |
| GET | `/ai/nearby/ui` | **Kakao Map 데모 페이지 (Web UI)** |

**`/ui` 페이지 기능**:
- 페르소나 선택 (VP-001~004) → 자동 좌표 세팅
- 반경(m) · 결과 개수 조절
- 병원 ↔ 약국 토글
- **"정신건강의학과만" 체크박스** (`dgsbjtCd=03` on/off)
- 사이드바 리스트 ↔ 지도 마커 양방향 동기화
- 마커 클릭 → Kakao 길찾기 URL 새 창

**게이팅**:
- 좌표 없음 → 400
- HIRA API 오류 → 502 (Bad Gateway)
- Kakao 키 없음 → REST 라우트는 계속 동작, `/ui`는 경고 표시

### 4.5 f1.py 확장 (+166 lines)

**신규 상수**:
```python
PERSONA_LOCATIONS = {
    "VP-001": (37.4763, 126.9633),  # 서울 관악
    "VP-002": (37.5172, 127.0473),  # 서울 강남
    "VP-003": (37.4837, 126.9295),  # 서울 관악구
    "VP-004": (37.5509, 126.8495),  # 서울 강서
}
```

**신규 F1Result 필드**:
```python
@dataclass
class F1Result:
    ...
    patient_lat: float | None
    patient_lng: float | None
    nearby_psychiatric: list[dict]   # Crisis 발동 시 top-3
```

**신규 메서드**:
- `_get_nearby_agent()` — lazy singleton
- `_fetch_crisis_facilities(lat, lng, k=3)` — dgsbjtCd=03 top-k 조회
- Crisis 핸들러: `safety.crisis_triggered=True` 시 → `agent_response`에 근처 정신과 top-3 자동 첨부 (이름·거리·전화)

**CLI 신규 인자**:
- `--lat FLOAT` / `--lng FLOAT` — 임의 좌표 (페르소나 기본값 덮어쓰기)

**Report 확장**: Crisis 턴 아래 "🚨 위기 대응 · 근처 정신건강의학과" 섹션 자동 삽입.

### 4.6 설정 · DI · main.py

#### `src/config.py` 신규 필드
```python
# HIRA
hira_service_key: str = Field(default="", ...)  # 공공데이터포털 발급
hira_hospital_service_url: str = Field(default="https://apis.data.go.kr/B551182/hospInfoServicev2")
hira_pharmacy_service_url: str = Field(default="https://apis.data.go.kr/B551182/pharmacyInfoService")

# Kakao
kakao_rest_api_key: str = Field(
    default="",
    validation_alias=AliasChoices("KAKAO_REST_KEY_ENCODED", "KAKAO_REST_API_KEY_ACTUAL"),
)
kakao_map_javascript_key: str = Field(
    default="",
    validation_alias=AliasChoices("KAKAO_JS_KEY_ENCODED", "KAKAO_MAP_JAVASCRIPT_KEY"),
)
```

**이유**: `.env`의 팀 관례(`KAKAO_REST_KEY_ENCODED`)와 docs canonical 이름(`KAKAO_REST_API_KEY`) 모두 accept.

#### `src/dependencies.py` 추가
- `get_hira_hospital_adapter()` / `get_hira_pharmacy_adapter()` (fail-fast on missing key)
- `get_kakao_local_adapter()` — Kakao 키 없으면 `None` 반환 (optional)
- `get_nearby_agent()` — Hospital + Pharmacy 어댑터 조합

#### `src/main.py`
- `from src.routes.nearby import router as nearby_router`
- `app.include_router(nearby_router)`

---

## 5. 실전 검증 결과

### 5.1 HIRA API 응답 정합성

**서울시청 (37.5665, 126.9780) 반경 1km**:
- 병원: 총 435건 중 상위 20건 정렬 (거리 0.02~0.98km) ✅
- 약국: 총 130건 중 상위 20건 정렬 ✅
- 좌표 sanity check 통과 (KR 범위)

### 5.2 Kakao Local ↔ HIRA 좌표 교차 검증

Kakao Local geocoding으로 얻은 좌표 vs HIRA 병원 좌표 오차:
- 서울시청, 광화문, 신촌, 강남역 4개 지점: **0~51m 오차** (사실상 일치)
- HIRA 좌표를 신뢰 가능한 것으로 확정 → Kakao geocoding은 optional한 보정용

### 5.3 페르소나별 근처 정신건강의학과 (`dgsbjtCd=03`, 반경 5km)

| VP | 위치 | 정신과 개수 | Top-1 병원 | 거리 |
|---|---|---|---|---|
| VP-001 | 관악 | 15 | 관악서울대학교병원 | 0.4km |
| VP-002 | 강남 | 41 | 강남세브란스병원 등 | 0.6km |
| VP-003 | 관악구 | **79** | **중앙대학교병원** | **3.3km** |
| VP-004 | 강서 | 56 | **이화여자대학교의과대학부속서울병원** | **1.4km** |

### 5.4 Crisis + 근처 정신과 통합 (canned utterances)

**VP-003 (관악구)** — Turn 2 crisis 발동 시:
```
🚨 위기 대응 · 근처 정신건강의학과 (5km 이내)
1. 중앙대학교병원 (3.28km) ☎ 1800-1114
2. 대림성모병원 (4.15km) ☎ 02-829-9000
3. 가톨릭대학교 여의도성모병원 (4.65km) ☎ 1661-7575
```

**VP-004 (강서구)** — Turn 3 crisis 발동 시:
```
🚨 위기 대응 · 근처 정신건강의학과 (5km 이내)
1. 이화여자대학교의과대학부속서울병원 (1.36km) ☎ 1522-7000
2. 이화여자대학교의과대학부속목동병원 (3.61km) ☎ 02-2650-5114
3. 서울특별시서남병원 (4.57km) ☎ 1566-6688
```

### 5.5 음성(STT) 입력에서도 동일하게 동작 (bundled test)

로컬 병합된 `add/f1-stt-and-ocr` 브랜치의 STT 파이프라인을 이 브랜치에서 실행:

| VP | 입력 | Crisis 턴 | Nearby 정신과 top-3 | 결과 |
|---|---|---|---|---|
| VP-003 | 🎤 `VP-003-{001,002}.mp3` (2개) | Turn 2 | 중앙대/대림성모/여의도성모 | ✅ 동일 결과 |
| VP-004 | 🎤 `VP-004-{001~003}.mp3` (3개) | Turn 3 | 이대서울/이대목동/서남 | ✅ 동일 결과 |

**결론**: 텍스트 · 음성 두 입력 경로 모두 동일한 Crisis + 근처 정신과 자동 안내 흐름을 재현.

---

## 6. 테스트 스크립트 (신규)

| 스크립트 | 목적 |
|---|---|
| `tests/smoke_nearby_hira.py` | HIRA 서울시청 반경 검색 정합 확인 |
| `tests/smoke_kakao_local.py` | Kakao Local geocoding + HIRA 좌표 교차 검증 |
| `tests/smoke_nearby_personas.py` | 4 페르소나 각각 병원/약국 검색 |
| `tests/smoke_psychiatric_personas.py` | `dgsbjtCd=03` 필터 정합 (VP별 정신과 개수) |
| `tests/smoke_crisis_nearby.py` | Crisis + Nearby 통합 (canned crisis 발화) |

---

## 7. 산출물 (`docs/ai/simulation_results/nearby_smoke/`)

```
hospitals_smoke.json          (HIRA 병원 반경 검색 결과)
pharmacies_smoke.json         (HIRA 약국 반경 검색 결과)
kakao_local_smoke.json        (Kakao Local + HIRA 교차 검증)
personas_nearby.json          (4 페르소나 상세 결과)
psychiatric_personas.json     (dgsbjtCd=03 페르소나별 정신과)
crisis_nearby.json            (Crisis + Nearby 통합 결과)
```

VP-003/004 crisis 시나리오 세션 파일도 포함 (conversation.json + report.md + checklist.md).

---

## 8. 보안 · 명세 준수

### 보안
- ✅ **HIRA/Kakao REST API 키 backend only** — client에 노출되지 않음
- ✅ **Kakao JavaScript SDK 키만** `/ui` HTML에 임베드 (도메인 등록으로 스코프 제한: `localhost:8080`)
- ✅ `.env` 커밋 금지 유지 (실제 키 포함)

### FR 정합
- ✅ **FR-011** Crisis 시 자원 안내: 109/119 + **근처 정신과 top-3 실시간 조회**
- ✅ 개인정보 안전 필드: `emergency_available`, `open_now` → 데이터 없으면 `null` (`True`로 추정 절대 금지)
- ✅ Data provenance: `source="HIRA_openapi"` / `source="kakao_local"` 명시

---

## 9. Test plan

- [ ] `.venv/bin/python -m tests.smoke_nearby_hira` — 서울시청 반경 1km 병원/약국
- [ ] `.venv/bin/python -m tests.smoke_kakao_local` — Kakao ↔ HIRA 좌표 교차 검증
- [ ] `.venv/bin/python -m tests.smoke_nearby_personas` — 4 페르소나 nearby 검색
- [ ] `.venv/bin/python -m tests.smoke_psychiatric_personas` — dgsbjtCd=03 필터
- [ ] `.venv/bin/python -m tests.smoke_crisis_nearby` — canned crisis + nearby (VP-003/004)
- [ ] `.venv/bin/python -m src.f1 --persona VP-003 --max-turns 5 --audio-vp-default` — 음성 crisis + nearby (VP-003)
- [ ] `.venv/bin/python -m src.f1 --persona VP-004 --max-turns 5 --audio-vp-default` — 음성 crisis + nearby (VP-004)
- [ ] `uv run uvicorn src.main:app --port 8080` + 브라우저 `http://localhost:8080/ai/nearby/ui` → 페르소나 선택 → 정신과만 토글 확인
- [ ] `uv run pytest apps/ai-server/tests` — 기존 회귀

---

## 10. Notes

- **로컬에서 `origin/add/f1-stt-and-ocr` 병합됨** (커밋 `999975e`): 음성 crisis 시나리오 검증을 위해 STT 어댑터/에이전트/f1 통합을 이 브랜치로 가져옴. `add/f1-stt-and-ocr` (PR #38) 이 먼저 Master 병합될 예정이면, 이 PR은 그 이후에 rebase 없이 clean 병합 가능.
- **Kakao Map JavaScript SDK 도메인 제약**: 현재 등록된 도메인은 `localhost:8080` — `127.0.0.1` / 다른 포트는 401. dev 서버는 반드시 `localhost:8080`으로 실행.
- **HIRA ServiceKey 발급**: 공공데이터포털 로그인 → "국민건강보험공단 병원정보서비스" / "약국정보서비스" 각각 활용 신청 (승인 즉시).
- 원격 `Master` 브랜치는 이 PR을 통해서만 갱신 (직접 커밋 없음, 팀 규정 준수).

---

## 11. Known Issues

- **HIRA API 간헐 5xx**: `hira_base._fetch_page`의 지수 백오프로 자동 재시도됨 (2s → 4s → 8s). 3회 실패 시 502 반환 → F1 crisis 핸들러는 예외 catch 후 근처 정신과 목록 비운 채 계속 진행 (109/119 안내는 유지).
- **Kakao Map SDK 도메인 미등록 시**: `/ui` HTML은 렌더되지만 지도 영역이 빈 채로 남고 콘솔 401. 사이드바 리스트 기능은 정상 동작.
- **Nearby ordering vs 도로 거리**: Haversine 직선 거리 기준. 실제 도로 거리는 Kakao Directions API가 필요 (추후 작업 후보).

---

## 12. PR 생성 명령

```bash
gh pr create \
  --base Master \
  --head add/map-api \
  --title "feat(ai-server): HIRA + Kakao Map — 근처 병원/약국 + Crisis 자동 안내" \
  --body-file docs/ai/pr_description_map_api.md
```
