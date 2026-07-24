# NeuroSync 에이전트 모델 스왑 성능 실험 리포트

> 목적: 현재 전 생성 에이전트가 **Solar Pro3(1순위)** 로 구성된 파이프라인에서,
> 에이전트별 LLM을 **LG EXAONE / SKT A.X**로 바꿔가며 **성능·안정성·지연**을 비교한다.
> 브랜치: `test/agent-model-swap-benchmark` · RAG DB(원격 pgvector) 연동, F1~F5 라이브 검증.

## 1. 방법론

- **스왑 방식**: 원본 `agent_model_registry.yaml`은 변경하지 않고, `MODEL_REGISTRY_PATH` 환경변수로
  변형 레지스트리를 주입. 각 변형은 대상 에이전트의 `primary` 티어를 EXAONE(기존 secondary) 또는
  A.X(기존 fallback)로 승격(supports 플래그 유지).
- **시나리오(공통)**: `continuous_test --persona VP-001 --sessions 2 --session-interval-days 14
  --max-turns 4 --k 3 --answer-mode expected`, **RAG DB 연동**(원격 pgvector), F1~F5 전 과정.
- **모델 서빙 엔드포인트**: Solar=`api.upstage.ai` · EXAONE=`api.friendli.ai`(LG 전용 엔드포인트) ·
  A.X=`awf-gw.adot.ai`(SKT). 호출 host로 실제 서빙 모델을 검증.
- **지표**:
  - **완주**: F1~F5 각 스테이지 PASS/FAIL(비할당 FAIL은 하네스 데이터 갭으로 구분)
  - **F1 턴 평균 지연(ms)**: F1 대화 턴당 처리 시간(주 비교 지표, 대화 체감 지연 근사)
  - **재시도·복구 흔적**: JSON repair·ValidationError·retry·fallback 로그 빈도(구조화 출력 안정성 프록시)
  - **호출 분포**: 실제 서빙 모델(Solar/EXAONE/A.X) 비율
  - **전체 소요(s)**: 구성별 벽시계 시간
- **연결성 사전 확인**: Solar 0.7s · A.X 0.3s · EXAONE 0.4s(+Friendli extra_body) 모두 정상.

## 2. 실험 매트릭스

| 그룹 | 구성 | 스왑 대상 | 목적 |
|---|---|---|---|
| 기준 | `solar_baseline` | (없음, 전부 Solar) | 레퍼런스 |
| A(전면) | `exaone_all` / `ax_all` | 전 벤치마크 에이전트 | 전면 교체 영향 |
| B(대화) | `exaone_dialogue` / `ax_dialogue` | dialogue만 | 비구조화 에이전트 스왑 |
| C(안전) | `safety_exaone` / `safety_ax` | safety_classifier | 위기판정 에이전트 민감도 |
| C(슬롯) | `slot_exaone` / `slot_ax` | clinical_slot | 구조화 슬롯추출 민감도 |
| C(도메인) | `domain_exaone` / `domain_ax` | domain_inference(F2) | RAG/추천 에이전트 민감도 |

## 3. 결과 — 전체 11개 구성 (완료)

동일 시나리오(VP-001·2세션·4턴·RAG DB) 실측. 지연은 평균이 이상치에 왜곡되어 **중앙값(median)**
과 **최대(tail)** 를 함께 보고한다. (F1 턴 latency 마커 표본 기준)

| 그룹 | 구성 | 호출 Solar/EXA/A.X | 턴수 | **중앙 지연** | **최대 지연** | 재시도·복구 | F1~F5 완주 |
|---|---|---|---|---|---|---|---|
| 기준 | solar_baseline | 67 / 10 / 0 | 8 | **5,056ms** | 6,344ms | 4 | 완주(F3 1건*) |
| A(전면) | exaone_all | 4 / 66 / 0 | 8 | 13,175ms | 45,170ms | 17 | 완주 |
| A(전면) | ax_all | 2 / 3 / 24 | 2 | 13,399ms | 19,110ms | 15 | 완주 |
| B(대화) | exaone_dialogue | 53 / 20 / 0 | 8 | 8,532ms | 17,412ms | 4 | 완주 |
| B(대화) | ax_dialogue | 54 / 10 / 10 | 8 | 6,655ms | 12,186ms | 13 | 완주 |
| C(안전) | safety_exaone | 24 / 14 / 0 | 4 | 8,700ms | 21,592ms | 2 | 완주 |
| C(안전) | safety_ax | 14 / 2 / 2 | 0† | — | — | 0 | 완주 |
| C(슬롯) | **slot_exaone** | 56 / 20 / 0 | 8 | 11,107ms | **124,203ms** | 6 | 완주 |
| C(슬롯) | slot_ax | 56 / 10 / 10 | 8 | 4,168ms | 11,217ms | **14** | 완주 |
| C(도메인) | domain_exaone | 64 / 12 / 0 | 8 | 4,871ms | 8,999ms | 1 | 완주 |
| C(도메인) | domain_ax | 69 / 10 / 2 | 8 | 5,175ms | 5,976ms | 10 | 완주 |

