# `apps/mobile` — 환자 모바일 앱

> **Owner**: Platform 팀 (단독)
> **언어/프레임워크**: React Native + Expo (또는 RN CLI)
> **PRD**: 마스터 PRD §5.4 Pages (mobile 행), §5.5 Flow A·D

## 책임 범위

- 회원가입/로그인/동의 UI (FR-001, FR-026, FR-027, FR-034)
- 홈 화면 (FR-003)
- 사전 문진 채팅 UI (WebSocket 클라이언트) (FR-004)
- PHQ-9/GAD-7 UI (FR-006, FR-007)
- 문서 업로드 UI (카메라/갤러리/PDF) (FR-008)
- **음성 입력 UI (Push-to-Talk, 마이크 권한, 녹음 파형, 편집·전송)** (FR-033, FR-035, FR-037)
- 위험 신호 대응 화면 `/emergency` (FR-011)
- 병원 찾기 (FR-012)
- 리포트 상태 (FR-013)
- 알림 수신·표시 (FR-014, FR-024)

## AI는 호출하지 않음
모든 호출은 Platform API(`apps/api`) 경유. AI 서버에 직접 접근 금지.

## 디렉토리 구조 (예정)

```
apps/mobile/
├── package.json
├── app.json
├── src/
│   ├── screens/
│   ├── features/
│   │   ├── auth/
│   │   ├── intake-chat/
│   │   ├── intake-voice/   # STT UI
│   │   ├── intake-phq9/
│   │   ├── intake-gad7/
│   │   ├── documents/
│   │   ├── emergency/
│   │   └── hospitals/
│   ├── api/                # Platform API 클라이언트
│   ├── ws/                 # WebSocket 채팅
│   └── shared/
└── ios/ android/
```
