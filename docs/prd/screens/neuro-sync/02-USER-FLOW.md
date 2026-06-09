# Neuro-Sync User Flow — Mobile

> **Platform**: Mobile (React Native)
> **Source**: PRD §5.5 (Flow A/B/C/D). 본 문서는 모바일 환자 관점에서 분기 조건을 확장.
> **Generated**: 2026-06-06

본 문서는 PRD §5.5의 Flow A (환자 사전 문진), Flow C (안전 파이프라인), Flow D (STT 입력)를 모바일 환자 관점에서 확장한다. Flow B (의료진)는 웹 전용이므로 본 문서에서 제외.

---

## Flow A: 환자 사전 문진 (Mobile 확장)

### A.1 전체 시퀀스

```mermaid
flowchart TD
  Start([앱 진입]) --> CheckSeen{온보딩 본 적?}
  CheckSeen -->|No| Onboarding["/onboarding\n1/4 → 4/4"]
  CheckSeen -->|Yes| CheckAuth{accessToken 유효?}
  Onboarding -->|완료| CheckAuth

  CheckAuth -->|No| Login["/login"]
  CheckAuth -->|Yes| Home["/home"]

  Login -->|로그인 성공| RoleCheck{role 검증}
  RoleCheck -->|patient| Home
  RoleCheck -->|clinician/admin| RoleBlock["안내 모달:\n본 앱은 환자용입니다"]
  RoleBlock --> Login

  Login -->|회원가입 링크| RegStep1["/register Step1\n4개 동의"]
  RegStep1 -->|동의 완료| RegStep2["/register Step2\n프로필 입력"]
  RegStep2 -->|연령 확인| AgeCheck{만 14세 미만?}
  AgeCheck -->|Yes Phase 2| GuardianFlow["법정대리인 동의 분기\nFR-027 (Demo 미포함)"]
  AgeCheck -->|No| RegStep3["/register Step3\n음성 동의 옵션 FR-034"]
  RegStep3 -->|가입 완료| Home

  Home -->|문진 시작 CTA| ResumeCheck{진행 중 세션?}
  ResumeCheck -->|Yes| ResumeModal["이어하기? 새로 시작?"]
  ResumeCheck -->|No| NewSession[POST /sessions]
  ResumeModal -->|이어하기| Chat
  ResumeModal -->|새로 시작| NewSession
  NewSession --> Chat["/intake/chat\nAI 대화"]

  Chat -->|일반 발화 →| Chat
  Chat -->|위험 발화 감지| Emergency["/emergency Modal"]
  Chat -->|진행률 70%+ → 다음| PHQ9["/intake/phq9"]
  Chat -->|뒤로 + 저장| Home

  PHQ9 -->|9문항 완료| GAD7["/intake/gad7"]
  GAD7 -->|7문항 완료| Docs["/intake/documents\nDemo: Stub"]
  Docs -->|업로드 or 건너뛰기| Submit["/intake/submit\n최종 확인"]

  Submit -->|제출| SubmitAPI[POST /sessions/:id/submit]
  SubmitAPI -->|202 Accepted| Status["/report/status\n생성 중 polling"]
  Status -->|completed| Done["완료 카드\n홈으로"]
  Done --> Home

  Emergency -->|"전화/안전질문 응답"| EmergencyDone["복귀 안내"]
  EmergencyDone --> Home
```

### A.2 분기 조건 상세

