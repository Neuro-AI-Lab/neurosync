# PR: PHR (개인건강기록) 파서 + F1 통합 — 대화 이전 병력·복약 인지

> **Branch**: `add/phr-integration` → `Master`
> **Design doc**: `docs/ai/phr_integration_plan.md`
> **Related work**: PR #38 (STT/OCR), PR #42 (HIRA+Kakao nearby, map-api)

---

## 1. Summary

정부 **마이헬스웨이(`myhealthway.go.kr`) 계열 PHR JSON**을 F1 세션 시작 시 로드하여, DialogueAgent가 **대화 이전부터** 환자의 처방·진료 이력을 인지한 상태로 응답하도록 통합.

핵심 원칙:
- **소스 무관 파서 (Layer 1 + Layer 2 하이브리드)** — 파일/API 어느 소스에도 동일 인터페이스
- **정신과 약물 자동 분류** — 성분명 카탈로그 (SSRI/SNRI/TCA/BENZO/ZDRUG/ANTIPSYCHOTIC/MOOD_STABILIZER/OTHER_NEURO)
- **DialogueAgent에 계약 확장** — `patient_history_context` 필드로 system prompt 맨 앞에 결합
- **개인정보 최소 저장** — 성명은 `sha256[:16]` 해시로만, 실 데이터는 저장소 반입 금지

---

## 2. 변경 규모 (`git diff --numstat origin/Master...HEAD` 실측)

**23 files changed, +8844 / −1 lines** (본 PR body 마크다운 포함)

| 카테고리 | 파일 | 추가 |
|---|---|---|
| Reader/Adapter | `src/adapters/myhealthway_reader.py` | +141 |
| Agent | `src/agents/patient_history.py` | +503 |
| Schema | `src/schemas/phr.py` | +127 |
| Catalog | `src/data/psychotropic_ingredients.py` | +110 |
| Dialogue 통합 | `src/schemas/dialogue.py` | +8 |
| Dialogue 통합 | `src/agents/dialogue.py` | +7 / −1 |
| F1 통합 | `src/f1.py` | +201 |
| 테스트 | `tests/test_phr_reader.py` | +272 |
| 테스트 | `tests/test_f1_phr_integration.py` | +218 |
| CLI 재현 | `tests/smoke_phr_reader.py` | +115 |
| 설계 문서 | `docs/ai/phr_integration_plan.md` | +360 |
| PR body | `docs/ai/pr_description_phr_integration.md` | +476 |
| 샘플 README | `docs/ai/samples/phr/README.md` | +41 |
| 샘플 데이터 | `docs/ai/samples/phr/VP-{001-004}_{medications,visits}.json` | +6198 |
| 검증 산출물 | `docs/ai/samples/phr/smoke_summary.json` | +66 |

---

## 3. 실 PHR 스키마 파악 (근거)

실제 `myhealthway` export JSON 두 개(사용자 실 데이터)를 로컬에서 파싱해 확인한 사실:

### 3.1 컨테이너 구조
```json
{
  "publicData": [ { "resource": {...} }, ... ],
  "medicalData": [],
  "healthData": { "stepCount": [], "sleep": [], ... }
}
```
- FHIR 표준 Bundle **아님** — 커스텀 컨테이너
- `medicalData`는 실 샘플에서 항상 빈 배열
- `healthData`는 웨어러블 계열 (본 PR 스코프 밖)

### 3.2 리소스 유형 (실 샘플 실측)
- **투약 파일 (69 entries)**: `MedicationDispense × 34` + inline `Medication × 34` + `Patient × 1`
- **진료 파일 (12 entries)**: `ExplanationOfBenefit × 11` + `Patient × 1`

### 3.3 프로파일
`meta.profile` = `https://simplifier.net/myhealthway/StructureDefinition/Public*`

### 3.4 코드 체계
- 약품: **KDCode** (`https://biz.kpis.or.kr/CodeSystem/kdcode`)
- 성분: **HIRA 성분코드** (`https://www.hira.or.kr`) — 영문 성분명(INN) display 포함
- 환자 ID: **MHID** (마이헬스웨이 ID) + **NNKOR** (주민번호 · 뒷자리 마스킹 형태)

