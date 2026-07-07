# Grounding Audit — VP-001

> Source: /home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/backups/invalidated_20260703/VP-001/VP-001_20260703_010840_conversation.json
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
| chief_complaint | **grounded** | 잠을 잘 못 자는 게 제일 힘들다 | lexical evidence in patient utterances |
| history_of_present_illness | **grounded** | 누우면 머릿속이 시끄러워져서 한 시간 정도 뒤척이다가 겨우 잠들고, 새벽에도 두세 번 깨며 아침에 매우 피곤함 | lexical evidence in patient utterances |
| past_psychiatric_history | **ungrounded** | 정신과 진료 경험 없음 | negative template without ask evidence (slot was never asked and answered with negation) |
| medical_history | **ungrounded** | 진단받은 신체 질환 없음, 복용 약 없음 | negated value without polarity-consistent evidence (no negated patient statement supports it) |
| personal_social_history | **ungrounded** | 어머니와 주 2회 통화 | no lexical evidence in patient utterances |
| family_history | **ungrounded** | 어머니 과거 수면 문제 있었음 | no lexical evidence in patient utterances |
| substance_use_history | **ungrounded** | 음주 안 함 | negative template without ask evidence (slot was never asked and answered with negation) |
| mental_status_exam | **ungrounded** | 말투 차분, 피로감 관찰됨 | observation slot without lexical evidence (excluded from grounded coverage by design) |
| risk_assessment | **ungrounded** | 자살/자해 사고 명시적 부인 | risk_assessment is never accepted from the extractor (populated only by the safety probe protocol) |
