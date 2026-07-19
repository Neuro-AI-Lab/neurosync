# PHR (개인건강기록) 통합 설계 계획

> **Status**: DRAFT — 구현 착수 전 리뷰용
> **Owner**: AI Research (LLM/외부 API 연동)
> **Scope**: `apps/ai-server/src/adapters,schemas,agents` + `docs/ai/`
> **Prior art**: HIRA/Kakao (`add/map-api`), OCR (`add/f1-stt-and-ocr`)

---

## 1. 배경

환자의 **개인건강기록(PHR)** — 정부 마이헬스웨이(`myhealthway.go.kr`) 계열에서 export된 JSON — 을 Neuro-Sync F1 파이프라인이 소비할 수 있게 한다. 이 문서는 실 샘플(2개)의 스키마 파악 결과를 기반으로 리더 계층 · 표준화 스키마 · F1 통합 지점을 정의한다.

**목표**:
- 진료 방문 이력과 투약 이력을 F1이 이해할 수 있는 typed 모델로 변환
- 정신과 계열 약물·이력을 자동 식별
- Handoff/System prompt/Safety grounding 에 필요한 형태로 요약

**비목표(v1)**:
- 실시간 PHR API 풀링 (auth OAuth 등 · Phase 3에서)
- 진단(ICD-10) 기반 이력 분석 (샘플에 상병정보 마스킹돼 있음 · 데이터 소스 개선 시 재검토)

---

## 2. 실 샘플 스키마 파악 (2026-07-10)

### 2.1 포맷
- **FHIR R4 기반 국내 커스텀 프로파일**
- `meta.profile` = `https://simplifier.net/myhealthway/StructureDefinition/Public*`
- 표준 Bundle 형식은 아니고, 다음 컨테이너 사용:
  ```json
  { "publicData": [...], "medicalData": [...], "healthData": {...} }
  ```
  - `publicData` — 공공(건보공단 · 마이헬스웨이) 데이터. 이번 스코프의 주 대상
  - `medicalData` — 병원 EHR (샘플에는 비어있음)
  - `healthData` — 걸음수·수면·혈당 등 웨어러블 계열 (이번 스코프 밖)

### 2.2 리소스 유형 분포 (실 샘플 기준)

| 파일 | 총 엔트리 | 리소스 유형 |
|---|---|---|
| `phr_...2096.json` | 69 | MedicationDispense × 34, Medication × 34, Patient × 1 |
| `phr_...9581.json` | 12 | ExplanationOfBenefit × 11, Patient × 1 |

투약 이력과 진료비 청구 이력이 별도 파일로 분리 배포되는 것으로 관측.

### 2.3 리소스별 핵심 필드

#### `MedicationDispense` (조제 완료 이벤트)
```
identifier             — UUID
status                 — "completed"
whenPrepared           — 조제일 (ISO date)
daysSupply.value       — 총 일수
dosageInstruction[0].text                    — "1캡슐" 등
dosageInstruction[0].timing.repeat.frequency — 1일 복용 횟수
dosageInstruction[0].doseAndRate[0].doseQuantity.value — 회당 용량
medicationReference.resource                 — 인라인 Medication
contained[Organization]                      — 조제 약국 (name, address)
subject.reference                            — Patient/{id}
```

#### `Medication` (인라인)
```
code.coding[0]
  system  = "https://biz.kpis.or.kr/CodeSystem/kdcode"
  code    = KDCode (예: "057600080")
  display = 상품명 (예: "잘도스캡슐(에르도스테인)_(0.3g/1캡슐)")
ingredient[0].itemReference.resource         — Substance
  code.coding[0]
    system  = "https://www.hira.or.kr"
    code    = HIRA 성분코드 (예: "153101ACH")
    display = 성분명 영문 (예: "erdosteine")
```

#### `ExplanationOfBenefit` (진료비 청구 = 방문 이력)
```
billablePeriod.start   — 진료·조제 시작일
type.coding[0].code    — "pharmacy" 또는 "professional"
patient.reference      — Patient/{id}
provider.reference     — Organization/{id} (요양기관)
contained[Organization][type.text ∈ {병의원, 약국, 보험사}]
  name, address.text
supportingInfo[*]      — hospitalized/related/other 코드 (부호화, 임상적으로 사용 어려움)
total.value            — 진료비 총액
diagnosis              — ⚠️ 실 샘플에서는 비어있음 (프로파일이 상병정보 마스킹)
```

#### `Patient`
```
identifier[MHID]        — 마이헬스웨이 ID
identifier[NNKOR]       — 주민번호 (뒷자리 마스킹 형태 "0004293******")
name[0].text            — 성명 (평문 · PII)
```