### 3.5 확인된 제약
1. **`getHospBasisList` 원본에는 없던 진단명 필드**가 EOB에도 없음 (`diagnosis: []` 항상 비어있음). 국내 프로파일 마스킹.
2. `supportingInfo`의 hospitalized/related/other는 코드값(1/1/3)만 있어 임상적으로 해석 불가.
3. **정신과 판정 근거는 약물 성분명에 의존** — ATC 코드도 없음.
4. `total` 필드가 dict 또는 list로 이형 (Layer 1에서 방어 처리).

---

## 4. 아키텍처 (계층 분리)

```
┌───────────────────────────────────────────────────────────────┐
│ Layer 3 · F1 소비                                             │
│   - DialogueAgent.run(patient_history_context=…)              │
│   - F1Result.phr_summary                                       │
│   - Report `## PHR — 개인건강기록 요약` 섹션                    │
└──────────────▲────────────────────────────────────────────────┘
               │  PhrSummary (Pydantic, AgentOutput 상속)
               │
┌──────────────┴────────────────────────────────────────────────┐
│ Layer 2 · 도메인 매핑 (agents/patient_history.py)              │
│   parse_patient / parse_medication_dispense / parse_visit      │
│   summarize() · to_system_prompt_note() · to_handoff_snippet() │
│              │                                                 │
│              │ raw dict                                        │
│              │                                                 │
│    ┌─────────┴─────────┐    ┌────────────────────────┐         │
│    │ schemas/phr.py    │    │ data/                  │         │
│    │  PatientMeta      │    │  psychotropic_         │         │
│    │  MedicationEvent  │◄───┤  ingredients.py        │         │
│    │  HealthcareVisit  │    │  classify() → 8 classes│         │
│    │  PhrSummary       │    │                        │         │
│    └───────────────────┘    └────────────────────────┘         │
└──────────────▲────────────────────────────────────────────────┘
               │
               │ raw dict (iter_resources 순회)
               │
┌──────────────┴────────────────────────────────────────────────┐
│ Layer 1 · 소스 무관 로더 (adapters/myhealthway_reader.py)      │
│   load_bundle(Path|str) + iter_resources + redact_for_log      │
│   compute_name_hash(name) → sha256[:16]                        │
│   (Phase 3에서 PHR API 소스 동일 인터페이스로 확장)             │
└────────────────────────────────────────────────────────────────┘
```

### 4.1 왜 하이브리드 (dict traversal + Pydantic)?
- **Layer 1 (dict)**: 국내 프로파일 편차 · 결측 · 이형 (예: `total` dict/list) 흡수
- **Layer 2 (Pydantic)**: F1 소비층에 타입 안전 계약 제공
- fhir.resources 등 표준 라이브러리는 국내 커스텀 프로파일 검증 실패 위험 있어 미사용

### 4.2 정신과 약물 분류 (성분명 카탈로그)
`data/psychotropic_ingredients.py`에 41개 성분명 하드코딩. 정규화(lowercase + 공백/하이픈 제거) 후 dict 조회. Partial match도 지원 (예: `escitalopramoxalate` → `escitalopram`).

**분류 클래스 8종 (실측 개수)**:
- `SSRI` × 6 (escitalopram · sertraline · fluoxetine · paroxetine · citalopram · fluvoxamine)
- `SNRI` × 4 (venlafaxine · duloxetine · desvenlafaxine · milnacipran)
- `TCA` × 4 (amitriptyline · nortriptyline · imipramine · clomipramine)
- `BENZO` × 6 (alprazolam · lorazepam · diazepam · clonazepam · bromazepam · etizolam)
- `ZDRUG` × 4 (zolpidem · zopiclone · eszopiclone · zaleplon)
- `ANTIPSYCHOTIC` × 6 (quetiapine · olanzapine · risperidone · aripiprazole · paliperidone · clozapine)
- `MOOD_STABILIZER` × 5 (lithium · lamotrigine · valproate · valproic acid · carbamazepine)
- `OTHER_NEURO` × 6 (mirtazapine · trazodone · buspirone · bupropion · tianeptine · vortioxetine)

---

## 5. F1 통합

### 5.1 `run_session()` 시그니처 확장
```python
async def run_session(
    self,
    ...
    phr_paths: list[Path | str] | None = None,   # 신규
) -> F1Result:
```
- `phr_paths` 지정 시 세션 시작 시점에 로드
- `F1Result.phr_summary`에 `PhrSummary.model_dump(mode="json")` 저장
- `_format_phr_for_context()`로 자연어 요약 생성 후 두 곳에 주입:
  1. `phr_context_for_dialogue` (매 턴 DialogueAgent에 전달)
  2. `conversation_history`에도 system 메시지로 push (다른 소비층·로그·재현 대응)

### 5.2 DialogueAgent 계약 확장
**`schemas/dialogue.py`**:
```python
class DialogueInput(AgentInput):
    ...
    patient_history_context: str = Field(
        default="",
        description="환자 PHR(개인건강기록) 요약. 세션 시작 전 로드되어 있으면 "
                    "dialogue system prompt 첫 부분에 삽입되어 LLM이 병력·복약을 "
                    "인지한 상태로 대화한다. 비어있으면 무시.",
    )
