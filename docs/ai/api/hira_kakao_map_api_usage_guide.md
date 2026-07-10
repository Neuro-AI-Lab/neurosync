# HIRA 병원/약국 API + Kakao Map API 입력/출력 연동 리포트

> 작성일: 2026-06-25  
> 검수일: 2026-06-27  
> 대상: HIRA 병원정보서비스, HIRA 약국정보서비스, Kakao Maps JavaScript SDK, Kakao Maps URL, 선택적 Kakao Local REST API  
> 목적: HIRA에서 받은 병원/약국 위치 정보를 Kakao Map에 표시하기 위한 요청 형태, 출력 형태, 필드 매핑, 활용 방식을 정리한다.  
> 보안: 실제 `ServiceKey`, Kakao JavaScript 키, Kakao REST API 키는 `.env` 또는 배포 환경 변수에만 저장한다. 이 문서에는 키 값을 기록하지 않는다.  
> 상태 구분: **검증됨** = 기존 Hira 마크다운 검증 내용 기준, **Web 연동 기준** = Kakao Maps JavaScript SDK 기준, **선택 사용** = 좌표 보정 등 필요할 때만 사용.

## 0. 공통 요청/응답 및 연동 구조

### 공통 처리 흐름

```text
사용자 위치 또는 검색 조건 확보
  -> Backend에서 HIRA 병원/약국 API 호출
  -> HIRA 원본 응답 파싱
  -> 병원/약국 공통 field로 정규화
  -> XPos/YPos를 lng/lat로 변환
  -> 거리 계산 및 반경 필터
  -> map.markers 출력 생성
  -> Web/App에서 Kakao Map SDK로 marker 렌더링
```

### API별 책임

| API | 책임 | Key 위치 |
| --- | --- | --- |
| HIRA 병원정보서비스 | 병원명, 주소, 전화번호, 종별, 좌표 제공 | Backend |
| HIRA 약국정보서비스 | 약국명, 주소, 전화번호, 좌표 제공 | Backend |
| Kakao Maps JavaScript SDK | 지도 표시, marker, infoWindow, bounds, clusterer | Web client |
| Kakao Maps URL | 지도 바로가기, 길찾기 바로가기 | Key 불필요 |
| Kakao Local REST API | 주소 geocoding, 좌표 변환, 장소 검색 | Backend 권장 |

### 공통 좌표 규칙

HIRA와 Kakao Map의 좌표 이름과 입력 순서가 다르다.

| 원천 | 필드 | 의미 | 앱 field | Kakao `LatLng` 인자 |
| --- | --- | --- | --- | --- |
| HIRA | `XPos` | 경도 | `lng`, `longitude` | 두 번째 인자 |
| HIRA | `YPos` | 위도 | `lat`, `latitude` | 첫 번째 인자 |

```js
new kakao.maps.LatLng(place.lat, place.lng)
```

주의:

- `XPos`를 latitude로 넣으면 marker가 전혀 다른 위치에 찍힌다.
- marker를 생성하기 전에 `lat`, `lng`가 숫자인지 확인한다.
- 좌표가 없는 병원/약국은 목록에는 남길 수 있지만 지도 marker에서는 제외한다.

---

## 1. 환경 변수 및 키 구분

### 환경 변수 입력 형태

```env
HIRA_SERVICE_KEY=<issued_hira_service_key>
KAKAO_MAP_JAVASCRIPT_KEY=<issued_kakao_javascript_key>
KAKAO_REST_API_KEY=<issued_kakao_rest_api_key>
```

| 이름 | 필수 | 사용 위치 | 설명 |
| --- | --- | --- | --- |
| `HIRA_SERVICE_KEY` | 필수 | Backend | 공공데이터포털 HIRA Open API 호출용 일반 인증키 |
| `KAKAO_MAP_JAVASCRIPT_KEY` | Web 사용 시 필수 | Web client | Kakao Maps JavaScript SDK 로딩용 |
| `KAKAO_REST_API_KEY` | 선택 | Backend | Kakao Local REST API 호출용 |

주의:

- HIRA key는 client에 노출하지 않는다.
- Kakao REST API key도 client에 노출하지 않는다.
- Kakao JavaScript key는 브라우저에 들어가는 키이므로 카카오디벨로퍼스에서 Web 플랫폼 도메인 제한을 설정한다.
- 문서, commit, 로그, JSON 출력 파일에 실제 key 값을 남기지 않는다.

---

## 2. 건강보험심사평가원_병원정보서비스

- 상태: **검증됨**
- Base endpoint: `https://apis.data.go.kr/B551182/hospInfoServicev2`
- 대표 operation: `getHospBasisList`
- Method: `GET`
- 용도: 병원 기본 정보와 위치 좌표를 가져와 지도 marker와 병원 목록을 만든다.

### 입력 형태

```http
GET https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList
  ?ServiceKey={HIRA_SERVICE_KEY}
  &pageNo=1
  &numOfRows=20
  &_type=json
```