### 2.4 발견된 제약

1. **진단명(ICD-10) 없음** — EOB `diagnosis`가 항상 빈 배열. 진료 이력에서 "무슨 병으로 갔는지"는 알 수 없다. 방문 사실과 기관·비용만.
2. **`supportingInfo`가 코드 원본** — hospitalized=1, related=1, other=3 같은 값이 담기지만 코드북 없이는 의미 해석 불가.
3. **정신과 판정 근거는 약물 이름/성분**에 의존 — 진단 없으므로 KDCode/성분명 카탈로그와 매칭해서만 추정 가능.
4. **개인정보 평문** — 성명, 병원·약국명·주소·조제일 실 데이터. 파일 자체를 저장소에 반입하면 안 됨.

---

## 3. 아키텍처

### 3.1 계층 분리 (기존 어댑터 패턴 재사용)

```
apps/ai-server/src/
├── adapters/
│   └── myhealthway_reader.py   # 소스(파일/API) 추상화 · 로더 · redact_for_log
├── schemas/
│   └── phr.py                  # Pydantic 도메인 모델 (typed)
├── agents/
│   └── patient_history.py      # raw → PhrSummary 요약 · 정신과 판정 · 요약 텍스트 생성
├── data/
│   └── psychotropic_ingredients.py  # 성분명·KDCode → ATC(N05/N06) 룰
└── tests/
    └── smoke_phr_reader.py     # 샘플 파일 파싱 정합 검증

docs/ai/
├── phr_integration_plan.md     # (본 문서)
└── samples/phr/                # ⚠️ **평문 실데이터 저장 금지**
    ├── README.md               # 익명화 지침
    └── phr_anonymized_*.json   # 익명화된 샘플만 허용
```

### 3.2 표준화 도메인 모델 (schemas/phr.py)

```python
class MedicationEvent(BaseModel):
    dispensed_at: date           # whenPrepared
    pharmacy: str
    pharmacy_address: str | None
    kd_code: str                 # KDCode
    hira_ingredient_code: str | None
    product_name: str            # 상품명
    ingredient_name: str | None  # 성분명 (영문)
    days_supply: int             # 일수
    daily_frequency: int         # 1일 복용 횟수
    dose_per_take: float         # 회당 용량
    dose_form_text: str          # "1캡슐" 등
    is_psychotropic: bool        # 판정 결과
    psychotropic_class: Literal["SSRI","SNRI","TCA","BENZO","ZDRUG",
                                 "ANTIPSYCHOTIC","MOOD_STABILIZER",
                                 "OTHER_NEURO","NON_PSYCHIATRIC"]

class HealthcareVisit(BaseModel):
    visited_at: date             # billablePeriod.start
    facility_name: str           # 요양기관
    facility_kind: Literal["pharmacy","medical","other"]  # 약국/병의원/기타
    claim_type: str              # pharmacy | professional
    total_cost: Decimal | None
    diagnosis_codes: list[str]   # ICD-10 (있으면; 국내 마스킹 시 빈 리스트)

class PatientMeta(BaseModel):
    mhid: str                    # myhealthway ID
    name_hash: str               # 성명은 해시로만 저장 (원문 로그 금지)
    rn_masked: str               # 주민번호 마스킹 원본 그대로

class PhrSummary(BaseModel):
    patient: PatientMeta
    medications: list[MedicationEvent]
    visits: list[HealthcareVisit]
    # 파생 지표
    psychotropic_medications: list[MedicationEvent]  # is_psychotropic=True 만
    has_psychiatric_history: bool                    # psychotropic 있으면 True
    date_range: tuple[date, date] | None             # 데이터 커버 기간
    generated_at: datetime
```

### 3.3 어댑터 인터페이스 (adapters/myhealthway_reader.py)

```python
class MyHealthWayReader(VendorAdapter):
    """
    Source-agnostic PHR loader.
    v1: file path 만 지원
    Phase 3: PHR API 또는 사용자 업로드도 같은 인터페이스로.
    """
    async def load_bundle(self, source: Path | str) -> dict:
        """Raw JSON 원본 반환. 파일 존재/포맷 검증."""

    def redact_for_log(self, payload: dict) -> dict:
        """이름·주민번호·병원명·주소 마스킹된 사본 반환."""
```

### 3.4 에이전트 인터페이스 (agents/patient_history.py)