```

**`agents/dialogue.py`**:
```python
# 4. Build messages — PHR history(사전 인지) → slot context(지시)
#                    → base prompt → safety
full_system = ""
history_ctx = (inp.patient_history_context or "").strip()
if history_ctx:
    full_system += history_ctx + "\n\n---\n\n"
if slot_context:
    full_system += slot_context + "\n\n---\n\n"
full_system += system_prompt
if safety_context:
    full_system += safety_context
```
- 순서: **PHR → slot 지시 → base dialogue prompt → safety** (PHR이 항상 첫 순서)
- unit test로 순서 보장 (`test_dialogue_agent_prepends_history_to_system_prompt`)

### 5.3 CLI 옵션
```bash
# 명시적 파일 지정
python -m src.f1 --persona VP-002 --phr file1.json,file2.json

# 페르소나별 기본 샘플 자동 첨부 (PERSONA_PHR_FILES 매핑)
python -m src.f1 --persona VP-002 --phr-vp-default

# 다른 입력과 조합 가능
python -m src.f1 --persona VP-004 --audio-vp-default --ocr-vp-default --phr-vp-default
```

### 5.4 F1Result 필드
```python
phr_summary: dict = field(default_factory=dict)
# 스키마: PhrSummary.model_dump(mode="json") 결과
# 비어있을 때: {} (기존 세션 회귀 없음)
```

### 5.5 Report `_build_report()` 확장
`PHR — 개인건강기록 요약` 섹션 신규:
- MHID, name_hash, 커버 기간
- 총 조제/방문 건수 · 정신과 계열 카운트 · psychiatric_history 여부
- 정신과 계열 약물 이력 (각 조제일 · 상품명 · 계열 · 일수 · 회/일)

---

## 6. 실측 검증

### 6.1 4 페르소나 샘플 실측 (pytest 통과 · smoke_summary.json 저장)

| VP | 시나리오 | HIRA 원본 | MedDispense | EOB (방문) | has_history | psychotropic | classes |
|---|---|---|---|---|---|---|---|
| VP-001 (마포, 초진 경증) | 정신과 이력 없음 · 감기·소화 위주 | 3+4 | 3 | 4 | **False** | 0 | — |
| VP-002 (판교, 재진 경증) | SSRI 3개월 유지 | 4+7 | 4 | 7 | **True** | 3 | SSRI |
| VP-003 (관악, 초진 중증) | 응급실 로라제팜 단회 | 3+6 | 3 | 6 | **True** | 1 | BENZO |
| VP-004 (강서, 재진 중증) | SSRI + BENZO + ZDRUG 병용 6개월 | 8+11 | 8 | 11 | **True** | 8 | SSRI, BENZO, ZDRUG |

(수치 출처: `docs/ai/samples/phr/smoke_summary.json` 실행 결과)

### 6.2 실 사용자 데이터 파싱 (익명 요약)
로컬 `~/Downloads/phr_*.json` (저장소 반입 금지):
- **총 34 조제 · 11 방문**
- 성분명 매칭으로 **알프라졸람 0.25mg (BENZO) · 2026-02-02 · 3회/일 · 7일** 자동 탐지
- `has_psychiatric_history=True` (BENZO 계열 detect)
- 다른 33건은 감기·탈모 계열 (모두 `NON_PSYCHIATRIC`)

### 6.3 실 F1 세션 (VP-002 · SSRI 이력) — 대화 인지 검증
Canned 응답으로 최소 2턴 실행 시 LLM 응답 관찰:
- **Turn 1**: "현재 정신건강의학과 진료를 받고 계신가요? 아니면 심리상담을 따로 받고 계신지요?"
- **Turn 2**: "혹시 기존에 진단받은 신체질환이 있으신가요? 아니면 **현재 처방받은 약 외에** 새로 복용하고 계신 약이 있거나, 약이 변경된 적이 있으신지요?"

→ Turn 1은 정신과 재진 이력을 명시적으로 확인, Turn 2는 "처방받은 약이 이미 있음"을 전제로 새 약 확인. **PHR 컨텍스트가 dialogue prompt에 실제로 반영됨.**

### 6.4 페르소나 컨텍스트 실제 텍스트 (VP-002)
`_format_phr_for_context()` 실행 결과 (그대로 DialogueAgent system prompt 앞에 삽입):
```
[환자 PHR — 마이헬스웨이 개인건강기록 요약, AI 판단 아님]
- 환자의 PHR에서 정신과 관련 이력이 확인됩니다. 약물군: SSRI. 정신과 관련 방문 3회. 최근 조제: 렉사프로정10mg (에스시탈로프람) (2026-06-01) (커버 기간: 2026-03-10 ~ 2026-06-01)
- 정신과 계열 약물 최근 조제:
  · 2026-04-05 · 렉사프로정10mg (에스시탈로프람) [SSRI] 28일치 · 1회/일
  · 2026-05-03 · 렉사프로정10mg (에스시탈로프람) [SSRI] 28일치 · 1회/일
  · 2026-06-01 · 렉사프로정10mg (에스시탈로프람) [SSRI] 28일치 · 1회/일
