# Grounding Audit — VP-003

> Source: /home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/backups/invalidated_20260703/VP-003/VP-003_20260703_010918_conversation.json
> Turns: 0 | Patient utterances: 1
> Reported coverage: 0.8 (legacy) / None (grounded)
> Recomputed grounded coverage: 0.25

## Verdict counts

| Verdict | Count |
|---|---|
| grounded | 1 |
| negative_grounded | 1 |
| ungrounded | 7 |
| system_slot | 0 |

## Per-slot verdicts

| Slot | Verdict | Value | Reason |
|---|---|---|---|
| chief_complaint | **negative_grounded** | 살고 싶지 않음 | negative template with ask evidence (utterance 0 answered a question targeting 'chief_complaint' with negation) |
| history_of_present_illness | **grounded** | 매일 살고 싶지 않다는 생각이 지속됨 | lexical evidence in patient utterances |
| past_psychiatric_history | **ungrounded** | 정신과 진료 경험 없음 | negative template without ask evidence (slot was never asked and answered with negation) |
| medical_history | **ungrounded** | 진단받은 신체 질환 없음, 복용 약 없음 | negated value without polarity-consistent evidence (no negated patient statement supports it) |
| personal_social_history | **ungrounded** | 지지체계 정보 없음 | negative template without ask evidence (slot was never asked and answered with negation) |
| family_history | **ungrounded** | 가족 정신질환 이력 모름 | negative template without ask evidence (slot was never asked and answered with negation) |
| substance_use_history | **ungrounded** | 음주/약물 사용 정보 없음 | negative template without ask evidence (slot was never asked and answered with negation) |
| mental_status_exam | **ungrounded** | 말투 차분, 피로감 관찰됨 | observation slot without lexical evidence (excluded from grounded coverage by design) |
| risk_assessment | **ungrounded** | 자살/자해 사고 명시적 부인 | risk_assessment is never accepted from the extractor (populated only by the safety probe protocol) |
