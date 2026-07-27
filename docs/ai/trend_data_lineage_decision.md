# 대시보드 "상태 변화 추이" 그래프 공백 — 데이터 계보 결정 보고서

**작성일:** 2026-07-27
**기준 커밋:** Master `6c73d1b` (PR #96, #97 머지 직후)
**근거 entry:** BUG-092, ADR-049, ADR-050(moot 처리 경위 포함), PLAN-2026-W31-WEBDASH
**조사 담당:** data (본 문서는 writer가 해당 RESULT를 재구성)

## 배경

의료진 웹 대시보드의 "상태 변화 추이" 그래프가 데모 데이터셋에서 공백으로 나타난다. qa가 이전에
관찰한 502(`TREND_UNAVAILABLE`)와 그래프 공백이 같은 원인인지, 이미 해소되었는지, 남은 갭이
무엇인지를 data가 코드·스키마·DB 실측으로 조사했다.

## 1. 읽기 계보 — 예상과 반전

`GET /api/v1/sessions/{id}/report/trend`의 구현은 `get_report_trend`
(`apps/api/src/api/v1/sessions.py:734`)이다. Master `6c73d1b` 시점 코드는
**`rag.longitudinal_series` / `rag.session_insights`를 전혀 읽지 않는다.**

실제 조회 경로는 다음과 같다.

- 현재 세션의 척도 점수: `_session_scales()` (`sessions.py:701-706`)
- 같은 환자의 직전 세션: `sessions.py:783-798`
- 결정론적 방향 판정: `_pairwise_direction()` (`sessions.py:709-721`) — PHQ-9 → GAD-7 → AUDIT-C →
  PHQ-4 우선순위로 척도를 선택
- 즉, 트렌드는 `questionnaire_results` 테이블 값만으로 산출되며 LLM/RAG 서비스 호출이 없다.
  코드 주석(`sessions.py:800-804`)이 cross-service 호출 제거를 명시한다.

**qa가 관찰한 502(`TREND_UNAVAILABLE`)의 근본 원인**은 폐기된 `POST /ai/temporal/summarize` 호출
(pre-merge `b19aadc` 코드, 당시 line ~654)이었다. **PR #96이 이 호출 경로를 이미 코드 레벨로
제거했다.** ai-server 측 `routes/temporal.py:11-14`는 "The former `POST /ai/temporal/summarize`...
has been retired... `/analyze` is the sole live surface"라고 명시하며, `/ai/temporal/analyze`는
완전 stateless(DB 미접촉)다. 다만 이 502 해소는 **로컬 api :8000이 머지된 코드로 재시작된 이후에만
유효**하다 — 재시작 여부는 실행 환경 상태이므로 별도 확인이 필요하다.

## 2. 스키마 실물

| 테이블 | DDL 위치 | 주요 컬럼 | 실측 행 수 |
|:--|:--|:--|:--|
| `rag.longitudinal_series` | `apps/api/alembic/versions/0008_pipeline_output_homes.py:57-69` | id/patient_id/session_id/scale/total_score/severity/measured_at/series(jsonb)/generated_at, UNIQUE(patient_id,scale,measured_at) | 0 |
| `rag.session_insights` | `0005_rag_corpus_schema.py:125-140` + 0007/0008 증분 | session_id(PK, FK sessions.id)/patient_id(FK users.id)/flags/phq9_score/gad7_score/암호화 컬럼/embedding vector(4096)/slots(jsonb) 등 | 0 |

두 테이블 모두 `rag` 스키마 소유이며 DDL은 apps/api alembic(0005~0010)이 관리한다.

## 3. 쓰기 계보 — writer 부재 확정

리포지토리 전체에서 `INSERT INTO rag.`를 검색한 결과, 유일한 INSERT는
`apps/ai-server/src/rag/tooling/load_simulations.py`(:348, :419)이다. 이는 오프라인 CLI로
호출 트리거가 없으며, 목적은 VP(가상환자) 시뮬레이션 코퍼스 적재(`docs/ai/simulation_results`의
소스)이고 UPSTAGE 임베딩이 필요하다. apps/api에는 이 두 테이블에 대한 모델/writer가 전혀 없다.

**명시적 설계 금지**가 코드에 남아 있다.

- `apps/api/src/models/session.py:65-66`: "rag.session_insights.slots는 VP 시뮬레이션 코퍼스
  테이블이므로 실환자 슬롯은 반드시 이 플랫폼 컬럼에만" (코퍼스 오염 방지)
- `apps/api/src/services/chat.py:376-377`: 동일 취지의 주석

PR #96 diff 범위(`b19aadc..6c73d1b`)에는 `load_simulations`/`temporal` 계열 변경이 0건이다 —
writer 부재는 #96 이후에도 그대로다.

## 4. 시드 공백 원인

`seed_demo.py`에는 `rag.*` 참조가 0건이다. 이는 "시드 누락 버그"가 아니라 **의도된
아키텍처**로 판단된다 — 이 두 테이블은 실/데모 환자 데이터로 채워지도록 설계되어 있지 않다.
운영(DGX) 환경에서도 세션이 아무리 쌓여도 이 테이블은 채워지지 않는다(코드 경로 전체에 걸친
구조적 사실). **DGX DB 실측 자체는 UNVERIFIED — 접근 불가하여 직접 확인하지 못했다.**

## 5. 남은 갭

502 제거 후에도 그래프가 의미 있게 채워지려면 다음이 필요하다.

- 동일 환자의 2회 이상 세션
- 각 세션의 `questionnaire_results`

현 데모 DB는 환자 5명 / 세션 5개(1인당 1세션)이므로 "이전 방문"이 존재하지 않아 트렌드가
공백으로 남는다.

## 6. 옵션 비교

| 옵션 | 내용 | 노력 | 평가 |
|:--|:--|:--|:--|
| ① seed에 `rag.*` 합성 시계열 INSERT | 시드 스크립트가 직접 두 테이블에 합성 데이터를 넣음 | S~M | **아키텍처 위반**(명시적 금지 경로 무시 + 코퍼스 오염) + **trend 엔드포인트가 이 테이블을 읽지 않으므로 그래프에 무효과**(사문화 writer가 됨) → 폐기 권고 |
| ② seed에 동일 환자 시간차 재방문 세션(+`questionnaire_results`) 추가 | 데모 환자에게 두 번째(과거) 세션과 문진 결과를 추가 | — | trend는 이미 이 데이터만으로 산출되므로 즉시 반영됨, LLM 비용 0(문진 채점은 결정론적), data 영역 순수 시드 확장, 아키텍처 위반 없음 → **권고** |
| ③ 현상 유지 | 아무 조치 없음 | — | `apps/web/lib/api.ts:286, 290`의 `getReportTrend`는 실패 시 null 반환(비차단) — 트렌드 카드만 공백으로 남고 나머지 대시보드는 정상 |

## 7. 권고안 (data 조사, writer 재구성)

옵션② 채택, 옵션① 폐기를 권고한다. 전제 조건은 **로컬 api :8000을 머지된 코드로 재시작**하여
502(`TREND_UNAVAILABLE`)가 실제로 소멸했는지 확인한 뒤, 시드 확장을 진행하는 것이다.

## 결정 요청

사용자가 선택해야 할 사항:

1. **502 해소 확인**: 로컬 api :8000 재시작 후 `/report/trend` 호출을 재현 테스트하여 502가
   실제로 사라졌는지 확인할 것인가 — 확인 담당(qa 재검증 vs developer 자체 확인)을 누구로 할 것인가?
2. **시드 확장 채택**: 옵션②(동일 환자 재방문 세션 + `questionnaire_results` 추가)를 채택할
   것인가, 아니면 옵션③(현상 유지, 트렌드 카드 공백 수용)으로 둘 것인가?
3. **옵션① 폐기 확정**: `rag.longitudinal_series`/`rag.session_insights`에 대한 시드 writer
   추가는 아키텍처 위반이자 무효과이므로 폐기하는 것으로 확정할 것인가 — 아니면 이 두 테이블을
   향후 다른 기능(예: 장기 추세 분석 고도화)에서 실제로 읽도록 trend 엔드포인트를 개편하는
   별도 로드맵 항목으로 남길 것인가?
4. **DGX 실측 검증**: DGX DB에서의 `rag.*` 테이블 상태(현재 UNVERIFIED)를 언제 확인할 것인가 —
   다음 배포 점검 시점에 포함할 것인가?
---
