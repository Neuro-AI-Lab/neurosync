# Grounding Audit — VP-003

> Source: /home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/VP-003/VP-003_20260707_155149_conversation.json
> Turns: 12 | Patient utterances: 12
> Reported coverage: 0.6 (legacy) / 0.375 (grounded)
> Recomputed grounded coverage: 0.375

## Verdict counts

| Verdict | Count |
|---|---|
| grounded | 3 |
| negative_grounded | 0 |
| ungrounded | 0 |
| system_slot | 0 |

## Per-slot verdicts

| Slot | Verdict | Value | Reason |
|---|---|---|---|
| chief_complaint | **grounded** | 살고 싶지 않음, 매일 밤 자살 생각, 수면 장애(새벽 3시 기상 후 재입면 불가) | lexical evidence with polarity-consistent negation (negated patient statement supports the value) |
| history_of_present_illness | **grounded** | 매일 밤 자살 생각 지속, 새벽 3시 기상 후 재입면 불가, 천장만 보며 '살아서 뭐하나' 생각 반복 | lexical evidence in patient utterances |
| risk_assessment | **grounded** | 자살/자해 사고 표현 있음 — 환자 발화: "... 도움이 되나요? 뭘 해도 안 될 것 같은데."; 구체적 계획/의도 부인 — 환자 발화: ".... | populated by the safety probe protocol (probe_events) |
