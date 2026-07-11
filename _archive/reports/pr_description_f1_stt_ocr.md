# PR: F1에 STT + OCR + InputNormalizer + Sentiment 통합

> **Branch**: `add/f1-stt-and-ocr` → `Master`
> **Related checklist**: T1-F1-DEV-002~013
> **PRD reference**: `docs/ai/PRD_task1.md` L76 — F1 = 대화 · 안전 · 입력 정규화 · STT · OCR

---

## 1. Summary

F1 파이프라인을 **텍스트 전용에서 텍스트·음성(STT)·문서(OCR) 3가지 입력을 지원**하는 완전한 멀티에이전트 구조로 확장.

**변경 규모**: 76 files, +12,110 / -68 lines (병합 후 재검증 산출물 포함 시 84 files, +13,367 / -94).

---

## 2. 관련 체크리스트 (`docs/ai/checklist_task1.md`)

- ✅ **T1-F1-DEV-002** InputNormalizerAgent 구현 + f1.py 통합
- ✅ **T1-F1-DEV-003** STT Agent + SKT A.X adapter
- ✅ **T1-F1-DEV-004** OCR Agent + Upstage Document Parse adapter
- ✅ **T1-F1-DEV-007** POST /ai/stt/transcribe 라우트
- ✅ **T1-F1-DEV-008** POST /ai/ocr/parse 라우트
- ✅ **T1-F1-DEV-011~013** SentimentAnalyzer 매 턴 (Mode A) + 세션 (Mode B) f1.py 통합

---

## 3. 아키텍처 (완성)

```
[텍스트 / 음성(STT) / 문서(OCR)]
         ↓
   InputNormalizer   ← 모든 입력이 여기로 수렴 (STT 오인식·구어체·방언 정규화)
         ↓
   ┌─────┴──────┐
   ▼            ▼
Dialogue     Safety(1차, patient message)
   │            ↑
   └─ AI 응답 ─→ Safety(2차, post-dialogue — AI 응답 자체 안전 검사)
             ↕
   SentimentAnalyzer
   ├─ Mode A (매 턴, per-utterance)  → F1TurnLog.sentiment
   └─ Mode B (세션 종료, session-level) → F1Result.session_sentiment
```

---

## 4. 신규 파일 상세

### 4.1 어댑터 (Adapters)

#### `src/adapters/skt_ak_stt.py` (225 lines) 🆕

**역할**: SKT A.X STT Batch API 클라이언트. `VendorAdapter` 상속 (LLMAdapter 아님).

**핵심 클래스**:
```python
class SktAkSttAdapter(VendorAdapter):
    async def transcribe(audio: bytes, *, message_id, keywords, ...) -> dict
```

**3단계 파이프라인**:
1. `GET /v1/stt/upload-token?fileSize=N` → `upload_token` 발급
2. `PUT /v1/stt/upload/{upload_token}` → `file_key` 발급
3. `POST /v1/stt/transcript` → 전사 결과 (utterances[], words[])

**주요 특징**:
- 인증: `X-API-Key` 헤더
- 재시도: 429/5xx 지수 백오프 (2s→4s→8s, 최대 3회)
- 파일 제한: 100MB / 30분 (spec §6.6)
- `redact_for_log()`: API key 마스킹 + audio bytes → `<binary N bytes>` 표기

#### `src/adapters/solar_document_parse.py` (160 lines) 🆕

**역할**: Upstage Document Parse (OCR + 레이아웃 분석) 클라이언트.

**핵심 클래스**:
```python
class SolarDocumentParseAdapter(VendorAdapter):
    async def parse(document: bytes, filename: str, *, ...) -> dict
```

**HTTP 요청**:
- `POST /v1/document-digitization` (multipart)
- Form fields: `model=document-parse`, `ocr=auto`, `output_formats=["markdown","text","html"]`, `coordinates=true`, `chart_recognition=true`

**주요 특징**:
- 인증: `Authorization: Bearer $UPSTAGE_API_KEY`
- 재시도: 429/5xx 지수 백오프, 최대 3회
- 타임아웃: 120초 (긴 문서 대응)

### 4.2 에이전트 (Agents)