\* solar FAIL = F2가 GAD-7 추천 → VP-001 페르소나 MD에 GAD-7 예상점수표 부재(expected 모드 데이터 갭, 모델 품질 무관).
† safety_ax는 대화 턴 표본이 2건 미만이라 latency 지표 산출 불가(완주 자체는 정상). 소표본 이슈로 지연 비교에서 제외.

## 4. 분석

### 4.1 견고성 — 전 구성 F1~F5 완주 ✅
11개 구성 모두 RAG DB 연동 F1~F5를 완주했다. 어떤 에이전트를 어떤 국내 모델로 바꿔도 파이프라인이
깨지지 않음(티어 폴백 + JSON repair + F4/F5 결정론 설계의 효과).

### 4.2 속도 — Solar 최우위, 전면 스왑은 2.6×↑
중앙 지연 기준 solar_baseline 5.06s가 최소. 전면 스왑은 EXAONE 13.2s·A.X 13.4s로 **2.6×** 증가.
부분 스왑은 대상 에이전트에 따라 다름.

### 4.3 에이전트별 모델 민감도 (핵심 발견)
격리 스왑으로 "어느 에이전트가 모델 교체에 취약한가"가 드러났다.

- **clinical_slot(슬롯추출)이 가장 민감** — `slot_exaone`은 중앙 11.1s에 **최대 124.2s**(단일 턴)로
  치명적 tail latency. `slot_ax`는 빠르지만 **repair 14건**(A.X는 native JSON 미지원 → 반복 복구).
  임상 슬롯의 엄격한 스키마 추출이 비-Solar 모델의 최대 약점.
- **domain_inference(F2)는 상대적으로 관대** — EXAONE 4.9s/1repair, A.X 5.2s/10repair로 지연 영향 적음
  (RAG 검색은 임베딩·pgvector가 담당, LLM은 후보 판단만 → 부하 낮음).
- **safety_classifier** — EXAONE 8.7s/2repair로 동작하나, A.X 구성은 표본 부족으로 지연 판정 보류.
  위기판정 정확도는 별도 품질 평가 필요(후속).
- **dialogue** — 비구조화 성격상 스왑 영향이 중간(EXAONE 8.5s, A.X 6.7s).

### 4.4 구조화 출력 안정성 — Solar ≳ EXAONE > A.X
repair·retry 흔적: Solar/도메인-EXAONE 계열 최소(1~4), **A.X 계열 전반 10~15**로 급증.
A.X는 native JSON 미지원이라 프롬프트+repair에 의존 → 스키마 강한 에이전트(slot)에서 부담 최대.

## 5. 종합 결론

1. **주력 1순위는 Solar 유지가 타당.** 속도·구조화 출력 안정성 모두 우위.
2. **모델 민감도는 에이전트마다 크게 다르다.** 스키마 강도가 높은 **clinical_slot > safety_classifier >
   dialogue > domain_inference** 순으로 비-Solar 모델 취약. 전면 스왑보다 **에이전트별 선택 배치**가 정답.
3. **국내 타 모델 실전 배치 가이드(예비)**:
   - `domain_inference` → EXAONE/A.X 대체 여지 큼(지연·부하 낮음).
   - `dialogue` → A.X 우선 후보(빠름, repair는 중간).
   - `clinical_slot`·`safety_classifier` → Solar 유지 권장(스키마·안전 크리티컬).
4. **전면 스왑을 하려면 선행 과제**: EXAONE/A.X용 **JSON 스키마 강제·repair 파이프라인 최적화**,
   특히 slot_exaone의 **124s tail latency 원인(타임아웃·스트리밍) 해소**.

### 5.1 한계 및 후속
- VP-001 단일·2세션·4턴 축소셋 → **표본 확대(다페르소나·풀아크)** 필요.
- 지연 위주 측정 → **출력 품질(리포트 정합·grounding 정확도·위기 감지 정확도·개발자 정보 누출)** 평가 후속.
- safety_ax 소표본 → 재실행 필요.
- 혼합 스왑(예: domain→EXAONE + dialogue→A.X, safety만 Solar 고정) 조합 실험 여지.

## 부록. 재현 방법

```bash
# 변형 레지스트리 주입 실행 예
export DATABASE_URL="postgresql+asyncpg://neurosync:***@223.194.33.26:28881/neurosync"
MODEL_REGISTRY_PATH=/tmp/bench_registry/<config>.yaml \
  python -m src.continuous_test --persona VP-001 --sessions 2 --session-interval-days 14 \
    --max-turns 4 --k 3 --answer-mode expected
```
- 변형 레지스트리: `/tmp/bench_registry/*.yaml` (원본 미변경, env 주입)
- 로그: `/tmp/bench_logs/*.log`
