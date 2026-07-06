# Grounding Audit — VP-004

> Source: docs/ai/simulation_results/VP-004/VP-004_20260706_224114_conversation.json
> Turns: 12 | Patient utterances: 11
> Reported coverage: 0.6 (legacy) / 0.625 (grounded)
> Recomputed grounded coverage: 0.625

## Verdict counts

| Verdict | Count |
|---|---|
| grounded | 5 |
| negative_grounded | 0 |
| ungrounded | 0 |
| system_slot | 0 |

## Per-slot verdicts

| Slot | Verdict | Value | Reason |
|---|---|---|---|
| chief_complaint | **grounded** | 약을 바꿨는데도 증상이 개선되지 않고 오히려 악화됨. 하루 종일 지속되는 우울감과 이유 없는 눈물, 공황 발작의 빈도와 재발에 대한 두려움 | lexical evidence in patient utterances |
| risk_assessment | **grounded** | 자살/자해 사고 표현 있음 — 환자 발화: "가끔 안 먹을 때 있어요. 먹어도 별로 달라지는 게 없으니까… 카페인은 커피 두 잔 정도 마셔요. ... | populated by the safety probe protocol (probe_events) |
| history_of_present_illness | **grounded** | 약을 변경했으나 효과가 없고 오히려 증상이 악화됨. 하루 종일 지속되는 우울감과 이유 없는 눈물, 공황 발작이 자주 발생하며 재발에 대한 공포를... | lexical evidence in patient utterances |
| substance_use_history | **grounded** | 가끔 식사를 거름. 카페인은 커피 두 잔 정도 섭취. 약은 가끔 복용하지 않음 | lexical evidence with polarity-consistent negation (negated patient statement supports the value) |
| medical_history | **grounded** | 두통, 근육통, 손 떨림 | lexical evidence in patient utterances |
