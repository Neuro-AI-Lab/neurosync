# Grounding Audit — VP-001

> Source: /home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/VP-001/VP-001_20260707_153451_conversation.json
> Turns: 12 | Patient utterances: 12
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
| chief_complaint | **grounded** | 잠을 잘 못 자요. 한 시간은 뒤척이는 것 같아요. | lexical evidence in patient utterances |
| history_of_present_illness | **grounded** | 회사 대규모 프로젝트 데드라인이 다가오면서부터 증상이 시작됨. 최근 집중도 잘 안 되고 실수도 잦아 힘들어함. | lexical evidence in patient utterances |
| substance_use_history | **grounded** | 술은 주 1~2회 맥주 한 캔 정도 마셔요. 카페인은 커피를 많이 마시는 편이에요. 수면제나 진정제는 복용한 적 없어요. | lexical evidence with polarity-consistent negation (negated patient statement supports the value) |
| risk_assessment | **grounded** | 자살/자해 사고 탐색 질문에 부인 — 환자 발화: "아니요, 그런 생각은 없어요. 그냥 좀 힘들 뿐이지 그 정도는 아니에요." | populated by the safety probe protocol (probe_events) |