#### `src/agents/stt.py` (143 lines) 🆕

**역할**: SKT A.X STT 응답을 typed `STTOutput`으로 변환.

**핵심 클래스**:
```python
class STTAgent(BaseAgent):
    async def transcribe(audio: bytes, meta: STTInput) -> STTOutput
```

**변환 로직**:
- vendor `utterances[]` → typed `segments: list[STTSegment]`
- concatenated text 조립 (whitespace-joined)
- FR-035 준수: `user_confirmed=False` 항상 초기값 (UI가 True 승격)
- FR-036 준수: `audio_retention_expires_at` = ISO8601 (`now + 48h`)
- Adapter 실패 시 empty `STTOutput` + `reason_summary` (세션은 계속)

#### `src/agents/ocr.py` (394 lines) 🆕

**역할**: Upstage Document Parse 응답 → 구조화된 임상 정보 추출.

**핵심 클래스**:
```python
class OCRAgent(BaseAgent):
    async def parse(document: bytes, meta: OCRInput) -> OCROutput
```

**7단계 처리**:
1. **Adapter 호출** → Upstage raw JSON
2. **Elements → OCRBlocks** (`_structure_blocks`):
   - Upstage `category` (heading1/table/paragraph) → 신뢰도 합성
   - Coordinates → `BoundingBox` (min/max 계산)
3. **문서 유형 자동 감지** (`_detect_document_type`):
   - 진단서: "진단서", "임상적 추정", "F41.9" 등 키워드 카운트
   - 처방전, 상담기록(consultation), 검사결과(lab_result)
4. **임상 요약 추출** (`_build_summary`): 정규식 8종
   - `_ICD_PATTERN` — F41.9 / F419 (KCD-8 형식)
   - `_DATE_PATTERNS` — 2026-07-08 / 2026.07.08 / 2026년 7월 8일
   - `_SCALE_PATTERN` — PHQ-9/GAD-7/PHQ-4/WHO-5/AUDIT-C 점수
   - `_DEPT_PATTERN` — 정신건강의학과 등
   - `_MED_DOSAGE_PATTERN` — "약물명 용량단위"
   - `_NAME_PATTERN`, `_AGE_PATTERN`, `_GENDER_PATTERN` — 환자 정보
5. **Confidence 4단계 게이팅** (spec §Confidence Threshold):
   - `≥ 0.9` clean · `0.7~0.9` info · `0.5~0.7` verify · `< 0.5` retry (value nulled)
6. **`source="ocr_extracted"` 마커** 강제 (AI 진단 아님 명시)
7. **Low-confidence 아이템 리스트** 생성 (severity별)

### 4.3 스키마 (Pydantic Schemas)

#### `src/schemas/stt.py` (92 lines) 🆕

**주요 클래스**:
- `STTMode` — `"batch" | "streaming"`
- `STTSegment` — `text, start_ms, end_ms, speaker`
- `STTInput` — `patient_id, filename, mode, language, keywords, agreement_of_data_collection`
- `STTOutput` — `text, segments, confidence (None: spec §6.7), audio_retention_expires_at, user_confirmed (FR-035)`

**설계 원칙**: SKT A.X는 confidence를 제공하지 않으므로 (spec §6.7) `confidence: float | None` — 값 조작 금지.

#### `src/schemas/ocr.py` (183 lines) 🆕

**주요 클래스**:
- `DocumentType` — `"diagnosis" | "prescription" | "consultation" | "lab_result" | "unknown"` (**spec 정합 이름** — 이전 `counseling_record`, `test_result`에서 변경)
- `SourceType` — `"document" | "ocr_extracted"`
- `BoundingBox` — 좌상단 x/y + width/height + page
- `OCRBlock` — `block_id, field, value, confidence, bounding_box, needs_verification, source ("ocr_extracted"), category`
- `Medication` — `name, dose, frequency, route, confidence`
- `ExtractedSummary` — `diagnoses, diagnosis_codes, medications, department, dates, scale_scores, patient_{name,age,gender}`
- `LowConfidenceItem` — `severity: "info" | "verify" | "retry"`
- `OCRInput`, `OCROutput`