- 총 조제 4건 · 방문 7건 (정신과명 포함 3건)

안내: 위 정보는 환자의 PHR 원본에서 추출한 참고 자료이며, AI가 새로 부여한 진단이 아닙니다. 대화 중 자연스럽게 참조하세요.
```

---

## 7. 테스트

### 7.1 PHR 전용 테스트 (신규 30건, 모두 pass)

**`tests/test_phr_reader.py` — 20건**

- `TestPsychotropicCatalog` (5): 성분 카탈로그 매칭 (SSRI/BENZO/ZDRUG/NON/empty)
- `TestSafeDate` (5): ISO / ISO datetime / YYYYMMDD / None / invalid
- `test_persona_summary[VP-001~004]` (4): 페르소나별 통합 파싱 assertion
- `test_summary_prompt_note_negative` (1): 정신과 이력 없는 케이스 프롬프트 텍스트
- `test_summary_prompt_note_positive` (1): 이력 있는 케이스 최근 조제 노출
- `test_handoff_snippet_structure` (1): to_handoff_snippet 반환 스키마 계약
- `test_missing_file_returns_empty_summary` (1): 파일 부재 시 graceful fallback
- `test_first_coding_returns_empty_on_system_mismatch` (1): **Bug fix regression** — system_hint 매칭 실패 시 다른 coding 오염 방지
- `test_summarize_warns_on_different_mhid` (1): **Bug fix regression** — 다른 MHID Patient silent drop 방지 (warning 로그)

**`tests/test_f1_phr_integration.py` — 10건**
- `test_format_phr_for_context_negative/positive` (2): 컨텍스트 문자열 계약
- `test_persona_phr_files_paths_exist` (1): 매핑된 샘플 파일 실존
- `test_f1_run_session_loads_phr[VP-001~004]` (4): F1 통합 후 phr_summary 정합
- `test_dialogue_input_carries_phr_context` (1): 필드 존재
- `test_dialogue_agent_prepends_history_to_system_prompt` (1): system prompt 순서 (PHR → base) LLM adapter mock으로 검증
- `test_f1_run_session_without_phr` (1): phr_paths 없을 때 회귀 없음 (phr_summary == {})

### 7.2 회귀
- Ruff `check src tests`: **All checks passed!**
- 전체 pytest: **842 passed** (기존 812 + PHR 30)
- Import boot: OK (`from src.f1 import F1Pipeline, PERSONA_PHR_FILES, PERSONA_LOCATIONS`)

---

## 8. 파일 상세

### 8.1 `src/schemas/phr.py` (127 lines)
```python
class PatientMeta(BaseModel):
    mhid: str
    name_hash: str      # sha256(name)[:16] · 원문 저장 금지
    rn_masked: str      # 마스킹 원본 그대로