위치 기반 검색 예시:

```http
GET https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList
  ?ServiceKey={HIRA_SERVICE_KEY}
  &pageNo=1
  &numOfRows=100
  &_type=json
  &xPos=127.05983
  &yPos=37.61955
  &radius=20000
```

지역/조건 기반 검색 예시:

```http
GET https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList
  ?ServiceKey={HIRA_SERVICE_KEY}
  &pageNo=1
  &numOfRows=20
  &_type=json
  &sidoCd=110000
  &sgguCd=110022
  &dgsbjtCd=01
  &clCd=31
```

### 입력 파라미터

| 파라미터 | 필수 | 예시 | 설명 |
| --- | --- | --- | --- |
| `ServiceKey` | 필수 | `.env` | HIRA 인증키 |
| `pageNo` | 옵션 | `1` | 페이지 번호 |
| `numOfRows` | 옵션 | `20` | 한 페이지 결과 수 |
| `_type` | 옵션 | `json` | JSON 응답 요청. 미지정 시 XML 응답 가능 |
| `yadmNm` | 옵션 | `삼성` | 병원명 검색어 |
| `sidoCd` | 옵션 | `110000` | 시도 코드 |
| `sgguCd` | 옵션 | `110022` | 시군구 코드 |
| `dgsbjtCd` | 옵션 | `01` | 진료과목 코드 |
| `clCd` | 옵션 | `31` | 의료기관 종별 코드 |
| `xPos` | 옵션 | `127.05983` | 기준 경도 |
| `yPos` | 옵션 | `37.61955` | 기준 위도 |
| `radius` | 옵션 | `20000` | 반경. 미터 단위 |

주의:

- 공공데이터포털 문서와 예제에 따라 `ServiceKey`와 `serviceKey` 표기가 섞여 보일 수 있다.
- 이 문서에서는 HIRA 폴더의 기존 입력/출력 리포트와 맞춰 `ServiceKey`로 표기한다.
- 실제 client 구현에서는 실호출로 동작하는 표기를 하나로 고정한다.

### 출력 형태

HIRA 공통 envelope 구조:

```json
{
  "response": {
    "header": {
      "resultCode": "00",
      "resultMsg": "NORMAL SERVICE."
    },
    "body": {
      "items": {
        "item": [
          {
            "ykiho": "...",
            "yadmNm": "예시병원",
            "addr": "서울특별시 ...",
            "telno": "02-000-0000",
            "clCd": "31",
            "clCdNm": "의원",
            "sidoCd": "110000",
            "sidoCdNm": "서울",
            "sgguCd": "110022",
            "sgguCdNm": "노원구",
            "dgsbjtCd": "01",
            "dgsbjtCdNm": "내과",
            "XPos": "127.05983",
            "YPos": "37.61955"
          }
        ]
      },
      "numOfRows": 20,
      "pageNo": 1,
      "totalCount": 123
    }
  }
}
```

XML 응답 형태:

```xml
<response>
  <header>
    <resultCode>00</resultCode>
    <resultMsg>NORMAL SERVICE.</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <ykiho>...</ykiho>
        <yadmNm>예시병원</yadmNm>
        <addr>서울특별시 ...</addr>
        <telno>02-000-0000</telno>
        <clCd>31</clCd>
        <clCdNm>의원</clCdNm>
        <XPos>127.05983</XPos>
        <YPos>37.61955</YPos>
      </item>
    </items>
    <numOfRows>20</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>123</totalCount>
  </body>
</response>
```

### 주요 출력 필드

| HIRA field | 의미 | 정규화 field |
| --- | --- | --- |
| `ykiho` | 암호화 요양기호 | `source_id` |
| `yadmNm` | 병원명 | `name`, `title` |
| `addr` | 주소 | `address` |
| `telno` | 전화번호 | `phone` |
| `clCd`, `clCdNm` | 의료기관 종별 코드/명 | `type_code`, `type_name` |
| `sidoCd`, `sidoCdNm` | 시도 코드/명 | `sido_code`, `sido_name` |
| `sgguCd`, `sgguCdNm` | 시군구 코드/명 | `sggu_code`, `sggu_name` |
| `dgsbjtCd`, `dgsbjtCdNm` | 진료과목 코드/명 (⚠️ 아래 note) | `subject_code`, `subject_name` |
| `XPos` | 경도 | `lng`, `longitude` |
| `YPos` | 위도 | `lat`, `latitude` |