**Confidence 상수**:
```python
CONFIDENCE_HIGH = 0.9
CONFIDENCE_LOW = 0.7
CONFIDENCE_VERIFY = 0.5
```

### 4.4 라우트 (FastAPI Routes)

#### `src/routes/stt.py` (112 lines) 🆕

**엔드포인트**: `POST /ai/stt/transcribe` (multipart)

**Form 필드**:
- `audio: UploadFile` — mp3/wav/opus/flac 등
- `session_id`, `patient_id`, `mode` (batch/streaming), `language`, `keywords` (콤마 구분), `agreement_of_data_collection`, `request_id`

**게이팅**:
- 빈 파일 → 400
- >100MB → 413 (spec §6.6)
- streaming 요청 → 501 (미구현)
- 알 수 없는 Content-Type → 경고만 (Upstage/SKT가 실제 처리 가능한지 판단)

#### `src/routes/ocr.py` (97 lines) 🆕

**엔드포인트**: `POST /ai/ocr/parse` (multipart)

**Form 필드**:
- `document: UploadFile` — PDF/JPEG/PNG/DOCX 등
- `session_id`, `patient_id`, `document_type_hint`, `confidence_threshold`, `request_id`

**게이팅**:
- 빈 파일 → 400
- >50MB → 413 (Upstage spec §5.6)
- Content-Type 화이트리스트 (PDF, JPEG, PNG, BMP, TIFF, HEIC, DOCX, PPTX, XLSX)

### 4.5 f1.py 확장 (+630 lines)

가장 큰 변경. **`F1Pipeline` 클래스**에 다음 추가:

**신규 인스턴스 필드**:
- `self.normalizer: InputNormalizerAgent` (mandatory)
- `self.sentiment: SentimentAnalyzerAgent` (mandatory)
- `self._ocr: OCRAgent | None` (lazy load — UPSTAGE_API_KEY 없으면 skip)
- `self._stt: STTAgent | None` (lazy load — SKT_A_X_API_KEY 없으면 skip)

**신규 헬퍼 메서드**:
- `_normalize_patient_message()` — 정규화 (STT/텍스트 구분)
- `_analyze_utterance_sentiment()` — Sentiment Mode A
- `_analyze_session_sentiment()` — Sentiment Mode B
- `_transcribe_audio_inputs()` — 세션 시작 시 mp3 → text 일괄 전사
- `_process_ocr_documents()` — 세션 시작 시 PDF → OCROutput 리스트

**`run_session()` 시그니처 확장**:
```python
async def run_session(
    self,
    patient_input_fn: Callable | None = None,        # audio_inputs 있으면 None 허용
    ...
    ocr_documents: list[Path | str] | None = None,   # 신규
    ocr_document_hints: list[DocumentType] | None = None,  # 신규
    audio_inputs: list[Path | str] | None = None,    # 신규
) -> F1Result
```

**세션 시작 로직**:
- `audio_inputs` 있으면 → 모든 mp3 배치 STT → 순차 `patient_input_fn` 자동 구성
- `ocr_documents` 있으면 → 모든 PDF OCR → `conversation_history`에 system 메시지로 주입

**매 턴 로직** (Turn 0 및 메인 루프 공통):
```
1. raw_patient_message = await patient_input_fn(...)
2. patient_message, turn_norm_meta = await _normalize_patient_message(raw)
3. safety_out = await self.safety.run(SafetyInput(patient_message, history))
4. slot_out = await self.clinical_slot.run(...)
5. dialogue_out = await self.dialogue.run(...)
6. turn_sentiment = await _analyze_utterance_sentiment(patient_message)
7. post_safety = await self.safety.run(SafetyInput(agent_response, history+patient))  ← 재검사
8. Log turn (normalizer_meta, sentiment, dialogue_safety_ctrs)
```

**세션 종료 로직**:
- `_finalize_async()`: Sentiment Mode B (세션 궤적 + 지배 정서) 계산 → `result.session_sentiment`