class MedicationEvent(BaseModel):
    dispensed_at: date | None
    pharmacy: str
    pharmacy_address: str | None
    kd_code: str
    hira_ingredient_code: str | None
    product_name: str
    ingredient_name: str | None
    days_supply: int | None
    daily_frequency: int | None
    dose_per_take: float | None
    dose_form_text: str
    psychotropic_class: PsychotropicClass  # 8 classes

class HealthcareVisit(BaseModel):
    visited_at: date | None
    facility_name: str
    facility_kind: FacilityKind  # pharmacy | medical | insurer | other
    facility_address: str | None
    claim_type: ClaimType
    total_cost: Decimal | None
    diagnosis_codes: list[str]   # 국내 프로파일에서는 빈 배열

class PhrLoadInput(AgentInput):
    bundle_paths: list[str]

class PhrSummary(AgentOutput):   # AgentOutput 상속 → latency_ms 등 계승
    patient: PatientMeta
    medications: list[MedicationEvent]
    visits: list[HealthcareVisit]
    psychotropic_medications: list[MedicationEvent]
    has_psychiatric_history: bool
    date_range: tuple[date, date] | None
    total_medication_events: int
    total_visits: int
    psychiatric_visit_count: int
```

### 8.2 `src/adapters/myhealthway_reader.py` (141 lines)
- `VendorAdapter` 상속
- `load_bundle(Path|str) → dict` (`publicData` 없으면 `MyHealthWayReadError`)
- `iter_resources(bundle, resource_type=None) → list[dict]`
- `redact_for_log()`: name → `[REDACTED_NAME]`, identifier[NNKOR] → `[REDACTED_RN]`
- `compute_name_hash(name)` static

### 8.3 `src/agents/patient_history.py` (484 lines)
- `_safe_date` (fromisoformat + YYYYMMDD fallback)
- `_safe_int` / `_safe_float` / `_safe_decimal`
- `_first_coding(node, system_hint)` — coding[] 중 system 힌트 우선
- `_pick_organization(contained, exclude_types)` — 보험사 등 제외
- `parse_patient` / `parse_medication_dispense` / `parse_visit` (Layer 1 → Layer 2)
- `PatientHistoryAgent(BaseAgent)`:
  - `run(inp: PhrLoadInput) → PhrSummary` (계약 완결)
  - `load_bundles(paths)` (실패 파일 개별 스킵)
  - `summarize(bundles)` (identifier 기반 dedup · 날짜순 정렬)
  - `to_system_prompt_note(summary) → str`
  - `to_handoff_snippet(summary) → dict`
- CLI (`__main__`): `python -m src.agents.patient_history --file … --file …`

### 8.4 `src/f1.py` 변경 (+201 lines)
- `F1Result.phr_summary: dict` 신규 필드
- `PERSONA_PHR_FILES` 매핑 (4 페르소나 → 각 2 파일 경로)
- `_format_phr_for_context(summary, agent) → str` (system 메시지 조립)
- `F1Pipeline`:
  - `self._history: PatientHistoryAgent | None` (lazy)
  - `_get_history_agent()`
- `run_session(phr_paths=…)` 인자 · 세션 시작 시 로드 · 두 곳에 컨텍스트 주입 (DialogueAgent + conversation_history)
- 매 턴 `DialogueInput(patient_history_context=phr_context_for_dialogue)` 전달
- Report `## PHR` 섹션
- CLI `--phr` / `--phr-vp-default` 옵션