> ⚠️ **실측 확인 (2026-07-10)**: `getHospBasisList`는 **응답 item에 `dgsbjtCd`/`dgsbjtCdNm`을 포함하지 않는다.** 응답에는 진료과별 의사 인원수 카운터(`mdeptGdrCnt`, `mdeptResdntCnt`, `cmdcGdrCnt`, `detyGdrCnt`, `pnursCnt` 등)만 있다. 요청 파라미터로는 사용되지만 응답 필드로는 반환되지 않는 필터 파라미터인 셈. 병원별 개별 진료과 상세는 `getDgsbjtInfo2` 등 별도 서비스가 필요. 신경-싱크는 병원 검색을 항상 `dgsbjtCd=03`로 필터하므로, 응답 후처리에서 모든 hospital place에 `subject_code="03"`, `subject_name="정신건강의학과"`를 태그해 (`_build_response` 참조), UI/AI 사용측이 진료과 확정 정보를 받도록 처리한다 (data provenance = filter-derived).

### Kakao Map 활용

병원정보서비스 출력은 다음 용도로 사용한다.

- 병원 목록 item 생성
- 병원 상세 panel 또는 bottom sheet 표시
- 병원 marker 생성
- 현재 위치 기준 거리 계산
- Kakao 길찾기 URL 생성

정규화 예시:

```json
{
  "id": "hospital:{source_id}",
  "entity_type": "hospital",
  "source_id": "...",
  "name": "예시병원",
  "title": "예시병원",
  "address": "서울특별시 ...",
  "phone": "02-000-0000",
  "type_code": "31",
  "type_name": "의원",
  "lat": 37.61955,
  "lng": 127.05983,
  "latitude": 37.61955,
  "longitude": 127.05983,
  "distance_km": 0.35,
  "coordinate_source": "hira",
  "emergency_available": null
}
```

주의:

- `emergency_available`은 HIRA 병원 기본정보만으로 확정하지 않는다.
- `null`을 응급 가능으로 표시하면 안 된다.

---

## 3. 건강보험심사평가원_약국정보서비스

- 상태: **검증됨**
- Base endpoint: `https://apis.data.go.kr/B551182/pharmacyInfoService`
- 대표 operation: `getParmacyBasisList`
- Method: `GET`
- 용도: 약국 기본 정보와 위치 좌표를 가져와 지도 marker와 약국 목록을 만든다.

주의:

- 공식 operation 이름은 `getParmacyBasisList`다.
- `Pharmacy`가 아니라 `Parmacy`로 표기되어 있으므로 URL path를 임의로 고치지 않는다.

### 입력 형태

```http
GET https://apis.data.go.kr/B551182/pharmacyInfoService/getParmacyBasisList
  ?ServiceKey={HIRA_SERVICE_KEY}
  &pageNo=1
  &numOfRows=20
  &_type=json
```

위치 기반 검색 예시:

```http
GET https://apis.data.go.kr/B551182/pharmacyInfoService/getParmacyBasisList
  ?ServiceKey={HIRA_SERVICE_KEY}
  &pageNo=1
  &numOfRows=100
  &_type=json
  &xPos=127.05983
  &yPos=37.61955
  &radius=20000
```

지역/이름 기반 검색 예시:

```http
GET https://apis.data.go.kr/B551182/pharmacyInfoService/getParmacyBasisList
  ?ServiceKey={HIRA_SERVICE_KEY}
  &pageNo=1
  &numOfRows=20
  &_type=json
  &sidoCd=110000
  &sgguCd=110022
  &yadmNm=온누리
```

### 입력 파라미터

| 파라미터 | 필수 | 예시 | 설명 |
| --- | --- | --- | --- |
| `ServiceKey` | 필수 | `.env` | HIRA 인증키 |
| `pageNo` | 옵션 | `1` | 페이지 번호 |
| `numOfRows` | 옵션 | `20` | 한 페이지 결과 수 |
| `_type` | 옵션 | `json` | JSON 응답 요청. 미지정 시 XML 응답 가능 |
| `sidoCd` | 옵션 | `110000` | 시도 코드 |
| `sgguCd` | 옵션 | `110022` | 시군구 코드 |
| `emdongNm` | 옵션 | `월계동` | 읍면동명 |
| `yadmNm` | 옵션 | `온누리` | 약국명 검색어 |
| `xPos` | 옵션 | `127.05983` | 기준 경도 |
| `yPos` | 옵션 | `37.61955` | 기준 위도 |
| `radius` | 옵션 | `20000` | 반경. 미터 단위 |

주의:

- 공식 operation 이름은 `getParmacyBasisList`다.
- `Pharmacy`가 아니라 `Parmacy` 표기를 사용한다.
- 병원정보서비스와 동일하게 실제 client 구현에서는 `ServiceKey` 또는 `serviceKey` 표기를 실호출로 검증해 고정한다.

### 출력 형태

JSON 응답 형태:

```json
{
  "response": {
    "header": {
      "resultCode": "00",
      "resultMsg": "NORMAL SERVICE."
    },
    "body": {
      "items": {
        "item": [
          {
            "ykiho": "...",
            "yadmNm": "예시약국",
            "addr": "서울특별시 ...",
            "telno": "02-000-0000",
            "sidoCd": "110000",
            "sidoCdNm": "서울",
            "sgguCd": "110022",
            "sgguCdNm": "노원구",
            "XPos": "127.05983",
            "YPos": "37.61955"
          }
        ]
      },
      "numOfRows": 20,
      "pageNo": 1,
      "totalCount": 123
    }
  }
}
```

