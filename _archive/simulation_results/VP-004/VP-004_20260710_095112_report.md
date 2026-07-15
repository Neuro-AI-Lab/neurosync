# F2 Domain Inference Report — VP-004

## Repro metadata

| Field | Value |
|---|---|
| git HEAD | `c2acc90dc5388a0597cd80b23aa003ca799693ab` |
| model_used | solar-pro3-260323 |
| prompt_version | v2 |
| input_file | `/home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/VP-004/VP-004_20260710_095042_conversation.json` |
| input_sha256 | `e69dad8544d4b97213d76b060966e904800c1dca8ee11be69bf65d34720a399f` |
| mode | **rag** |
| latency_ms | 19368.7 |
| generated_at | 2026-07-10T09:51:02.348872 |
| finish_reason | stop |
| usage | {'prompt_tokens': 3774, 'completion_tokens': 1630, 'total_tokens': 5404} |

## Retrieval

- mode: rag
- chunks_returned: 12
- chunk_ids: ['case_card:209', 'case_card:1038', 'case_card:430', 'qa:1612', 'qa:1225', 'qa:225', 'case_card:940', 'case_card:664', 'case_card:1045', 'qa:1438', 'qa:1685', 'qa:1515']
- queries: ['약을 두 번 바꿨음에도 우울증이 호전되지 않고 오히려 악화되었으며, 공황 발작이 새로 발생하여 불안해하고 있음', "우울한 기분이 거의 매일 지속되며 이유 없이 눈물이 자주 나고, 수면 장애(잠 못 자고 악몽)로 인해 번역 작업 및 마감 기한을 놓치는 등 일상생활에 영향을 받고 있음. '이러다 정말 끝날 것 같다'는 생각이 들지만 죽고 싶은 것은 아니며, 공황 발작 시 '이러다 죽는 것 같다'는 공포를 경험함"]

## Domain candidates