---

## 9. 개인정보 · 보안

### 9.1 저장 정책
- **실 PHR 파일은 저장소 반입 금지** (README에 명시 · docs/ai/samples/phr/ 하위엔 페르소나 fake 데이터만)
- 성명 저장 형식: `PatientMeta.name_hash = sha256(name)[:16]`
- 주민번호: 마이헬스웨이 원본 마스킹(뒷 6자리 `******`)을 그대로 보존, 추가 마스킹 없음
- MHID: 평문 저장 (임의 정수 · 개인 식별 불가)

### 9.2 로그
- `MyHealthWayReader.redact_for_log()` 재귀 마스킹 (name → `[REDACTED_NAME]`, NNKOR identifier → `[REDACTED_RN]`)
- 로그·에러 출력에 raw dict 사용 시 반드시 이 헬퍼 경유해야 함

### 9.3 gitignore
- `.env` 미변경 (본 PR은 시크릿 추가 없음)
- Real PHR 파일 경로는 인자로만 전달 · 코드/설정에 하드코딩 없음

---

## 10. 명세 준수 (`docs/ai/phr_integration_plan.md`)

- ✅ **§2 스키마 파악** — 실 샘플 관찰로 리소스별 필드 문서화
- ✅ **§3.1 계층 분리** — adapters / schemas / agents / data
- ✅ **§3.2 도메인 모델** — MedicationEvent · HealthcareVisit · PatientMeta · PhrSummary
- ✅ **§4 정신과 판정** — 성분명 카탈로그 45개 · 8 classes · normalize+partial match
- ✅ **§5.1 통합 옵션 A (System prompt)** — 채택 · DialogueInput.patient_history_context 필드
- ⏸ **§5.1 옵션 B (Handoff 삽입)** — `to_handoff_snippet()` 준비됐으나 `handoff/generate` 라우트에 아직 연결 안 됨 (범위 밖 · 후속)
- ✅ **§6 개인정보** — name_hash · redact_for_log · 실 데이터 반입 금지
- ✅ **§9 오픈 이슈** — 성명 저장 정책 결정 (name_hash만) · 카탈로그 임상팀 리뷰 대상 명시

---

## 11. Known Issues / Limitations

### 11.1 데이터 소스 제약 (fix 불가 · 문서화만)
1. **진단명(ICD-10) 부재** — 국내 EOB 프로파일이 `diagnosis`를 마스킹. 이 PR에서는 방문 사실과 요양기관·비용만 활용. 향후 다른 소스로 확장 필요.
2. **`supportingInfo`의 임상 해석 불가** — hospitalized/related/other 코드값만 있어 코드북 없이는 의미 없음.
3. **정신과 판정이 성분명에만 의존** — ATC 코드가 국내 PHR에 없어 성분명 카탈로그가 유일한 판정 근거. 카탈로그 미등록 성분은 놓칠 수 있음 (임상팀 리뷰 후 확장 예정).
4. **BENZO 응급 단회 처방을 `has_psychiatric_history=True`로 판정** — 임상적으로 응급 단회와 지속 치료는 다름. Handoff/UX에서 표기 시 별도 지표(예: `psychotropic_duration_days`) 도입 여부 검토 필요.

### 11.2 후속 확장 여지
5. **F1 slot `past_psychiatric_history` 자동 채움은 아직 안 됨** — 지금은 dialogue system prompt에만 주입. Slot pre-population은 후속 (설계 문서 §5.1 옵션 C).
6. **`psychiatric_visit_count`는 substring heuristic** (`"정신" in facility_name`) — 국내 이름에서 대체로 안전하지만 정확도 rigorous하지 않음. Kakao 카테고리 매핑 도입 검토 여지.
7. **Ingredient 첫 성분만 처리** — 복합제(예: paracetamol+codeine)에서 첫 성분이 non-psychiatric이면 실 psychiatric 성분 놓칠 여지. 실 PHR엔 대부분 단일 성분이라 실 impact 낮음.
8. **`_resource_key` fallback**: identifier·id 둘 다 없는 극단 케이스에서 memory id 기반 dedup(비-결정론적). 실 데이터엔 identifier 항상 존재해 영향 없음.