XML 응답 형태:

```xml
<response>
  <header>
    <resultCode>00</resultCode>
    <resultMsg>NORMAL SERVICE.</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <ykiho>...</ykiho>
        <yadmNm>예시약국</yadmNm>
        <addr>서울특별시 ...</addr>
        <telno>02-000-0000</telno>
        <XPos>127.05983</XPos>
        <YPos>37.61955</YPos>
      </item>
    </items>
    <numOfRows>20</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>123</totalCount>
  </body>
</response>
```

### 주요 출력 필드

| HIRA field | 의미 | 정규화 field |
| --- | --- | --- |
| `ykiho` | 암호화 요양기호 또는 기관 식별자 | `source_id` |
| `yadmNm` | 약국명 | `name`, `title` |
| `addr` | 주소 | `address` |
| `telno` | 전화번호 | `phone` |
| `sidoCd`, `sidoCdNm` | 시도 코드/명 | `sido_code`, `sido_name` |
| `sgguCd`, `sgguCdNm` | 시군구 코드/명 | `sggu_code`, `sggu_name` |
| `XPos` | 경도 | `lng`, `longitude` |
| `YPos` | 위도 | `lat`, `latitude` |

### Kakao Map 활용

약국정보서비스 출력은 다음 용도로 사용한다.

- 약국 목록 item 생성
- 약국 marker 생성
- 병원 주변 약국 검색
- 현재 위치 기준 거리 계산
- Kakao 길찾기 URL 생성

정규화 예시:

```json
{
  "id": "pharmacy:{source_id}",
  "entity_type": "pharmacy",
  "source_id": "...",
  "name": "예시약국",
  "title": "예시약국",
  "address": "서울특별시 ...",
  "phone": "02-000-0000",
  "lat": 37.61955,
  "lng": 127.05983,
  "latitude": 37.61955,
  "longitude": 127.05983,
  "distance_km": 0.12,
  "coordinate_source": "hira",
  "open_now": null,
  "night_service_available": null,
  "holiday_service_available": null
}
```

주의:

- HIRA 약국 기본정보만으로 현재 영업 중 여부를 확정하지 않는다.
- `open_now=null`을 영업 중으로 표시하면 안 된다.
- 심야/휴일 약국 안내가 필요하면 별도 데이터가 필요하다.

---

## 4. Backend API 설계 및 응답 Contract

HIRA 원본 응답은 provider별 필드명이 섞여 있으므로 client에는 공통 contract로 내려주는 것이 좋다.

### Endpoint

```http
GET /api/v1/hospitals/search
GET /api/v1/pharmacies/search
GET /api/v1/hospitals/report
GET /api/v1/pharmacies/report
```

권장:

- client는 HIRA API와 Kakao REST API를 직접 호출하지 않는다.
- Backend는 HIRA 원본 응답을 정규화한 뒤 `places`와 `map.markers`를 같은 id 체계로 내려준다.
- report endpoint는 다중 페이지 수집이 필요할 때만 사용하고 `max_pages` 제한을 둔다.

### 병원 검색 API 입력 형태

권장 endpoint 예시:

```http
GET /api/v1/hospitals/search?lat=37.61955&lng=127.05983&radius_km=3&page_no=1&num_of_rows=20
```

| Query | 필수 | 설명 |
| --- | --- | --- |
| `lat` | 선택 | 기준 위도. 거리 계산 및 HIRA `yPos` 변환에 사용 |
| `lng` | 선택 | 기준 경도. 거리 계산 및 HIRA `xPos` 변환에 사용 |
| `radius_km` | 선택 | 반경 km. HIRA 호출 시 meter 단위 `radius`로 변환 |
| `name` | 선택 | 병원명 검색어 |
| `sido_cd` | 선택 | 시도 코드 |
| `sggu_cd` | 선택 | 시군구 코드 |
| `subject_code` | 선택 | 진료과목 코드 |
| `hospital_type_code` | 선택 | 의료기관 종별 코드 |
| `page_no` | 선택 | 페이지 번호 |
| `num_of_rows` | 선택 | 한 페이지 결과 수 |

### 약국 검색 API 입력 형태

권장 endpoint 예시:

```http
GET /api/v1/pharmacies/search?lat=37.61955&lng=127.05983&radius_km=3&page_no=1&num_of_rows=20
```

| Query | 필수 | 설명 |
| --- | --- | --- |
| `lat` | 선택 | 기준 위도. 거리 계산 및 HIRA `yPos` 변환에 사용 |
| `lng` | 선택 | 기준 경도. 거리 계산 및 HIRA `xPos` 변환에 사용 |
| `radius_km` | 선택 | 반경 km. HIRA 호출 시 meter 단위 `radius`로 변환 |
| `name` | 선택 | 약국명 검색어 |
| `sido_cd` | 선택 | 시도 코드 |
| `sggu_cd` | 선택 | 시군구 코드 |
| `page_no` | 선택 | 페이지 번호 |
| `num_of_rows` | 선택 | 한 페이지 결과 수 |

