# 배포 및 백엔드 통합 계획 — 임상 멀티에이전트 F1-F5 on the AI server

> **상태:** APPROVED (user, 2026-07-20). **범위:** `apps/ai-server`를 배포 가능(Docker) 상태로 만들고
> 백엔드와 통합 가능(stateless compute API)하게 만든다. **소유:** conductor-orchestrated lightweight fleet.

## 1. 운영 자산 인벤토리 (배포되는 것)

| 자산 | 경로 | 런타임 이미지 포함? |
|---|---|---|
| 프로덕션 소스 (agents/schemas/routes/services/scoring/rag/adapters/engines F1-F5) | `apps/ai-server/src/` | yes |
| 고정(pinned) 프롬프트 (safety v2, dialogue v4, domain_inference v2, handoff v2/v3) | `docs/ai/prompts/` | **yes — Dockerfile gap G1** |
| 한국어 폰트 자산 (F5 PDF embedding) | `apps/ai-server/scripts/` + assets | **yes — gap G2** |
| 런타임 데이터 캐시 | `src/data/hira_efficacy_cache.json` | yes |
| 공유 계약(shared contracts) | `packages/shared-contracts/python` | yes (Dockerfile에 이미 포함) |
| `.env` (모든 키; 물리적으로 전달, 커밋 절대 금지) | operator-managed | env, 이미지 아님 |
| RAG corpus (case_card 1248 / qa 1789 / symptom 40 / disease 27 / pgvector 4096) | DB server (외부 28881 / compose 내부 5432) | DB, 이미지 아님 |
| tests + scenario packs + personas | repo | CI 전용 |
| `experiments/`, `_archive/` | local | 배포 절대 금지 |

## 2. 리팩터링 세트 (이번 사이클)

| ID | 변경 | 설계 |
|---|---|---|
| R1 | `POST /ai/temporal/analyze` + `POST /ai/handoff/report` | 순수 F4/F5 엔진 위의 얇은 wrapper. 요청은 세션 series를 담아 보낸다(stateless); 응답은 temporal.json / report(md + PDF/FHIR을 base64 또는 file refs로) |
| R2 | Stateless compute 원칙 | 백엔드가 환자/세션 identity + persistence를 소유한다; ai-server는 세션 상태를 절대 저장하지 않는다. REV-001의 "no server-side session persistence"를 구조적으로 해소한다 |
| R3 | `POST /ai/survey/plan` | `resolve_effective_scale` + safety-net + SI-supplement 결정을 노출(F2 출력 + crisis 상태 입력 → administer-plan 출력). 실 환자에게 문항을 시행하는 것은 APP이 담당한다 |
| R4 | Contracts promotion | Ledger-entry / temporal-request / report-request+response 모델을 `packages/shared-contracts`로 이동해 `apps/api`가 타입을 공유하도록 한다 |
| G1-G3 | Dockerfile: prompts + fonts COPY, HEALTHCHECK; HIRA/KAKAO/LLM_TIMEOUT 키에 대한 compose env passthrough | |

**Deferred (P2 backlog):** idempotency guard, request_id propagation(REV-001 major 항목), narrative activation(gated), FHIR `$validate` external option.

## 3. 배포 런북 (Docker)

1. 로컬: `docker compose -f infra/deploy/docker-compose.yml build ai-server` → 컨테이너 smoke(boot, `/health`, route smoke).
2. 전달: `docker save` → `ssh DGX docker load` (또는 private registry).
3. AI 서버: `.env` 배치(operator), `docker compose up -d`; DB는 compose 내부 `postgres:5432` 또는 이후 분리 시 외부 28881 — env-DSN만으로 전환.
4. 검증: `/health` 200, DB preflight, prompt SHA pin, F1 1턴 + F5 report 1건 smoke.

## 4. 게이트

qa(CI-mirror + route contract 테스트 + 컨테이너 build/boot smoke) → clinical-validator가 `/ai/survey/plan` 시맨틱을 quick pass(safety-net/SI-supplement 결정이 검증된 동작과 일치해야 함) → critic 문구/회귀 검토. 로컬 커밋만 수행하며, 사용자의 명시적 word가 있을 때만 publish한다.

## 5. v2 (2026-07-20, ADR-041) — RAG 통합 + nearby 폐기 + PHR 격하

### (a) 최종 라우트 표면