| 분기 | 조건 | 결과 |
|------|------|------|
| 온보딩 표시 | `AsyncStorage.hasSeenOnboarding !== 'true'` | `/onboarding` 첫 진입 |
| 자동 로그인 | `accessToken` 존재 + JWT exp > 현재 | `/home` 직진. 만료 시 `refreshToken`으로 갱신 시도 |
| Role 차단 | `user.role !== 'patient'` | 모달 안내 + 로그아웃 |
| 법정대리인 동의 (Phase 2) | `currentYear - birthYear < 14` | `/register` Step2에서 보호자 본인인증 단계 추가 (Demo 미포함) |
| 문진 이어하기 | `sessions.status === 'in_progress'` 1건 이상 | 모달 `이어하기 / 새로 시작 / 취소` |
| Chat → PHQ-9 이동 | `progress >= 0.7` AND AI가 `next:phq9` 시그널 송신 | 자동 페이지 전환 (사용자 확인 후) |
| Documents 건너뛰기 | Demo 시 기본 활성 / Phase 2는 선택적 | Submit으로 직행 |
| 위험 감지 | WebSocket `risk:detected` (level ∈ {medium, high, critical}) | `/emergency` Modal 즉시 push (Chat 상태는 background 저장) |

### A.3 모바일 특수 분기

| 상황 | 처리 |
|------|------|
| 앱 백그라운드 → 포그라운드 (3분 이상 idle) | accessToken 유효성 재확인. 만료 시 silent refresh, 실패 시 `/login` |
| 네트워크 끊김 (NetInfo offline) | 상단 빨간 배너 + 입력 disabled. 재연결 시 자동 재시도 |
| 푸시 알림 탭 (Phase 2) | 딥링크로 해당 화면 직진. 미로그인 상태면 `/login` 후 큐잉 |
| 마이크 권한 거부 (FR-037) | `/intake/chat`에서 마이크 버튼 비활성화 + "설정에서 권한 허용" 토스트 + 키보드 폴백 |
| 위험 감지 중 백그라운드 진입 | 로컬 알림 "지금 도움이 필요하시면 1393으로 전화하세요" — Phase 2 |

---

## Flow C: 안전 파이프라인 (Safety) — Mobile 관점

PRD §5.5 Flow C를 모바일 클라이언트의 상태 전이 관점에서 재서술.

```mermaid
flowchart TD
  UserTyping["환자가 메시지 작성"] --> Send[전송 버튼 또는 Enter]
  Send --> Optimistic["UI: 메시지 말풍선 즉시 표시\n(optimistic update)"]
  Optimistic --> WSSend["WS: user:message + idempotencyKey"]
  WSSend --> WaitParallel{서버 병렬 검사}

  WaitParallel -->|ai:token 스트리밍| AIResponse["AI 답변 말풍선\n토큰 단위 append"]
  AIResponse -->|ai:complete| ProgressUpdate["진행률 헤더 갱신"]

  WaitParallel -->|risk:detected 수신| RiskHandle["Reducer: chat.status = 'paused'\n입력창 disabled"]
  RiskHandle --> Vibrate["햅틱 피드백 (heavy)"]
  Vibrate --> NavReplace["Navigation.replace('/emergency')\n(뒤로 가기 차단)"]
  NavReplace --> EmergencyScreen["/emergency 화면"]

  EmergencyScreen --> Hotlines["3개 핫라인 버튼:\n1393 / 119 / 1577-0199"]
  Hotlines -->|탭| TelLink["Linking.openURL('tel:1393')"]
  EmergencyScreen --> SafetyQ["안전 확인 질문:\n'지금 혼자 있나요?'"]
  SafetyQ -->|예/아니오| RiskLogUpdate["PATCH risk_event\nstatus='acknowledged'"]
  SafetyQ --> ContactInvite["비상 연락처 전화 안내\n(회원가입 시 등록)"]

  EmergencyScreen --> Return["'안전한 곳에 있어요' 버튼"]
  Return --> ResumeOrHome{문진 재개?}
  ResumeOrHome -->|Yes| ChatResume["/intake/chat 재진입\n위험 감지 직후 컨텍스트 표시"]
  ResumeOrHome -->|No| HomeReturn["/home"]
```

### C.1 클라이언트 상태 전이

```
chat.status: 'idle' → 'sending' → 'streaming' → 'idle'
                              ↘  'paused' → '/emergency' modal push → resume
```

