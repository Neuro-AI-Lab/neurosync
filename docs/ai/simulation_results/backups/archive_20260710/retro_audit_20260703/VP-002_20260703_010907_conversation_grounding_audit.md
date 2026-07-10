# Grounding Audit — VP-002

> Source: /home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/backups/invalidated_20260703/VP-002/VP-002_20260703_010907_conversation.json
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
| chief_complaint | **grounded** | 새로운 일을 시작하거나 집중해야 할 때 머릿속이 하얘지고 계획 세우는 데 어려움 | lexical evidence in patient utterances |
| history_of_present_illness | **grounded** | 수업 준비는 가능해졌으나 수업 외적인 일 시작 시 막막함과 집중력 저하 지속 | lexical evidence in patient utterances |
| past_psychiatric_history | **ungrounded** | 정신과 진료 경험 없음 | negative template without ask evidence (slot was never asked and answered with negation) |
| medical_history | **ungrounded** | 진단받은 신체 질환 없음, 복용 약 없음 | negated value without polarity-consistent evidence (no negated patient statement supports it) |
| personal_social_history | **ungrounded** | 아내와 함께 생활하며 산책 및 계획 수립 시 도움 받음 | no lexical evidence in patient utterances |
| family_history | **ungrounded** | 모름 | negative template without ask evidence (slot was never asked and answered with negation) |
| substance_use_history | **ungrounded** | 술 거의 안 먹음 | negative template without ask evidence (slot was never asked and answered with negation) |
| mental_status_exam | **ungrounded** | 차분한 말투, 피로감 관찰됨 | observation slot without lexical evidence (excluded from grounded coverage by design) |
| risk_assessment | **ungrounded** | 자살/자해 사고 명시적 부인 | risk_assessment is never accepted from the extractor (populated only by the safety probe protocol) |