`apps/ai-server/src/main.py`는 정확히 11개 라우터를 등록한다(검증: `grep "include_router"
apps/ai-server/src/main.py`, 2026-07-20 재확인 — `phr` 라우터 추가로 이전 기록한 10개에서
1개 증가): `chat`, `domain`, `handoff`, `ocr`, `phr`, `safety`, `sentiment`, `slots`,
`stt`, `survey`, `temporal`. **`/nearby`는 제거되었다** — `NearbyFacilitiesAgent`, 해당 라우트
모듈(`src/routes/nearby.py`), 스키마(`src/schemas/nearby.py`), 그리고
`hira_hospital`/`hira_pharmacy`/`hira_madm_dtl`/`kakao_local` adapter가 모두 코드베이스에서
삭제되었다(스펙은 `_archive/legacy_code/agent_inventory_wave6/16_nearby_facilities.md`에 archived,
HIRA/Kakao 사용 가이드도 함께 archived). 위 1절의 자산 인벤토리(`docs/ai/prompts/` pin 목록)는
`rag_trigger_judge` 프롬프트 디렉터리가 더 이상 존재하지 않는다는 점을 제외하면 이번 wave로 변경되지
않았다(Policy-B judge 폐기, 아래 (c) 참조). `phr` 라우터(`POST /ai/phr/context`)는 아래
"(e) 호출 시퀀스"에서 상세 기술한다.

### (b) 백엔드 세션-시작 환자-컨텍스트 계약

PHR 처리는 LLM을 직접 호출하는 임상 에이전트(`PatientHistoryAgent`, 구 agent 17, 스펙은
`_archive/legacy_code/agent_inventory_wave6/17_patient_history.md`에 archived)에서 순수 코드
유틸리티인 `src/phr_ingest.py`(모듈 함수: `load_bundles`, `summarize`, `to_system_prompt_note`,
`to_handoff_snippet` — 모듈을 직접 읽어 검증함. 자체 docstring에 "ADR-041: demoted from
`src.agents.patient_history.PatientHistoryAgent`... to this plain module of functions"라고
명시)로 격하되었다. 계약 내용:

- **소유권:** 백엔드가 자체 DB에 PHR 저장(persistence, 환자 identity)을 소유한다 — ai-server는 PHR
  데이터를 절대 저장하지 않으며, 이 계획의 기존 stateless-compute 원칙(위 R2)과 일치한다.
- **전송:** 세션 시작 시(또는 매 턴, 호출자 선택), 백엔드가 MyHealthWay 형식의 PHR JSON — 또는
  이미 계산해 둔 파싱-완료 컨텍스트 문자열 — 을 세션-시작/턴 요청에 담아 ai-server로 전달한다.
- **파싱:** ai-server가 `src/phr_ingest.py`를 통해 원본 JSON을 파싱하고(`src/adapters/
  myhealthway_reader.py`는 변경 없음, 여전히 Layer 1), `to_system_prompt_note()`로 짧은
  자연어 노트로 렌더링한다.
- **채널:** 파싱된 노트는 이번 wave 이전과 동일한 필드로 `DialogueAgent`에 도달한다 —
  `DialogueInput.patient_history_context` — 이름·형태·allowlist 상태 모두 변경 없음. BUG-022
  필드 allowlist 가드(`tests/repro/test_bug_022.py`)는 이 필드를 `DialogueInput`에 대해 기존
  리뷰 노트와 함께 여전히 licensing한다; 이번 wave는 해당 테스트나 allowlist를 건드리지 않았다.

### (c) 앱 측 병원 검색 — 기능 소유권 이관