| 이벤트 | UI 효과 | 사이드이펙트 |
|--------|--------|-------------|
| `risk:detected` (level=medium) | 노란 배너 "안전 확인이 필요해요" + 대화 계속 | risk_event log (status=detected) |
| `risk:detected` (level=high) | 즉시 `/emergency` modal push | risk_event log + (Phase 2) 비상 연락처 SMS |
| `risk:detected` (level=critical) | 즉시 `/emergency` + 1393 자동 다이얼 prompt | risk_event log + (Phase 2) 의료진 대시보드 알림 |

### C.2 백 버튼 / 제스처 차단

iOS 스와이프 백 제스처 + Android 하드웨어 백 버튼은 `/emergency` 노출 중 차단한다.
- iOS: `navigation.setOptions({ gestureEnabled: false })`
- Android: `useFocusEffect` + `BackHandler.addEventListener('hardwareBackPress', () => true)`

명시적 종료 경로는 "안전한 곳에 있어요" 버튼 1개로만 제공.

---

## Flow D: STT 입력 (Push-to-Talk) — Mobile 상세

PRD §5.5 Flow D를 모바일 RN 구현 관점에서 확장.

```mermaid
flowchart TD
  Idle["입력창 idle\n마이크 버튼 노출"] --> LongPress{마이크 버튼\n길게 누름}

  LongPress --> ConsentGate{음성 동의\nFR-034 옵트인?}
  ConsentGate -->|No| ConsentSheet["바텀시트:\n'음성 입력을 위해\n동의가 필요합니다'\n[설정으로 이동]"]
  ConsentGate -->|Yes| PermGate{앱 마이크 권한}

  PermGate -->|denied| PermSheet["바텀시트:\n'마이크 권한이 필요합니다'\n[설정 열기] [키보드로 입력]"]
  PermGate -->|granted| StartRec["recording 상태 진입"]

  StartRec --> RecordingUI["UI:\n- 파형 시각화 (24ch FFT)\n- 경과 시간 mm:ss\n- 빨간 펄스 인디케이터\n- 취소(드래그 업) 힌트"]
  RecordingUI --> ListenRelease{버튼 떼기 or\n위로 드래그}

  ListenRelease -->|위로 드래그 취소| Cancel["녹음 폐기\n입력창 idle 복귀"]
  ListenRelease -->|버튼 떼기| StopRec["녹음 종료\nOpus 16kHz encode"]
  ListenRelease -->|30초 초과| AutoStop["자동 종료 + 토스트:\n'녹음은 최대 30초입니다'"]
  AutoStop --> StopRec

  StopRec --> Transcribing["transcribing 상태\n버튼 스피너 + '변환 중...'\n입력창 disabled"]
  Transcribing --> Upload["POST /api/v1/stt/transcribe\nmultipart"]

  Upload -->|"200 OK\n신뢰도 >= 0.6"| FillInput["입력창에 텍스트 자동 채움\n(편집 가능, 자동 송신 X)\nFR-035"]
  Upload -->|"422 STT_LOW_CONFIDENCE\nor 신뢰도 < 0.6"| RetryUI["인라인 안내:\n'잘 들리지 않았어요\n다시 말씀해 주세요'\nFR-037"]
  Upload -->|"503 STT_UNAVAILABLE\n5xx / timeout 5s"| FallbackUI["키보드 폴백:\n입력창 포커스 + 안내 토스트\nFR-037"]
  Upload -->|"403 VOICE_CONSENT_REQUIRED"| ConsentSheet

  FillInput --> UserEdit["사용자 검토/수정"]
  UserEdit -->|"'전송' 버튼 탭"| SendMsg["WS user:message + idempotencyKey\n(Safety/LLM 파이프라인 진입)"]
  UserEdit -->|"입력창 비우기"| Idle
  RetryUI -->|재시도 마이크 탭| StartRec
  FallbackUI --> Idle
```

### D.1 상태 머신 (Recording State)