### 다중 페이지 리포트 입력 형태

현재 위치 기준으로 반경 내 목록을 넓게 수집해야 하면 report 형태의 endpoint를 둔다.

```http
GET /api/v1/hospitals/report?lat=37.61955&lng=127.05983&radius_km=20&num_of_rows=1000&max_pages=50
```

```http
GET /api/v1/pharmacies/report?lat=37.61955&lng=127.05983&radius_km=20&num_of_rows=1000&max_pages=50
```

| Query | 필수 | 설명 |
| --- | --- | --- |
| `lat` | 권장 | 기준 위도 |
| `lng` | 권장 | 기준 경도 |
| `radius_km` | 권장 | 반경 km. 기본값은 서비스 정책으로 결정 |
| `num_of_rows` | 선택 | HIRA 한 페이지 결과 수 |
| `max_pages` | 선택 | 최대 조회 페이지 수 |

주의:

- HIRA 전체 건수가 많을 수 있으므로 `max_pages` 제한이 필요하다.
- 전체 건수를 모두 가져오지 못한 경우 `truncated=true`를 내려준다.
- client는 `truncated=true`일 때 일부 결과임을 표시할 수 있다.

### 공통 출력 형태

```json
{
  "generated_at": "2026-06-25T00:00:00+00:00",
  "source": "HIRA",
  "query": {
    "kind": "hospital",
    "lat": 37.61955,
    "lng": 127.05983,
    "radius_km": 20,
    "page_no": 1,
    "num_of_rows": 1000
  },
  "sources": {
    "hospital": {
      "result_code": "00",
      "result_msg": "NORMAL SERVICE.",
      "format": "json",
      "page_no": 1,
      "num_of_rows": 1000,
      "total_count": 123,
      "returned_count": 1000,
      "normalized_count": 998,
      "pages_fetched": 1,
      "truncated": false
    }
  },
  "places": [
    {
      "id": "hospital:{source_id}",
      "entity_type": "hospital",
      "name": "예시병원",
      "address": "서울특별시 ...",
      "phone": "02-000-0000",
      "type_name": "의원",
      "lat": 37.61955,
      "lng": 127.05983,
      "distance_km": 0.35
    }
  ],
  "map": {
    "provider": "kakao",
    "coordinate_source": "HIRA XPos/YPos",
    "markers": [
      {
        "id": "hospital:{source_id}",
        "entity_type": "hospital",
        "title": "예시병원",
        "address": "서울특별시 ...",
        "phone": "02-000-0000",
        "lat": 37.61955,
        "lng": 127.05983,
        "distance_km": 0.35,
        "coordinate_source": "hira"
      }
    ]
  },
  "notice": "병원 기본 정보입니다. 응급 가능 여부는 HIRA 병원 기본정보만으로 확정하지 않습니다."
}
```

### Marker 출력 필드

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `id` | 필수 | 목록 item과 marker를 연결하는 식별자 |
| `entity_type` | 필수 | `hospital` 또는 `pharmacy` |
| `title` | 필수 | marker title 또는 infoWindow 제목 |
| `address` | 선택 | 주소 표시 |
| `phone` | 선택 | 전화번호 표시 |
| `lat` | 필수 | 위도 |
| `lng` | 필수 | 경도 |
| `distance_km` | 선택 | 기준 위치와의 거리 |
| `coordinate_source` | 권장 | `hira`, `kakao_geocoded` 등 |

---

## 5. Kakao Maps JavaScript SDK

- 상태: **Web 연동 기준**
- Base URL: `https://dapi.kakao.com/v2/maps/sdk.js`
- 용도: 지도 표시, marker 표시, infoWindow 표시, marker click 이벤트, clusterer 사용

### SDK 요청 형태

기본 요청:

```http
GET https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_MAP_JAVASCRIPT_KEY}
```

자동 로드를 끄고 필요한 시점에 초기화하는 요청:

```http
GET https://dapi.kakao.com/v2/maps/sdk.js?autoload=false&appkey={KAKAO_MAP_JAVASCRIPT_KEY}
```

clusterer 포함 요청:

```http
GET https://dapi.kakao.com/v2/maps/sdk.js?autoload=false&libraries=clusterer&appkey={KAKAO_MAP_JAVASCRIPT_KEY}
```

### 입력 파라미터

| 파라미터 | 필수 | 예시 | 설명 |
| --- | --- | --- | --- |
| `appkey` | 필수 | `.env` | Kakao JavaScript 키 |
| `autoload` | 선택 | `false` | `false`면 `kakao.maps.load()`로 직접 초기화 |
| `libraries` | 선택 | `clusterer` | 추가 라이브러리. `services`, `clusterer`, `drawing` 등 |

