# Grounding Audit — VP-004

> Source: /home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/backups/invalidated_20260703/VP-004/VP-004_20260703_010942_conversation.json
> Turns: 3 | Patient utterances: 3
> Reported coverage: 0.8 (legacy) / None (grounded)
> Recomputed grounded coverage: 0.25

## Verdict counts

| Verdict | Count |
|---|---|
| grounded | 2 |
| negative_grounded | 0 |
| ungrounded | 7 |
| system_slot | 0 |

## Per-slot verdicts

| Slot | Verdict | Value | Reason |
|---|---|---|---|
| chief_complaint | **grounded** | 약을 바꿔도 나아지지 않아 공황 재발에 대한 두려움과 불안이 지속됨 | lexical evidence in patient utterances |
| history_of_present_illness | **grounded** | Escitalopram 20mg과 Alprazolam 0.25mg 복용 중이나 증상 호전 없음. 2차례 약물 변경 후에도 공황 재발에 대한 두려... | lexical evidence with polarity-consistent negation (negated patient statement supports the value) |
| mental_status_exam | **ungrounded** | 말투: 불안하고 떨리는 목소리, 호흡 곤란에 대한 공포감 표현, 자해 생각은 있으나 실행하지 않음 | observation slot without lexical evidence (excluded from grounded coverage by design) |
| risk_assessment | **ungrounded** | 자살/자해 사고 명시적 부인, 공황 재발에 대한 극심한 불안 호소 | risk_assessment is never accepted from the extractor (populated only by the safety probe protocol) |
| past_psychiatric_history | **ungrounded** | 정신과 진료 경험 없음 | negative template without ask evidence (slot was never asked and answered with negation) |
| medical_history | **ungrounded** | 진단받은 신체 질환 없음, 복용 약: Escitalopram 20mg, Alprazolam 0.25mg | negated value without polarity-consistent evidence (no negated patient statement supports it) |
| personal_social_history | **ungrounded** | 지지체계 정보 없음 | negative template without ask evidence (slot was never asked and answered with negation) |
| family_history | **ungrounded** | 가족 정신질환 이력 모름 | negative template without ask evidence (slot was never asked and answered with negation) |
| substance_use_history | **ungrounded** | 음주/물질 사용 정보 없음 | negative template without ask evidence (slot was never asked and answered with negation) |
