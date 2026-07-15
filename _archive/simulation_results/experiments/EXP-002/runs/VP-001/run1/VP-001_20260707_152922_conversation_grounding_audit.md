# Grounding Audit — VP-001

> Source: /home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/VP-001/VP-001_20260707_152922_conversation.json
> Turns: 12 | Patient utterances: 12
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
| chief_complaint | **grounded** | 잠들기 어려움, 새벽 각성, 낮 시간 피로 및 집중력 저하 | lexical evidence in patient utterances |
| history_of_present_illness | **grounded** | 최근 대규모 프로젝트 마감 기한으로 인한 스트레스가 심해지면서 수면 문제가 악화됨. 잠들기 어려움, 수면 유지 어려움, 수면 부족으로 인한 집중... | lexical evidence in patient utterances |
| substance_use_history | **grounded** | 주 1-2회 맥주 한 캔 섭취, 카페인 섭취량 줄이려고 노력 중 | lexical evidence in patient utterances |
| personal_social_history | **grounded** | 직장 동료와 주 2회 통화, 어머니와 주 2회 통화 | lexical evidence in patient utterances |
| risk_assessment | **grounded** | 자살/자해 사고 탐색 질문에 부인 — 환자 발화: "아니요, 그런 생각은 없어요. 그냥 좀 힘들 뿐이지 그 정도는 아니에요." | populated by the safety probe protocol (probe_events) |