### 출력 형태

SDK 요청은 JSON을 반환하지 않는다. script가 로드되면 브라우저 전역 객체가 생성된다.

| 객체 | 의미 |
| --- | --- |
| `window.kakao` | Kakao SDK namespace |
| `kakao.maps` | Kakao Maps namespace |
| `kakao.maps.Map` | 지도 객체 생성자 |
| `kakao.maps.LatLng` | 좌표 객체 생성자 |
| `kakao.maps.Marker` | marker 생성자 |
| `kakao.maps.InfoWindow` | infoWindow 생성자 |
| `kakao.maps.LatLngBounds` | 여러 marker를 포함하는 bounds 생성자 |
| `kakao.maps.MarkerClusterer` | marker clusterer. `libraries=clusterer` 필요 |

### 지도 생성 입력 형태

```js
const map = new kakao.maps.Map(document.getElementById("map"), {
  center: new kakao.maps.LatLng(37.61955, 127.05983),
  level: 7,
});
```

| 옵션 | 필수 | 설명 |
| --- | --- | --- |
| `center` | 필수 | 지도 중심 좌표. `new kakao.maps.LatLng(lat, lng)` |
| `level` | 선택 | 지도 확대 레벨. 숫자가 클수록 더 멀리 보임 |

### Marker 생성 입력 형태

```js
const marker = new kakao.maps.Marker({
  map,
  position: new kakao.maps.LatLng(place.lat, place.lng),
  title: place.title,
});
```

커스텀 marker image를 쓰는 경우:

```js
const marker = new kakao.maps.Marker({
  map,
  position: new kakao.maps.LatLng(place.lat, place.lng),
  title: place.title,
  image: markerImage,
});
```

권장 marker 구분:

| Marker | 표현 | 설명 |
| --- | --- | --- |
| 현재 위치 | 파란 원형 marker | 사용자 기준점 |
| 병원 | 빨간 `H` marker | 병원 검색 결과 |
| 약국 | 초록 `P` marker | 약국 검색 결과 |

### Marker click 출력/처리 형태

Marker click은 별도 HTTP 응답이 아니라 browser event다.

```js
kakao.maps.event.addListener(marker, "click", () => {
  selectPlace(markerData.id);
});
```

권장 처리:

```text
marker click
  -> markerData.id 확인
  -> 같은 id의 목록 item 찾기
  -> 목록 item 선택 상태 표시
  -> 목록 영역 스크롤
  -> infoWindow 표시
  -> 필요 시 지도 중심 이동
```

### InfoWindow 출력 예시

```html
<div style="padding:10px 12px;min-width:220px;font-size:13px;line-height:1.5">
  <strong>예시병원</strong><br>
  서울특별시 ...<br>
  02-000-0000<br>
  <a href="https://map.kakao.com/link/to/예시병원,37.61955,127.05983" target="_blank">카카오맵 길찾기</a>
</div>
```

---

## 6. Kakao Maps URL

Kakao Maps URL은 별도 key 없이 지도 앱 또는 웹 Kakao Map으로 이동할 때 사용한다.

### 지도 바로가기 요청 형태

```http
GET https://map.kakao.com/link/map/{name},{lat},{lng}
```

예시:

```text
https://map.kakao.com/link/map/예시병원,37.61955,127.05983
```

### 길찾기 요청 형태

```http
GET https://map.kakao.com/link/to/{name},{lat},{lng}
```

예시:

```text
https://map.kakao.com/link/to/예시병원,37.61955,127.05983
```

### 입력 파라미터

| 값 | 설명 |
| --- | --- |
| `{name}` | 목적지 이름. URL encoding 필요 |
| `{lat}` | 목적지 위도 |
| `{lng}` | 목적지 경도 |

주의:

- 이름에 공백, 괄호, 특수문자가 있으면 URL encoding을 한다.
- 길찾기 URL은 marker의 `lat`, `lng`를 그대로 사용한다.
- 출발지는 Kakao Map이 사용자 환경에서 처리한다.

---

## 7. Kakao Local REST API 선택 사용

HIRA 좌표가 없거나 주소 기반 좌표 보정이 필요할 때만 Kakao Local REST API를 백엔드에서 사용한다.

- 상태: **선택 사용**
- Base endpoint: `https://dapi.kakao.com/v2/local/search/address.json`
- Method: `GET`
- 인증: `Authorization: KakaoAK {KAKAO_REST_API_KEY}`

### 주소 검색 입력 형태

```http
GET https://dapi.kakao.com/v2/local/search/address.json?query={address}
Authorization: KakaoAK {KAKAO_REST_API_KEY}
```

예시:

```http
GET https://dapi.kakao.com/v2/local/search/address.json?query=서울특별시%20노원구%20...
Authorization: KakaoAK {KAKAO_REST_API_KEY}
```

### 출력 형태

