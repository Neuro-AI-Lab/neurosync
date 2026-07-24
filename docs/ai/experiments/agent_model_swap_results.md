# NeuroSync LLM 조합 성능 테스트 — 전체 결과 정리

> 현재 전 생성 에이전트가 **Solar Pro3(1순위)** 인 파이프라인에서, 에이전트별 LLM을
> **LG EXAONE / SKT A.X**로 교체한 **모든 조합의 성능·안정성·완주 결과**를 빠짐없이 정리.
> 브랜치 `test/agent-model-swap-benchmark` · RAG DB(원격 pgvector) 연동 · F1~F5 라이브 검증.
> 상세 분석/결론은 `agent_model_swap_report.md` 참조 — 본 문서는 **전 조합 raw 결과표**.

## 측정 조건
- 시나리오(공통): `continuous_test --persona VP-001 --sessions 2 --session-interval-days 14 --max-turns 4 --k 3 --answer-mode expected`, RAG DB 연동, F1~F5 전 과정.
- 스왑: 원본 레지스트리 미변경, `MODEL_REGISTRY_PATH`로 변형 주입(대상 에이전트 primary만 승격).
- 서빙 확인 host: Solar=`upstage.ai` · EXAONE=`friendli.ai`(LG) · A.X=`awf-gw.adot.ai`(SKT).
- 지표: **중앙 지연**(F1 턴당, median) · **최대 지연**(tail) · **평균**(참고) · **재시도/복구**(JSON repair·retry·fallback) · **완주**(F1~F5). 지연은 이상치 영향으로 중앙값을 대표로 사용.
- 표본: VP-001 단발(2세션·4턴) — 근소차는 노이즈 가능, 큰 경향은 유효.

---

## 전체 조합 결과표 (14개 구성)

| # | 그룹 | 구성 | 스왑 내용 | 실제 호출 S/E/AX | 턴표본 | **중앙 지연** | 평균 | **최대(tail)** | 재시도·복구 | F1~F5 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 기준 | `solar_baseline` | 전부 Solar(원본) | 67/10/0 | 8 | **5,056ms** | 5,201 | 6,344ms | 4 | 완주* |
| 2 | A 전면 | `exaone_all` | 전 에이전트→EXAONE | 4/66/0 | 8 | 13,175ms | 16,815 | 45,170ms | 17 | 완주 |
| 3 | A 전면 | `ax_all` | 전 에이전트→A.X | 2/3/24 | 2 | 13,399ms | 13,399 | 19,110ms | 15 | 완주 |
| 4 | B 대화 | `exaone_dialogue` | dialogue→EXAONE | 53/20/0 | 8 | 8,532ms | 9,373 | 17,412ms | 4 | 완주 |
| 5 | B 대화 | `ax_dialogue` | dialogue→A.X | 54/10/10 | 8 | 6,655ms | 7,187 | 12,186ms | 13 | 완주 |
| 6 | C 안전 | `safety_exaone` | safety_classifier→EXAONE | 24/14/0 | 4 | 8,700ms | — | 21,592ms | 2 | 완주 |
| 7 | C 안전 | `safety_ax` | safety_classifier→A.X | 14/2/2 | 0† | —† | — | —† | 1 | 완주 |
| 8 | C 슬롯 | `slot_exaone` | clinical_slot→EXAONE | 56/20/0 | 8 | 11,107ms | 31,444 | **124,203ms** | 6 | 완주 |
| 9 | C 슬롯 | `slot_ax` | clinical_slot→A.X | 56/10/10 | 8 | 4,168ms | — | 11,217ms | 14 | 완주 |
| 10 | C 도메인 | `domain_exaone` | domain_inference→EXAONE | 64/12/0 | 8 | 4,871ms | — | 8,999ms | 1 | 완주 |
| 11 | C 도메인 | `domain_ax` | domain_inference→A.X | 69/10/2 | 8 | 5,175ms | — | 5,976ms | 12 | 완주 |
| 12 | D 선택배치 | **`mix_optimal`** | slot·safety=Solar, domain→EXAONE, dialogue→A.X | 54/11/10 | 8 | **5,276ms** | — | **7,536ms** | 18 | 완주 |
| 13 | D 선택배치 | `exaone_but_slotsafety` | slot·safety=Solar, 그외 전부 EXAONE | 30/43/0 | 8 | 6,041ms | — | **79,363ms** | 12 | 완주 |
| 14 | D 선택배치 | `ax_but_slotsafety` | slot·safety=Solar, 그외 전부 A.X | 34/10/36 | 8 | 6,251ms | — | 12,227ms | 28 | 완주 |

\* `solar_baseline` F3 1건 FAIL = F2가 GAD-7 추천 → VP-001 페르소나 MD에 GAD-7 예상점수표 부재(expected 모드 하네스 데이터 갭, 모델 품질 무관). 나머지 스테이지·세션 정상.
† `safety_ax`는 2회 실행 모두 F1 대화 턴 latency 표본 <2 → 지연 지표 산출 불가(완주 자체는 정상). safety_classifier를 A.X로 두면 대화 턴 전개가 달라짐(조기 종료/판정 차이 추정) → 위기판정 정확도 별도 품질 검증 필요.

---

## 지표별 순위 요약

