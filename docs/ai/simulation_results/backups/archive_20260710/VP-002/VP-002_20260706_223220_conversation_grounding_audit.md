# Grounding Audit — VP-002

> Source: docs/ai/simulation_results/VP-002/VP-002_20260706_223220_conversation.json
> Turns: 12 | Patient utterances: 12
> Reported coverage: 0.6 (legacy) / 0.875 (grounded)
> Recomputed grounded coverage: 0.875

## Verdict counts

| Verdict | Count |
|---|---|
| grounded | 6 |
| negative_grounded | 1 |
| ungrounded | 0 |
| system_slot | 0 |

## Per-slot verdicts

| Slot | Verdict | Value | Reason |
|---|---|---|---|
| history_of_present_illness | **grounded** | 6주 전 정신건강의학과 첫 진료 후 에스시탈로프람 복용 시작, 초기 위장 부작용 있었으나 현재는 호전됨. 수업 준비 능력 회복, 기분 개선, 수... | lexical evidence in patient utterances |
| risk_assessment | **grounded** | 자살/자해 사고 탐색 질문에 부인 — 환자 발화: "자해나 타인에게 해를 끼치고 싶은 생각은 전혀 없어요. 지금은 그런 생각보다는, 다시 일상으... | populated by the safety probe protocol (probe_events) |
| chief_complaint | **grounded** | 약 복용 6주 후 증상 호전 확인 | lexical evidence in patient utterances |
| medical_history | **negative_grounded** | 특별한 신체질환 없음 | negative template with ask evidence (utterance 2 answered a question targeting 'medical_history' with negation) |
| substance_use_history | **grounded** | 술 거의 안 마심, 카페인은 평소대로 섭취하나 저녁에 주의함, 수면제/진정제 복용 없음 | lexical evidence with polarity-consistent negation (negated patient statement supports the value) |
| personal_social_history | **grounded** | 아내 지원, 동료와 점심 모임 재개 | lexical evidence in patient utterances |
| past_psychiatric_history | **grounded** | 처음 정신건강의학과 진료, 경도 우울 진단 | lexical evidence in patient utterances |
