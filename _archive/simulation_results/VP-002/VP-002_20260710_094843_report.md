# F2 Domain Inference Report — VP-002

## Repro metadata

| Field | Value |
|---|---|
| git HEAD | `c2acc90dc5388a0597cd80b23aa003ca799693ab` |
| model_used | solar-pro3-260323 |
| prompt_version | v2 |
| input_file | `/home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/VP-002/VP-002_20260710_094832_conversation.json` |
| input_sha256 | `30eeb80a599515863dbab16444e85bd1adb81a02c71248452ed8d54c08ec37b6` |
| mode | **rag** |
| latency_ms | 10421.1 |
| generated_at | 2026-07-10T09:48:43.834221 |
| finish_reason | stop |
| usage | {'prompt_tokens': 3433, 'completion_tokens': 1017, 'total_tokens': 4450} |

## Retrieval

- mode: rag
- chunks_returned: 9
- chunk_ids: ['case_card:1038', 'case_card:858', 'case_card:1024', 'qa:1092', 'qa:509', 'qa:816', 'case_card:433', 'qa:319', 'qa:1225']
- queries: ['약 복용 6주 후 증상 호전되어 진찰 받으러 옴', '약 복용 6주 후 증상 호전, 아내 도움으로 산책 및 외식 통해 점진적 개선, 아직 완전하지는 않으나 예전보다 나아짐']

## Domain candidates

