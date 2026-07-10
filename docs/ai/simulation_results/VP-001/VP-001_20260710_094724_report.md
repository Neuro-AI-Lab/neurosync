# F2 Domain Inference Report — VP-001

## Repro metadata

| Field | Value |
|---|---|
| git HEAD | `c2acc90dc5388a0597cd80b23aa003ca799693ab` |
| model_used | solar-pro3-260323 |
| prompt_version | v2 |
| input_file | `/home/neuroai/users/dhkim/aichampion/neurosync/docs/ai/simulation_results/VP-001/VP-001_20260710_094714_conversation.json` |
| input_sha256 | `51ba8ad42251b3fe495d234e39b5a8a7b56e3b429b831b925a4894bf19480831` |
| mode | **rag** |
| latency_ms | 6903.1 |
| generated_at | 2026-07-10T09:47:23.993990 |
| finish_reason | stop |
| usage | {'prompt_tokens': 3731, 'completion_tokens': 1097, 'total_tokens': 4828} |

## Retrieval

- mode: rag
- chunks_returned: 12
- chunk_ids: ['case_card:933', 'case_card:1215', 'case_card:924', 'qa:1262', 'qa:745', 'qa:488', 'case_card:382', 'case_card:280', 'case_card:564', 'qa:879', 'qa:654', 'qa:1537']
- queries: ['잠을 잘 못 자고 있어요. 누우면 머리가 복잡해지고, 한 시간 넘게 뒤척이다가 겨우 잠들어요. 새벽에도 두세 번 깨서 다시 잠드는 데 시간이 걸려요.', '최근 회사 프로젝트 데드라인으로 인해 스트레스를 많이 받았으며, 이로 인해 집중이 잘 안 되고 실수를 자주 하여 선임에게 지적을 받음. 이로 인해 수면 문제가 악화되어 잠들기 어려움, 새벽 각성, 수면 유지 곤란 등의 증상이 나타남.']

## Domain candidates

### sleep (confidence=0.9)
- [OK] rag_chunk:case_card:933 — "내담자는 수면 문제와 피로감을 주요 증상으로 호소하고 있다. 잠에 드는 데 어려움을 겪고 있으며, 심할 때는 새벽 4~5시까지 잠들지 못하는 경우가 있다. 이러한 수면 패턴의 변화로 인해 피로감이 지속되고 있으며, 이는 일상생활에 영향을 미치고 있다."
- [OK] rag_chunk:qa:745 — "35세 여성이 최근 3개월간 주 4일 이상 잠들기 어렵고, 한밤중에 자주 깨어나며, 아침에 일찍 깨는 증상을 호소합니다. 이러한 증상으로 인해 일상생활에 심각한 지장을 받고 있습니다. 이 환자의 상태를 가장 적절히 설명하는 진단명은 무엇인가요? A: 불면장애"
- [OK] rag_chunk:qa:488 — "40세 여성이 잠을 잘 이루지 못해 병원에 방문했다. 환자는 반년 전부터 일주일에 4~5번 쉽게 잠들지 못하고 자주 깬다고 호소한다. 수면다원검사 결과는 정상이었다. 환자에게 수면위생교육을 실시할 때 올바르게 전달해야 할 내용은 무엇인가? A: 4) 잠들기 전 1~2시간 내에 격렬한 운동은 피한다."
- [OK] utterance:turn_0 — "제가 요즘 잠을 잘 못 자고 있어요. 누우면 머리가 복잡해지고, 한 시간 넘게 뒤척이다가 겨우 잠들어요. 새벽에도 두세 번 깨서 다시 잠드는 데 시간이 걸려요."
- recommended_surveys: ['PSQI', 'ISI']

