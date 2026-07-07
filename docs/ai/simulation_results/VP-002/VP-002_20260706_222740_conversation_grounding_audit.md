# Grounding Audit — VP-002

> Source: docs/ai/simulation_results/VP-002/VP-002_20260706_222740_conversation.json
> Turns: 12 | Patient utterances: 9
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
| chief_complaint | **grounded** | 업무 스트레스와 의욕 저하로 인한 우울감 및 무기력 | lexical evidence in patient utterances |
| risk_assessment | **grounded** | 자살/자해 사고 탐색 질문에 부인 — 환자 발화: "아니요, 그런 생각은 전혀 없었어요. 아내가 많이 신경 써주고, 약도 꾸준히 먹다 보니까 마... | populated by the safety probe protocol (probe_events) |
| history_of_present_illness | **grounded** | 6주 전 정신건강의학과 첫 방문 후 약물 복용 시작. 초기에는 매일 아침 무기력, 점심 거르기, 수면 장애, 피로감, 수업 준비 어려움, 퇴근 ... | lexical evidence in patient utterances |