```json
{
  "documents": [
    {
      "address_name": "서울특별시 노원구 ...",
      "x": "127.05983",
      "y": "37.61955"
    }
  ],
  "meta": {
    "total_count": 1,
    "pageable_count": 1,
    "is_end": true
  }
}
```

### HIRA 좌표와 병합 규칙

```text
HIRA XPos/YPos 있음
  -> HIRA 좌표 우선 사용
  -> coordinate_source="hira"

HIRA XPos/YPos 없음 + 주소 있음
  -> Kakao Local REST API로 geocoding
  -> coordinate_source="kakao_geocoded"

HIRA 좌표와 geocoding 좌표가 크게 다름
  -> 자동 덮어쓰기 금지
  -> 검증 queue 또는 관리자 확인 대상으로 분류
```

주의:

- Kakao REST API key는 client에 노출하지 않는다.
- geocoding 결과를 HIRA 좌표보다 무조건 우선하지 않는다.
- 좌표 source를 남겨야 이후 품질 검증이 가능하다.

---

## 8. 거리 계산 및 반경 필터

### 입력 형태

```json
{
  "user_lat": 37.61955,
  "user_lng": 127.05983,
  "place_lat": 37.62100,
  "place_lng": 127.06000,
  "radius_km": 20
}
```

### 출력 형태

```json
{
  "distance_km": 0.162,
  "inside_radius": true
}
```

처리 규칙:

- 사용자 좌표가 없으면 `distance_km=null`로 둔다.
- 병원/약국 좌표가 없으면 `distance_km=null`로 둔다.
- `radius_km`가 있으면 반경 밖 장소는 제외한다.
- 결과는 가까운 순으로 정렬한다.

---

## 9. 오류 처리

| 상황 | Backend response | Client 처리 |
| --- | --- | --- |
| HIRA key 없음 | 설정 오류 | 운영 환경 변수 확인 |
| HIRA 인증 실패 | `HIRA_UPSTREAM_ERROR` | 검색 실패 안내 |
| HIRA timeout | retryable error | 재시도 안내 |
| HIRA quota 초과 | upstream error | 잠시 후 재시도 안내 |
| Kakao JavaScript key 오류 | SDK load fail | 카카오디벨로퍼스 key/도메인 확인 |
| Kakao Web 플랫폼 미등록 | SDK load fail | Web 플랫폼 도메인 등록 |
| 좌표 없음 | marker 제외 | 목록에는 표시 가능 |
| 결과 없음 | 빈 배열 | empty state 표시 |
| 위치 권한 거부 | 정상 흐름 | 지역 선택 또는 수동 검색 UI 표시 |

권장 오류 출력:

```json
{
  "error": {
    "code": "HIRA_UPSTREAM_ERROR",
    "message": "검색 정보를 불러오지 못했습니다.",
    "retryable": true,
    "upstream_result_code": "...",
    "upstream_result_msg": "..."
  }
}
```

---

## 10. 보안 및 개인정보

### Key 보안

- HIRA `ServiceKey`는 Backend에서만 사용한다.
- Kakao REST API key는 Backend에서만 사용한다.
- Kakao JavaScript key는 Web SDK용이므로 도메인 제한을 반드시 설정한다.
- 실제 key 값을 문서, commit, issue, log, analytics에 남기지 않는다.

### 위치정보 보안

- 현재 위치는 병원/약국 검색 목적에만 사용한다.
- 사용자 식별자와 정밀 좌표를 함께 로그에 남기지 않는다.
- 위치 저장이 필요하면 목적, 보관 기간, 삭제 정책을 명시한다.
- 임시 검색 좌표와 실제 사용자 좌표를 구분한다.

### 의료/약국 정보 표시 제한

- HIRA 병원 기본정보만으로 응급실 운영, 야간 진료, 실시간 진료 가능 여부를 확정하지 않는다.
- HIRA 약국 기본정보만으로 현재 영업 중, 심야 운영, 휴일 운영, 재고 여부를 확정하지 않는다.
- 전화번호가 있으면 방문 전 전화 확인을 유도할 수 있다.

---

## 11. 활용 시나리오

### 현재 위치 기준 병원 지도

```text
현재 위치 lat/lng 확보
  -> /api/v1/hospitals/search 또는 report 호출
  -> places 목록 표시
  -> map.markers를 Kakao marker로 렌더링
  -> 병원 marker click 시 병원 상세 표시
  -> 길찾기 URL 연결
```

### 현재 위치 기준 약국 지도

```text
현재 위치 lat/lng 확보
  -> /api/v1/pharmacies/search 또는 report 호출
  -> places 목록 표시
  -> map.markers를 Kakao marker로 렌더링
  -> 약국 marker click 시 약국 상세 표시
  -> 길찾기 URL 연결
```

### 병원 상세 화면의 주변 약국