```
'idle' ─[long press]→ 'requesting-permission' ─[granted]→ 'recording'
                                              └[denied]→ 'idle' + sheet

'recording' ─[release]→ 'encoding' ─[done]→ 'transcribing'
            ├[drag-up cancel]→ 'idle'
            └[30s auto-stop]→ 'encoding'

'transcribing' ─[200 OK conf>=0.6]→ 'filled' (input editable)
              ├[low confidence]→ 'retry-prompt'
              ├[5xx/timeout]→ 'fallback-text' (키보드)
              └[403 consent]→ 'consent-required'

'filled' ─[send tap]→ 'idle' (메시지 큐 진입)
        └[clear]→ 'idle'
```

### D.2 모바일 UX 디테일

| 요소 | 사양 |
|------|------|
| 마이크 버튼 hit area | 최소 48×48 dp (a11y), 시각 크기 56dp 권장 |
| Long press threshold | 200ms (즉각 반응) |
| 햅틱 피드백 | 녹음 시작: light, 종료: medium, 위험 감지: heavy |
| 녹음 중 화면 dim | 배경 0.5 opacity 어둡게 — 집중 유도 |
| 파형 업데이트 | 60fps, 24 채널 FFT bin |
| 취소 제스처 | 마이크 버튼 위로 80px 드래그 시 빨간 X 표시 → 떼면 폐기 |
| 백그라운드 진입 시 | 즉시 녹음 종료 + 폐기 (오디오 누설 방지) |
| 호출 중 다른 음성 입력 (전화 등) | iOS `AVAudioSession` interruption → 녹음 종료 + idle 복귀 |

### D.3 48시간 폐기 잡 (FR-036)

클라이언트는 알 필요 없음. 다만 `/settings`에서 "변환 즉시 삭제" 옵션을 토글하면 백엔드에 `audio_recordings.delete_immediately = true`로 변경된 동의 스냅샷 신규 발급.

---

## Flow E: 동의 변경 (Settings) — Mobile 신규

PRD에는 명시되지 않았으나, FR-026/FR-034 동의가 옵트인 가능하므로 모바일 설정 화면의 동의 변경 플로우를 명시한다.

```mermaid
flowchart TD
  Settings["/settings"] --> ConsentList["동의 관리 진입"]
  ConsentList --> ItemTap{항목 탭}

  ItemTap -->|약관/개인정보/민감정보| ReadOnly["내용 보기 (변경 불가)\n탈퇴로만 철회"]
  ItemTap -->|위험 통보 동의 FR-026| RiskToggle{토글 변경}
  ItemTap -->|음성 입력 동의 FR-034| VoiceToggle{토글 변경}

  RiskToggle -->|"옵트아웃"| RiskWarning["경고 모달:\n옵트아웃 시 위험 감지\n알림이 제한됩니다.\n계속하시겠습니까?"]
  RiskWarning -->|확인| RiskUpdate["POST /consents\n새 snapshot 발급"]

  VoiceToggle -->|"옵트아웃"| VoiceWarning["안내:\n음성 입력이 비활성화됩니다.\n원본 오디오는\n48시간 내 자동 삭제됩니다."]
  VoiceWarning -->|확인| VoiceUpdate["POST /consents\n새 snapshot 발급"]

  RiskUpdate --> Refetch["WS 재인증 + 사용자 캐시 갱신"]
  VoiceUpdate --> Refetch
  Refetch --> ConsentList
```

---

## Flow F: 오프라인 / 에러 폴백 (모바일 공통)

```mermaid
flowchart TD
  AnyScreen["임의 화면"] --> NetCheck{NetInfo isConnected?}

  NetCheck -->|true| Normal[정상 동작]
  NetCheck -->|false| OfflineBanner["상단 배너:\n'인터넷 연결 없음'\n빨강 배경"]

  OfflineBanner --> ActionType{사용자 액션}
  ActionType -->|read 액션| CacheRead["React Query stale 캐시 표시"]
  ActionType -->|write 액션| Queue["Mutation queue에 보관\n+ 토스트 '연결 복구 시 자동 전송'"]
  ActionType -->|채팅 전송| DisableInput["입력창 disabled +\n메시지 큐"]

  Normal --> Reconnect{재연결}
  Queue --> Reconnect
  Reconnect -->|true| Flush["큐 flush + 배너 해제"]

  AnyScreen --> ServerErr{5xx 에러}
  ServerErr -->|true| ErrorScreen["인라인 에러 UI:\n'잠시 후 다시 시도해 주세요'\n[재시도] 버튼\n입력 내용 보존 안내"]
```

