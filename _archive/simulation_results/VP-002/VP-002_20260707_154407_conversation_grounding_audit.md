# Grounding Audit — VP-002

> Source: /home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/VP-002/VP-002_20260707_154407_conversation.json
> Turns: 12 | Patient utterances: 10
> Reported coverage: 0.6 (legacy) / 0.5 (grounded)
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
| history_of_present_illness | **grounded** | 약 복용 6주 경과, 수업 준비 가능, 주말 외식 가능, 수면 개선(잠들기 30분 이내, 6~7시간 수면), 간헐적 야간 각성, 식욕 정상화, ... | lexical evidence in patient utterances |
| risk_assessment | **grounded** | 자살/자해 사고 탐색 질문에 부인 — 환자 발화: "아니요, 그런 생각은 전혀 없었어요. 아내가 많이 도와줘서 그런지, 그런 생각은 한 번도 안... | populated by the safety probe protocol (probe_events) |
| chief_complaint | **grounded** | 약 복용 6주 후 증상 호전 확인 및 회복 경과 보고 | lexical evidence in patient utterances |
| personal_social_history | **grounded** | 중학교 국어 교사, 아내와 경기도 성남시 거주, 아내의 병원 동행 및 일상 지원 | lexical evidence in patient utterances |
