# Neuro-Sync Developer Handoff — Mobile (React Native)

> **Platform**: React Native (iOS/Android)
> **Source PRD**: v1.4
> **Generated**: 2026-06-06
> **Phase Scope**: Phase 1a + 1b + Demo Polish (8주 데모)

본 문서는 `/implement` 단계 RN 엔지니어가 PRD/Screen Spec을 들고 즉시 코딩에 착수할 수 있도록 **FR ↔ Screen ↔ Component 매핑, API/WS contract, 상태 관리, 구현 순서, 수용 기준**을 한 곳에 묶은 핸드오프 문서다.

원천 문서:
- PRD: [`PRD_neuro-sync.md`](../../PRD_neuro-sync.md) v1.4 (§3 FR, §5.1 API, §5.4 Pages, §6 Phases)
- IA: [`01-IA.md`](./01-IA.md)
- Flow: [`02-USER-FLOW.md`](./02-USER-FLOW.md) (Flow A/C/D/E/F/G)
- Screen Spec: [`03-SCREEN-SPEC.md`](./03-SCREEN-SPEC.md) (S-01 ~ S-13)
- Wireframe: [`04-WIREFRAME.html`](./04-WIREFRAME.html)

---

## Table of Contents

- [§1. FR ↔ Screen ↔ Component Traceability Matrix](#1-fr--screen--component-traceability-matrix)
- [§2. Screen ↔ API Endpoint Map](#2-screen--api-endpoint-map)
- [§3. WebSocket Event Handling (`/intake/chat` 딥다이브)](#3-websocket-event-handling-intakechat-딥다이브)
- [§4. Component Inventory](#4-component-inventory)
- [§5. State Management Map](#5-state-management-map)
- [§6. Platform-Specific Implementation Notes](#6-platform-specific-implementation-notes)
- [§7. Security Checklist (Mobile)](#7-security-checklist-mobile)
- [§8. Implementation Order & Task Decomposition](#8-implementation-order--task-decomposition)
- [§9. Acceptance Criteria per Screen](#9-acceptance-criteria-per-screen)
- [§10. Open Questions for the Engineer](#10-open-questions-for-the-engineer)
- [§11. Risks Specific to Mobile Implementation](#11-risks-specific-to-mobile-implementation)

### 용어 (프로젝트 한정)

- **Handoff Report**: 환자 사전 문진 결과를 의료진이 5초 안에 파악할 수 있게 구조화한 문서 (주호소·현병력·위험 신호·문진 점수·문서 요약·원문 근거 인용). 모바일 환자는 본문 미열람, **상태(생성 중/준비 완료)만** 확인. 의료진 웹 전용. PRD FR-018.
- **Safety Guard**: 채팅 중 위험 발화(자살·자해·타해)를 1초 내 분류하는 별도 AI 모듈. 위험 감지 시 메인 LLM 응답을 차단하고 `risk:detected` 이벤트를 클라이언트에 푸시한다. PRD FR-005.

---

## §1. FR ↔ Screen ↔ Component Traceability Matrix

> Owner: `P` = Platform / `A` = AI Research / `S` = Shared (양 팀). Mobile 엔지니어는 `P`/`S` 행만 직접 구현하면 된다.
> Phase: `1a` / `1b` / `Polish` (8주 데모 범위) / `P2+` (Phase 2 이후 — 본 데모 OUT)
> Critical Path: 데모 시연 핵심 플로우 (`/login → /home → /intake/chat → /emergency`, `/login → /home → /intake/chat → phq9 → gad7 → submit → /report/status`)

| FR ID | Owner | Mobile Scope | Screen(s) | Key Components | Critical Path | Phase |
|-------|-------|--------------|-----------|----------------|---------------|-------|
| FR-001 | P | ✓ | S-02 `/login`, S-03 `/register` | `<EmailInput>`, `<PasswordInput>`, `<ConsentCheckbox>`, `<ConsentDetailSheet>` | ✓ | 1a |
| FR-002 | P | ✓ | S-03 `/register` Step2, S-13 `/settings` | `<PhoneInput>`, `<RegionPicker>`, `<ProfileCard>` | ✓ | 1a |
| FR-003 | P | ✓ | S-04 `/home` | `<GreetingHeader>`, `<StartIntakeCard>`, `<ResumeIntakeCard>`, `<EmergencyEntryButton>` | ✓ | 1a |
| FR-004 | S | ✓ (UI/WS) | S-05 `/intake/chat` | `<MessageList>`, `<MessageBubble>`, `<MessageComposer>`, `<StreamingCursor>` | ✓ | 1b |
| FR-005 | S | ✓ (수신/라우팅) | S-05 `/intake/chat` → S-10 `/emergency` | `<WSConnectionBanner>`, `risk:detected` reducer, `<EmergencyEntryButton>` | ✓ | 1a (수신부) / 1b (완전) |
| FR-006 | P | ✓ | S-06 `/intake/phq9` | `<QuestionnaireHeader>`, `<QuestionText>`, `<LikertOptions>`, `<NavButtons>` | ✓ | 1b |
| FR-007 | P | ✓ | S-07 `/intake/gad7` | (FR-006과 동일) | ✓ | 1b |
| FR-008 | P | △ (Stub) | S-08 `/intake/documents` | `<EmptyState>` + Stub 카피 (Demo). Phase 2: `<DocumentCard>`, `<UploadOptionsSheet>` | ✗ (Stub) | P2+ |
| FR-009 | S | ✗ | (백엔드만) | — | ✗ | P2+ |
| FR-010 | P | ✓ | S-09 `/intake/submit` | `<SummaryCard>`, `<ComplianceNotice>`, `<PrimaryButton>` | ✓ | 1b |
| FR-011 | P | ✓ | S-10 `/emergency` | `<EmergencyHeader>`, `<HotlineCard>`, `<SafetyQuestion>`, `<EmergencyExitButton>` | ✓ | 1a |
| FR-012 | P | △ (Stub) | S-11 `/hospitals` | Demo: `<EmptyState>` + 119 CTA. Phase 2: `<HospitalListCard>`, `<HospitalMap>` | ✗ (Stub) | P2+ |
| FR-013 | P | ✓ | S-04 `/home`, S-12 `/report/status` | `<ReportStatusCard>`, `<ProgressBar>` (estimate) | ✓ | 1b |
| FR-014 | P | ✗ (Demo OUT) | (Phase 2: S-04 알림 카운트, S-12 알림 신청) | (Phase 2) | ✗ | P2+ |
| FR-015 | P | ✗ Mobile | (의료진 웹 전용, 모바일은 `role=patient` 고정) | — | — | — |
| FR-016~FR-021 | P | ✗ Mobile | (의료진 웹 전용) | — | — | — |
| FR-018 (모바일 측면) | S | ✓ (상태만) | S-12 `/report/status` | `<ReportStatusCard>` (generating/ready/failed) | ✓ | 1b |
| FR-022 | S | ✓ (PATCH) | S-10 `/emergency` | `risk_events` PATCH (acknowledge, called_1393, aloneStatus) | ✓ | 1a |
| FR-023 | P | ✗ Mobile | (백엔드 미들웨어. 클라이언트는 traceId 헤더 echo) | — | — | 1a (백엔드) |
| FR-024 | P | ✗ (Demo OUT) | (Phase 3: 푸시 알림) | (FCM/APNs) | ✗ | P3+ |
| FR-025 | P | ✗ (Demo OUT) | (Phase 3: 심평원 API) | — | ✗ | P3+ |
| FR-026 | P | ✓ (동의 수집/관리) | S-03 `/register` Step1, S-13 `/settings` 동의 관리 | `<ConsentCheckbox>` (위험 통보), `<ConsentToggle>` | ✓ | 1a |
| FR-027 | P | ✗ (Demo OUT) | (Phase 2: `/register` 보호자 본인인증 분기) | — | ✗ | P2+ |
| FR-028 | P | ✗ Mobile (Demo OUT) | (Phase 2: 파일 보안. Mobile은 MIME pre-check만) | — | ✗ | P2+ |
| FR-029 | P | ✗ (Demo OUT) | (Phase 2: S-13 `/settings` 회원 탈퇴) | (Phase 2) | ✗ | P2+ |
| FR-030 | P | **Out of mobile scope** (백엔드 hash chain) | — | — | — | P2+ |
| FR-031 | P | **Out of mobile scope** (의료진 웹 세션) | — | — | — | P2+ |
| FR-032 | S | ✗ (Demo OUT, 백엔드 저장) | — | — | ✗ | P2+ |
| FR-033 | S | ✓ (마이크 UI/REST) | S-05 `/intake/chat` recording state | `<MicButton>`, `<RecordingOverlay>`, `<MessageComposer recordingState>` | ✓ | 1b |
| FR-034 | P | ✓ (동의) | S-03 `/register` Step1 (옵션), S-13 `/settings` | `<ConsentCheckbox>` (음성), `<ConsentToggle>` | ✓ | 1a (동의) / 1b (사용) |
| FR-035 | S | ✓ (편집/명시 전송) | S-05 `/intake/chat` filled state | `<MessageComposer value editable>`, 명시적 `[↑]` 송신 | ✓ | 1b |
| FR-036 | P | △ (옵션 토글) | S-13 `/settings` "변환 즉시 삭제" | `<ConsentToggle deleteImmediately>` (백엔드 일임) | ✗ (옵션) | 1b |
| FR-037 | S | ✓ (폴백 UI) | S-05 `/intake/chat` retry/fallback | `<RetryAfterSTTBanner>`, 키보드 포커스 강제 | ✓ | 1b |

### 1.1 Critical Path 시각화

```
[A. Auth + Safety 코어]
S-01 onboarding → S-02 login → S-04 home → S-05 chat
                                              │
                                              └─ (위험) → S-10 emergency  [FR-005, FR-011, FR-022, FR-026]

[B. 문진 완주]
S-05 chat → S-06 phq9 → S-07 gad7 → S-08 docs(stub) → S-09 submit → S-12 report/status

[C. STT 보조]
S-05 chat (mic long-press) → recording → transcribing → filled → 명시 송신
                                                                   ↓
                                                        (실패) → S-05 retry/fallback
```

---

## §2. Screen ↔ API Endpoint Map

> 인증: `Authorization: Bearer <accessToken>` (REST), `auth:connect` 초기 프레임 (WS — PRD §5.1).
> Error 포맷: `{ success: false, error: { code, message, details }, meta: { traceId } }` (PRD §5.1).
> Rate Limit: 사용자별 분당 60 REST / 30 chat. 로그인은 IP당 분당 5.

| Screen | Method | Endpoint | When | 비고 |
|--------|--------|----------|------|------|
| S-01 `/onboarding` | — | (호출 없음) | — | AsyncStorage 로컬만 |
| S-02 `/login` | POST | `/api/v1/auth/login` | "로그인" 탭 | `{ email, password, role: 'patient' }`. 403 ROLE_MISMATCH 시 모달 |
| S-03 `/register` | POST | `/api/v1/auth/register` | Step 3 "가입 완료" | PRD §5.1 register body. `guardianConsent`는 Demo 미사용 |
| S-04 `/home` | GET | `/api/v1/sessions?status=in_progress&limit=1` | 진입 시 | Resume 카드 표시용 |
| S-04 `/home` | GET | `/api/v1/sessions/:id/report?status_only=1` | 최근 리포트 카드용 | (백엔드 협의 필요 — 또는 별도 `/api/v1/users/me/dashboard`) |
| S-05 `/intake/chat` | POST | `/api/v1/sessions` | 신규 세션 시작 | 응답 `sessionId`를 WS URL에 사용 |
| S-05 `/intake/chat` | **WS** | `/ws/v1/sessions/:sessionId/chat` | 진입 직후 | §3 deep dive |
| S-05 `/intake/chat` | POST (multipart) | `/api/v1/stt/transcribe` | mic 떼면 | FR-033. 응답 `transcriptionId`를 다음 `user:message` payload에 첨부 |
| S-05 `/intake/chat` | PATCH | `/api/v1/sessions/:id` | "그만하기" | `{ status: 'paused' }` (백엔드 협의) — Demo는 로컬 저장만 |
| S-06 `/intake/phq9` | POST | `/api/v1/sessions/:id/questionnaires` | 9문항 완료 | `{ type: 'PHQ9', answers: number[9], completedAt }`. severity는 반환되지만 환자에게 미표시 |
| S-07 `/intake/gad7` | POST | `/api/v1/sessions/:id/questionnaires` | 7문항 완료 | `type: 'GAD7'` |
| S-08 `/intake/documents` (Demo) | — | (없음, Stub) | — | Phase 2: POST `/api/v1/sessions/:id/documents` (multipart) |
| S-09 `/intake/submit` | POST | `/api/v1/sessions/:id/submit` | "최종 제출" | 202 Accepted + `{ reportId, estimatedSeconds }` |
| S-10 `/emergency` | (없음 진입 시) | — | risk:detected 또는 수동 진입 | 진입 후 액션별 PATCH |
| S-10 `/emergency` | PATCH | `/api/v1/risk_events/:id` | 핫라인 탭 / 안전 질문 답변 / 종료 | `{ interaction, aloneStatus, acknowledgedAt }` (백엔드 협의) |
| S-11 `/hospitals` (Demo) | — | (없음, Stub) | — | Phase 2: GET `/api/v1/hospitals/search?region=&lat=&lng=` |
| S-12 `/report/status` | GET | `/api/v1/sessions/:id/report` | 3초 간격 polling, 최대 60초 | `status: 'generating'|'ready'|'failed'`. 본문은 의료진 전용 — `status_only=1` 또는 별도 status 엔드포인트 협의 |
| S-13 `/settings` | GET | `/api/v1/users/me` | 진입 시 | 프로필 캐시 |
| S-13 `/settings` | PATCH | `/api/v1/users/me` | 프로필 수정 | (Phase 2 확장 가능성) |
| S-13 `/settings` | POST | `/api/v1/consents` | 동의 토글 변경 | 새 `consent_snapshot` 발급. 응답 후 WS 재인증 (Flow E) |
| S-13 `/settings` 로그아웃 | POST | `/api/v1/auth/logout` | 로그아웃 탭 | refresh token 폐기 |
| 공통 (백그라운드) | POST | `/api/v1/auth/refresh` | accessToken 만료 60s 이내 | silent refresh |

### 2.1 백엔드 협의 필요 항목 (Mobile 관점)

- `/api/v1/sessions?status=in_progress` 페이지네이션 응답 스키마 — Resume 카드 UX 결정.
- `/api/v1/risk_events/:id` PATCH 권한 — 환자 본인이 자신의 risk_event에 PATCH 가능한지 RLS 확인.
- `/api/v1/sessions/:id/report` 환자 호출 시 본문 마스킹 vs 별도 status 엔드포인트 — 의료진 전용 데이터 노출 방지.
- `/api/v1/consents` 응답 후 WebSocket 재인증 필요 시 서버가 어떤 토큰 갱신을 요구하는지.

---

## §3. WebSocket Event Handling (`/intake/chat` 딥다이브)

### 3.1 연결 라이프사이클

```
[open]
  └─→ C→S { type: 'auth:connect', payload: { accessToken } }
       ├─→ S→C { type: 'auth:connected', payload: { sessionId, expiresAt } } → state.connected = true
       └─→ S→C { type: 'auth:error',     payload: { code } }                 → close (1008)

[send loop]
  C→S { type: 'user:message', payload: { content, inputModality, sttTranscriptionId?, idempotencyKey, sentAt } }

[receive loop]
  S→C ai:token              → 마지막 AI 말풍선에 토큰 append
  S→C ai:complete           → 스트리밍 cursor 제거, progress 업데이트
  S→C risk:detected (med)   → 인라인 노란 배너, 대화 지속
  S→C risk:detected (high)  → navigation.navigate('Emergency', { riskEventId }) + 입력 disabled
  S→C risk:detected (crit)  → 위 + 1393 자동 다이얼 prompt
  S→C auth:refresh_required → silent refresh → C→S auth:refresh
  S→C error                 → 에러 토스트 + 입력 재활성

[close]
  코드 1008 (정책 위반) — auth 실패: 재시도 금지, 로그인 화면으로
  코드 1006/1011 (비정상) — exponential backoff 재연결 (500ms → 1s → 2s → 5s, cap 30s)
```

### 3.2 이벤트 ↔ State Reducer

| Event | Direction | `chat.status` 전이 | UI 효과 | 사이드이펙트 |
|-------|-----------|-------------------|--------|-------------|
| `auth:connect` | C→S | `'connecting'` | 초기 스피너 | timeoutId (5s) 등록 |
| `auth:connected` | S→C | `'idle'` | 스피너 제거 | timeout 해제 |
| `auth:refresh_required` | S→C | (변경 없음) | — | `POST /auth/refresh` 호출 |
| `auth:refresh` | C→S | (변경 없음) | — | — |
| `auth:error` | S→C | `'disconnected'` | 모달 + `/login` replace | accessToken 폐기 |
| `user:message` | C→S | `'sending'` | optimistic 말풍선 | composer dim, mutation queue 추가 |
| `ai:token` | S→C | `'streaming'` | 마지막 AI bubble append | scroll to bottom |
| `ai:complete` | S→C | `'idle'` | cursor 제거 + progress | 메시지 영구 저장 |
| `risk:detected` (medium) | S→C | `'idle'` 유지 | 인라인 노란 배너 | risk_event 캐시 |
| `risk:detected` (high/critical) | S→C | `'paused-by-risk'` | composer disabled + 햅틱 heavy | navigation.navigate('Emergency') |
| `error` | S→C | `'idle'` | 토스트 | 마지막 mutation 재시도 큐 |
| (network drop) | — | `'disconnected'` | 상단 `<WSConnectionBanner>` | backoff 재연결 시도 |

### 3.3 클라이언트 큐 & 멱등성

- 모든 `user:message`에 `idempotencyKey: uuid()` 부여 → 재연결 후 재전송 시 중복 risk_event 방지 (PRD §5.1 C-7 보안).
- 송신 큐: `pendingMessages: Map<idempotencyKey, payload>` (Zustand). `ai:complete` 또는 `error` 수신 시 pop.
- 재연결 시 큐에 남은 payload를 순차 재전송. 5회 재시도 후에도 실패 시 사용자에게 에러 표시 + 수동 재시도.

### 3.4 토큰 갱신 시퀀스

```
S → C auth:refresh_required (만료 60s 전)
C: POST /api/v1/auth/refresh { refreshToken } → { accessToken, expiresIn }
C → S auth:refresh { accessToken }
S → C (silent OK) — 연결 유지
```

실패 시 (refresh 401): WS close 1008 → `/login` replace + AsyncStorage clear (단 `hasSeenOnboarding` 유지).

### 3.5 백그라운드 / 포그라운드 (모바일 특수)

- 백그라운드 진입 → WS 연결 자체는 OS가 곧 종료 (iOS 30~180s, Android 다양). 자동 close 처리 + 포그라운드 복귀 시 재연결.
- 포그라운드 복귀 시 accessToken 유효성 재확인 → 유효 시 즉시 재연결 + 큐 flush, 무효 시 silent refresh 후 재연결.
- 녹음 중 백그라운드 진입 → **즉시 녹음 종료 + 폐기** (Flow D.2, 오디오 누설 방지).

---

## §4. Component Inventory

> 03-SCREEN-SPEC.md 부록 B의 인벤토리에 라이브러리·props 타입·a11y 노트를 보강한 버전. 화면별 매핑은 §1 참조.

### 4.1 Common (Shared) — 모든 화면에서 재사용

| Component | Props 타입 스케치 | Library 권장 | a11y / 비고 |
|-----------|------------------|-------------|-----------|
| `<SafeScreen>` | `{ children, scroll?: boolean, edges?: Edge[] }` | `react-native-safe-area-context` | iOS notch + Android system bars |
| `<KeyboardSafeView>` | `{ children, behavior?: 'padding'|'height' }` | `KeyboardAvoidingView` 래퍼 | iOS=padding / Android=height |
| `<PrimaryButton>` | `{ label, onPress, loading?, disabled?, fullWidth? }` | RN core `Pressable` | role="button", min hit 48dp |
| `<SecondaryButton>` | (위와 동일) | — | — |
| `<DangerButton>` | (위 + state-danger color) | — | 로그아웃/탈퇴 |
| `<TextLink>` | `{ label, onPress, to?: Route }` | — | role="link" |
| `<TextInput>` | `{ value, onChangeText, error?, label?, hint?, secureTextEntry? }` | RN core | role="none" — label 분리 |
| `<EmailInput>` | (TextInput + `keyboardType='email-address'`, `autoCapitalize='none'`, `autoComplete='email'`) | — | 검증: RFC 5322 lite |
| `<PasswordInput>` | `{ ..., visible: boolean, onToggleVisible }` | — | `secureTextEntry={!visible}`, `autoComplete='password'` |
| `<PhoneInput>` | `{ value, onChangeText, error? }` | `libphonenumber-js` (E.164) | `keyboardType='phone-pad'` |
| `<RegionPicker>` | `{ value: {sido, sigungu}, onChange }` | 자체 Picker (정적 JSON) | "거주 지역" 2단 |
| `<Sheet>` | `{ visible, onClose, children, snapPoints? }` | `@gorhom/bottom-sheet` | swipe-down, accessibilityViewIsModal |
| `<Modal>` | `{ visible, onClose, children }` | RN core `Modal` | — |
| `<ConfirmModal>` | `{ title, message, confirmLabel, cancelLabel, onConfirm, onCancel, danger? }` | — | — |
| `<Toast>` | `{ message, type: 'info'|'error'|'success' }` | `react-native-toast-message` | auto-dismiss 3s |
| `<Banner>` | `{ message, type, dismissable?, onRetry? }` | 자체 | offline, error, info |
| `<ProgressBar>` | `{ value: 0~1, label? }` | 자체 | accessibilityValue |
| `<StepIndicator>` | `{ current: number, total: number }` | 자체 | "1단계 / 4단계 중" |
| `<SkeletonCard>` | `{ height, width? }` | `react-content-loader` 또는 자체 | shimmer |
| `<EmptyState>` | `{ icon?, title, description?, cta?: { label, onPress } }` | 자체 | — |
| `<BottomTabBar>` | (react-navigation 제공) | `@react-navigation/bottom-tabs` | tabs: home/hospitals/settings |
| `<OfflineBanner>` | (NetInfo 구독) | `@react-native-community/netinfo` | 상단 고정 |

### 4.2 Domain — 화면별 특화 컴포넌트

| Component | Props 타입 스케치 | 적용 화면 | 비고 |
|-----------|------------------|----------|------|
| `<OnboardingPager>` | `{ steps: Step[], onComplete: () => void }` | S-01 | `react-native-pager-view` |
| `<ConsentCheckbox>` | `{ label, required: boolean, checked, onChange, onPressDetail }` | S-03 Step1 | "[필수]" prefix red |
| `<ConsentDetailSheet>` | `{ versionedHtml: string, version: string }` | S-03 | 약관 버전 명시 |
| `<ConsentToggle>` | `{ type: 'risk_notification'|'voice'|'delete_immediately', value: boolean, onChange, disabled? }` | S-13 | 옵트아웃 시 경고 모달 트리거 |
| `<GreetingHeader>` | `{ userName, timeOfDay: 'morning'|'noon'|'evening'|'night' }` | S-04 | — |
| `<ResumeIntakeCard>` | `{ sessionId, progressPct, onResume }` | S-04 | 있을 때만 노출 |
| `<StartIntakeCard>` | `{ onStart, estimatedMinutes: 15 }` | S-04 | Primary CTA |
| `<ReportStatusCard>` | `{ reportId, status: 'generating'|'ready'|'failed', submittedAt }` | S-04, S-12 | — |
| `<EmergencyEntryButton>` | `{ onPress }` | S-04, S-13 | state-danger, "지금 도움이 필요해요" |
| `<ChatHeader>` | `{ progressPct, onClose }` | S-05 | "그만하기" 모달 트리거 |
| `<MessageList>` | `{ messages: Message[], streamingMessageId?: string }` | S-05 | `FlatList` inverted, auto-scroll |
| `<MessageBubble>` | `{ role: 'user'|'ai'|'system', content, inputModality?: 'text'|'voice', sentAt }` | S-05 | voice → 🎤 아이콘 |
| `<StreamingCursor>` | `{ visible: boolean }` | S-05 | blinking 500ms |
| `<MessageComposer>` | `{ value, onChangeText, onSend, onStartRecording, onCancelRecording, recordingState: 'idle'|'recording'|'transcribing'|'filled'|'fallback' }` | S-05 | 멀티 상태 컴포넌트 |
| `<MicButton>` | `{ state: 'idle'|'recording'|'transcribing'|'disabled', onLongPressIn, onLongPressOut, onCancelGesture }` | S-05 | 56dp, 햅틱 |
| `<RecordingOverlay>` | `{ elapsedMs: number, waveformData: number[], cancelHover: boolean }` | S-05 recording | 24ch FFT, 30s auto-stop |
| `<RetryAfterSTTBanner>` | `{ reason: 'low-conf'|'silent'|'noise'|'timeout', onRetry, onKeyboard }` | S-05 | 인라인 |
| `<WSConnectionBanner>` | `{ connected: boolean, reconnecting?: boolean, onRetry }` | S-05 | 상단 dismissable |
| `<QuestionnaireHeader>` | `{ current: number, total: number, instrument: 'PHQ9'|'GAD7' }` | S-06, S-07 | 진행률 |
| `<QuestionText>` | `{ text, weekFraming: '지난 2주 동안' }` | S-06, S-07 | 인용부호 처리 |
| `<LikertOptions>` | `{ options: { label, value }[], value: number, onChange }` | S-06, S-07 | 4점 척도 |
| `<NavButtons>` | `{ onPrev, onNext, nextDisabled?, prevDisabled? }` | S-06, S-07 | — |
| `<DocumentCard>` (P2) | `{ id, type, filename, sizeBytes, ocrStatus, onDelete }` | S-08 P2 | — |
| `<UploadOptionsSheet>` (P2) | `{ onCamera, onGallery, onFile }` | S-08 P2 | MIME whitelist |
| `<SummaryCard>` | `{ title, subtitle, status?: 'complete'|'partial', onEdit? }` | S-09 | — |
| `<ComplianceNotice>` | `{}` | S-09 | Appendix C 카피 고정 |
| `<EmergencyHeader>` | `{}` | S-10 | red banner, 햅틱 heavy on mount |
| `<HotlineCard>` | `{ icon, number, name, subtitle?, onCall }` | S-10 | tel: deep link |
| `<SafetyQuestion>` | `{ question, onAnswer: (alone: boolean) => void }` | S-10 | — |
| `<EmergencyExitButton>` | `{ onPress }` | S-10 | 유일한 종료 경로 |
| `<HospitalListCard>` (P2) | `{ name, address, phone, distanceKm, hasNightCare }` | S-11 P2 | — |
| `<HospitalMap>` (P2) | `{ markers, center, onPinPress }` | S-11 P2 | `react-native-maps` |
| `<ProfileCard>` | `{ name, email, onEdit }` | S-13 | — |
| `<SettingsSection>` | `{ title, items: SettingsItem[] }` | S-13 | — |
| `<SettingsRow>` | `{ label, icon?, right: 'arrow'|'toggle'|'text', value?, onPress }` | S-13 | — |
| `<DangerRow>` | `{ label, onPress }` | S-13 | "회원 탈퇴" (Phase 2) |

### 4.3 Heavy (특별 주의)

| Component | 주의사항 |
|-----------|---------|
| `<MessageComposer>` | recordingState 5종 + KeyboardAvoidingView + 권한·동의 게이트 결합. **첫 PR에 통합 테스트 필수**. |
| `<MicButton>` | iOS/Android 권한 흐름 분기, long-press 200ms 임계값, drag-up 취소 (`PanResponder`). 햅틱 차이 (iOS UIImpactFeedbackGenerator vs Android Vibrator). |
| `<RecordingOverlay>` | 60fps 파형 렌더. `react-native-reanimated` shared values + `react-native-svg` 또는 Skia. 30s 자동 종료 타이머. |
| `<MessageList>` | `FlatList inverted` + 스트리밍 시 ai:token append 성능. 마지막 메시지만 re-render (memo + selector). |
| `<EmergencyHeader>` | 첫 진입 시 햅틱 heavy 1회. iOS 백 제스처 `gestureEnabled: false` + Android `BackHandler` 등록. |
| `<HotlineCard>` | `Linking.canOpenURL('tel:...')` 사전 체크 + 실패 시 토스트. |
| `<ConsentDetailSheet>` | 약관 HTML 내 외부 링크 클릭 시 `Linking.openURL` + `Sheet` 위에서 가독성. |
| WebSocket 클라이언트 | 자체 클래스 권장 (`ReconnectingChatSocket`). 라이브러리(`reconnecting-websocket`)는 RN 환경에서 호환 이슈 있음. |

---

## §5. State Management Map

> 라이브러리: **React Query** (v5) — 서버 캐시. **Zustand** — 클라이언트 UI 상태 (chat 상태머신, recording, 토큰 등). **AsyncStorage** — 비민감. **SecureStore** (`expo-secure-store` 또는 `react-native-keychain`) — accessToken/refreshToken.

### 5.1 React Query Keys (서버 상태)

| Key | 적용 화면 | Stale Time | Cache Time | 비고 |
|-----|----------|-----------|-----------|------|
| `['me']` | S-04, S-13 | 5min | 30min | 프로필 + 동의 스냅샷 요약 |
| `['sessions', { status: 'in_progress' }]` | S-04 | 30s | 5min | Resume 카드 |
| `['session', sessionId]` | S-05, S-09 | 0 (always fresh) | 1h | 진입 시 항상 refetch |
| `['session', sessionId, 'messages']` | S-05 | 0 | 1h | WS와 병합 (initial fetch + 실시간 append) |
| `['questionnaire', sessionId, 'PHQ9'\|'GAD7']` | S-06, S-07 | Infinity (제출 후) | Infinity | 완료 후 immutable |
| `['session', sessionId, 'report']` | S-12 | 3s (generating) / Infinity (ready) | 1h | polling은 `refetchInterval` |
| `['consents', 'me']` | S-13 | 0 | 30min | 변경 후 invalidate |

### 5.2 Zustand 슬라이스 (UI 상태)

```ts
// stores/authStore.ts
type AuthState = {
  accessToken: string | null;       // 메모리 only — SecureStore 미러
  refreshToken: string | null;
  user: { id, email, role: 'patient' } | null;
  hydrate: () => Promise<void>;     // 앱 부팅 시 SecureStore → 메모리
  setTokens: (a, r) => void;
  logout: () => Promise<void>;
};

// stores/chatStore.ts
type ChatState = {
  status: 'idle' | 'connecting' | 'sending' | 'streaming' | 'paused-by-risk' | 'disconnected';
  pendingMessages: Map<string, MessagePayload>;  // idempotencyKey → payload
  streamingMessageId: string | null;
  progressPct: number;
  wsConnected: boolean;
  reduce: (event: WSEvent) => void;
};

// stores/recordingStore.ts
type RecordingState = {
  state: 'idle' | 'requesting-permission' | 'recording' | 'encoding' | 'transcribing' | 'filled' | 'retry-prompt' | 'fallback-text';
  elapsedMs: number;
  waveformData: number[];
  draftText: string;                // STT 결과 또는 사용자 편집
  transcriptionId: string | null;
};

// stores/consentStore.ts (단기 — React Query로 옮길 수도 있음)
type ConsentState = {
  riskNotification: boolean;
  voice: boolean;
  deleteImmediately: boolean;
};
```

### 5.3 AsyncStorage / SecureStore 키

| Key | Storage | 값 | 화면 | 비고 |
|-----|---------|---|------|------|
| `accessToken` | SecureStore | JWT 문자열 | 전역 | 15분 만료 |
| `refreshToken` | SecureStore | JWT 문자열 | 전역 | 7일 만료 |
| `hasSeenOnboarding` | AsyncStorage | `'true'` | S-01 | 4스텝 완료 시 set |
| `lastSessionId` | AsyncStorage | uuid | S-04 | 빠른 Resume |
| `intake.draft.<sessionId>` | AsyncStorage | `{ messages, currentStep }` | S-05~S-09 | 오프라인 드래프트 |
| `phq9.draft.<sessionId>` | AsyncStorage | `number[]` (부분 응답) | S-06 | 매 응답마다 set |
| `gad7.draft.<sessionId>` | AsyncStorage | `number[]` | S-07 | 동일 |
| `deviceId` | SecureStore | uuid | 전역 | 첫 실행 시 생성 (감사 로그용) |

> **금지**: 비밀번호, 민감 환자 정보(이름/연락처 평문), 위험 이벤트 본문은 로컬 저장 금지. 모두 서버 RLS 통과 후 메모리만.

---

## §6. Platform-Specific Implementation Notes

### 6.1 iOS

| 항목 | 사양 |
|------|------|
| Info.plist `NSMicrophoneUsageDescription` | "사전 문진 중 음성으로 응답하시려면 마이크 권한이 필요합니다. 녹음은 사용자가 버튼을 누르는 동안만 수행됩니다." |
| Info.plist `NSLocationWhenInUseUsageDescription` (Phase 2) | "가까운 정신건강의학과를 찾기 위해 위치 정보가 필요합니다." |
| Info.plist `LSApplicationQueriesSchemes` | `tel` (전화 걸기), `mailto` (Phase 2 문의) |
| SafeAreaView | `react-native-safe-area-context`의 `SafeAreaProvider` 최상위 + 화면별 `edges=['top','bottom']` |
| KeyboardAvoidingView behavior | `'padding'` (iOS만) |
| 백 제스처 차단 (`/emergency`) | `navigation.setOptions({ gestureEnabled: false })` |
| AVAudioSession interruption (통화 등) | `expo-av` `Audio.setAudioModeAsync({ interruptionModeIOS: DUCK_OTHERS })` + 인터럽션 핸들러로 녹음 종료 |
| 햅틱 | `expo-haptics` `ImpactFeedbackStyle.Heavy` (위험), `.Light` (녹음 시작), `.Medium` (종료) |
| 백그라운드 모드 | 별도 capability 불요 (음성/위치 백그라운드 사용 안 함) |

### 6.2 Android

| 항목 | 사양 |
|------|------|
| AndroidManifest `<uses-permission>` | `RECORD_AUDIO`, `INTERNET`, `ACCESS_NETWORK_STATE`, `VIBRATE`, (Phase 2) `ACCESS_FINE_LOCATION`, `CAMERA` |
| AndroidManifest `<queries>` | `<intent><action android:name="android.intent.action.DIAL"/></intent>` (전화 걸기 query API 30+) |
| `KeyboardAvoidingView behavior` | `'height'` |
| 백 버튼 차단 (`/emergency`) | `useFocusEffect` + `BackHandler.addEventListener('hardwareBackPress', () => true)` |
| 햅틱 | `react-native-haptic-feedback` (Vibrator API 통합) |
| Audio focus | `expo-av` `Audio.setAudioModeAsync({ shouldDuckAndroid: true })` |
| `<application>` `usesCleartextTraffic="false"` | 강제 HTTPS (TLS 1.3) |
| Network Security Config | `cleartextTrafficPermitted=false` + (Phase 2) 인증서 핀닝 |

### 6.3 Shared (Deep Link / 공통)

| 항목 | 사양 |
|------|------|
| URI scheme | `ns://` (iOS `CFBundleURLTypes` / Android `<intent-filter android:scheme="ns">`) |
| Deep Link `ns://intake/resume` | `sessions.status='in_progress'` 발견 시 `/intake/chat?resumeSessionId=...` (IA §4) |
| Deep Link `ns://emergency` | Phase 3. 외부 트리거로 `/emergency` 직진 |
| `react-navigation` linking config | `{ prefixes: ['ns://', 'https://app.neuro-sync.kr'], config: { screens: { Intake: 'intake/resume', Emergency: 'emergency' } } }` |
| 푸시 알림 (Phase 3) | FCM (Android) + APNs (iOS), payload data에 deep link path |
| App ID | 결정 필요 (Open Q §10) — `kr.wigtn.neurosync` 잠정 |

---

## §7. Security Checklist (Mobile)

| 항목 | 요구 | 라이브러리 / 구현 | Phase |
|------|------|-------------------|-------|
| accessToken 저장 | SecureStore (Keychain/Keystore) | `expo-secure-store` 또는 `react-native-keychain` | 1a |
| refreshToken 저장 | 동일 | 동일 | 1a |
| 평문 토큰 로그 금지 | console.log 마스킹 헬퍼 | 자체 `redact()` + Sentry beforeSend hook | 1a |
| TLS 1.3 강제 | iOS ATS 기본값 + Android Network Security Config | — | 1a |
| 인증서 핀닝 | (권장, Phase 2) | `react-native-ssl-pinning` 또는 `react-native-cert-pinner` | P2+ |
| 화면 캡처 방지 (`/intake/chat`, `/emergency`) | iOS: 캡처 감지 후 블러. Android: `FLAG_SECURE` | `expo-screen-capture` `preventScreenCaptureAsync()` | 1b |
| 잭/루트 탐지 | (Phase 4) | `jail-monkey` | P4+ |
| 디바이스 ID 영속성 | SecureStore uuid (앱 첫 실행 시 생성) | — | 1a |
| 화면 비활성 시 앱 스위처에서 내용 가림 | iOS: AppState 'inactive' 시 splash 오버레이 | 자체 `<PrivacyOverlay>` 컴포넌트 | 1b |
| WebSocket 토큰 노출 방지 (PRD C-7) | URL query 금지, `auth:connect` 초기 프레임으로만 전송 | §3 참조 | 1a |
| 음성 동의 게이트 (FR-034) | 미동의 시 `<MicButton state='disabled'>` + 마이크 권한 자체 요청 금지 | `<MessageComposer>` 내부 분기 | 1b |
| 명시적 전송 강제 (FR-035) | STT 결과는 무조건 편집 가능 상태로 채움. 자동 송신 코드 path 0건 | 코드 리뷰 시 grep | 1b |
| 48시간 폐기 정책 표시 (FR-036) | 동의 화면 + `/settings` 상시 안내 | `<ConsentDetailSheet>`, `<ConsentToggle>` 카피 | 1a / 1b |
| 마이크 권한 거부 시 키보드 폴백 (FR-037) | 권한 거부 시 마이크 disabled + 입력창 포커스 | `<MessageComposer>` 내부 | 1b |
| Role 검증 (FR-015 보조) | 로그인 응답 `user.role !== 'patient'` 시 즉시 로그아웃 + 안내 | `authStore.setTokens` 내부 | 1a |
| 5xx 응답에 민감정보 echo 안 함 | 백엔드 책임. 클라이언트는 traceId만 표시 | — | 1a |
| Crashlytics / Sentry 마스킹 | breadcrumb 필터로 메시지 본문/PII 제거 | Sentry beforeBreadcrumb | 1a |

---

## §8. Implementation Order & Task Decomposition

> 8주 데모 D-Day 2026-07-31 기준. PRD §6 Phase 1a (3주) + Phase 1b (4주) + Demo Polish (1주). Mobile FE 1인 가정 (BE/AI와 병행).

### 8.1 Phase 1a (W1~W3, 2026-06-04 ~ 06-24)

| # | Task | FRs | Screens | Output |
|---|------|-----|---------|--------|
| T01 | RN 프로젝트 셋업 (Expo vs RN CLI 결정 — §10), TypeScript, ESLint, react-navigation, React Query, Zustand, SecureStore, NetInfo, Sentry | — | — | 부팅 가능한 빈 앱 |
| T02 | 디자인 토큰 + 공통 컴포넌트 1차 (`<SafeScreen>`, `<PrimaryButton>`, `<TextInput>`, `<Banner>`, `<Toast>`, `<EmptyState>`, `<ProgressBar>`, `<StepIndicator>`, `<SkeletonCard>`, `<OfflineBanner>`) | — | 모든 화면 | Storybook 또는 RN devtools 카탈로그 |
| T03 | 인증 인프라 (SecureStore 토큰, axios interceptor, refresh queue, role gate) | FR-001 | — | `useAuth`, `apiClient` |
| T04 | S-01 `/onboarding` (4 step, AsyncStorage) | — | S-01 | 화면 + 단위테스트 |
| T05 | S-02 `/login` (검증, 에러 매핑, role-mismatch, account-locked) | FR-001 | S-02 | — |
| T06 | S-03 `/register` 3 step (4개 동의 + 음성 동의 옵션 + 프로필 + 계정. 만 14세 미만은 Demo 안내만) | FR-001, FR-002, FR-026, FR-034 | S-03 | — |
| T07 | Bottom Tab + S-04 `/home` (Resume/Start/ReportStatus/EmergencyEntry 카드 + 시간대 인사) | FR-003, FR-013 | S-04 | — |
| T08 | S-10 `/emergency` UI (hotlines, safety question, exit, 백 제스처/하드웨어 백 차단, 햅틱) | FR-011, FR-022, FR-026 | S-10 | — |
| T09 | S-13 `/settings` 기본 (프로필, 동의 관리, 로그아웃) + 동의 변경 모달 카피 | FR-002, FR-026, FR-034 | S-13 | — |
| T10 | WebSocket 클라이언트 클래스 (`ReconnectingChatSocket`) + `auth:connect` 초기 프레임 + idempotencyKey 큐 + backoff | FR-004 (인증부), FR-005 (수신부) | S-05 (1차) | 단위테스트 mocked WS |
| T11 | `risk:detected` → `/emergency` 강제 라우팅 + 의료진 대시보드 연계 확인 (Mock) | FR-005, FR-022 | S-05 → S-10 | E2E happy path |

**Phase 1a Gate (W3 종료)**: 로그인 → 홈 → 가짜 채팅 화면에서 mock `risk:detected` 수신 → `/emergency` 전환 + hotline 동작 확인.

### 8.2 Phase 1b (W4~W7, 2026-06-25 ~ 07-22)

| # | Task | FRs | Screens | Output |
|---|------|-----|---------|--------|
| T12 | S-05 `/intake/chat` 1차 (FlatList inverted, MessageList/Bubble, MessageComposer 텍스트 전용, ai:token 스트리밍, progress 헤더, "그만하기" 모달) | FR-004 | S-05 | — |
| T13 | WSConnectionBanner + 재연결 + 토큰 silent refresh (`auth:refresh_required`) + Sentry 통합 | FR-004 | S-05 | — |
| T14 | `<MicButton>` + `<RecordingOverlay>` + 권한 흐름 + 음성 동의 게이트 + drag-up 취소 + 30s 자동 종료 + 백그라운드 폐기 | FR-033, FR-034 | S-05 | iOS/Android 디바이스 수동 테스트 |
| T15 | STT REST 업로드 (multipart) + transcribing 상태 + `<RetryAfterSTTBanner>` (low-conf/timeout/5xx) + 키보드 폴백 (FR-037) | FR-033, FR-035, FR-037 | S-05 | — |
| T16 | FR-035 명시 전송: STT 결과 → 편집 가능 입력창 자동 채움 + 자동 송신 금지. 송신 시 `inputModality='voice'` + `sttTranscriptionId` 첨부 | FR-035 | S-05 | 코드 리뷰 grep "autoSend" 0건 |
| T17 | S-06 `/intake/phq9` (9문항, Likert, 로컬 저장, POST questionnaires) + S-07 `/intake/gad7` (7문항) | FR-006, FR-007 | S-06, S-07 | — |
| T18 | S-08 `/intake/documents` Stub + S-11 `/hospitals` Stub (Demo) | FR-008 (Stub), FR-012 (Stub) | S-08, S-11 | — |
| T19 | S-09 `/intake/submit` 요약 카드 + ComplianceNotice + POST submit | FR-010 | S-09 | — |
| T20 | S-12 `/report/status` polling (3s 간격, 60s timeout, generating-overdue 처리) | FR-013, FR-018 (상태만) | S-12 | — |
| T21 | 화면 캡처 방지 (`/intake/chat`, `/emergency`) + AppState inactive 시 PrivacyOverlay | (보안) | S-05, S-10 | — |
| T22 | `<EmergencyExitButton>` PATCH risk_event + 안전 질문 응답 PATCH + 핫라인 탭 시 PATCH | FR-022, FR-026 | S-10 | — |
| T23 | Deep Link 통합 (`ns://intake/resume`) + react-navigation linking | — | S-04, S-05 | — |
| T24 | Flow F (오프라인) — NetInfo 배너 + mutation queue + WS auto-reconnect | (NFR) | 전 화면 | — |

**Phase 1b Gate (W7 종료)**: 가상 페르소나 3건 — 일반 환자(완주), 위험 발화 환자(Safety Gate), STT 사용자(녹음→편집→송신).

### 8.3 Demo Polish (W8, 2026-07-23 ~ 07-31)

| # | Task | 영역 |
|---|------|------|
| T25 | UX 마이크로카피 점검 (03-SCREEN-SPEC §0.10 매핑 확인) + 에러/로딩 카피 통일 | 전 화면 |
| T26 | 데모 시드 환자 (가상 페르소나 3~5명) — register/login 자동화 스크립트 | — |
| T27 | 데모 시나리오 스크립트 작성 + 데모 영상 백업 녹화 (라이브 실패 대비) | — |
| T28 | iOS/Android 빌드 배포 (TestFlight + Internal Testing) | — |
| T29 | 외부 LLM/STT rate limit·캐시 검증 + WS reconnect 스트레스 테스트 | — |
| T30 | 최종 회귀 테스트 + Sentry 모니터 활성화 + 데모 발표 자료 정합성 확인 | — |

---

## §9. Acceptance Criteria per Screen

> Gherkin one-liner. PRD §2.2 시나리오에서 인용한 항목은 (PRD §2.2) 표기.

| Screen | Acceptance Criteria |
|--------|---------------------|
| S-01 `/onboarding` | Given 첫 실행 When 4 step 완료 또는 건너뛰기 Then `hasSeenOnboarding=true` 저장 + `/login` 진입 |
| S-02 `/login` | Given 유효 자격증명 When `role='patient'` 응답 Then `/home` replace, accessToken SecureStore 저장. Given role≠patient Then 안내 모달 + 로그아웃 |
| S-02 `/login` | Given 5회 실패 Then 15분 잠금 모달 |
| S-03 `/register` | Given 필수 4개 동의 모두 체크 + 프로필 유효 + 비밀번호 정책 통과 When 가입 완료 Then 201 + `/home` |
| S-03 `/register` | Given 이메일 중복 Then 409 EMAIL_EXISTS → 인라인 + "[로그인하기]" |
| S-04 `/home` | Given `sessions.in_progress` 존재 Then Resume 카드 노출 + 새 문진 카드 비활성. Given 첫 사용자 Then "사전 문진 시작" CTA만 |
| S-04 `/home` | Given "지금 도움이 필요해요" 탭 Then `/emergency` modal push |
| S-05 `/intake/chat` | Given 진입 When `auth:connect` 송신 Then 5초 내 `auth:connected` 수신. 미수신 시 모달 + 재시도 |
| S-05 `/intake/chat` | Given AI 응답 스트리밍 중 When `ai:token` 수신 Then 마지막 AI 말풍선에 append, `ai:complete` 시 cursor 제거 |
| S-05 `/intake/chat` | (PRD §2.2) Given 위험 발화 입력 When `risk:detected (high)` 수신 Then 일반 대화 즉시 중단 + `/emergency` 강제 전환 + risk_event 서버 저장 |
| S-05 `/intake/chat` | (PRD §2.2) Given 음성 동의 옵트인 + 마이크 권한 허용 When 마이크 long-press → release Then 녹음 종료 + STT 변환 + 입력창에 텍스트 자동 채움 + **자동 송신 안 함** |
| S-05 `/intake/chat` | (PRD §2.2) Given STT 신뢰도 < 0.6 Then "다시 말씀해 주세요" 안내 |
| S-05 `/intake/chat` | (PRD §2.2) Given STT 5xx/timeout Then 키보드 입력 모드 자동 전환 + 토스트 안내 |
| S-05 `/intake/chat` | Given 음성 동의 옵트아웃 When 마이크 탭 Then 바텀시트 "설정에서 동의 필요" + 마이크 버튼 비활성 |
| S-06 `/intake/phq9` | Given 9문항 응답 완료 When POST questionnaires 200 Then GAD-7로 자동 전환. severity는 환자에게 미표시 |
| S-07 `/intake/gad7` | (위와 동일, 7문항) Then `/intake/documents` 전환 |
| S-08 `/intake/documents` (Demo) | Given 진입 Then "정식 버전에서 제공" Stub + "건너뛰고 다음으로" CTA → `/intake/submit` |
| S-09 `/intake/submit` | Given 모든 카드 완료 When "최종 제출" 탭 → 202 Then `/report/status` replace. Given 카드 partial Then 경고 배지 + 해당 단계로 이동 가능 |
| S-09 `/intake/submit` | Compliance notice (Appendix C 카피) 항상 노출 |
| S-10 `/emergency` | Given 진입 Then 1393/119/1577-0199 + 비상 연락처 카드 즉시 노출, 백 제스처/하드웨어 백 차단 |
| S-10 `/emergency` | Given 핫라인 탭 Then `Linking.openURL('tel:...')` + PATCH risk_event interaction='called_xxx' |
| S-10 `/emergency` | Given 안전 질문 응답 Then PATCH risk_event aloneStatus + acknowledgedAt |
| S-10 `/emergency` | Given "안전한 곳에 있어요" 탭 Then 모달 닫기 + 직전 화면 복귀 (risk_event.status는 변경 없음) |
| S-11 `/hospitals` (Demo) | Given 진입 Then Stub 안내 + "119 전화 걸기" CTA만 활성 |
| S-12 `/report/status` | Given `status='generating'` Then 3초 간격 polling, 진행 막대 + 카운트다운. 60초 초과 시 안내 + 홈 복귀 허용 |
| S-12 `/report/status` | Given `status='ready'` Then 체크 카드 + "홈으로" CTA. 리포트 본문은 환자에게 미노출 |
| S-13 `/settings` | Given FR-026 옵트아웃 토글 Then 경고 모달 → 확인 시 새 consent_snapshot 발급 + WS 재인증 |
| S-13 `/settings` | Given FR-034 옵트아웃 Then 안내 + 48시간 자동 삭제 명시 |
| S-13 `/settings` | Given 로그아웃 + 진행 중 세션 존재 Then "저장 후 로그아웃" 확인 모달 |
| 공통 (Flow F) | Given NetInfo offline Then 상단 빨강 배너 + 입력 disabled / read는 stale 캐시 / write는 큐잉 |
| 공통 | Given accessToken 만료 임박 Then silent refresh. 실패 시 `/login` replace |

---

## §10. Open Questions for the Engineer

> `/implement` 착수 전 BE/AI/PM과 결정 필요. 권장값을 함께 표기.

1. **Expo (managed/dev-client) vs RN CLI** — 데모 8주 일정 기준 Expo dev-client 권장 (네이티브 모듈은 `expo-av`, `expo-secure-store`, `expo-haptics`, `expo-screen-capture`로 대부분 커버). 단 인증서 핀닝/jailbreak 탐지를 Phase 2에 도입할 계획이면 RN CLI로 미리 갈 수도 있음.
2. **오디오 녹음 라이브러리** — `expo-av` (Expo 일관) vs `react-native-audio-recorder-player` (Opus 직접 지원). 권장: `expo-av`로 WAV 16kHz mono PCM 녹음 → 백엔드가 변환. Opus 클라이언트 인코딩은 Phase 2.
3. **WebSocket reconnect 파라미터** — 초기 backoff 500ms, factor 2, cap 30s, max attempts 무한 (사용자가 명시적으로 종료할 때까지). 5회 실패 후 사용자에게 모달 1회 알림. 합의 필요.
4. **`/api/v1/sessions/:id/report` 환자 호출 시 본문 노출 여부** — 의료진 전용이므로 환자 호출 시 `{ status, generatedAt }`만 반환하는 별도 status 엔드포인트가 깔끔. BE와 협의.
5. **`/api/v1/risk_events/:id` PATCH 권한** — 환자가 본인 risk_event의 일부 필드(`interaction`, `aloneStatus`)에 PATCH 가능한지 RLS 정의. 또는 별도 `/api/v1/risk_events/:id/interactions` POST 엔드포인트가 더 명확.
6. **App ID / 번들 ID** — 잠정 `kr.wigtn.neurosync` (iOS) / `kr.wigtn.neurosync` (Android). 확정 필요.
7. **STT REST vs WS 스트리밍** — Demo는 REST 업로드만 (PRD §5.1 권고). WS 스트리밍은 Phase 2 사용성 개선.
8. **푸시 알림 (Phase 2)** — FCM/APNs 모두 사용. 알림 토큰 등록 엔드포인트 BE와 합의.
9. **A.dot STT 계약 상태** — Demo는 Whisper 모드 고정 (PRD §6 명시). 모바일 코드 상으로는 vendor 무관 (백엔드 adapter).
10. **Deep Link `ns://emergency` 외부 트리거** — Phase 3. Demo는 in-app 위험 감지만.
11. **위험 발화 감지 후 채팅 재개 흐름** — `/emergency` 종료 후 `/intake/chat` 복귀 시 직전 컨텍스트(직전 5턴) 표시 여부. Demo는 단순 홈 복귀로 가는 것 권장. Flow C 참조.
12. **분석/이벤트 트래킹** — Mixpanel/Amplitude 등 도입 여부. 의료 도메인 PII 노출 위험으로 Demo는 보류 권장 (Sentry crash만).

---

## §11. Risks Specific to Mobile Implementation

| 리스크 | 영향 | 완화 |
|--------|------|------|
| **iOS WebSocket 백그라운드 종료** | 채팅 중 백그라운드 시 연결 끊김 → 재진입 시 message loss 위험 | (a) `idempotencyKey` 큐로 미송신 메시지 재전송, (b) 포그라운드 복귀 시 자동 재연결, (c) 30분 이상 백그라운드 시 세션 일시 정지 안내 |
| **A.dot STT swap 윈도우** | Demo는 Whisper, 이후 A.dot 도입 시 동작 변화 가능성 | 클라이언트는 vendor agnostic (응답 shape 동일) — §5.1 STT Adapter 인터페이스로 격리 |
| **Expo vs RN CLI 전환 비용** | Phase 4에 핀닝/루트 탐지 도입 시 Expo eject 필요 가능성 | Expo dev-client로 시작 + 네이티브 모듈 도입 시 RN CLI 전환 비용 사전 계산 |
| **녹음 중 통화/알람 인터럽션** | 오디오 누설 또는 부분 녹음 | iOS `AVAudioSession` interruption listener + Android Audio focus loss → 즉시 종료 + 폐기 (Flow D.2) |
| **위험 감지 latency** | Safety Guard 1초 SLA 초과 시 위험 발화에 일반 응답이 먼저 도착 | 클라이언트는 `risk:detected` 수신 즉시 진행 중 ai:token도 중단 + composer disable. 이전 토큰은 그대로 두되 `paused-by-risk` 배너 표시 |
| **FlatList inverted 성능** | 스트리밍 시 매 토큰마다 re-render → 발열·드롭 프레임 | 마지막 메시지만 memoize + `getItemLayout` + `windowSize=10` |
| **권한 다이얼로그 UX** | 처음 진입 시 마이크 권한 거부하면 영원히 회복 안 됨 (iOS는 OS 설정 필요) | "설정 열기" CTA + `Linking.openSettings()`. 거부 후에도 키보드 폴백으로 기능 100% 유지 |
| **AsyncStorage 보안** | 평문 저장 — 탈옥/루트 시 노출 | 민감 데이터는 절대 AsyncStorage 금지. 토큰은 SecureStore 강제. 드래프트 메시지는 평문 OK (이미 서버 RLS 통과 데이터 아님) |
| **데모 환경 외부 API rate limit** | LLM/STT 호출 폭주 시 429 → 데모 실패 | Demo Polish 단계에서 시드 페르소나로 사전 캐시 + Whisper 모드 quota 사전 확인 |
| **앱 스위처 미리보기 누설** | iOS 앱 스위처에 채팅 화면 노출 | AppState 'inactive' 시 `<PrivacyOverlay>` (splash) 띄움 |
| **딥링크 토큰 누설** | URL query에 토큰 노출 시 보안 사고 | URL query에 토큰 금지. WS는 `auth:connect` 초기 프레임, REST는 Authorization 헤더만 |
