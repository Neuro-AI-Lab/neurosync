# F2 Domain Inference Report — VP-003

## Repro metadata

| Field | Value |
|---|---|
| git HEAD | `c2acc90dc5388a0597cd80b23aa003ca799693ab` |
| model_used | solar-pro3-260323 |
| prompt_version | v2 |
| input_file | `/home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/VP-003/VP-003_20260710_094933_conversation.json` |
| input_sha256 | `fb8c15edd92bf75c17da1260089c2f054c27cf7670c095f7b58841471c65d224` |
| mode | **rag** |
| latency_ms | 8497.7 |
| generated_at | 2026-07-10T09:49:42.669176 |
| finish_reason | stop |
| usage | {'prompt_tokens': 3452, 'completion_tokens': 1125, 'total_tokens': 4577} |

## Retrieval

- mode: rag
- chunks_returned: 10
- chunk_ids: ['case_card:847', 'case_card:563', 'case_card:940', 'qa:1685', 'qa:1268', 'qa:206', 'case_card:664', 'case_card:678', 'case_card:873', 'qa:256']
- queries: ['살고 싶지 않다, 죽고 싶다는 생각이 매일 계속 든다', '매일 죽고 싶다는 생각이 지속되며, 새벽 3시에 깨서 천장만 보는 수면 장애, 식욕 저하로 편의점 음식만 섭취, 매일 술 마심, 아무것도 하고 싶지 않은 무기력 상태']

## Domain candidates

