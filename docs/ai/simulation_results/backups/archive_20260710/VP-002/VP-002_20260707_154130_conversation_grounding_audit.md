# Grounding Audit — VP-002

> Source: /home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/VP-002/VP-002_20260707_154130_conversation.json
> Turns: 9 | Patient utterances: 9
> Reported coverage: 0.6 (legacy) / 1.0 (grounded)
> Recomputed grounded coverage: 1.0

## Verdict counts

| Verdict | Count |
|---|---|
| grounded | 4 |
| negative_grounded | 4 |
| ungrounded | 0 |
| system_slot | 0 |

## Per-slot verdicts

| Slot | Verdict | Value | Reason |
|---|---|---|---|
| chief_complaint | **grounded** | 수면 개선 및 일상 회복 상태 확인 | lexical evidence in patient utterances |
| history_of_present_illness | **grounded** | 6주 전 에시탈로프람 10mg 복용 시작, 초기 위장 불편 있었으나 현재는 호전됨. 주말 기분 호전 및 우울감 감소, 에너지 증가로 퇴근 후 산... | lexical evidence in patient utterances |
| substance_use_history | **grounded** | 술 섭취 감소(아내 권유), 수면제 미사용, 카페인 보통 섭취, 비타민 복용(아내 제공) | lexical evidence with polarity-consistent negation (negated patient statement supports the value) |
| past_psychiatric_history | **negative_grounded** | 없음 | negative template with ask evidence (utterance 1 answered a question targeting 'past_psychiatric_history' with negation) |
| medical_history | **negative_grounded** | 없음 | negative template with ask evidence (utterance 2 answered a question targeting 'medical_history' with negation) |
| personal_social_history | **negative_grounded** | 없음 | negative template with ask evidence (utterance 3 answered a question targeting 'personal_social_history' with negation) |
| family_history | **negative_grounded** | 없음 | negative template with ask evidence (utterance 4 answered a question targeting 'family_history' with negation) |
| risk_assessment | **grounded** | 자살/자해 사고 탐색 질문에 부인 — 환자 발화: "아니요, 그런 생각은 전혀 없어요. 그런 생각은 전혀 없었어요." | populated by the safety probe protocol (probe_events) |