### depression (confidence=0.85)
- [OK] rag_chunk:case_card:1038 — "내담자는 우울과 관련하여 몇 가지 주요 증상을 보이고 있다. 첫째, 내담자는 피곤함을 자주 느끼고 기운이 없다고 보고했으며, 이는 신체적 무기력감으로 나타날 수 있다. 둘째, 식욕이 줄어들었다고 언급하여 체중 변화나 식습관의 변화가 있을 가능성이 있다. 셋째, 내담자는 일상적인 활동 중에도 빨리 집에 가서 쉬고 싶다는 생각을 자주 한다고 하여, 일상생활에서의 흥미나 즐거움이 감소했음을 시사한다."
- [OK] rag_chunk:case_card:858 — "내담자는 우울한 기분과 피로감을 호소하며, 특히 점심 이후에 우울감이 심해진다고 말했다. 수면 문제와 식욕 변화도 경험하고 있으며, 자신을 실패자로 느끼는 경향이 있다. 내담자는 통증으로 인해 약을 복용하고 있으며, 이는 우울감에 영향을 미치고 있다. 또한, 일상적인 활동에 대한 흥미가 감소하고, 집중하기 어려운 상태다."
- [OK] rag_chunk:case_card:1024 — "내담자는 완벽하지 않으면 시작하지 않으려는 경향과 작은 실수에도 자책하는 경향이 있으며, 최근 탁구 시합에서 4등을 한 후 자책감이 심해졌다고 한다. 또한, 구글 드라이브 링크를 잘못 보낸 것에 대해서도 큰 자책감을 느끼고 있다. 이러한 증상들은 내담자의 우울 점수 9점과 관련이 있을 것으로 보인다."
- [OK] utterance:turn_0 — "약 먹은 지 6주 됐는데, 좀 나아진 것 같아서 진찰 받으러 왔어요."
- [OK] utterance:turn_1 — "약 먹은 지 6주 됐는데, 좀 나아진 것 같아서 진찰 받으러 왔어요."
- [OK] utterance:turn_4 — "가족 중에 정신과 치료를 받은 적 있는 분은 없어요. 아내가 걱정해줘서 병원에 왔지만, 지금은 힘든 건 있어도 스스로를 해치고 싶은 마음은 없어요."
- [OK] utterance:turn_5 — "술은 예전보다 많이 줄였어요. 아내가 신경 쓰니까 거의 안 마시고 있고, 카페인도 크게 안 먹고 있어요. 수면은 많이 나아졌고, 수면제도 필요 없어졌어요."
- [OK] utterance:turn_7 — "아내 외에 가까운 친구나 가족은 아직 크게 의지하진 않아요. 그래도 아내하고 산책하거나 주말에 외식하면서 조금씩 나아지고 있어요. 아직 완전하지는 않지만, 예전보다는 훨씬 나아졌어요."
- [OK] utterance:turn_9 — "가족 중에 정신과 치료를 받은 분은 없어요. 아내가 걱정해줘서 병원에 왔지만, 지금은 힘든 건 있어도 스스로를 해치고 싶은 마음은 없어요. 아내 덕분에 조금씩 나아지고 있어서, 예전보다는 훨씬 나아졌어요."
- **1 evidence item(s) STRIPPED by grounding cascade (ADR-014):**
  - [STRIPPED:rejected_quote_mismatch] utterance:turn_3 — "가족 중에 정신과 치료를 받은 적 있는 분은 없어요. 아내가 걱정해줘서 병원에 왔지만, 지금은 힘든 건 있어도 스스로를 해치고 싶은 마음은 없어요." (quote is not lexically supported by the utterance's actual text)
- recommended_surveys: ['PHQ-9']

## Department candidates

- 정신건강의학과 (domain_ref=depression) — 우울감, 피로감, 식욕 감소, 수면 개선, 자책감, 일상 활동 흥미 감소 등의 증상이 관찰되며, 항우울제 복용 후 6주간 점진적 호전을 보이고 있음. 현재 약물 치료 중이며, 추가 평가 및 치료 계획 수립을 위해 정신건강의학과 진료가 필요함.

## Summary

환자는 항우울제 복용 6주 후 피로감, 식욕 감소, 일상 활동 흥미 감소, 자책감 등의 우울 증상이 있으나 수면 개선 및 약물 복용으로 점진적 호전을 보이고 있음. 위험 요소(자살/자해 사고)는 없으며, 현재 약물 치료 중으로 정신건강의학과 진료를 통해 치료 효과 평가 및 추가 치료 계획 수립이 필요함.

## Whitelist audit

- counts: {'accepted': 9, 'rejected_unknown_source': 0, 'rejected_quote_mismatch': 1, 'rejected_unknown_source_type': 0, 'rejected_risk_lexicon': 0}
- orphan departments: 0

## Evidence provenance (enhancement #4)

- rag_chunk(case_card): 3
- rag_chunk(qa): 0
- rag_chunk(other/unrecognized prefix): 0
- utterance: 6

## Grounding cascade (ADR-014)

- candidates before -> after: 1 -> 1 (0 eliminated)
- eliminated domains: (none)
- evidence stripped (all reasons): 1
- evidence stripped (risk-lexicon, ADR-014 recurrence count): 0

## AI 예상질환 (experimental, non-diagnostic)

- mode: **rag_live**
- is_diagnostic: False
- disclaimer: 이 정보는 AI가 생성한 참고용 예상 질환 후보이며 의학적 진단이 아닙니다. 최종 진단과 치료 방향은 반드시 의료진의 판단에 따라 결정되어야 합니다.
- reason_summary: 5 disease candidate(s) derived from 9 retrieved chunk(s) via symptom-keyword match (path1, ADR-020). similarity_score is a RAG cosine-similarity signal between the retrieved chunk and the Stage-1 query — NOT a patient-to-disease similarity, and NOT a calibrated probability (two-hop proxy, RES-001 §2 step 9 / ADR-020 condition 3).
- 계절성 정동장애 (similarity_score=0.444) — qa:1092 — "..., 부작용 관리 방법)을 제안한다. 셋째, 환자가 치료 과정에서 느끼는 불안감을 줄이기 위해 심리적 지지를 제공하고, 필요시 심리치료를 병행한다...."
- 월경전 불쾌장애 (similarity_score=0.444) — qa:1092 — "..., 부작용 관리 방법)을 제안한다. 셋째, 환자가 치료 과정에서 느끼는 불안감을 줄이기 위해 심리적 지지를 제공하고, 필요시 심리치료를 병행한다...."
- 우울 삽화(우울증) (similarity_score=0.394) — qa:319 — "...후 6주째 우울감을 호소하며 내원하였다. 그녀는 최근 식욕이 감소하고, 불면증이 있으며, 아기에게 관심이 없고 자신이 아기를 잘 돌볼 수 없다는 생..."
- 소아·청소년 우울증 (similarity_score=0.394) — qa:319 — "...후 6주째 우울감을 호소하며 내원하였다. 그녀는 최근 식욕이 감소하고, 불면증이 있으며, 아기에게 관심이 없고 자신이 아기를 잘 돌볼 수 없다는 생..."
- 범불안장애 (similarity_score=0.391) — qa:1225 — "Q: 56세 여성이 6개월 전 남편을 사별한 뒤 우울감, 불안, 초조함을 느껴 병원에 내원하였다. 다른 병원에서 5일 전 escitalopr..."