### depression (confidence=0.9)
- [OK] utterance:turn_2 — "매일 들어요. 사, 그런 생각이 계속 들어요. 어떻게 해야 할지 모르겠고... 아무것도 하고 싶지 않아요."
- [OK] utterance:turn_4 — "네. 그냥 힘들어요."
- [OK] utterance:turn_5 — "매일 들어요. 사, 그런 생각이 계속 들어요. 어떻게 해야 할지 모르겠고... 아무것도 하고 싶지 않아요."
- [OK] utterance:turn_7 — "잠을 못 자요. 새벽 3시에 깨서... 그냥 천장만 봐요. 밥도 안 먹어요. 편의점 음식 하나 먹는 게 다예요. 술 안 마시면 못 버텨요. 매일 마셔요."
- [OK] utterance:turn_9 — "체중은 빠졌어요. 7킬로 줄었어요. 밥도 안 먹고... 주, 술 안 마시면 못 버텨요. 매일 마셔요. 잠도 못 자고... 새벽 3시에 깨서 천장만 봐요."
- **8 evidence item(s) STRIPPED by grounding cascade (ADR-014):**
  - [STRIPPED:rejected_risk_lexicon] rag_chunk:case_card:847 — "내담자는 지속적인 우울감을 경험하고 있으며, 이는 일상적인 감정으로 자리 잡고 있다고 표현했다. 우울한 감정은 자존감에 대한 공격이나 과거의 상처가 드러날 때, 그리고 일상생활이 감당하기 힘들 만큼 바쁠 때 촉발된다고 했다. 내담자는 우울한 감정이 늘 따라다니는 것 같다고 느끼며, 기분이 우울하고 일상 활동에 대한 흥미가 줄어드는 것을 자주 경험한다고 말했다. 또한, 주의 집중이 잘 안 되고 삶에 대한 희망이 가끔 사라진다고 느끼며, 죽고 싶다는 생각이 가끔 든다고 했다." (quote contains risk-class expression(s) (죽고 싶, 죽고싶) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
  - [STRIPPED:rejected_risk_lexicon] rag_chunk:case_card:563 — "내담자가 우울한 기분과 자살 생각을 표현하며, 통증으로 인해 일상생활에 어려움을 겪고 있음을 드러냈다. 내담자는 통증이 지속되며 진통제를 맞아도 효과가 없을 때가 있고, 이로 인해 식욕과 수면에도 문제가 발생한다고 말했다. 또한, 내담자는 지속적인 통증을 견뎌야 한다는 부담감을 느끼고 있으며, 가족들이 자신의 존재를 어떻게 생각할지에 대한 불안감도 드러냈다. 내담자가 세상이 위험하다고 느끼며, 전쟁과 같은 뉴스가 슬픔을 유발한다고 말했다." (quote contains risk-class expression(s) (자살) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
  - [STRIPPED:rejected_risk_lexicon] rag_chunk:case_card:664 — "내담자는 매사에 흥미나 즐거움이 없고, 기분이 가라앉거나 우울하다고 느끼며, 잠들기 어렵거나 자주 깨는 수면 문제를 겪고 있다. 또한, 피곤함을 자주 느끼고, 식욕이 줄어들어 거의 매일 조금씩 먹는 상태이다. 자해를 하려는 생각이 가끔 들기도 하며, 자신을 실패자로 여기거나 가족을 실망시켰다고 느끼는 경우가 있다." (quote contains risk-class expression(s) (자해) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
  - [STRIPPED:rejected_risk_lexicon] utterance:turn_0 — "살고 싶지 않다, 그런 생각이 계속 들어요. 어떻게 해야 할지 모르겠고... 아무것도 하고 싶지 않아요." (quote contains risk-class expression(s) (살고 싶지 않, 살고싶지않) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
  - [STRIPPED:rejected_risk_lexicon] utterance:turn_1 — "살고 싶지 않다, 그런 생각이 계속 들어요. 어떻게 해야 할지 모르겠고... 아무것도 하고 싶지 않아요." (quote contains risk-class expression(s) (살고 싶지 않, 살고싶지않) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
  - [STRIPPED:rejected_risk_lexicon] utterance:turn_3 — "생각해 본 적은 없어요. 그냥 사라지고 싶은 거예요. 죽으면 편할 것 같다는 생각만 들어요. 구체적으로는... 몰라요. 아무것도 하고 싶지 않아요." (quote contains risk-class expression(s) (사라지고 싶, 사라지고싶, 죽으면 편할, 죽으면편할) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
  - [STRIPPED:rejected_risk_lexicon] utterance:turn_6 — "생각해 본 적은 없어요. 그냥 사라지고 싶은 거예요. 죽으면 편할 것 같다는 생각만 들어요. 구체적으로는... 몰라요. 아무것도 하고 싶지 않아요." (quote contains risk-class expression(s) (사라지고 싶, 사라지고싶, 죽으면 편할, 죽으면편할) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
  - [STRIPPED:rejected_risk_lexicon] utterance:turn_8 — "형. 형이긴 한데... 연락 안 해요. 짐이 되기 싫어서요. 지금 상태로는 더 힘들게 만들고 싶지 않아서." (quote contains risk-class expression(s) (짐이 되, 짐이되) — suicidal-ideation/self-harm/death-directed content is never domain-confidence evidence (prompt rule 2, code-enforced per ADR-014); cite a non-risk symptom or 징후 instead)
- recommended_surveys: ['PHQ-9', 'GAD-7']

## Department candidates

- 정신건강의학과 (domain_ref=depression) — 지속적인 우울감, 죽고 싶다는 생각, 수면 장애, 식욕 저하, 무기력, 알코올 의존 등 주요우울장애와 일치하는 증상이 다수 확인됨

## Summary

환자는 지속적인 우울감, 죽고 싶다는 생각, 수면 장애, 식욕 저하, 무기력, 알코올 의존 등의 증상을 호소하고 있으며, 주요우울장애와 일치하는 임상 양상이 관찰됩니다.

## Whitelist audit

- counts: {'accepted': 5, 'rejected_unknown_source': 0, 'rejected_quote_mismatch': 0, 'rejected_unknown_source_type': 0, 'rejected_risk_lexicon': 8}
- orphan departments: 0

## Evidence provenance (enhancement #4)

- rag_chunk(case_card): 0
- rag_chunk(qa): 0
- rag_chunk(other/unrecognized prefix): 0
- utterance: 5

## Grounding cascade (ADR-014)

- candidates before -> after: 1 -> 1 (0 eliminated)
- eliminated domains: (none)
- evidence stripped (all reasons): 8
- evidence stripped (risk-lexicon, ADR-014 recurrence count): 8

## AI 예상질환 (experimental, non-diagnostic)

- mode: **rag_live**
- is_diagnostic: False
- disclaimer: 이 정보는 AI가 생성한 참고용 예상 질환 후보이며 의학적 진단이 아닙니다. 최종 진단과 치료 방향은 반드시 의료진의 판단에 따라 결정되어야 합니다.
- reason_summary: 0 of 10 retrieved chunk(s) yielded a disease candidate this run (no canonical symptom keyword matched, or every match was dropped by the risk-lexicon filter) — a legitimate 0-candidate outcome, not an error (RES-001 §2 step 7). similarity_score is a RAG cosine-similarity signal between the retrieved chunk and the Stage-1 query — NOT a patient-to-disease similarity, and NOT a calibrated probability (two-hop proxy, RES-001 §2 step 9 / ADR-020 condition 3). 16 candidate vote(s) dropped by the risk-lexicon filter before ranking (VAL-011/ADR-020 condition 1).
- (no candidates)