**신규 데이터 필드**:
```python
@dataclass
class F1TurnLog:
    ...
    normalizer_meta: dict         # 정규화 원본/결과/changes
    sentiment: dict                # Mode A: polarity, arousal, emotions, risk_signal
    dialogue_safety_ctrs: int | None    # post-dialogue Safety 재검사
    dialogue_safety_risk: str | None

@dataclass
class F1Result:
    ...
    ocr_documents: list[dict]      # 세션 시작 시 OCR 처리한 문서들
    stt_transcripts: list[dict]    # 세션 시작 시 STT 처리한 오디오들
    session_sentiment: dict        # Mode B: dominant_emotions, signal_strength, trajectory
```

**신규 CLI 인자** (`main()`):
- `--audio path1,path2,...` — 명시적 mp3 경로
- `--audio-vp-default` — 편의: `VP-XXX-*.mp3` 자동 탐색
- `--ocr path1,path2,...` — 명시적 PDF 경로
- `--ocr-hint diagnosis,prescription,...` — 문서 유형 힌트
- `--ocr-vp-default` — 편의: `VP-XXX_*_ocr.pdf` 자동 탐색

**Report/Checklist 확장**:
- `_build_report()`: OCR 섹션 + STT 섹션 신규
- `_build_checklist()`: OCR/STT attached 체크 신규

### 4.6 설정 · DI · main.py

#### `src/config.py`

**변경**: SKT env 별칭 지원 via `pydantic.AliasChoices`:
```python
skt_a_x_api_key: str = Field(
    default="",
    validation_alias=AliasChoices("SKT_A_X_API_KEY", "SKT_A_X_K1"),
)
skt_a_x_rest_base_url: str = Field(
    default="https://awf-gw.adot.ai",
    validation_alias=AliasChoices("SKT_A_X_REST_BASE_URL", "SKT_A_X_BASE_URL"),
)
skt_a_x_stt_streaming_model: str = Field(default="A.X_STT_note_streaming")
skt_a_x_stt_batch_model: str = Field(default="A.X_STT_note_batch")
```

**이유**: `.env`는 `SKT_A_X_K1=...` / `SKT_A_X_BASE_URL=...` 형식 (팀 관례), 코드는 canonical 이름. 둘 다 accept.

#### `src/dependencies.py`

**추가**:
- `SktAkSttAdapter`, `SolarDocumentParseAdapter` import
- `STTAgent`, `OCRAgent` import
- `get_model_router()`에 SKT/Upstage 조건부 어댑터 등록:
  - `UPSTAGE_API_KEY` 있으면 → `solar-pro3` + `solar-document-parse`
  - `SKT_A_X_API_KEY` 있으면 → `ak-llm` + `skt-ak-stt`
- `get_stt_agent()` 신규 (lru_cache 싱글턴)
- `get_ocr_agent()` 신규 (lru_cache 싱글턴)

#### `src/main.py`

**추가**:
- `from src.routes.stt import router as stt_router`
- `from src.routes.ocr import router as ocr_router`
- `app.include_router(ocr_router)`, `app.include_router(stt_router)`

**충돌 해결** (Master 병합 시):
- Master가 추가한 `domain_router` (F2)와 이 브랜치의 `ocr_router`/`stt_router` 모두 유지
- 최종 총 routes: 17개

#### `pyproject.toml`

- `python-multipart>=0.0.9` 추가 (FastAPI multipart form 처리)

---

## 5. 실전 검증 결과

### 5.1 STT 정확도 (4 VP · 총 22 mp3)

| VP | 페르소나 | 파일 수 | 평균 Char Sim | 평균 지연 | Safety 마커 손실 |
|---|---|---|---|---|---|
| **VP-001** | 김서연 (초진 경증) | 7 | **98.7%** | 952ms | 0/7 |
| **VP-002** | 이준호 (재진 경증) | 10 | **99.2%** | 1,039ms | 0/10 |
| **VP-003** | 박민수 (초진 중증) | 2 | **97.1%** | 952ms | 0/2 |
| **VP-004** | 최하은 (재진 중증) | 3 | **100.0%** | 936ms | 0/3 |
| **합계** | — | **22** | **평균 98.75%** | **970ms** | **0/22** ✅ |