### depression (confidence=0.6)
- [OK] rag_chunk:case_card:1038 — "내담자는 우울과 관련하여 몇 가지 주요 증상을 보이고 있다. 첫째, 내담자는 피곤함을 자주 느끼고 기운이 없다고 보고했으며, 이는 신체적 무기력감으로 나타날 수 있다. 둘째, 식욕이 줄어들었다고 언급하여 체중 변화나 식습관의 변화가 있을 가능성이 있다. 셋째, 내담자는 일상적인 활동 중에도 빨리 집에 가서 쉬고 싶다는 생각을 자주 한다고 하여, 일상생활에서의 흥미나 즐거움이 감소했음을 시사한다. 이러한 증상들은 내담자의 우울 상태를 반영하며, 이는 경미한 수준의 우울로 평가되었다. 내담자는 38년째 약을 복용 중이며, 약을 먹지 못했을 때 응급실에 실려간 경험이 있다. 또한, 약물 부작용으로 인해 신체적 불편함을 겪고 있으며, 경제적으로 아내에게 의존하는 상황에서 가장으로서의 부담감을 느끼고 있다. 과거 아버지와의 사건으로 인해 병이 시작되었으며, 이로 인해 가족 내에서의 갈등과 심리적 부담을 안고 있다. 이러한 요인들이 내담자의 우울과 불안에 영향을 미치고 있다."
- **3 evidence item(s) STRIPPED by grounding cascade (ADR-014):**
  - [STRIPPED:rejected_risk_lexicon] rag_chunk:case_card:209 — "내담자는 남편의 우울증과 공황장애, 자살 사고에 대한 진단서를 보고 충격을 받았으며, 남편이 자살 충동을 느낀다는 사실에 불안감을 느꼈다. 또한, 언니와의 대화에서 과거의 가족 상처가 다시 떠오르며 불안과 내적 갈등을 경험하고 있다. 내담자는 가족 내에서 중재자 역할을 하며, 이러한 역할이 자신에게 소모적임을 인식하고 있다. 시어머니와의 관계에서도 비슷한 중재자 역할을 하며, 시어머니의 전화가 올 때마다 불안감을 느끼고 있다. 내담자는 가족 내에서 중재자 역할을 하며, 가족 구성원 간의 갈등을 조정하고자 하는 책임감을 느끼고 있다. 이러한 역할은 내담자에게 정서적 부담을 주고 있으며, 가족의 기대와 요구에 부응해야 한다는 압박감을 느끼고 있다. 또한, 남편의 정신 건강 문제와 관련된 스트레스 사건, 시어머니와의 복잡한 관계, 언니와의 과거 상처에 대한 대화 등은 내담자의 불안과 스트레스를 가중시키고 있다. 내담자는 이러한 상황에서 대처전략 부족과 부정적 생활습관을 경험하고 있으며, 가족력과 과거정신질환의 영향도 받고 있다." (quote contains risk-class expression(s) (자살) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
  - [STRIPPED:rejected_risk_lexicon] utterance:turn_3 — "우울한 기분은 거의 모든 날 있어요. 이유 없이 눈물이 자주 나서... 거의 매일 그래요. 잠도 못 자고, 악몽도 자꾸 꾸고. 결국 번역도 못 하고, 마감도 놓치고... "이러다 정말 끝날 것 같기도 해요." 근데 죽고 싶은 건 아니고... 그냥 이 아픔이 멈추면 좋겠다 싶을 때가 있어요." (quote contains risk-class expression(s) (죽고 싶, 죽고싶) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
  - [STRIPPED:rejected_risk_lexicon] utterance:turn_4 — "가끔 아프면 이 느낌이 멈출까 싶을 때가 있어요. 근데 한 적은 없어요... "이러다 죽는 것 같다"는 공포는 있는데, 실제로 죽고 싶은 건 아니에요." (quote contains risk-class expression(s) (죽고 싶, 죽고싶) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
- recommended_surveys: ['PHQ-9', 'GAD-7']

### anxiety (confidence=0.5)
- [OK] rag_chunk:case_card:430 — "내담자는 자신의 상황에 대해 긍정적인 생각을 하려고 노력하고 있지만, 여전히 불안감과 우울함을 느끼고 있습니다. 특히, 모든 것이 잘될 것이라는 기대가 실망으로 이어질 수 있다는 걱정이 있다. 또한, 내담자는 기분이 가라앉고, 사는 게 허무하게 느껴지는 등의 증상을 경험하고 있다. 내담자는 과거의 큰 스트레스 사건 이후로 우울과 불안이 증가했으며, 이로 인해 타인과의 갈등이 빈번하게 발생했습니다. 또한, 내담자는 술과 담배를 통해 스트레스를 해소하려고 하지만, 이는 건강에 해로운 영향을 미치고 있습니다. 내담자는 자신의 부정적인 생각과 행동이 스트레스에 대한 반응임을 인식하고 있으며, 이를 개선하기 위해 노력하고 있습니다."
- [OK] utterance:turn_0 — "약을 바꿨는데도 안 낫고 오히려 더 나빠진 것 같아요. 오늘은 공황 발작이 너무 무서워요. 또 오면 어떡하지... 하는 생각이 계속 들어요."
- [OK] utterance:turn_1 — "약을 바꿨는데도 안 낫고 오히려 더 나빠진 것 같아요. 오늘은 공황 발작이 너무 무서워요. 또 오면 어떡하지... 하는 생각이 계속 들어요."
- [OK] utterance:turn_2 — "네, 진료는 받고 있어요. 이전에 우울증이라고 하셨는데, 약 두 번 바꿔도 안 낫고 오히려 더 나빠졌어요. 지금 공황 발작까지 생기면서 더 힘들어하고 있어요."
- [OK] utterance:turn_7 — "갑자기 심장이 막 뛰고 숨이 안 쉬어져요. 진짜 죽을 것 같아요. 지난번에 응급실 갈 정도로 심했어요. 지금도 또 오면 어떡하지... 하는 공포가 항상 있어요."
- **1 evidence item(s) STRIPPED by grounding cascade (ADR-014):**
  - [STRIPPED:rejected_risk_lexicon] rag_chunk:case_card:209 — "내담자는 남편의 우울증과 공황장애, 자살 사고에 대한 진단서를 보고 충격을 받았으며, 남편이 자살 충동을 느낀다는 사실에 불안감을 느꼈다. 또한, 언니와의 대화에서 과거의 가족 상처가 다시 떠오르며 불안과 내적 갈등을 경험하고 있다. 내담자는 가족 내에서 중재자 역할을 하며, 이러한 역할이 자신에게 소모적임을 인식하고 있다. 시어머니와의 관계에서도 비슷한 중재자 역할을 하며, 시어머니의 전화가 올 때마다 불안감을 느끼고 있다. 내담자는 가족 내에서 중재자 역할을 하며, 가족 구성원 간의 갈등을 조정하고자 하는 책임감을 느끼고 있다. 이러한 역할은 내담자에게 정서적 부담을 주고 있으며, 가족의 기대와 요구에 부응해야 한다는 압박감을 느끼고 있다. 또한, 남편의 정신 건강 문제와 관련된 스트레스 사건, 시어머니와의 복잡한 관계, 언니와의 과거 상처에 대한 대화 등은 내담자의 불안과 스트레스를 가중시키고 있다. 내담자는 이러한 상황에서 대처전략 부족과 부정적 생활습관을 경험하고 있으며, 가족력과 과거정신질환의 영향도 받고 있다." (quote contains risk-class expression(s) (자살) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
- recommended_surveys: ['GAD-7', 'PANAS']

## Department candidates

- 정신건강의학과 (domain_ref=depression) — 우울감, 눈물, 수면장애, 피로감, 흥미 상실 등 우울 증상과 함께 공황 발작, 지속적인 불안, 죽음에 대한 공포 등 불안 증상이 복합적으로 나타나며, 가족 내 중재자 역할과 과거 가족 상처로 인한 스트레스가 확인됨. 자살 사고는 언급되었으나 구체적 계획이나 의도는 부인됨.
- 정신건강의학과 (domain_ref=anxiety) — 공황 발작, 죽음에 대한 공포, 지속적인 불안, 스트레스 대처 전략 부족 등이 확인됨. 우울 증상과 함께 불안 증상이 두드러지며, 가족 관계와 과거 스트레스 사건이 불안 악화에 기여함.

## Summary

환자는 지속적인 우울감, 무기력, 수면장애, 식욕 감소, 눈물 등 우울 증상과 함께 공황 발작, 죽음에 대한 공포, 지속적인 불안, 가족 내 중재자 역할로 인한 정서적 부담 등 불안 증상을 호소하고 있습니다. 자살 사고는 언급되었으나 구체적 계획이나 의도는 부인되었으며, 가족력과 과거 스트레스 사건이 현재 증상에 영향을 미치고 있습니다.

## Whitelist audit

- counts: {'accepted': 6, 'rejected_unknown_source': 0, 'rejected_quote_mismatch': 0, 'rejected_unknown_source_type': 0, 'rejected_risk_lexicon': 4}
- orphan departments: 0

## Evidence provenance (enhancement #4)

- rag_chunk(case_card): 2
- rag_chunk(qa): 0
- rag_chunk(other/unrecognized prefix): 0
- utterance: 4

## Grounding cascade (ADR-014)

- candidates before -> after: 2 -> 2 (0 eliminated)
- eliminated domains: (none)
- evidence stripped (all reasons): 4
- evidence stripped (risk-lexicon, ADR-014 recurrence count): 4

## AI 예상질환 (experimental, non-diagnostic)

- mode: **rag_live**
- is_diagnostic: False
- disclaimer: 이 정보는 AI가 생성한 참고용 예상 질환 후보이며 의학적 진단이 아닙니다. 최종 진단과 치료 방향은 반드시 의료진의 판단에 따라 결정되어야 합니다.
- reason_summary: 5 disease candidate(s) derived from 12 retrieved chunk(s) via symptom-keyword match (path1, ADR-020). similarity_score is a RAG cosine-similarity signal between the retrieved chunk and the Stage-1 query — NOT a patient-to-disease similarity, and NOT a calibrated probability (two-hop proxy, RES-001 §2 step 9 / ADR-020 condition 3). 12 candidate vote(s) dropped by the risk-lexicon filter before ranking (VAL-011/ADR-020 condition 1).
- 계절성 정동장애 (similarity_score=0.493) — case_card:1045 — "...내담자는 자신의 선택에 대한 확신이 부족하며, 이는 삶의 방향성에 대한 불안으로 이어질 수 있다. 사회적 관계에서는 친구들과의 만남이 드물고, 주로..."
- 월경전 불쾌장애 (similarity_score=0.493) — case_card:1045 — "...내담자는 자신의 선택에 대한 확신이 부족하며, 이는 삶의 방향성에 대한 불안으로 이어질 수 있다. 사회적 관계에서는 친구들과의 만남이 드물고, 주로..."
- 범불안장애 (similarity_score=0.455) — qa:1612 — "...재흡수 억제제(SSRI) 치료를 시작했다. 치료 후 환자는 심한 불안과 초조를 호소하고 있다. 이러한 부작용을 줄이기 위해 가장 적절한 조치는 무엇..."
- 우울 삽화(우울증) (similarity_score=0.449) — qa:1515 — "Q: 28세 여성이 2주 전부터 지속된 불면을 주소로 내원하였다. 2주 전 남편이 갑작스럽게 교통사고로 사망한 뒤부..."
- 소아·청소년 우울증 (similarity_score=0.449) — qa:1515 — "Q: 28세 여성이 2주 전부터 지속된 불면을 주소로 내원하였다. 2주 전 남편이 갑작스럽게 교통사고로 사망한 뒤부..."