병원/약국 검색은 더 이상 ai-server 기능이 아니다. 소유권은 앱(APP) 팀으로 이관되어
사용자-개시(user-initiated) 앱 측 기능이 된다 — 이 backend/ai-server 파이프라인을 전혀 경유하지
않는다. Crisis flow(`agents/orchestrator.py::_CRISIS_MESSAGES`)는 고정된 hotline
텍스트(`109`, `119`/`112`, `1577-0199`, 원문 그대로, grep으로 검증)를 유지하지만, 더 이상 그
응답의 일부로 실시간 nearby-hospital 조회를 수행하지 않는다. 환경변수 영향: `HIRA`
hospital/pharmacy/MadmDtl 키와 `KAKAO_*` 키는 **더 이상 ai-server가 소비하지 않는다**(dev
compose, `infra/deploy/docker-compose.yml`은 이제 `HIRA_SERVICE_KEY`,
`HIRA_DRUG_EFFICACY_SERVICE_URL`, `LLM_CLIENT_TIMEOUT_S`, `PROMPTS_BASE_DIR`만 passthrough —
파일을 직접 읽어 검증). `HIRA_SERVICE_KEY` 자체는 계속 live 상태지만, PHR
정신과-약물(psychotropic-medication) 분류용 HIRA drug-efficacy adapter(`src/phr_ingest.py`)에만
scoped되며 병원 검색과는 무관하다. archived된 HIRA/Kakao map API 사용 가이드
(`hira_map_api_integration.md`, `hira_kakao_map_api_usage_guide.md`)는 이 기능을 인계받는 앱
팀을 위한 역사적 레퍼런스로 `_archive/legacy_code/agent_inventory_wave6/`에 위치한다.

### (d) 이미지 위생(hygiene)

`apps/ai-server/Dockerfile`은 더 이상 `tests/` 디렉터리를 프로덕션 이미지에 `COPY`하지 않는다
(검증: Dockerfile에 `COPY apps/ai-server/tests` 라인 없음 — `src`, `pyproject.toml`, 고정
프롬프트 디렉터리, 폰트 자산만 복사됨). 이미지에 실리는 프롬프트 디렉터리는 고정(pinned)/런타임
버전만 포함한다 — `docs/ai/prompts/`는 현재 사용 중인 에이전트당 정확히 하나의 버전만 보유한다
(검증: `find docs/ai/prompts -type f`): `safety_classifier/v2`, `dialogue/v4`,
`domain_inference/v2`, `clinical_slot/v3`, `sentiment_analyzer/v2`, `handoff_generator/v2`와
`v3`, `input_normalizer/v1`, `ocr/v1`, `stt/v1`, `orchestrator/v1`, `evidence_verifier/v1` —
`rag_trigger_judge/` 프롬프트 디렉터리(Policy-B judge, (a)에서 폐기)는 더 이상 디스크에 존재하지
않는다.

### (e) 호출 시퀀스