**SLA (2,000ms)** 대비 지연 절반 이하. **자살/자해 관련 표현 손실 0건** (VP-003의 "살고 싶지 않", "사라지고 싶", VP-004의 "죽을 것 같" 등 모두 보존).

### 5.2 OCR 정확도 (4 VP 진단서 PDF)

| VP | 환자 | 추출 결과 | 지연 |
|---|---|---|---|
| VP-001 | 김서연 28F | 상세불명의 불안장애 (F419), 비기질성 불면증 (F510), PHQ-9=7, GAD-7=8 | 2.4s |
| VP-002 | 이준호 35M | 경도 우울에피소드 (F320), PHQ-9=7, GAD-7=5 | 3.4s |
| VP-003 | 박민수 42M | 중증 우울장애 (F322), PHQ-9=22, GAD-7=14 | 3.5s |
| VP-004 | 최하은 31F | 주요우울장애 (F322), 공황장애 (F410), PHQ-9=21, GAD-7=16 | 3.4s |

**4/4 PASS**, SLA (10s) 대비 3배 여유.

### 5.3 F1 전체 파이프라인 (STT + Normalizer + 4 agent + Sentiment + Post-Safety)

| VP | Turns | Crisis | Coverage | Session CTRS | Session Sentiment |
|---|---|---|---|---|---|
| VP-001 | 7 | No | 40%/38% | 4 | sadness/anxiety strong |
| VP-002 | 10 | No | 60%/62% | 4 | **hope/relief moderate** ← 재진 개선 |
| **VP-003** | **2** | **✅ Turn 2** | 40%/25% | 3 | **despair/sadness strong** ← 위기 |
| **VP-004** | **3** | **✅ Turn 3** | 40%/25% | 3 | **anxiety/despair strong** ← 위기 |

**Crisis 시나리오 정확 동작**: VP-003/004에서 자살/자해 발화 감지 → Safety probe 트리거 → Escalation (plan/means disclosure) → CRISIS → "자살예방상담전화 109, 응급전화 119로 연락해 주세요" → 세션 즉시 종료.

### 5.4 명세 준수 검증 (VP-002 샘플 Turn 5)

```
normalizer_meta:   있음 (input_type=stt_transcript)
sentiment:         polarity=0.85 (arousal=medium)
dialogue_safety:   CTRS=5 risk=none  ← AI 응답 자체 안전
```

---

## 6. 테스트 스크립트 (신규)

| 스크립트 | 목적 |
|---|---|
| `tests/smoke_ocr_upstage.py` | Upstage Document Parse API smoke (4 VP PDF 벤더 직접 호출) |
| `tests/smoke_stt_skt.py` | SKT A.X STT API smoke (`--vp VP-001~004` 파라미터) |
| `tests/test_ocr_integration.py` | OCRAgent 통합 (4 VP PDF, 자동 assert: doc_type, blocks, ICD, patient) |
| `tests/verify_stt_to_f1.py` | STT → F1 재현 검증 (원본 텍스트 세션과 slot·CTRS·coverage 비교) |

---

## 7. 산출물 (`docs/ai/simulation_results/`)

### 오디오 (사용자 제공, TTS 생성)
```
VP-001/VP-001-{001-007}.mp3   ( 7개)
VP-002/VP-002-{001-010}.mp3   (10개)
VP-003/VP-003-{001-002}.mp3   ( 2개)
VP-004/VP-004-{001-003}.mp3   ( 3개)
────────────────────────────  총 22개
```

### 문서 (사용자 제공)
```
VP-{001-004}/*_ocr.pdf   (4개 진단서 PDF)
```

### 검증 산출물
```
VP-{001-004}/*_ocr_agent_output.json      (OCRAgent 정식 출력)
VP-{001-004}/*_ocr_upstage_raw.json       (Upstage 원본 응답)
VP-{001-004}/*_ocr_upstage_summary.md     (Markdown 요약)
VP-{001-004}/VP-XXX_stt_smoke_results.json (STT 개별 결과)
VP-001/VP-001_stt_replay_diff.json         (STT vs 원본 텍스트 대비)
```