### F.1 오프라인 정책 (페이지별)

| 페이지 | 오프라인 동작 |
|--------|-------------|
| `/onboarding`, `/login`, `/register` | 입력은 가능, 제출 시 큐잉 (단 로그인은 즉시 에러 안내) |
| `/home` | 마지막 캐시 표시 + 오프라인 배지 |
| `/intake/chat` | 입력은 가능 (로컬 보존), 송신 큐잉. WebSocket 끊김 시 자동 재연결 |
| `/intake/phq9`, `/intake/gad7` | 응답 로컬 저장 → 재연결 시 일괄 송신 |
| `/intake/documents` | 업로드 큐잉 (Phase 2) |
| `/intake/submit` | 명시적 차단 — "제출은 인터넷 연결 후 가능합니다" |
| `/emergency` | **항상 동작** — 핫라인 전화 걸기는 셀룰러로 진행 |
| `/hospitals` | 캐시된 결과만 표시 (Phase 2) |
| `/report/status` | 마지막 polling 결과 표시 |
| `/settings` | 읽기 전용, 변경은 큐잉 |

---

## Flow G: 첫 사용자 진입 (Onboarding First-Run)

```mermaid
flowchart TD
  FirstLaunch["앱 첫 실행"] --> O1["/onboarding 1/4\n'40분 진료, 20분은 과거력 청취에 소진됩니다'"]
  O1 -->|다음| O2["/onboarding 2/4\n'미리 정리해 두면 의사가\n핵심을 빠르게 파악합니다'"]
  O2 -->|다음| O3["/onboarding 3/4\n'위기 순간에는\n즉시 1393으로 연결됩니다'"]
  O3 -->|다음| O4["/onboarding 4/4\n'본 앱은 진단/치료를 하지 않습니다.\n의료진의 진료를 돕는 도구입니다.'"]
  O4 -->|시작하기| MarkSeen["AsyncStorage.set('hasSeenOnboarding', 'true')"]
  MarkSeen --> Login["/login"]

  O1 -.->|건너뛰기| Login
  O2 -.->|건너뛰기| Login
  O3 -.->|건너뛰기| Login
```

**원칙**:
- 4스텝 이하 (인지부하 최소화)
- 마지막 스텝은 **Non-Goals 명시** (PRD §1.3 정렬) — 의료 도구로서의 신뢰 형성
- "건너뛰기"는 항상 노출 (강요 금지)

---

## Critical Edge Cases (Mobile)

| 케이스 | 처리 |
|--------|------|
| 채팅 중 앱 강제 종료 후 재실행 | `sessions.status='in_progress'` 발견 → 홈에서 "이어하기" 카드 노출 |
| 동시 다중 세션 진입 | 백엔드가 1개 active session만 허용. 신규 요청 시 기존 session 자동 종료 + 안내 |
| Push-to-Talk 중 위험 발화 | STT 변환 후 입력창에 채워지지만 **자동 송신은 안 함** (FR-035). 사용자가 명시적 송신 후 Safety Guard가 감지 |
| `/emergency` 진입 후 앱 종료 | 백엔드 risk_event status는 `detected`로 유지. 재실행 시 홈 진입 전 안전 확인 모달 1회 노출 (Phase 2) |
| 로그아웃 시 진행 중 세션 | "저장 후 로그아웃"만 허용. 진행률 ≥ 50% 시 확인 모달 |
| 회원 탈퇴 (Phase 2) | FR-029 정책 — 즉시 삭제 항목과 가명처리 항목 분리 안내 후 처리 |
