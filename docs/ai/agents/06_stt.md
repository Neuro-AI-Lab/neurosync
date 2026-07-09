# Agent 06: STT Agent

> **상태 배너 — 미구현 (설계 스펙만 존재)**: 3-way 감사 기준, `apps/ai-server/src/agents/`에 `stt` 관련 에이전트 구현 파일이 존재하지 않는다. 이 문서는 설계 의도를 기술한 스펙이며, as-built 코드가 아니다.

## 개요

| 항목 | 내용 |
|---|---|
| **Agent ID** | `06` |
| **Agent Name** | `STTAgent` |
| **역할** | 음성-텍스트 변환 (Speech-to-Text) |
| **LLM Routing** | fixed (SKT A.X STT) |

## 목적

환자의 음성 입력을 텍스트로 변환한다. SKT A.X STT를 고정 벤더로 사용하며, streaming(WebSocket)과 batch(REST) 두 가지 모드를 지원한다. 변환된 transcript는 **사용자 확인/편집 전에 LLM으로 자동 전송되지 않는다** (FR-035). 음성 데이터는 **48시간 후 삭제**된다 (FR-036).

## 두 가지 모드

| 모드 | 프로토콜 | 용도 | 지연시간 |
|---|---|---|---|
| Streaming | WebSocket | 실시간 대화 중 음성 입력 | 실시간 (chunk 단위) |
| Batch | REST API | 업로드된 음성 파일 처리 | 파일 길이 의존 |

## 입력

| 필드 | 타입 | 설명 |
|---|---|---|
| `audio_data` | `binary \| stream` | 음성 데이터 (PCM 16-bit, 16kHz mono 권장) |
| `mode` | `enum` | `streaming`, `batch` |
| `language` | `string` | `ko-KR` (기본값) |
| `session_id` | `string` | 세션 ID |
| `patient_id` | `string` | 환자 식별자 |

## 출력

```json
{
  "session_id": "sess_20260618_001",
  "patient_id": "pt_12345",
  "mode": "streaming",
  "transcript": {
    "text": "두달 전부텉 우울하구 잠을 몬자요",
    "is_final": true,
    "segments": [
      { "text": "두달 전부텉", "start_ms": 0, "end_ms": 1200 },
      { "text": "우울하구", "start_ms": 1300, "end_ms": 1800 },
      { "text": "잠을 몬자요", "start_ms": 1900, "end_ms": 2600 }
    ]
  },
  "user_confirmed": false,
  "metadata": {
    "audio_duration_ms": 2600,
    "vendor": "skt_ax_stt",
    "audio_retention_expires_at": "2026-06-20T14:30:00+09:00",
    "timestamp": "2026-06-18T14:30:00+09:00"
  }
}
```

## 핵심 동작

1. **Streaming 모드**: WebSocket을 통해 audio chunk를 실시간으로 전송하고, 중간 결과(partial)와 최종 결과(final)를 수신한다.
2. **Batch 모드**: REST API로 음성 파일을 업로드하고, 처리 완료 후 결과를 수신한다.
3. **사용자 확인 필수 (FR-035)**: transcript는 반드시 사용자가 확인/편집한 후에만 다음 단계(LLM)로 전달된다. `user_confirmed: false` 상태에서는 LLM에 전송하지 않는다.
4. **음성 데이터 삭제 (FR-036)**: 음성 원본은 처리 완료 후 48시간 내에 삭제한다. `audio_retention_expires_at`에 삭제 예정 시각을 기록한다.
5. **Confidence score 미제공**: SKT A.X STT는 confidence score를 제공하지 않는다. 따라서 STT 결과의 신뢰도는 InputNormalizerAgent에서 간접적으로 판단한다.
6. **Segment 타임스탬프**: 각 발화 구간의 시작/종료 시각을 밀리초 단위로 기록한다.

## 안전 제약

1. **자동 LLM 전송 금지 (FR-035)**: STT transcript를 사용자 확인 없이 LLM으로 전송하지 않는다.
2. **음성 데이터 보존 제한 (FR-036)**: 48시간 초과 보존 금지. 만료 시 자동 삭제 스케줄러가 동작한다.
3. **개인정보 보호**: 음성 데이터는 암호화 저장하며, 환자 동의 범위 내에서만 처리한다.
4. **타 벤더 전송 금지**: 음성 데이터를 SKT A.X STT 이외의 서비스로 전송하지 않는다.

## 실패 시 대응

| 실패 유형 | 대응 |
|---|---|
| STT 서비스 장애 | "음성 인식이 일시적으로 불가합니다. 텍스트로 입력해주세요." 안내 |
| WebSocket 연결 끊김 | 자동 재연결 시도 (최대 3회). 실패 시 batch 모드로 전환 제안 |
| 음성 품질 저하 (노이즈) | 가능한 범위까지 변환 후 사용자에게 확인 요청. "음성이 잘 들리지 않았어요. 확인해주세요." |
| 48시간 삭제 실패 | 즉시 재시도 + 인시던트 로그. 수동 삭제 알림 발송 |
| Batch 처리 timeout | 사용자에게 "처리 중입니다" 안내 후 polling. 최대 대기 시간 초과 시 텍스트 입력 안내 |