**Gap 발견 배경(EXP-028b, 2026-07-20):** `POST /ai/chat/respond`는 의도적으로 슬롯 추출을
실행하지 않는다 — `POST /ai/slots/extract`는 별개 라우트다(`routes/chat.py` 자체 주석: "this
route never runs slot extraction itself", design은 `dialogue.py:216` 참조). 백엔드가 이 시퀀스를
모르면 handoff report의 슬롯 section이 비어있는 채로 사용자에게 노출되는 결과로 이어진다
(user-visible consequence). 아래는 코드(`routes/*.py`)를 직접 읽어 검증한, backend가 실제로
호출해야 하는 순서다.

**매 턴(각 사용자 메시지마다) — 반드시 2개 라우트를 함께 호출:**

1. `POST /ai/chat/respond`(`DialogueInput`/`DialogueOutput`) — dialogue + safety를 처리한다.
   `body.session_state`로 이전 턴의 `SessionState`(`OrchestratorAgent`가 관리)를 되돌려주고,
   응답의 `session_state`(dict)를 다음 턴 요청에 그대로 실어 보내야 한다 — 라운드트립 필수. 이
   라우트는 `body.filled_slots`를 **읽기만** 하며 갱신하지 않는다(추출은 아래 2번의 몫). PHR
   컨텍스트는 `body.patient_history_context`(문자열)로 매 턴 전달해야 한다 — 세션 시작 시
   1회 로드해 두었다고 이후 턴에 자동으로 유지되는 필드가 아니다.
2. `POST /ai/slots/extract`(`ClinicalSlotInput`/`ClinicalSlotOutput`) — 슬롯 누적을 담당한다.
   요청은 `conversation_history`(전체 대화)와 `current_slots`(이미 수집된 값 dict, `dict[str,
   Any]`, 병합/컨텍스트용)를 받는다. **응답의 필드명에 주의**: `extracted_slots`(`dict[str, Any]`,
   슬롯 키→값)가 실제 슬롯 값 dict이고, `filled_slots`는 값이 채워진 슬롯 **키 목록**(`list[str]`)
   일 뿐 값 dict가 아니다 — 두 스키마가 `filled_slots`라는 같은 이름을 다른 shape로 쓴다
   (`DialogueInput.filled_slots`는 `dict[str, str]`, `ClinicalSlotOutput.filled_slots`는
   `list[str]`). **백엔드는 `ClinicalSlotOutput.extracted_slots`를 보관했다가, 다음 턴의
   `POST /ai/chat/respond` 요청의 `filled_slots`(dict)로, 그리고 다음
   `POST /ai/slots/extract` 요청의 `current_slots`로 전달해야 한다** — ai-server는 턴 사이에
   슬롯 상태를 저장하지 않는다(stateless compute 원칙, R2).

**백엔드가 턴 사이에 보관/전달해야 하는 것 — 정확히 3가지:**

| 항목 | 어디서 오는가 | 다음 턴에 어떻게 쓰는가 |
|---|---|---|
| `session_state` | `POST /ai/chat/respond` 응답의 `session_state` 필드 | 다음 `POST /ai/chat/respond` 요청의 `session_state`로 그대로 전달 |
| 슬롯 값 dict | `POST /ai/slots/extract` 응답의 `extracted_slots` 필드(`filled_slots`가 아님 — 그건 키 목록) | 다음 `POST /ai/chat/respond` 요청의 `filled_slots`(dict)로 전달(+ 다음 `POST /ai/slots/extract` 요청의 `current_slots`로도 전달) |
| `conversation_history` | 백엔드 자체 turn 기록(사용자 발화 + `assistant_response`를 누적) | 매 `POST /ai/chat/respond`의 `conversation_history`, 매 `POST /ai/slots/extract`의 `conversation_history`로 전달 |

**세션 시작 1회:**

`POST /ai/phr/context`(`PhrContextRequest`/`PhrContextResponse`) — MyHealthWay 형식 PHR JSON
bundle을 요청 body로 전달하면(stateless, LLM/디스크 I/O 없이 `src.phr_ingest`의 순수 함수만 실행),
응답의 `context`(문자열)를 받는다. 이 문자열을 위 "매 턴" 1번의 `patient_history_context`에
매 턴 실어 보내야 한다 — `/ai/phr/context`는 세션당 1회만 호출한다.

**세션 종료 시:**

1. `POST /ai/domain/infer` — 이제 **완전한 F2 산출물**을 반환한다(`DomainInferRouteResponse`):
   `domain_candidates`(whitelist cascade 이후), `department_candidates`, `orphan_departments`,
   `ai_predicted_disease`(top-5, 각 `similarity_score` 포함), `retrieval_meta`(`mode` 필드로
   `rag`/`llm_only` 구분), `summary`. 2026-07-20 이전 버전은 Stage 2(LLM 호출)만 노출하고
   cascade/AI-predicted-disease population을 건너뛰었으나(EXP-028 finding: handoff report의
   disease_similarity 차트가 전부 비어 있었음), 이제 `src.f2`의 code-side 함수를 그대로 재사용해
   전체 아티팩트를 조립한다.
2. `POST /ai/survey/plan`(`SurveyPlanRequest`/`SurveyPlanResponse`) — `/ai/domain/infer` 응답의
   `ai_predicted_disease.recommended_questionnaire`/`recommendation_caveat`와 세션의
   `crisis_triggered`/`session_ctrs`를 넘기면, 시행할 척도(`scale`)·`administration_mode`·
   `si_supplement` 여부·문항 목록(`items`)을 반환한다. 실제 환자에게 문항을 시행하는 것은 앱이
   담당한다.
3. (앱이 문항을 시행한 이후) `POST /ai/survey/score`(`SurveyScoreInput`/`SurveyScoreOutput`) —
   앱이 수집한 `responses`를 넘기면 결정론적 채점 결과(총점, severity, PHQ-9 item-9 SI flag 등)와
   함께 `record`(dict) 서브객체를 반환한다. 이 `record`를 그대로 저장해 두었다가, 이후
   `POST /ai/temporal/analyze`/`POST /ai/handoff/report` 호출 시
   `contracts.longitudinal.LongitudinalSessionEntry.f3`에 대입한다 — 클라이언트 측에서 채점/threshold
   로직을 재구현할 필요가 없다.

**필요 시(여러 세션 누적 후):**

`POST /ai/temporal/analyze`(`body.sessions` — 세션 records 배열, `body.vp_id`) →
`LongitudinalAnalysisOutput`. 이 라우트는 stateless이며 ledger 파일이나 다른 서버 측 세션
상태를 절대 읽지 않는다 — 매 호출 시 백엔드가 `sessions` 배열 전체를 실어 보내야 한다. 이어서
`POST /ai/handoff/report`(`body.sessions`, `body.vp_id`, `body.domain_inference`,
`body.include_charts`, `body.include_pdf`)를 호출하면 F4+F5를 내부적으로 재계산해
`report_markdown`/`fhir_bundle`/`pdf_base64`를 반환한다(`POST /ai/handoff/generate`는 이와
별개의, LLM-narrated report 생성용 pre-existing 라우트이며 이 F4+F5 stateless 흐름과는
무관하다).

**위기(crisis) 관련 필드 — `POST /ai/chat/respond` 응답:**

- `risk_level`(`RiskLevel` — `none`/`low`/`medium`/`high`/`critical`)와 `requires_human_review`
  (`bool`)는 이제 매 턴 실제 safety 판정값이 threading된다(BUG-046 fix, `EXP-028`). Crisis
  bypass(CTRS 1–2, dialogue LLM 호출을 건너뛰고 즉시 반환하는 `routes/chat.py`의 별도 분기)
  경로에서는 `requires_human_review`가 항상 `True`로 하드코딩된다. **Non-bypass 경로**(CTRS
  3–5, 즉 대부분의 턴)에서는 BUG-046 수정 이전에는 `risk_level="none"`/
  `requires_human_review=False`가 실제 판정과 무관하게 고정 반환되는 결함이 있었으나, 수정 이후
  `state.safety_status.risk_level`/`state.safety_status.requires_human_review`를 그대로
  threading한다.
- `requires_human_review`의 의미는 `SafetyOutput.requires_human_review`(CTRS `<= ACUTE`, 즉
  CTRS 1/2/3)에서 유래한다(`schemas/safety.py`) — **CTRS 3(급성기, 예: 수동적/passive 자살
  사고)도 `requires_human_review=true`로 온다**는 점을 백엔드가 명시적으로 인지해야 한다. CTRS
  1(`EMERGENCY`)=`risk_level=critical`, 2(`HIGH_RISK`)=`high`, 3(`ACUTE`)=`medium`,
  5(`STABLE`)=`none`(`schemas/common.py`의 CTRS→RiskLevel 매핑).

## 6. apps/api DGX 편입 (2026-07-22, ADR-046 결정 5/6, PRD §9 결정 #6/#8, §9a #1/#3, filemanager P1-1)

> **범위:** `infra/deploy/docker-compose.dgx.yml`에 `api` 서비스가 신설되었다(§6a는 apps/api
> 기동 런북, §6b는 ENCRYPTION_KEY 공유 SOP). 이 절은 파일 작성만 다룬다 — `alembic upgrade`
> 실행·실 배포 집행은 본 절의 범위 밖(운영 담당자가 아래 절차를 따라 수행).

### (a) apps/api 기동 런북

**작업 가정(ADR-046 결정 5, 명시적):** apps/api를 기존 DB(외부 상시 :28881)·ai-server와
동일 DGX + 동일 compose 파일에 co-locate한다 — 사용자로부터 별도 host 지시가 없어 기본값으로
채택. 외부 포트 `24856`은 미확정 working assumption(운영자 포트 할당 전까지) — ai-server의
확정 포트 `24855`와 달리 공식 할당 근거 없음, 반박 시 `docker-compose.dgx.yml`의 `api.ports`
한 줄만 교체하면 된다(코드 무영향).

1. **선행 조건 (순서 중요):**
   a. `apps/api/.env`를 DGX에 배치 — `DATABASE_URL`이 기존 상시 postgres
      (`223.194.33.26:28881`, asyncpg 드라이버)를 가리키는지 확인(`.env.example`의
      dev-local 값 `localhost:5432`가 그대로 남아있지 않은지 반드시 확인).
   b. `ENCRYPTION_KEY`를 §6b SOP에 따라 `apps/ai-server/.env`와 **동일 값**으로 주입 —
      순서상 이 SOP를 이 단계에서 먼저 완료해야 한다(아래 §6b).
   c. **`alembic upgrade head`를 수동으로 1회 실행** — 컨테이너 기동 전 또는 기동 직후,
      운영 담당자가 직접:
      ```
      cd apps/api && DATABASE_URL=<DGX DSN> uv run alembic upgrade head
      ```
      **이 compose 정의는 마이그레이션을 자동 실행하지 않는다**(init 컨테이너·entrypoint
      훅 없음, 의도적) — 프로덕션 DB에 대한 스키마 변경은 항상 운영자가 명시적으로 승인한
      수동 단계여야 한다는 원칙(§4 게이트 정신과 동일)을 따른다.
      **`head`(특정 revision 하드코딩 아님)를 쓰는 이유:** 마이그레이션 체인이
      `0009 → 0009a → 0010 → …`로 구성되어 있다 — `0009a`(하이픈→비하이픈 questionnaire_type
      백필, DB-F2, ADR-046 결정 7)가 `0010`(v3 CHECK 제약) **바로 앞에** 삽입되어 있으므로
      (`0010`의 `down_revision = "0009a"`), `alembic upgrade head`를 실행하면 alembic이 의존
      그래프를 자동으로 따라가 `0009a`를 `0010`보다 먼저 적용한다 — 운영자가 개별 revision
      순서를 손으로 챙길 필요가 없다. Phase 1에서 developer가 session_state 영속용 신규
      revision을 추가할 수 있으므로(discussion.md P1-2), 이 런북은 그 신규 revision을 미리
      알 필요 없이 `head`-상대로 항상 최신 체인 끝까지 따라간다.
      **주의(멱등성 아님):** 이미 `0010`+ 로 stamp된 DB에 `0009a`를 재적용하면 실패한다 —
      DGX 프로덕션 DB는 ADR-046 status(2026-07-22 probe)에서 hyphen 데이터 존재·`0010` 미적용
      확인됨(여전히 `0008` CHECK) → 이 DB에는 `head`가 안전하게 처음부터 순서대로 적용된다.
      다른 환경(로컬 dev 등)이 이미 `0010`+로 stamp되어 있다면 `0009a`는 alembic이 자동으로
      skip한다(체인에 이미 포함된 것으로 인식) — 별도 조치 불요.
   d. 마이그레이션 확인: `uv run alembic current`로 head 일치 확인(실행 여부 확인만,
      추가 DDL 없음).
2. `docker compose -f infra/deploy/docker-compose.dgx.yml up -d --build` — ai-server와 api
   둘 다 빌드/기동(기존 ai-server 절차와 동일 명령, api 서비스가 추가됐을 뿐 명령 자체는
   불변).
3. 검증: `curl -s localhost:24856/health` 200 확인 → DB 연결(선행 조건 a/c 성공 시 정상) →
   ai-server 연결(`AI_SERVER_URL=http://ai-server:8001`, 내부 compose 네트워크) 스모크(예:
   `/api/v1/sessions` 1건 생성 후 F1 1턴).
4. 롤백: api 서비스만 `docker compose stop api` — ai-server는 무영향(독립 서비스 정의,
   `depends_on`은 기동 순서만 강제, 상태 결합 없음).

**out of scope(코드 범위 밖, 설계 노트만):** §9a #2 WS TLS terminator — apps/api WS 핸들러가
프로덕션에서 TLS 종단을 어디서 받을지(nginx/traefik reverse-proxy 앞단 vs 앱단) 미결정.
이 compose 정의는 평문 포트 노출만 다루며 TLS 종단 구현은 후속 인프라 작업(이 브리프 범위
밖, developer/filemanager 후속).

### (b) ENCRYPTION_KEY 공유 SOP (ADR-046 결정 6, PRD §9 결정 #8, §9a #3)

**전제:** `apps/api/src/core/encryption.py`와 `apps/ai-server/src/rag/crypto.py`는 **동일
AES-256-GCM 키**를 전제로 바이트 호환 포맷(12바이트 nonce + ciphertext + 16바이트 GCM
tag)을 쓴다(`crypto.py` 모듈 docstring이 명시: "api가 넣은 값을 앱이 읽는 것과 마찬가지로,
여기서 넣은 message/name도 앱이 복호화한다"). 두 `.env`는 **독립적으로 관리**되며(각각
`apps/api/.env`, `apps/ai-server/.env`, 둘 다 gitignored) 키를 공유시키는 자동 메커니즘이
없다 — 값이 어긋나면 `_decode_key`/`_key()`가 base64 디코드 실패 또는 GCM tag 불일치로
예외를 던지고(양쪽 다 fail-loud, 조용한 원문 노출 없음 — `crypto.py` docstring: "복호화
실패 = 절대 원문 노출 금지"), ai-server 쪽은 해당 필드를 응답에서 제외하고 명시 로깅한다.

**단일 값 생성 → 양쪽 주입 절차:**

1. **한 번만** 생성(둘 중 어느 쪽에서 실행해도 무방, 값만 동일하면 됨):
   ```
   python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
   ```
   (이 명령은 `apps/api/.env.example`·`_decode_key`의 에러 메시지에 이미 동일하게
   존재 — 신규 규약 아님, 기존 키 생성법을 SOP로 공식화하는 것.)
2. 생성된 값을 **바이트 그대로**(공백·개행 없이) 두 파일에 동일하게 주입:
   - `apps/api/.env` → `ENCRYPTION_KEY=<값>`
   - `apps/ai-server/.env` → `ENCRYPTION_KEY=<값>`
3. 두 값이 실제로 동일한지 배포 전 확인(예: `diff <(grep ^ENCRYPTION_KEY apps/api/.env)
   <(grep ^ENCRYPTION_KEY apps/ai-server/.env | sed 's/ .*//')` — ai-server
   `.env.example`은 키 뒤에 설명 주석이 붙는 포맷이므로 값만 비교할 것) — 어느 한쪽이라도
   trailing whitespace/줄바꿈이 다르면 base64 디코드 단계에서 실패한다(`_decode_key`가
   `.strip()`을 적용하므로 순수 공백차는 방어되나, 값 자체가 다르면 반드시 실패).
4. compose `up` 전에 완료 — 두 서비스 모두 기동 시점에 이미 올바른 키를 읽어야 한다
   (compose `environment:`는 `ENCRYPTION_KEY`를 오버라이드하지 않음 — 각 서비스의
   `env_file`이 그대로 전달됨).

**로테이션 시 주의(양쪽 동시 갱신 필수):**

- 이 SOP는 **단일 키, 로테이션 미지원**(Demo 단계, `encryption.py` docstring: "Phase 2:
  KMS-backed key rotation (per-record `key_version`)" — 아직 미구현).
- 키를 교체하면 **기존에 그 키로 암호화된 모든 컬럼이 새 키로 복호화 불가**해진다(re-encrypt
  파이프라인 없음, 현 구현 범위 밖) — 로테이션은 곧 기존 암호화 데이터의 유실(또는 별도
  마이그레이션 스크립트가 선행되어야 함, 이 SOP 범위 밖).
  로테이션이 필요해지면: (1) 양쪽 서비스를 동시에 중지, (2) 새 키를 양쪽 `.env`에 동일하게
  주입(위 절차 반복), (3) 양쪽 서비스를 동시에 재기동. **한쪽만 갱신하고 다른 쪽을 갱신하지
  않으면** 그 사이 두 서비스가 서로 다른 키로 각자 쓰기/읽기를 하게 되어, ai-server가 쓴
  값을 api가 못 읽거나(또는 반대) 조용한 실패가 아니라 매 호출마다 예외/필드-제외가
  발생한다(fail-loud이므로 데이터 유실은 아니나 가용성 저하) — "동시" 갱신이 곧 롤아웃
  원자성 요구사항이다.
- Phase 2 KMS 도입 전까지는 이 수동 SOP가 유일한 메커니즘이다 — 자동화(secret 관리 도구)는
  PRD §9 결정 #8의 두 옵션 중 미채택(수동 절차 채택, 근거: Phase 1 범위에서 KMS 통합은
  과대설계).

### 배포-shape sweep 이후의 문서 표면

배포-shape sweep(개발-사이클 기록은 `_archive/` 아래로 archived, 통합에 필요한 문서만 repo에
잔류)에 따라, 현재 live `docs/ai/` 표면은 다음과 같다: 이 계획서(`deployment_integration_plan.md`),
`agents/` 스펙, `api/` 스펙, `prompts/`(고정 버전만), `agent_collaboration_f1f5.md`.
`workflow_checklist_f1f2.md`, `workflow_discussion_f1f2.md`, `workflow_results_f1f2.md`,
`lexicon_expansion_val010.md`는 그 sweep의 대상이며 이번 wave의 문서 동기화 작업에서는 편집하지
않는다 — 이번 사이클의 coordinator 명시적 범위 조정에 따라 범위 밖이다.