```python
class PatientHistoryAgent(BaseAgent):
    """PHR 원본 → PhrSummary + F1 소비 가능 요약 텍스트."""

    async def summarize(self, bundles: list[dict]) -> PhrSummary:
        """여러 PHR 파일 (예: 투약 + 진료) 병합 요약."""

    def to_system_prompt_note(self, summary: PhrSummary) -> str:
        """LLM system prompt에 붙일 짧은 자연어 요약. 예:
           '환자는 최근 6개월간 정신과 약물 이력 없음. 감기 관련 약 다수, 탈모 약 장기 복용 중.'
        """

    def to_handoff_snippet(self, summary: PhrSummary) -> dict:
        """인계 문서에 삽입할 구조화 데이터."""
```

---

## 4. 정신과 약물 판정 (핵심 로직)

### 4.1 판정 소스 (신뢰도 우선순위)
1. `ingredient_name` (영문 성분명) — 국제 통용 · 가장 안정적
2. `product_name` — 상품명 · 브랜드별 표기 다양성 커서 보조
3. `kd_code` — 카탈로그 매핑 필요

### 4.2 초기 성분명 카탈로그 (하드코딩 v1)

```python
PSYCHOTROPIC_INGREDIENTS = {
    # SSRI
    "escitalopram": "SSRI", "sertraline": "SSRI",
    "fluoxetine": "SSRI", "paroxetine": "SSRI", "citalopram": "SSRI",
    "fluvoxamine": "SSRI",
    # SNRI
    "venlafaxine": "SNRI", "duloxetine": "SNRI", "desvenlafaxine": "SNRI",
    "milnacipran": "SNRI",
    # 삼환계
    "amitriptyline": "TCA", "nortriptyline": "TCA", "imipramine": "TCA",
    "clomipramine": "TCA",
    # 벤조디아제핀
    "alprazolam": "BENZO", "lorazepam": "BENZO", "diazepam": "BENZO",
    "clonazepam": "BENZO", "bromazepam": "BENZO",
    # Z-drug
    "zolpidem": "ZDRUG", "zopiclone": "ZDRUG", "eszopiclone": "ZDRUG",
    # 항정신병
    "quetiapine": "ANTIPSYCHOTIC", "olanzapine": "ANTIPSYCHOTIC",
    "risperidone": "ANTIPSYCHOTIC", "aripiprazole": "ANTIPSYCHOTIC",
    # 기분안정제
    "lithium": "MOOD_STABILIZER", "lamotrigine": "MOOD_STABILIZER",
    "valproate": "MOOD_STABILIZER", "carbamazepine": "MOOD_STABILIZER",
    # 기타 신경계 (수면·불안 관련)
    "mirtazapine": "OTHER_NEURO", "trazodone": "OTHER_NEURO",
    "buspirone": "OTHER_NEURO",
}
```

- 매칭은 성분명을 lowercase + strip으로 정규화 후 사전 조회.
- 확장 시 `docs/ai/references/psychotropic_ingredients.md`에 근거 첨부.
- 향후 ATC 코드 매핑(N05/N06) 도입 가능 — 하지만 국내 PHR엔 ATC 없음.

### 4.3 판정 예시 (실 샘플)
샘플 사용자의 34개 약물 중 카탈로그와 매칭되는 성분: **없음**. 결과 `has_psychiatric_history = False`, `psychotropic_medications = []`. F1은 이 사실을 그대로 활용해 "정신과 이력 확인 안 됨" 로 안내.

---

## 5. F1 통합 지점 (v1 채택 후보)

### 5.1 통합 옵션 매트릭스

| # | 지점 | 구현 위치 | 우선순위 후보 |
|---|---|---|---|
| A | System prompt 병력 요약 삽입 | `f1.py` `run_session()` 시작부 · `prompts/dialogue` 리소스에 `{{patient_history}}` 슬롯 신규 | v1 |
| B | Handoff 문서에 완전 병력 자동 삽입 | `handoff/generate` 라우트 + PHR 로더 | v1 |
| C | F1 슬롯 pre-populate (`past_psychiatric_history`, `medical_history`) | `clinical_slot.py` 사전 채움 | v2 |
| D | Safety grounding — 자해/자살 이력 (진단 필드 확보되면) | `safety_classifier.py` context | 데이터 소스 개선 시 |

**v1 채택**: A + B (파서 완성되면 즉시 붙일 수 있음, 슬롯 관리 위험 낮음)

### 5.2 v1 사용 흐름

```
[Session 시작 시]
  1. FHIR 파일 경로(들) 입력 (CLI --phr / API 필드)
  2. MyHealthWayReader.load_bundle() 병렬 로드
  3. PatientHistoryAgent.summarize() → PhrSummary
  4. summary.to_system_prompt_note() → dialogue system prompt에 삽입
  5. summary → F1Result.phr_summary 필드로 세션 로그에 저장

[Handoff 생성 시]
  6. summary.to_handoff_snippet() → 인계 문서 "환자 병력" 섹션에 자동 삽입
```