### F1 세션 실행 결과 (VP별 여러 조합)
- 텍스트 전용 (기존 유지)
- STT only (`--audio-vp-default`)
- OCR only (`--ocr-vp-default`)
- STT + OCR 통합
- 각각 conversation.json + checklist.md + report.md

### TTS 스크립트
```
tts_scripts/README.md
tts_scripts/patient_tts_index.json    (프로그램 배치용)
tts_scripts/VP-{001-004}_patient_tts.md
```

---

## 8. 명세 준수 (`docs/ai/prompts/ocr/v1.system.md`, `docs/ai/agents/06_stt.md`)

### OCR spec 정합
- ✅ **Confidence 4단계 게이팅**: ≥0.9 clean / 0.7-0.9 info / 0.5-0.7 verify / <0.5 retry
- ✅ **`source="ocr_extracted"` 마커** 강제 (AI 진단 아님 명시)
- ✅ **`document_type`**: `consultation`, `lab_result` (spec 정합, 이전 `counseling_record`/`test_result`에서 변경)

### STT spec 정합
- ✅ **FR-035**: `user_confirmed=False` 초기값 (UI가 True 승격)
- ✅ **FR-036**: `audio_retention_expires_at = now + 48h`
- ✅ **Confidence 미조작**: SKT A.X는 confidence 미제공 (spec §6.7), `confidence: float | None`

---

## 9. Test plan

- [ ] `.venv/bin/python -m tests.test_ocr_integration` — OCR 4 VP PDF (4/4 PASS 예상)
- [ ] `.venv/bin/python -m tests.smoke_stt_skt --vp VP-001` — STT 7 mp3 (98.7% char sim)
- [ ] `.venv/bin/python -m tests.smoke_stt_skt --vp VP-002` — STT 10 mp3 (99.2% char sim)
- [ ] `.venv/bin/python -m tests.smoke_stt_skt --vp VP-003` — STT 2 mp3 (97.1% char sim)
- [ ] `.venv/bin/python -m tests.smoke_stt_skt --vp VP-004` — STT 3 mp3 (100% char sim)
- [ ] `.venv/bin/python -m src.f1 --persona VP-001 --audio-vp-default --ocr-vp-default --ocr-hint diagnosis` — F1 end-to-end (Turn 7, CTRS 4)
- [ ] `.venv/bin/python -m src.f1 --persona VP-003 --audio-vp-default` — Crisis 시나리오 (Turn 2 crisis)
- [ ] `.venv/bin/python -m src.f1 --persona VP-004 --audio-vp-default` — Crisis 시나리오 (Turn 3 crisis)
- [ ] `uv run pytest apps/ai-server/tests` — 기존 회귀 (623 tests)

---

## 10. Notes

- 이 브랜치는 최신 Master를 이미 병합함 (`79b9bdf` — F2 DomainInference + RAG 보안 수정 포함)
- `main.py` 충돌 해결: OCR/STT/RAG/Domain 라우터 모두 유지 (총 17 routes)
- 원격 `Master` 브랜치는 이 PR로만 갱신됨 (직접 커밋 없음)
- `.env`의 `SKT_A_X_K1` 별칭 지원으로 별도 env 변경 불필요

---

## 11. Known Issues

- **InputNormalizer LLM 스키마 밖 응답** 간헐 발생 (`stt_misrecognition`, `ocr_misrecognition` 등 enum 밖 값) — Normalizer의 `_safe_fallback`으로 원문 사용, 데이터 손실 없음. 프롬프트 v2 개선 후속 작업 예정.
- STT 오인식 예시 (임상 판정 영향 없음):
  - "앱" → "랩" (VP-001)
  - "주 1~2회" → "주일 지회" (VP-001)
  - "에스시탈로프람" → "에스시탈 로프람" (VP-002, spacing만 다름)
  - "메일이에요" (VP-003, "매일이에요" 오인식 — safety 마커는 보존됨)

---

## 12. PR 재생성 명령

```bash
gh pr create \
  --base Master \
  --head add/f1-stt-and-ocr \
  --title "feat(ai-server): F1에 STT + OCR + InputNormalizer + Sentiment 통합" \
  --body-file docs/ai/pr_description_f1_stt_ocr.md
```