```text
사용자가 병원 선택
  -> 선택 병원의 lat/lng 확보
  -> /api/v1/pharmacies/search?lat={hospital.lat}&lng={hospital.lng}&radius_km=1 호출
  -> 주변 약국 목록과 marker 표시
```

### 지도와 목록 동기화

```text
목록 item click
  -> 같은 id의 marker 찾기
  -> map.panTo(marker position)
  -> infoWindow 표시

marker click
  -> 같은 id의 목록 item 찾기
  -> 목록 item 선택 표시
  -> 목록 item으로 scroll
  -> infoWindow 표시
```

---

## 12. 검증 체크리스트

### HIRA 입력/출력

- [ ] 병원정보서비스 `getHospBasisList` 요청 URL이 올바르다.
- [ ] 약국정보서비스 `getParmacyBasisList` 요청 URL이 올바르다.
- [ ] `ServiceKey`가 client로 노출되지 않는다.
- [ ] JSON 응답과 XML 응답을 모두 파싱할 수 있다.
- [ ] `items.item`이 1개일 때도 배열로 정규화된다.
- [ ] `resultCode`가 `00`이 아니면 오류로 처리한다.

### 좌표 매핑

- [ ] `XPos`가 `lng`로 매핑된다.
- [ ] `YPos`가 `lat`로 매핑된다.
- [ ] Kakao `LatLng`에 `lat, lng` 순서로 넣는다.
- [ ] 좌표가 없는 항목은 marker에서 제외된다.
- [ ] `coordinate_source`가 기록된다.

### Backend 출력

- [ ] `places`와 `map.markers`가 같은 `id` 체계를 사용한다.
- [ ] 병원 id는 `hospital:{source_id}` 형태다.
- [ ] 약국 id는 `pharmacy:{source_id}` 형태다.
- [ ] `distance_km`가 현재 위치 기준으로 계산된다.
- [ ] `radius_km` 기준 반경 필터가 적용된다.
- [ ] 다중 페이지 조회 시 `truncated` 상태를 알 수 있다.

### Kakao Map

- [ ] Web SDK에 JavaScript key를 사용한다.
- [ ] Kakao Web 플랫폼 도메인이 등록되어 있다.
- [ ] 카카오맵 사용 설정이 `ON`이다.
- [ ] 현재 위치 marker와 병원/약국 marker가 구분된다.
- [ ] 병원 marker와 약국 marker가 구분된다.
- [ ] marker click과 목록 item click이 동기화된다.
- [ ] marker가 많을 때 clusterer를 사용할 수 있다.
- [ ] 길찾기 URL이 정상 생성된다.

### 안전성

- [ ] `emergency_available=null`을 응급 가능으로 표시하지 않는다.
- [ ] `open_now=null`을 영업 중으로 표시하지 않는다.
- [ ] 심야/휴일/응급 정보가 필요하면 별도 데이터 연동이 필요하다고 표시한다.
- [ ] 실제 API key가 문서나 로그에 남지 않는다.

## 13. 다음 작업 체크리스트

- [ ] HIRA 병원정보서비스와 약국정보서비스의 `ServiceKey`/`serviceKey` 표기를 실제 호출 기준으로 하나로 고정한다.
- [ ] `getParmacyBasisList` 약국 item의 실응답 필드 샘플을 저장하고 `주요 출력 필드` 표와 비교한다.
- [ ] Kakao Maps JavaScript SDK를 실제 Web 도메인 또는 로컬 테스트 도메인에서 로드해 key/도메인 설정을 확인한다.
- [ ] `map.markers` id prefix 규칙을 `hospital:{source_id}`, `pharmacy:{source_id}` 중 하나로 구현에 반영한다.
- [ ] 좌표 누락 항목에 Kakao Local REST API geocoding을 적용할지 여부와 저장 정책을 결정한다.
- [ ] 응급/야간/휴일/영업 중 정보가 필요하면 HIRA 기본정보 외 별도 데이터 연동 범위를 정의한다.

## 14. 완료 기준

- HIRA 병원정보서비스 요청/출력 형태가 문서화되어 있다.
- HIRA 약국정보서비스 요청/출력 형태가 문서화되어 있다.
- HIRA 원본 field와 앱 정규화 field 매핑이 명확하다.
- `XPos/YPos`와 Kakao `LatLng` 좌표 순서가 명확하다.
- Backend가 내려줄 `map.markers` 출력 형태가 정의되어 있다.
- Kakao Maps JavaScript SDK 요청 형태와 출력 객체가 정리되어 있다.
- marker click, 목록 click, 길찾기 URL 활용 방식이 정리되어 있다.
- 테스트용 파일명이나 임시 구현 파일명 없이 API 활용 명세 중심으로 작성되어 있다.

## 참고 공식 링크

- 병원정보서비스: https://www.data.go.kr/data/15001698/openapi.do
- 약국정보서비스: https://www.data.go.kr/data/15001673/openapi.do
- Kakao Map 시작하기: https://developers.kakao.com/docs/ko/kakaomap/common