---

## 6. 개인정보 · 보안 원칙

- **원문 파일 저장소 반입 금지**: 실 PHR JSON은 `docs/ai/samples/phr/` 안에도 넣지 않는다. `~/Downloads/` 등 로컬에서만.
- **로그 마스킹**: `redact_for_log()`가 아래를 반드시 마스킹
  - 성명 → `[REDACTED_NAME]`
  - 주민번호(전체/부분) → `[REDACTED_RN]`
  - 요양기관명·주소 → 유지 (임상적으로 유용 · 익명화 필요 시 옵션)
- **성명 해시**: `PatientMeta.name_hash = sha256(name)[:16]`. 원문 저장 금지.
- **`.env`/시크릿에 PHR 파일 경로 하드코딩 금지**: 인자로 전달만.
- **익명화 스크립트**(별도 · 저장소 커밋용): `scripts/anonymize_phr.py` — 이름·주민번호·특정 식별자 마스킹 후 `phr_anonymized_*.json` 산출. 이 산출물만 저장소에 커밋 허용.

---

## 7. 구현 단계별 계획

### Phase 1 — Reader/Parser (v1 MVP)
- `adapters/myhealthway_reader.py` (~150 LOC)
- `schemas/phr.py` (~200 LOC)
- `agents/patient_history.py` (~250 LOC)
- `data/psychotropic_ingredients.py` (사전 카탈로그)
- `tests/smoke_phr_reader.py` (실 파일 2개로 검증 · 파일 경로는 인자)
- **완료 기준**: 두 샘플 파일을 하나의 `PhrSummary`로 병합, `has_psychiatric_history=False` 정합 확인

### Phase 2 — F1 통합 (A + B)
- `f1.py::run_session(phr_paths: list[Path] | None)` 인자 추가
- Dialogue system prompt에 `{{patient_history_note}}` 슬롯
- Handoff 생성기에 `phr_summary` 반영
- CLI 옵션 `--phr file1.json,file2.json`
- **완료 기준**: VP-001 세션에 임시 PHR 붙였을 때 대화가 병력을 인지하는지 확인

### Phase 3 — 실환자 데이터 연동 (장래)
- 마이헬스웨이 OAuth · 사용자 동의 흐름
- 정기 pull · 캐시 · 갱신 정책
- 진단 코드 확보 (다른 소스 · EHR 연동)

---

## 8. 산출물 명세

Phase 1 완료 시 새로 존재해야 하는 것:

- **코드**: 위 §3.1 트리대로 신규 파일 5종
- **테스트**: `smoke_phr_reader.py`, `test_patient_history_agent.py`
- **문서**:
  - 이 문서 최신 반영
  - `docs/ai/references/psychotropic_ingredients.md` (카탈로그 근거)
  - `docs/ai/samples/phr/README.md` (익명화 지침)
- **CLI/API 예시**:
  ```bash
  python -m src.agents.patient_history \
    --file ~/Downloads/phr_20260710_2096.json \
    --file ~/Downloads/phr_20260710_9581.json
  ```

---

## 9. 오픈 이슈 · 결정 필요

1. **성명 저장 정책** — 세션 로그(`F1Result`)에 name_hash만 저장할지, 아예 미저장할지. (기본안: name_hash만)
2. **정신과 판정 카탈로그의 관리 주체** — 임상팀 리뷰 필요. 초기엔 AI Research에서 하드코딩, 후속으로 임상 리뷰 사이클 도입.
3. **파일 조합 방식** — 사용자가 2개 이상 파일(투약/진료)을 함께 넣는 게 표준. `summarize()`가 여러 파일 병합 지원해야.
4. **진단 필드 부재에 대한 UX** — Handoff 문서에서 "진단 이력 확인 안 됨(소스 제약)" 명시 vs 조용히 생략. (기본안: 명시 · 투명성)
5. **다국어 성분명** — 국내 상품에 영문 성분명 없을 수 있음. 폴백으로 `product_name` 정규화 필요할 수도.

---

## 10. 리뷰 후 결정할 것

- [ ] Phase 1 착수 가부 · 우선순위
- [ ] 정신과 성분 카탈로그 초안 리뷰 (임상팀)
- [ ] 개인정보 처리 정책 (§6) 승인
- [ ] 저장소 커밋 정책 — 익명화 샘플만 허용 여부

---

*변경 이력: 2026-07-10 초안 (실 샘플 2개 파악 기반)*
