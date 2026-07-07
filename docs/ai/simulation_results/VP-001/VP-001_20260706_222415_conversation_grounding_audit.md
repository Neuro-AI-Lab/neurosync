# Grounding Audit — VP-001

> Source: docs/ai/simulation_results/VP-001/VP-001_20260706_222415_conversation.json
> Turns: 12 | Patient utterances: 12
> Reported coverage: 0.4 (legacy) / 0.5 (grounded)
> Recomputed grounded coverage: 0.5

## Verdict counts

| Verdict | Count |
|---|---|
| grounded | 4 |
| negative_grounded | 0 |
| ungrounded | 0 |
| system_slot | 0 |

## Per-slot verdicts

| Slot | Verdict | Value | Reason |
|---|---|---|---|
| chief_complaint | **grounded** | 잠을 잘 못 자고 누우면 생각이 많아져 한 시간 뒤척이며 새벽에도 두세 번 깨는 수면 문제 | lexical evidence in patient utterances |
| history_of_present_illness | **grounded** | 프로젝트 마감이 코앞인 상황에서 수면 시작 어려움, 새벽 각성, 피로감, 가슴 답답함, 어깨 뻐근함 등의 신체 증상 동반 | lexical evidence in patient utterances |
| substance_use_history | **grounded** | 주 1-2회 맥주 한 캔 섭취 (잠들기 전 아님) | lexical evidence with polarity-consistent negation (negated patient statement supports the value) |
| personal_social_history | **grounded** | 회사 동료 2명과 주 1-2회 맥주 한 캔 섭취, 어머니와 주 2-3회 통화 | lexical evidence in patient utterances |