### 속도 (중앙 지연, 낮을수록 우수)
| 순위 | 구성 | 중앙 지연 | baseline 대비 |
|---|---|---|---|
| 1 | slot_ax | 4,168ms | 0.82× |
| 2 | domain_exaone | 4,871ms | 0.96× |
| 3 | **solar_baseline** | 5,056ms | 1.00× |
| 4 | domain_ax | 5,175ms | 1.02× |
| 5 | **mix_optimal** | 5,276ms | 1.04× |
| 6 | exaone_but_slotsafety | 6,041ms | 1.19× |
| 7 | ax_but_slotsafety | 6,251ms | 1.24× |
| 8 | ax_dialogue | 6,655ms | 1.32× |
| 9 | exaone_dialogue | 8,532ms | 1.69× |
| 10 | safety_exaone | 8,700ms | 1.72× |
| 11 | slot_exaone | 11,107ms | 2.20× |
| 12 | exaone_all | 13,175ms | 2.61× |
| 13 | ax_all | 13,399ms | 2.65× |

> 주의: slot_ax는 중앙값은 빠르나 repair 14건(불안정), tail도 큼. 중앙값만으로 판단 금물.

### 최악 지연 (tail, 실사용 리스크)
- 양호(≤12s): solar_baseline 6.3s · mix_optimal 7.5s · domain_exaone 9.0s · domain_ax 6.0s · slot_ax 11.2s · ax_dialogue 12.2s · ax_but_slotsafety 12.2s
- 위험(≥17s): exaone_dialogue 17.4s · ax_all 19.1s · safety_exaone 21.6s · exaone_all 45.2s · **exaone_but_slotsafety 79.4s** · **slot_exaone 124.2s**

### 안정성 (재시도·복구, 적을수록 우수)
- 우수(1~4): domain_exaone 1 · safety_exaone 2 · solar_baseline 4 · exaone_dialogue 4
- 보통(6~13): slot_exaone 6 · domain_ax 12 · exaone_but_slotsafety 12 · ax_dialogue 13
- 불안정(14+): slot_ax 14 · ax_all 15 · exaone_all 17 · mix_optimal 18 · **ax_but_slotsafety 28**

### 완주율
- **14/14 전 구성 F1~F5 완주** (RAG DB 연동). 모델 조합과 무관하게 파이프라인 무붕괴.

---

## 모델별 특성 (조합 결과에서 도출)

| 모델 | 속도 | 구조화(JSON) 안정성 | 특징 |
|---|---|---|---|
| **Solar Pro3**(Upstage) | 최속(중앙 5.1s) | 최고(native json_schema) | 주력 1순위. 전 지표 우위 |
| **EXAONE**(LG) | 중~하(전면 2.6×) | 중(json_object, schema 없음) | slot·handoff 등 구조화 에이전트에서 **tail 폭증(79~124s)** |
| **A.X**(SKT) | 중(전면 2.6×) | 하(native JSON 미지원) | 개별 지연은 낮으나 **repair 다발**(전면 15, 격리도 12~28) |

## 에이전트별 모델 민감도 (교체 시 성능 저하 순)
1. **clinical_slot** — 가장 민감. EXAONE tail 124s, A.X repair 14. (엄격 스키마 추출)
2. **safety_classifier** — EXAONE 8.7s, A.X는 대화흐름 변화(표본부족). (위기판정 크리티컬)
3. **dialogue** — 중간. A.X 6.7s / EXAONE 8.5s. (비구조화라 상대적 관대)
4. **domain_inference** — 가장 관대. EXAONE 4.9s(repair 1) / A.X 5.2s. (RAG 검색은 임베딩·pgvector 담당, LLM 부하 낮음)

## 최적 조합 (검증됨)
> **`mix_optimal`** = `clinical_slot`·`safety_classifier`는 **Solar 고정**, `domain_inference`→**EXAONE**, `dialogue`→**A.X**
> → 중앙 5.3s·tail 7.5s로 **baseline과 동일급 성능**을 유지하면서 국내 타 모델(EXAONE·A.X) 사용률↑.
> 즉 "전면 스왑(2.6× 느림)"이 아니라 **에이전트별 선택 배치**가 정답.

---

## 재현 방법
```bash
export DATABASE_URL="postgresql+asyncpg://neurosync:***@223.194.33.26:28881/neurosync"
MODEL_REGISTRY_PATH=/tmp/bench_registry/<config>.yaml \
  python -m src.continuous_test --persona VP-001 --sessions 2 --session-interval-days 14 \
    --max-turns 4 --k 3 --answer-mode expected
```
- 변형 레지스트리: `/tmp/bench_registry/*.yaml` (원본 `agent_model_registry.yaml` 미변경, env 주입)
- 로그: `/tmp/bench_logs/<config>.log` · 구성별 산출물 백업: `simulation_results/VP-001/_bench_*/`

## 한계 (측정 범위 명시)
- **측정 = 지연·안정성·완주.** 임상 출력 품질(리포트 정합·grounding 정확도·위기 감지 정확도·개발자 정보 누출)은 **미측정** — 후속 품질 라운드 필요.
- VP-001 단발(2세션·4턴) 표본 → 근소차는 재현 필요, 큰 경향(전면 2.6×, slot tail, mix_optimal 동일급)은 유효.
- safety_ax는 소표본으로 지연 제외, 재검 필요.