### anxiety (confidence=0.7)
- [OK] rag_chunk:case_card:382 — "내담자는 수면 문제를 겪고 있으며, 자다가 자주 깨고 잠들기가 어렵다고 보고했다. 또한 집중력 저하와 쉽게 피로감을 느끼는 증상도 나타났다. 내담자는 불안하거나 초조해서 가만히 있기 어렵다고 하며, 실수에 대한 사후 반추로 인해 고통감을 느끼고 있다고 설명했다."
- [OK] rag_chunk:qa:879 — "30세 남자가 최근 몇 달 동안 지속적인 불안감과 수면 장애를 호소하며 내원했다. 환자는 직장에서의 과도한 업무 스트레스를 받고 있으며, 최근 집중력 저하와 우울한 기분을 느끼고 있다고 한다."
- **1 evidence item(s) STRIPPED by grounding cascade (ADR-014):**
  - [STRIPPED:rejected_quote_mismatch] utterance:turn_8 — "아니요. 그런 생각은 전혀 없어요. 그냥 좀 힘들 뿐이지, 그 정도는 아니에요." (quote is not lexically supported by the utterance's actual text)
- recommended_surveys: ['GAD-7']

### depression (confidence=0.5)
- [OK] rag_chunk:case_card:280 — "내담자는 회사와 남자친구와의 관계에서 많은 스트레스를 받고 있으며, 이로 인해 우울한 기분과 피로감을 호소하고 있다. 회사에서는 업무량이 많고, 예상치 못한 일들이 발생할 때 스트레스를 많이 받는다고 한다."
- [OK] rag_chunk:qa:654 — "45세 남성이 최근 몇 달 동안 지속적인 불안과 함께 수면 장애를 호소하며 내원하였다. 그는 직장에서의 스트레스가 많고, 최근 가족 문제로 인해 불안감이 더욱 악화되었다고 한다. 이 환자의 증상과 관련된 가장 가능성 높은 정신과적 진단은 무엇인가? A: 범불안장애"
- [OK] utterance:turn_7 — "최근에 회사에서 큰 프로젝트 데드라인이 다가오면서 스트레스를 많이 받았어요. 그 이후로 집중이 잘 안 되고, 실수도 늘어서 선임한테 지적도 받았거든요."
- recommended_surveys: ['PHQ-9']

## Department candidates

- 정신건강의학과 (domain_ref=sleep) — 수면 문제(불면장애), 불안 증상, 우울감 및 피로감이 복합적으로 나타나며, 직장 스트레스와 관련된 정서적 어려움이 확인됨

## Summary

환자는 수면 문제(불면장애)와 피로감을 주요 증상으로 호소하며, 수면 위생 관련 교육 내용이 필요함. 불안 증상(가슴 답답함, 어깨와 목의 뻐근함)과 직장 스트레스, 집중력 저하가 동반되어 있으며, 우울감 및 식욕 저하도 일부 관찰됨. 근거 청크와 환자 발화를 종합하여 수면, 불안, 우울 영역의 후보가 도출됨.

## Whitelist audit

- counts: {'accepted': 9, 'rejected_unknown_source': 0, 'rejected_quote_mismatch': 1, 'rejected_unknown_source_type': 0, 'rejected_risk_lexicon': 0}
- orphan departments: 0

## Evidence provenance (enhancement #4)

- rag_chunk(case_card): 3
- rag_chunk(qa): 4
- rag_chunk(other/unrecognized prefix): 0
- utterance: 2

## Grounding cascade (ADR-014)

- candidates before -> after: 3 -> 3 (0 eliminated)
- eliminated domains: (none)
- evidence stripped (all reasons): 1
- evidence stripped (risk-lexicon, ADR-014 recurrence count): 0

## AI 예상질환 (experimental, non-diagnostic)

- mode: **rag_live**
- is_diagnostic: False
- disclaimer: 이 정보는 AI가 생성한 참고용 예상 질환 후보이며 의학적 진단이 아닙니다. 최종 진단과 치료 방향은 반드시 의료진의 판단에 따라 결정되어야 합니다.
- reason_summary: 5 disease candidate(s) derived from 12 retrieved chunk(s) via symptom-keyword match (path1, ADR-020). similarity_score is a RAG cosine-similarity signal between the retrieved chunk and the Stage-1 query — NOT a patient-to-disease similarity, and NOT a calibrated probability (two-hop proxy, RES-001 §2 step 9 / ADR-020 condition 3).
- 계절성 정동장애 (similarity_score=0.489) — case_card:382 — "...중력 저하와 쉽게 피로감을 느끼는 증상도 나타났다. 내담자는 불안하거나 초조해서 가만히 있기 어렵다고 하며, 실수에 대한 사후 반추로 인해 고통감을..."
- 범불안장애 (similarity_score=0.489) — case_card:382 — "...중력 저하와 쉽게 피로감을 느끼는 증상도 나타났다. 내담자는 불안하거나 초조해서 가만히 있기 어렵다고 하며, 실수에 대한 사후 반추로 인해 고통감을..."
- 우울 삽화(우울증) (similarity_score=0.48) — case_card:280 — "...족들과의 관계에서도 불편함을 느끼고 있으며, 과거의 잘못된 선택에 대한 죄책감과 후회가 지속적으로 나타나고 있다. 이러한 상황들은 내담자의 수면 문제..."
- 월경전 불쾌장애 (similarity_score=0.466) — case_card:564 — "내담자는 우울한 기분과 무가치감을 경험하고 있으며, 수면 문제와 피로감도 호소하고 있다. 특히, 잠들기..."
- 소아·청소년 우울증 (similarity_score=0.459) — qa:745 — "...다. 이 환자의 상태를 가장 적절히 설명하는 진단명은 무엇인가요?
A: 불면장애"