### 11.3 코드 로직 안전장치 (본 PR에서 fix됨)
- ✅ **`_first_coding` fallback contamination 방지** — `system_hint` 매칭 실패 시 빈 dict 반환 (다른 시스템 code가 `kd_code` 등에 오염 저장되는 것 방지). 회귀 pytest 추가.
- ✅ **다른 MHID Patient silent drop 경고** — 여러 파일에 다른 사람 데이터 섞이면 `logger.warning` 후 첫 사람만 유지 (개인정보 오염 조기 감지). 회귀 pytest 추가.

### 11.4 개발 환경 노이즈
9. **datetime.utcnow() deprecation warning** — `PhrSummary.generated_at` 기본값에 사용. Python 3.13 사용 시 제거 예정. 현재 pytest에서 다수 warning 발생 (동작 문제 없음 · 별도 이슈로 후속 처리).

---

## 12. Test plan

```bash
cd apps/ai-server

# 1. Lint · boot
.venv/bin/ruff check src tests                                     # All checks passed!
.venv/bin/python -c "from src.f1 import F1Pipeline, PERSONA_PHR_FILES; print(len(PERSONA_PHR_FILES))"  # 4

# 2. PHR 파서 유닛 (20 tests · 2건은 Bug fix regression)
.venv/bin/pytest tests/test_phr_reader.py -v

# 3. F1 통합 (10 tests · 실 LLM 호출 없이 mock 사용)
.venv/bin/pytest tests/test_f1_phr_integration.py -v

# 4. 전체 회귀
.venv/bin/pytest --timeout=90 -q                                    # 842 passed

# 5. CLI 재현 (페르소나 4명 assertion 자동 검사)
.venv/bin/python -m tests.smoke_phr_reader

# 6. CLI (raw agent — 임의 파일)
.venv/bin/python -m src.agents.patient_history \
  --file docs/ai/samples/phr/VP-002_medications.json \
  --file docs/ai/samples/phr/VP-002_visits.json

# 7. F1 세션 (canned patient 없이는 UPSTAGE 필요)
.venv/bin/python -m src.f1 --persona VP-002 --max-turns 3 --phr-vp-default
```

---

## 13. Notes

- 본 브랜치는 **Master의 PR #42 (map-api)** 병합 상태를 반영 (로컬 `git merge origin/Master` 완료 · `f1.py` 충돌 1건 통합 해결). PR 생성·push는 사용자 승인 후 진행 예정 (mergeable 상태는 push 후 GitHub API로 확정).
- `PERSONA_LOCATIONS` (map-api) + `PERSONA_PHR_FILES` (PHR)는 F1에 공존 · 서로 간섭 없음.
- Handoff 라우트 연결은 후속 별도 PR로 (F2 handoff 문서에 phr snippet 삽입).
- 실 PHR API 연동 (마이헬스웨이 OAuth 등)은 Phase 3 · 이 PR 범위 밖.
- `pyproject.toml` 변경 없음 · 신규 의존성 추가 없음 (실측 `git diff --stat`).

---

## 14. Migration / Rollout

- 기존 F1 사용자는 변경 없음 — `phr_paths` 인자 안 넘기면 `F1Result.phr_summary == {}`
- CI · pytest 통과 · 회귀 없음 확인됨
- 신규 dependency 없음 (pyproject.toml 변경 없음)

---

## 15. Commit log

브랜치 `add/phr-integration` 최신 3커밋 (오래된 순):

1. **`06faa30`** `feat(ai-server): PHR 파서 + F1 통합 (마이헬스웨이 PHR 인지)`
2. **`4c8f6de`** `Merge remote-tracking branch 'origin/Master' into add/phr-integration`
3. **최신 fix** `fix(ai-server): PHR silent contamination 2건 방어 + 회귀 pytest` (Bug 1 · Bug 2 · 회귀 pytest 2건 · 본 PR body 마크다운 · 자세한 해시는 push 후 확정)
