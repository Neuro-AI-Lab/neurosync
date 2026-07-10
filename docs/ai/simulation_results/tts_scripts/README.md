# 환자 발화 TTS 스크립트

각 페르소나 대화 시뮬레이션에서 **환자(patient)가 발화한 문장만** 추출한 TTS-ready 스크립트.

## 목적

- **STT 파이프라인 테스트용 오디오 파일 생성** — 실제 음성 입력 시뮬레이션
- F1 통합 검증 (음성 → STT → InputNormalizer → Safety → Dialogue)
- Safety Classifier의 음성 경로 recall 검증 (VP-003/004의 자살/자해 발화 골드 셋)

## 파일 목록

| 페르소나 | 파일 | 이름 | 프로파일 | 발화 수 | TTS 문장 |
|---|---|---|---|---|---|
| VP-001 | [VP-001_patient_tts.md](./VP-001_patient_tts.md) | 김서연 | 28F · 초진 경증 · 불안+불면 | 7 | 17 |
| VP-002 | [VP-002_patient_tts.md](./VP-002_patient_tts.md) | 이준호 | 35M · 재진 경증 · 치료 중 | 10 | 35 |
| VP-003 | [VP-003_patient_tts.md](./VP-003_patient_tts.md) | 박민수 | 42M · 초진 중증 · ⚠️ 자살 사고 | 2 | 6 |
| VP-004 | [VP-004_patient_tts.md](./VP-004_patient_tts.md) | 최하은 | 29F · 재진 중증 · ⚠️ 공황+자살 | 3 | 7 |

**총 22개 발화 · 65개 TTS 문장**

## 통합 JSON (프로그램용)

`patient_tts_index.json` — 배치 TTS 처리용. 각 발화에 safety 판정 결과 태그 포함.

```python
import json
idx = json.load(open("docs/ai/simulation_results/tts_scripts/patient_tts_index.json"))
for vp_id, p in idx["personas"].items():
    for u in p["utterances"]:
        for i, sentence in enumerate(u["sentences"], 1):
            audio_id = f"{vp_id}_u{u['utterance_index']}_s{i}"
            # tts_call(sentence, voice=..., out=f"audio/{audio_id}.wav")
```

## 화자 프로파일 매핑 (권장)

| 페르소나 | 성별/나이 | 권장 화자 톤 |
|---|---|---|
| VP-001 김서연 | 여성 28세 | 20대 여성 · 지친 톤 · 차분 |
| VP-002 이준호 | 남성 35세 | 30대 남성 · 개선 중 · 안정 |
| VP-003 박민수 | 남성 42세 | 40대 남성 · 저음 · 우울 톤 |
| VP-004 최하은 | 여성 29세 | 20대 여성 · 불안 · 떨림 |

## ⚠️ Safety-critical 발화 처리

**VP-003, VP-004의 발화는 자살/자해 표현을 포함**합니다. 오디오 생성 시:

- 파일명에 `_CRITICAL_` 접두어 또는 명확한 라벨링
- Safety Classifier recall 골드 셋으로 사용 (STT 정확도 저하로 안전 신호 놓치지 않는지 검증)
- 데모/공개 자료에 사용 시 취급 주의 (자살 예방 가이드라인 준수)

## 문장 분할 규칙

- 종결 부호: `.` `!` `?` (한국어 종결 어미 뒤)
- **`~`은 종결 아님** — 범위 표현 유지 (예: "4~5시간")
- **`...` / `…`은 말줄임** — 앞 문장에 붙여 유지
- 6자 미만 파편은 이전 문장에 병합 (예: "안." → 앞 문장 뒤 붙임)
- 문단 개행은 문장 경계로 인정

## 다음 단계 (TTS 생성 시)

1. **벤더 선정**: Naver Clova / VARCO Voice / Google Cloud TTS / Azure
   - **VARCO Voice 권장** — 대회 무제한 특전 (`docs/ai/api/00_overview.md` §4)
2. **화자별 배정**: 위 매핑 표대로 각 VP에 다른 목소리
3. **감정 톤 지시**: 
   - CTRS 5-4 (안전): neutral, calm
   - CTRS 3 (medium): concerned, slower pace
   - CTRS 1-2 (crisis): heavy, low volume, pauses
4. **오디오 저장**: `docs/ai/simulation_results/{VP-ID}/audio/{VP-ID}_u{N}_s{M}.wav`
5. **STT 회귀 셋으로 등록**: `tests/simulation/audio/` 심볼릭 링크
