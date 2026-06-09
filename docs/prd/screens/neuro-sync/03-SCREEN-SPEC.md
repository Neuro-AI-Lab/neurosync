# Neuro-Sync Screen Spec — Mobile (RN)

> **Platform**: React Native (iOS/Android)
> **Target Devices**: 4.7" ~ 6.7" (375pt 기준 디자인, 320pt 최소 보장)
> **Source PRD**: v1.4 (FR-001~037)
> **Generated**: 2026-06-06
>
> **Style scope (out-of-scope here)**: 본 명세는 lo-fi 정보 구조와 상태 처리 위주. 브랜드 컬러/타이포/모션 결정은 `/implement` 직전 mockup 단계에서 확정.

---

## 0. 공통 디자인 원칙 (Cross-Screen Rules)

### 0.1 정보 밀도 (Density)
**Spacious** (공간 여유) — 환자가 우울/불안 상태일 가능성 ↑, 인지부하 최소화. 행간 1.5, padding 16~24dp.

### 0.2 에러 톤 (Error Voice)
**친근한 + 비난 없는** — "잘못된 입력입니다" ✗ / "이메일 형식을 한 번 더 확인해 주세요" ✓

### 0.3 빈 상태 철학 (Empty State)
**최소 텍스트 + 명확한 CTA** — 일러스트는 가능하지만 텍스트 ≤2줄. 다음 액션 1개만 강조.

### 0.4 전환 방식 (Transitions)
- 인증/온보딩/홈: **Native stack push** (좌→우 슬라이드)
- Intake 단계 이동: **Linear stack push** (진행감 강조)
- `/emergency`: **Modal present** (위→아래) + 백 제스처 차단
- `/settings` 하위: stack push

### 0.5 모바일 우선순위 (Mobile-First)
- **mobile-first** — 본 앱은 데스크탑/태블릿 미고려 (RN iOS/Android 폰만)
- SafeAreaView 필수 적용 (iOS notch, Android system bars)
- KeyboardAvoidingView (`behavior='padding'` iOS, `'height'` Android)
- Tablet 대응은 Phase 4 (HL7 FHIR 시점)

### 0.6 첫 화면 후크 (Hero Hook)
**value-first** — "초진 대기 6개월, 변화가 기록되지 않습니다" — 문제 직시 후 가치 제시.

### 0.7 a11y 공통
- TouchableOpacity 모두 `accessibilityRole`, `accessibilityLabel` 부여
- 텍스트 최소 14sp, 본문 16sp, 버튼 텍스트 16sp
- 동적 폰트 크기(`PixelRatio.getFontScale()`) 1.3까지 레이아웃 보장
- 포커스 순서 명시 (특히 폼)
- 색상 대비 WCAG AA (본 spec은 흑백 + 의미색만 사용)

### 0.8 의미색 팔레트 (Lo-fi)
| 목적 | 토큰 | 사용처 |
|------|------|--------|
| `text-primary` | `#0F172A` (gray-900) | 본문 |
| `text-secondary` | `#64748B` (gray-500) | 보조 |
| `surface` | `#FFFFFF` | 배경 |
| `surface-elevated` | `#F8FAFC` (gray-50) | 카드 |
| `border` | `#E2E8F0` (gray-200) | 구분선 |
| `state-danger` | `#DC2626` (red-600) | 위험/에러/응급 |
| `state-warning` | `#D97706` (amber-600) | 주의 |
| `state-success` | `#059669` (green-600) | 성공/완료 |
| `state-info` | `#2563EB` (blue-600) | CTA (잠정) |

> 브랜드 컬러는 mockup 단계에서 `state-info` 자리에 매핑.

### 0.9 공통 헤더 (Header) — Intake 시리즈
```
┌─────────────────────────────────┐
│ ←  사전 문진           [그만하기] │  ← 진행률 막대 (회색 막대 + 채움)
│ ▰▰▰▰▰▰▰░░░░░░░░  45%           │
└─────────────────────────────────┘
```
- 좌측: 백 버튼 (`/intake/chat`에서는 "그만하기" 모달 트리거)
- 우측: "그만하기" → 진행 저장 후 종료 확인

### 0.10 상태별 마이크로카피 표준
| 상태 | 표준 카피 (Korean) |
|------|------------------|
| loading (일반) | "잠시만요…" + 스피너 |
| loading (리포트 생성) | "AI가 의료진 전달 리포트를 만들고 있어요. 약 30초 소요됩니다." |
| empty (홈) | "진료 전 문진을 시작해 주세요." |
| empty (문서) | "업로드한 문서가 없어요. 문서가 없어도 진행할 수 있어요." |
| error (네트워크) | "인터넷 연결이 불안정해요. 입력하신 내용은 안전하게 보관됩니다." |
| error (서버) | "잠시 후 다시 시도해 주세요." |
| error (유효성) | (필드 옆 인라인) "이메일 형식을 한 번 더 확인해 주세요." |
| offline (배너) | "인터넷 연결 없음 · 복구 시 자동으로 다시 보냅니다" |

---

# Screen Specs

## S-01. `/onboarding`

| 항목 | 값 |
|------|---|
| Route | `/onboarding` |
| Audience | guest |
| Auth | None |
| Linked FRs | (UX 보조) |
| States | success (정적, 4 step) |
| Phase | 1a, Demo IN |

### 레이아웃
```
┌─────────────────────────────────┐
│             건너뛰기            │
│                                 │
│         [일러스트 영역]          │  ← lo-fi: 회색 박스
│                                 │
│   초진 대기 6개월,              │  ← 헤드라인
│   변화가 기록되지 않습니다.       │
│                                 │
│   본 앱은 진료 전 사전 문진을     │  ← 서브카피
│   AI와 함께 준비하도록 돕습니다.   │
│                                 │
│         ● ○ ○ ○                │  ← 진행 인디케이터
│                                 │
│         [   다음   ]            │  ← Primary CTA
└─────────────────────────────────┘
```

### Step별 카피
| Step | 헤드라인 | 서브카피 |
|------|---------|---------|
| 1/4 | 초진 대기 6개월, 변화가 기록되지 않습니다. | 본 앱은 진료 전 사전 문진을 AI와 함께 준비하도록 돕습니다. |
| 2/4 | 40분 진료, 20분은 과거력 청취에 소진됩니다. | 미리 정리해 두면 의사가 핵심을 빠르게 파악합니다. |
| 3/4 | 위기 순간에는 즉시 1393으로 연결됩니다. | 자살예방상담전화 / 응급의료 119 / 정신건강상담 1577-0199 |
| 4/4 | 본 앱은 진단·치료를 제공하지 않습니다. | AI는 환자의 정보를 구조화하고 요약합니다. 최종 판단은 의료진이 합니다. |

### 컴포넌트
| Component | Props | a11y |
|-----------|-------|------|
| `<OnboardingPager>` | `steps: Step[]`, `onComplete: () => void` | `accessibilityRole="adjustable"` |
| `<StepIndicator>` | `current: number`, `total: number` | "1단계 / 4단계 중" |
| `<PrimaryButton>` | `label`, `onPress`, `disabled?` | accessibilityRole="button" |
| `<SkipLink>` (text button) | `onPress` | "건너뛰기, 버튼" |

### 상호작용
- 좌우 스와이프 = 페이지 이동 (`PagerView` 또는 `react-native-pager-view`)
- "다음" 버튼 탭 = `pagerRef.setPage(+1)`
- 마지막 스텝 = "시작하기" 라벨, 탭 시 `AsyncStorage.set('hasSeenOnboarding', 'true')` + `navigation.replace('/login')`
- "건너뛰기" = 동일

---

## S-02. `/login`

| 항목 | 값 |
|------|---|
| Route | `/login` |
| Audience | guest |
| Auth | None |
| Linked FRs | FR-001 (환자 인증) |
| States | loading, error, success |
| Phase | 1a, Demo IN |

### 레이아웃
```
┌─────────────────────────────────┐
│                                 │
│         [로고]                  │
│         Neuro-Sync              │
│                                 │
│   ┌─────────────────────────┐   │
│   │ 이메일                  │   │
│   └─────────────────────────┘   │
│                                 │
│   ┌─────────────────────────┐   │
│   │ 비밀번호           [👁]  │   │
│   └─────────────────────────┘   │
│                                 │
│   [  로그인  ]                  │  ← Primary CTA, full-width
│                                 │
│   회원이 아니신가요? 가입하기     │  ← link
│                                 │
│   비밀번호를 잊으셨나요?         │  ← link (Phase 2)
│                                 │
└─────────────────────────────────┘
```

### 컴포넌트
| Component | Props | Validation | Microcopy |
|-----------|-------|-----------|-----------|
| `<EmailInput>` | `value`, `onChangeText`, `error?` | RFC 5322 | "이메일 형식을 한 번 더 확인해 주세요." |
| `<PasswordInput>` | `value`, `onChangeText`, `error?`, `visible: boolean` | 최소 12자 | "비밀번호는 12자 이상이에요." |
| `<PrimaryButton>` | `label='로그인'`, `loading?`, `disabled?` | — | loading 시 라벨 "로그인 중…" |
| `<TextLink>` | `label`, `to: Route` | — | — |

### 상태
| 상태 | UI | 트리거 |
|------|-----|--------|
| success | 로그인 성공 → `/home` replace | 200 OK |
| loading | Primary 버튼 스피너 + 입력창 disabled | 요청 중 |
| error (401 INVALID_CREDENTIALS) | 인라인 빨강 텍스트 "이메일 또는 비밀번호가 일치하지 않아요" | — |
| error (403 ACCOUNT_LOCKED) | 모달 "계정이 잠겼어요. 15분 후 다시 시도해 주세요" | 5회 실패 |
| error (403 ROLE_MISMATCH) | 모달 "본 앱은 환자 전용이에요. 의료진은 웹 대시보드를 이용해 주세요" | role != patient |
| error (네트워크) | 상단 빨강 배너 | NetInfo offline |

### 키보드
- iOS: `KeyboardAvoidingView behavior='padding'`
- Android: `behavior='height'`
- email 필드 `keyboardType='email-address'`, `autoCapitalize='none'`, `autoComplete='email'`
- password 필드 `secureTextEntry={!visible}`, `autoComplete='password'`
- Enter → 다음 필드 / 마지막 필드는 `onSubmitEditing` = 로그인

### Rate Limit (서버 측이지만 UI 반영)
- 분당 5회 — 클라이언트는 매 시도 후 1초 grace 추가하지 않음 (서버 권위)

---

## S-03. `/register`

| 항목 | 값 |
|------|---|
| Route | `/register` |
| Audience | guest |
| Auth | None |
| Linked FRs | FR-001 (4개 동의), FR-002 (프로필), FR-026 (위험 통보 동의), FR-034 (음성 동의, 옵션) |
| States | loading, error, success |
| Phase | 1a, Demo IN (FR-027 미성년은 Phase 2) |

3단계 stepper로 구성.

### Step 1/3 — 동의 (Consents)

```
┌─────────────────────────────────┐
│ ←  회원가입               1/3   │
│ ▰▰▰▰░░░░░░░░░░░  33%           │
├─────────────────────────────────┤
│                                 │
│   다음 항목에 동의해 주세요.      │
│                                 │
│  ┌───────────────────────────┐  │
│  │ ◯ 전체 동의               │  │  ← 선택사항 별도 표시
│  └───────────────────────────┘  │
│                                 │
│  ◯ [필수] 서비스 이용약관 [보기]  │
│  ◯ [필수] 개인정보 처리방침 [보기]│
│  ◯ [필수] 민감정보(의료) 수집 동의│
│         [상세보기]               │
│  ◯ [필수] 위험 신호 감지 시       │
│         통보 동의   [상세보기]   │
│  ◯ [선택] 음성 입력 사용 동의     │
│         [상세보기]               │
│                                 │
│         [   다음으로   ]        │  ← 4개 필수 모두 체크 시만 활성화
└─────────────────────────────────┘
```

#### 컴포넌트
| Component | Props | Microcopy |
|-----------|-------|-----------|
| `<ConsentCheckbox>` | `label`, `required: boolean`, `checked`, `onChange`, `onPressDetail` | 필수: `[필수]` prefix red |
| `<ConsentDetailSheet>` | `versionedHtml: string` | 약관 버전 표시 |
| `<PrimaryButton disabled={!allRequired}>` | — | — |

#### 동의 항목 상세
| 항목 | 필수 | API 필드 | 비고 |
|------|------|---------|------|
| 약관 | ✓ | `consents.tos` | tos_version 함께 |
| 개인정보 | ✓ | `consents.privacy` | privacy_version 함께 |
| 민감정보 | ✓ | `consents.sensitive` | PIPA §23 |
| 위험 통보 (FR-026) | ✓ (옵트인/아웃 양자택일) | `consents.riskNotification` | "옵트아웃 시 위험 감지 알림이 제한됩니다" 사이드노트 표시 |
| 음성 입력 (FR-034) | ✗ | (별도 후속 API 또는 inline) | 미동의 시 마이크 비활성화 안내 |

> 위험 통보 동의는 **체크박스 1개** 형태이되, 미체크 시 다음 버튼은 활성화되며 백엔드에 `riskNotification: false`로 전송 (정책상 옵트아웃 자체가 동의 행위).

### Step 2/3 — 프로필 (Profile)

```
┌─────────────────────────────────┐
│ ←  회원가입               2/3   │
│ ▰▰▰▰▰▰▰▰░░░░░░░ 66%            │
├─────────────────────────────────┤
│  이름                            │
│  ┌─────────────────────────┐    │
│  │                         │    │
│  └─────────────────────────┘    │
│                                 │
│  출생연도                        │
│  ┌─────────┐                    │
│  │ 1985 ▾  │                    │  ← Picker
│  └─────────┘                    │
│                                 │
│  성별                            │
│  [ 여성 ] [ 남성 ] [ 그 외 ]    │  ← Segmented
│                                 │
│  연락처 (휴대폰)                 │
│  ┌─────────────────────────┐    │
│  │ 010-                    │    │
│  └─────────────────────────┘    │
│                                 │
│  거주 지역                       │
│  ┌─────────────────────────┐    │
│  │ 시/도 ▾                 │    │
│  └─────────────────────────┘    │
│  ┌─────────────────────────┐    │
│  │ 시/군/구 ▾              │    │
│  └─────────────────────────┘    │
│                                 │
│  비상 연락처                     │
│  ┌─────────────────────────┐    │
│  │ 010-                    │    │
│  └─────────────────────────┘    │
│  ⓘ 위기 시 안내 또는 연락에 사용 │
│                                 │
│         [   다음으로   ]        │
└─────────────────────────────────┘
```

#### 입력 검증
| 필드 | 규칙 | Microcopy |
|------|------|-----------|
| 이름 | 1~30자, 공백 trim | "이름을 입력해 주세요" |
| 출생연도 | 1900~currentYear | "정확한 연도를 선택해 주세요" |
| 성별 | enum | — |
| 연락처 | E.164 (`+82-10-XXXX-XXXX` 변환) | "올바른 휴대폰 번호 형식이 아니에요" |
| 비상 연락처 | E.164, 본인 연락처와 동일 금지 | "본인 연락처와 다른 번호를 입력해 주세요" |
| 거주 지역 | 시/도 + 시/군/구 모두 필수 | "거주 지역을 선택해 주세요" |

#### 연령 분기 (FR-027, Phase 2 — Demo는 미적용)
- `currentYear - birthYear < 14` AND Phase 2 활성화 → Step 2 다음 버튼 클릭 시 "법정대리인 본인인증" 서브 스텝 추가
- Demo: 단순 안내 — "현재 데모 버전은 만 14세 이상만 지원합니다"

### Step 3/3 — 계정 (Account)

```
┌─────────────────────────────────┐
│ ←  회원가입               3/3   │
│ ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰ 100%          │
├─────────────────────────────────┤
│  이메일                          │
│  ┌─────────────────────────┐    │
│  │                         │    │
│  └─────────────────────────┘    │
│                                 │
│  비밀번호                        │
│  ┌─────────────────────────┐    │
│  │                    [👁]  │   │
│  └─────────────────────────┘    │
│  ▰▰▰▰░░░ 보통                  │  ← strength meter
│  • 12자 이상  ✓                 │
│  • 영문 대소문자 ✓              │
│  • 숫자 ✓                       │
│  • 특수문자 ✗                   │
│                                 │
│  비밀번호 확인                   │
│  ┌─────────────────────────┐    │
│  │                         │    │
│  └─────────────────────────┘    │
│                                 │
│  진료 예정 병원 (선택)           │
│  ┌─────────────────────────┐    │
│  │ 검색…                   │    │
│  └─────────────────────────┘    │
│                                 │
│         [   가입 완료   ]       │
└─────────────────────────────────┘
```

#### 비밀번호 정책 (PRD §4.5.2)
- 최소 12자
- 영문 대/소문자 + 숫자 + 특수문자
- strength meter: 0~4 점 (각 조건 1점)
- "가입 완료" 활성화 조건: 4/4 + 확인 일치

#### 에러 응답 매핑
| API Error | UI |
|-----------|-----|
| 400 INVALID_INPUT | 해당 필드 인라인 |
| 400 WEAK_PASSWORD | 비밀번호 필드 인라인 |
| 409 EMAIL_EXISTS | 이메일 필드 인라인 "이미 가입된 이메일이에요. [로그인하기]" |
| 422 CONSENT_REQUIRED | Step 1로 복귀 (모달 안내) |
| 422 GUARDIAN_CONSENT_REQUIRED | (Phase 2) 보호자 단계로 분기 |

---

## S-04. `/home`

| 항목 | 값 |
|------|---|
| Route | `/home` |
| Audience | patient |
| Auth | Required |
| Linked FRs | FR-003, FR-013 (리포트 상태) |
| States | loading, empty, error, success |
| Phase | 1a, Demo IN |

### 레이아웃 (성공 상태)
```
┌─────────────────────────────────┐
│  안녕하세요, 홍길동님           │  ← 타임 인사
│  오늘은 어떠신가요?             │
├─────────────────────────────────┤
│                                 │
│  ┌───────────────────────────┐  │
│  │ 진행 중인 사전 문진       │  │  ← (있을 때만) Resume card
│  │ 65% 완료 · 6/14 단계      │  │
│  │ [   이어서 진행   ]       │  │
│  └───────────────────────────┘  │
│                                 │
│  ┌───────────────────────────┐  │
│  │ 새 사전 문진 시작         │  │  ← Primary CTA
│  │ 약 15~20분 소요           │  │
│  │ [   문진 시작   ]         │  │
│  └───────────────────────────┘  │
│                                 │
│  ┌───────────────────────────┐  │
│  │ 최근 리포트 (지난주)      │  │  ← 완료된 리포트 카드
│  │ 의료진 전달 완료           │  │
│  │ 2026-05-30 제출           │  │
│  └───────────────────────────┘  │
│                                 │
│  ─────────────────────────────  │
│                                 │
│  ⚠️ 지금 도움이 필요해요         │  ← 안전 진입 (눈에 띄게)
│     [   응급 도움 받기   ]      │
│                                 │
├─────────────────────────────────┤
│  [🏠 홈] [🏥 병원] [⚙ 설정]    │  ← Bottom Tab
└─────────────────────────────────┘
```

### 상태
| 상태 | UI |
|------|-----|
| success (첫 진입, 세션 없음) | "새 사전 문진 시작" 카드만 노출 (empty 변형) |
| empty (전체 미사용 첫 진입) | 환영 메시지 + 가치 제안 1줄 + "문진 시작" CTA |
| in-progress (active session 1개) | Resume card 상단 노출 + 새 문진 카드 비활성 ("진행 중인 문진을 마쳐주세요") |
| report-pending | "AI가 의료진 전달 리포트를 만들고 있어요" 카드 + 상태 polling |
| report-ready | "리포트가 의료진에게 전달되었어요" 카드 |
| loading | 스켈레톤 카드 3개 |
| error | 인라인 에러 카드 + 재시도 버튼 |

### 컴포넌트
| Component | Props |
|-----------|-------|
| `<GreetingHeader>` | `userName`, `timeOfDay` |
| `<ResumeIntakeCard>` | `sessionId`, `progressPct`, `onResume` |
| `<StartIntakeCard>` | `onStart`, `estimatedMinutes: 15` |
| `<ReportStatusCard>` | `reportId`, `status`, `submittedAt` |
| `<EmergencyEntryButton>` | `onPress` (state-danger 색) |
| `<BottomTabBar>` | tabs: [home, hospitals, settings] |

### 핵심 카피
| 상황 | 카피 |
|------|------|
| 아침 (5~12시) | "좋은 아침이에요" |
| 낮 (12~18시) | "안녕하세요" |
| 저녁 (18~22시) | "오늘 하루 어떠셨어요?" |
| 밤 (22~5시) | "늦은 시간까지 수고하셨어요" |
| 첫 진입 | "환영합니다. 문진을 시작하면 의료진이 더 잘 도와드릴 수 있어요." |
| 응급 진입 라벨 | "지금 도움이 필요해요" (1393/119 안내 진입) |

---

## S-05. `/intake/chat` ★ Critical Screen

| 항목 | 값 |
|------|---|
| Route | `/intake/chat` |
| Audience | patient |
| Auth | Required |
| Linked FRs | FR-004 (AI 채팅), FR-005 (위험 감지), FR-033 (STT), FR-035 (편집/명시 전송), FR-037 (폴백) |
| States | loading, error, success, **recording**, **transcribing**, **paused-by-risk** |
| Phase | 1a (Safety) + 1b (Chat/STT), Demo IN |

### 레이아웃 (success — 일반 대화 중)
```
┌─────────────────────────────────┐
│ ←  사전 문진          [그만하기]│
│ ▰▰▰▰▰▰▰░░░░░░░░  45%           │
├─────────────────────────────────┤
│                                 │
│  ┌─────────────────────────┐    │
│  │ AI · 안녕하세요 길동님,  │    │  ← AI 말풍선 (좌)
│  │ 오늘은 어떤 점이 가장    │    │
│  │ 힘드신가요?              │    │
│  └─────────────────────────┘    │
│                                 │
│                ┌──────────────┐ │
│                │ 요즘 2주째   │ │  ← 사용자 말풍선 (우)
│                │ 잠을 못 자고 │ │
│                │ 우울해요.    │ │
│                └──────────────┘ │
│                          21:34  │
│                                 │
│  ┌─────────────────────────┐    │
│  │ AI · 잠을 못 주무신 지   │    │
│  │ 얼마나 되셨어요? ▋       │    │  ← 스트리밍 cursor
│  └─────────────────────────┘    │
│                                 │
├─────────────────────────────────┤
│  ┌──────────────────────┐ [🎤]  │  ← 입력창 + 마이크
│  │ 메시지 입력…         │  [↑] │
│  └──────────────────────┘       │
└─────────────────────────────────┘
```

### State Matrix
| 상태 | 트리거 | UI 변화 |
|------|--------|--------|
| `success.idle` | 기본 | 입력창 활성, 마이크 노출 |
| `success.sending` | 사용자 전송 | 메시지 optimistic 표시, 입력창 dim |
| `success.streaming` | `ai:token` 수신 | AI 말풍선 토큰 append + blinking cursor |
| `loading.initial` | 화면 진입 | 헤더 스켈레톤 + 입력창 disabled |
| `error.ws-disconnected` | WS close | 상단 빨강 배너 "연결이 끊겼어요 [다시 연결]" |
| `recording` | 마이크 long press | 입력창 영역 전체가 파형/타이머/취소힌트로 전환 |
| `transcribing` | 녹음 종료 → 업로드 중 | 마이크 자리에 스피너 + "변환 중…" 텍스트, 입력창 disabled |
| `paused-by-risk` | `risk:detected` 수신 | 입력창 즉시 disabled + 햅틱 + `/emergency` modal push |

### 컴포넌트
| Component | Props | 동작 |
|-----------|-------|-----|
| `<ChatHeader>` | `progressPct`, `onClose` | 그만하기 → 확인 모달 |
| `<MessageList>` | `messages: Message[]`, `streamingMessageId?` | `FlatList` 역순 + auto-scroll on new |
| `<MessageBubble>` | `role: 'user'|'ai'|'system'`, `content`, `inputModality?: 'text'|'voice'` | voice 메시지엔 작은 🎤 아이콘 |
| `<StreamingCursor>` | `visible` | blinking line |
| `<MessageComposer>` | `value`, `onChangeText`, `onSend`, `onStartRecording`, `onCancelRecording`, `recordingState` | 멀티 상태 컴포넌트 |
| `<MicButton>` | `state: 'idle'|'recording'|'transcribing'|'disabled'`, `onLongPressIn`, `onLongPressOut` | 56dp, 햅틱 |
| `<RecordingOverlay>` | `elapsedMs`, `waveformData`, `cancelHover` | 파형 24ch, 시간 mm:ss |
| `<RetryAfterSTTBanner>` | `reason: 'low-conf'|'silent'|'noise'` | 인라인 안내 |
| `<WSConnectionBanner>` | `connected: boolean`, `onRetry` | 상단 dismissable |

### 마이크로카피 (상태별)
| 상태 | 카피 |
|------|------|
| 입력창 placeholder | "메시지를 입력하거나 마이크를 길게 눌러 말씀해 주세요" |
| 음성 동의 미동의 시 (마이크 탭) | 바텀시트: "음성 입력을 사용하려면 설정에서 동의가 필요해요. [설정으로 이동]" |
| 마이크 권한 거부 시 | 바텀시트: "마이크 권한이 꺼져 있어요. [설정 열기] [키보드로 입력]" |
| 녹음 중 | 상단: "말씀해 주세요" / 하단 힌트: "↑ 위로 드래그하면 취소돼요" |
| 녹음 30초 도달 | 토스트: "녹음은 최대 30초예요. 변환 중…" |
| 변환 중 | 입력창 placeholder: "변환 중이에요…" |
| 변환 완료 후 (FR-035) | 입력창에 텍스트 자동 채움 + 토스트: "변환됐어요. 확인 후 보내주세요" |
| 신뢰도 < 0.6 (FR-037) | 인라인: "잘 들리지 않았어요. 다시 말씀해 주시거나 직접 입력해 주세요" |
| STT 5xx/timeout (FR-037) | 토스트: "음성 변환이 지연되고 있어요. 키보드로 입력해 주세요" + 입력창 포커스 |
| 네트워크 끊김 | 상단 배너 + 입력창 disabled "연결되면 자동으로 보내드릴게요" |
| 그만하기 모달 | "지금까지 입력한 내용은 자동 저장되어 있어요. 나중에 이어서 진행할 수 있어요. [이어서 진행] [그만하기]" |
| 위험 감지 직후 (`/emergency`로 떠나기 전 0.3s) | 햅틱 + 무 텍스트 (즉시 화면 전환) |

### WebSocket 이벤트 처리
| 수신 이벤트 | 처리 |
|-----------|-----|
| `auth:connected` | 헤더 진행률 갱신 |
| `auth:refresh_required` | 백그라운드 토큰 갱신 + `auth:refresh` 송신 |
| `ai:token` | 마지막 AI 말풍선에 append |
| `ai:complete` | 스트리밍 cursor 제거 + 진행률 업데이트 |
| `risk:detected` (level=high/critical) | 햅틱 heavy + Navigation.navigate('/emergency', { riskEventId }) |
| `risk:detected` (level=medium) | 노란 인라인 배너 + 대화 지속 |
| `error` | 에러 토스트 + 입력 재활성 |

### 송신 페이로드 (FR-033 idempotency)
```typescript
ws.send({
  type: 'user:message',
  payload: {
    content: text,
    inputModality: 'text' | 'voice',
    sttTranscriptionId?: 'stt_xxx',  // voice 시
    idempotencyKey: uuid(),          // 재시도 중복 방지
    sentAt: ISO8601,
  }
});
```

### 키보드 회피
- 컴포저는 `KeyboardAvoidingView`로 키보드 위에 부착
- 키보드 노출 시 메시지 리스트는 마지막 메시지 위치로 auto-scroll

### a11y
- 메시지 말풍선 `accessibilityRole="text"`, AI 메시지는 `accessibilityLabel="AI 메시지: ..."`로 명시
- 마이크 버튼 `accessibilityHint="길게 눌러 음성 입력"`, recording 중 "녹음 중. 손을 떼면 종료됩니다"

---

## S-06. `/intake/phq9`

| 항목 | 값 |
|------|---|
| Route | `/intake/phq9` |
| Audience | patient |
| Auth | Required |
| Linked FRs | FR-006 |
| States | loading, error, success |
| Phase | 1b, Demo IN |

### 레이아웃
```
┌─────────────────────────────────┐
│ ←  사전 문진          [그만하기]│
│ ▰▰▰▰▰▰▰▰▰░░░░░  60%             │  ← Chat 70% 끝 + PHQ-9 진입
├─────────────────────────────────┤
│  PHQ-9   3 / 9                  │  ← 문항 카운터
│                                 │
│  지난 2주 동안,                  │
│  다음 항목이 얼마나 자주          │
│  당신을 괴롭혔습니까?            │
│                                 │
│  3. 잠들기 어렵거나 자주          │  ← 문항
│     깨거나, 너무 많이 잠.        │
│                                 │
│  ┌─────────────────────────┐    │
│  │ ◯ 전혀 없음 (0)         │    │
│  ├─────────────────────────┤    │
│  │ ◯ 며칠 동안 (1)         │    │
│  ├─────────────────────────┤    │
│  │ ● 일주일 이상 (2)       │    │  ← selected
│  ├─────────────────────────┤    │
│  │ ◯ 거의 매일 (3)         │    │
│  └─────────────────────────┘    │
│                                 │
│         [이전]   [다음]          │
└─────────────────────────────────┘
```

### 9 문항 (K-PHQ-9 한국어판)
> 라이선스: PRD §8.2에서 해결된 것으로 기재 (제안서 단계 확정). 본 spec은 문항 번호만 명시, 정확한 문구는 라이선스 약정 텍스트 그대로 사용.

### 컴포넌트
| Component | Props |
|-----------|-------|
| `<QuestionnaireHeader>` | `current`, `total`, `instrument: 'PHQ9'` |
| `<QuestionText>` | `text`, `weekFraming: '지난 2주 동안'` |
| `<LikertOptions>` | `options: 4`, `value: 0-3`, `onChange` |
| `<NavButtons>` | `onPrev`, `onNext`, `nextDisabled` |

### 응답 저장
- 매 문항 응답 즉시 로컬 state + AsyncStorage 저장
- 9문항 완료 시 `POST /api/v1/sessions/:id/questionnaires` 호출 후 GAD-7로 자동 전환
- 응답 transit error 시 로컬 보존 + 재시도 큐

### 컴플라이언스 카피 (PRD §A 원칙)
- 화면 하단: "본 결과는 의료진 참고용이며, 진단이 아닙니다."

### 점수 표시 (Demo)
- 환자 본인에게는 **총점/severity 미표시** (PRD `severity는 의료진 참고용`)
- 완료 시 "응답이 저장되었어요"만 표시

---

## S-07. `/intake/gad7`

| 항목 | 값 |
|------|---|
| Route | `/intake/gad7` |
| Audience | patient |
| Auth | Required |
| Linked FRs | FR-007 |
| States | loading, error, success |
| Phase | 1b, Demo IN |

PHQ-9과 동일 구조, 7문항 4점 척도. `instrument='GAD7'`. 헤더 진행률은 `chat→phq9→gad7`이므로 80%대 표시.

> 라이선스: GAD-7 한국어판 동일 — PRD §8.2 해결 완료 항목.

완료 시 `/intake/documents` 자동 전환.

---

## S-08. `/intake/documents`

| 항목 | 값 |
|------|---|
| Route | `/intake/documents` |
| Audience | patient |
| Auth | Required |
| Linked FRs | FR-008, FR-009 (OCR), FR-028 (업로드 보안) |
| States | loading, empty, error, success |
| Phase | **Phase 2 정식** / Demo는 **Stub 화면** |

### Demo Stub 레이아웃
```
┌─────────────────────────────────┐
│ ←  사전 문진          [그만하기]│
│ ▰▰▰▰▰▰▰▰▰▰▰▰▰░░ 85%             │
├─────────────────────────────────┤
│                                 │
│         [문서 아이콘]            │
│                                 │
│   타 병원 진단서·처방전을         │
│   업로드할 수 있어요.            │
│                                 │
│   이 기능은 정식 버전에서         │
│   제공됩니다.                    │
│                                 │
│   문서가 없어도 진행할 수 있어요.  │
│                                 │
│         [건너뛰고 다음으로]      │
│                                 │
└─────────────────────────────────┘
```

### Phase 2 정식 레이아웃 (참고)
```
┌─────────────────────────────────┐
│  업로드한 문서                  │
│                                 │
│  ┌───────────────────────────┐  │
│  │ [thumb] 진단서_김선영.pdf │  │
│  │ 2.4MB · OCR 처리 중       │  │
│  │ [상태] [삭제]              │  │
│  └───────────────────────────┘  │
│                                 │
│  [+ 문서 추가]                  │
│   · 사진 촬영                   │
│   · 갤러리에서 선택              │
│   · 파일 (PDF)                  │
│                                 │
│  ⓘ 진단서·처방전·검사결과 등     │
│     20MB 이내 (JPG/PNG/PDF)     │
│                                 │
│         [다음으로]               │
└─────────────────────────────────┘
```

### Phase 2 컴포넌트 (참고)
| Component | Props |
|-----------|-------|
| `<DocumentCard>` | `id`, `type`, `filename`, `sizeBytes`, `ocrStatus`, `onDelete` |
| `<UploadOptionsSheet>` | `onCamera`, `onGallery`, `onFile` |
| `<FileTypeFilter>` | MIME whitelist enforce (FR-028) |

---

## S-09. `/intake/submit`

| 항목 | 값 |
|------|---|
| Route | `/intake/submit` |
| Audience | patient |
| Auth | Required |
| Linked FRs | FR-010 |
| States | loading, error, success |
| Phase | 1b, Demo IN |

### 레이아웃
```
┌─────────────────────────────────┐
│ ←  최종 확인          [그만하기]│
│ ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰ 100%           │
├─────────────────────────────────┤
│  의료진에게 전달할 내용을 확인해   │
│  주세요.                         │
│                                 │
│  ┌───────────────────────────┐  │
│  │ AI 사전 대화              │  │
│  │ 약 12개 메시지 교환        │  │
│  │ 주요 호소: 수면, 우울      │  │
│  └───────────────────────────┘  │
│                                 │
│  ┌───────────────────────────┐  │
│  │ PHQ-9                      │  │
│  │ 9문항 응답 완료            │  │
│  └───────────────────────────┘  │
│                                 │
│  ┌───────────────────────────┐  │
│  │ GAD-7                      │  │
│  │ 7문항 응답 완료            │  │
│  └───────────────────────────┘  │
│                                 │
│  ┌───────────────────────────┐  │
│  │ 업로드 문서                │  │
│  │ 0건 (선택 사항)            │  │
│  └───────────────────────────┘  │
│                                 │
│  ⚠️ 안내                         │
│  본 문진은 의료진의 진료를        │
│  돕기 위한 사전 정보 수집입니다.   │
│  AI는 진단이나 치료를 제공하지     │
│  않으며, 최종 판단은 의료진이     │
│  수행합니다.                     │
│                                 │
│         [   최종 제출   ]        │
│                                 │
│  제출 후에는 수정이 어려워요      │
└─────────────────────────────────┘
```

### 컴포넌트
| Component | Props |
|-----------|-------|
| `<SummaryCard>` | `title`, `subtitle`, `onEdit?` |
| `<ComplianceNotice>` | Appendix C 카피 고정 |
| `<PrimaryButton label='최종 제출'>` | `loading`, `disabled={!allCompleted}` |

### 누락 처리
- 임의의 카드가 미완성 (예: chat 70% 미만) → 해당 카드 상단에 노란 배지 "추가 응답이 도움돼요 [이어서 진행]"
- 필수가 비어 있으면 "최종 제출" 비활성

### 제출 후
- 202 Accepted 수신 → `navigation.replace('/report/status', { reportId, sessionId })`
- 에러 시 인라인 모달 + 재시도

---

## S-10. `/emergency` ★ Critical Safety Screen

| 항목 | 값 |
|------|---|
| Route | `/emergency` |
| Audience | patient |
| Auth | Required |
| Linked FRs | FR-011, FR-022 (risk_event), FR-026 (통보) |
| States | success (즉시 노출) |
| Phase | 1a, Demo IN |

### 레이아웃
```
┌─────────────────────────────────┐
│  ⚠️ 지금 당신의 안전이           │  ← Red banner background
│     가장 중요해요                │
│                                 │
│  도움을 받을 수 있는 곳이         │
│  여기 있어요.                    │
│                                 │
│  ┌───────────────────────────┐  │
│  │ 📞  1393                   │  │  ← XL CTA, full-width
│  │     자살예방상담전화        │  │
│  │     24시간 무료 상담        │  │
│  │ [   전화 걸기   ]          │  │
│  └───────────────────────────┘  │
│                                 │
│  ┌───────────────────────────┐  │
│  │ 🚑  119                    │  │
│  │     응급의료                │  │
│  │ [   전화 걸기   ]          │  │
│  └───────────────────────────┘  │
│                                 │
│  ┌───────────────────────────┐  │
│  │ 📞  1577-0199              │  │
│  │     정신건강상담전화        │  │
│  │ [   전화 걸기   ]          │  │
│  └───────────────────────────┘  │
│                                 │
│  ┌───────────────────────────┐  │
│  │ 등록된 비상 연락처          │  │
│  │ ○○○ 010-XXXX-XXXX         │  │
│  │ [   전화 걸기   ]          │  │
│  └───────────────────────────┘  │
│                                 │
│  ─────────────────────────────  │
│                                 │
│  지금 혼자 계신가요?             │  ← 안전 확인 질문
│  [   네, 혼자예요   ]           │
│  [   아니요, 같이 있어요   ]    │
│                                 │
│  ─────────────────────────────  │
│                                 │
│  [ 안전한 곳에 있어요 → 닫기 ]   │  ← 유일한 종료 경로
└─────────────────────────────────┘
```

### 강제 사항
- 백 제스처/하드웨어 백 버튼 **차단** (Flow C.2 참조)
- 어떤 화면에서든 `risk:detected` 수신 시 `navigation.navigate('Emergency', ...)` 즉시 push (Modal stack root)
- 첫 진입 시 햅틱 heavy 1회

### 컴포넌트
| Component | Props |
|-----------|-------|
| `<EmergencyHeader>` | banner with red background (state-danger) |
| `<HotlineCard>` | `icon`, `number`, `name`, `subtitle?`, `onCall` |
| `<SafetyQuestion>` | `question`, `onAnswer: (alone: boolean) => void` |
| `<EmergencyExitButton>` | 라벨 "안전한 곳에 있어요" |

### 동작
| 버튼 | 동작 |
|------|------|
| 1393/119/1577-0199 전화 | `Linking.openURL('tel:1393')` + `PATCH /risk_events/:id { interaction: 'called_1393' }` |
| 비상 연락처 전화 | 동일 + 등록 안 된 경우 카드 미표시 |
| 안전 질문 응답 | `PATCH /risk_events/:id { aloneStatus: bool, acknowledgedAt }` |
| "안전한 곳에 있어요" | 모달 닫고 직전 화면 복귀. `risk_event.status` 변경 없음 (의료진 확인 후 resolved) |

### 데이터 (서버 → 클라이언트)
화면 진입 시 `risk_events.notified_to` 정책에 따라:
- FR-026 동의 시 (high/critical): 진입 직후 "비상 연락처에 안내를 보냈어요" 토스트 (Phase 2 실 SMS)
- 동의 거부 시: 화면 노출만, 통보 안 함 — 토스트 없음

### Demo Stub 처리
- 실 SMS 미발송 (Phase 2). 대신 "비상 연락처에 안내가 발송됩니다 (정식 버전)" 안내 회색 배지

### 마이크로카피
- 헤드라인: "지금 당신의 안전이 가장 중요해요"
- 1393 부제: "24시간 무료 · 익명 상담 가능"
- 119 부제: "응급실 이송 필요 시"
- 1577-0199 부제: "정신건강 위기 상담"
- 안전 질문 (PRD §2.2): "지금 혼자 계신가요?"
- 종료 라벨: "안전한 곳에 있어요" (단정 표현 회피)

---

## S-11. `/hospitals`

| 항목 | 값 |
|------|---|
| Route | `/hospitals` |
| Audience | patient |
| Auth | Required |
| Linked FRs | FR-012, FR-025 (증상 추천, Phase 3) |
| States | loading, empty, error, success |
| Phase | **Phase 2 정식** / Demo는 Stub |

### Demo Stub 레이아웃
```
┌─────────────────────────────────┐
│  병원 찾기                       │
├─────────────────────────────────┤
│                                 │
│         [지도 아이콘]            │
│                                 │
│   가까운 정신건강의학과를         │
│   찾을 수 있어요.                │
│                                 │
│   이 기능은 정식 버전에서         │
│   제공됩니다.                    │
│                                 │
│   응급 상황이라면                 │
│   [   119 전화 걸기   ]          │
│                                 │
├─────────────────────────────────┤
│  [🏠 홈] [🏥 병원] [⚙ 설정]    │
└─────────────────────────────────┘
```

### Phase 2 정식 레이아웃 (참고)
```
┌─────────────────────────────────┐
│  병원 찾기                       │
│  ─────────────────────────────  │
│  [지역: 서울 ▾]  [응급 ☐]       │
│                                 │
│   [지도 영역 - 핀들]             │
│   현재 위치 ⊙                   │
│                                 │
│  ─────────────────────────────  │
│  목록 (12개)                    │
│                                 │
│  ┌───────────────────────────┐  │
│  │ ○○○ 신경정신과의원         │  │
│  │ 서울 강남구 역삼동…        │  │
│  │ 02-XXX-XXXX               │  │
│  │ 1.2km · 야간진료 가능      │  │
│  │ [📞 전화] [길찾기]         │  │
│  └───────────────────────────┘  │
│  ...                            │
└─────────────────────────────────┘
```

### 권한 (Phase 2)
- 위치 권한 요청 첫 진입 — denied 시 `empty` + "지역 선택" 폴백
- 거부 변경 시 안내: "정확한 검색을 위해 위치 권한이 필요해요. [설정 열기] [지역 선택]"

---

## S-12. `/report/status`

| 항목 | 값 |
|------|---|
| Route | `/report/status` |
| Audience | patient |
| Auth | Required |
| Linked FRs | FR-013, FR-018 (생성 큐), FR-014 알림 (Phase 2) |
| States | loading, error, success |
| Phase | 1b, Demo IN |

### 상태 변형
| 상태 | UI |
|------|-----|
| `report_generating` | 로딩 일러스트 + "AI가 의료진 전달 리포트를 만들고 있어요" + 카운트다운 "약 30초 소요" + 진행 막대 (estimate 기반) |
| `report_ready` | 체크 아이콘 + "리포트가 의료진에게 전달될 준비가 되었어요" + "홈으로" CTA |
| `report_failed` | 인라인 에러 + "다시 생성 요청" 버튼 (수동 트리거 — Phase 2) |

### 레이아웃 (생성 중)
```
┌─────────────────────────────────┐
│ ←  리포트 상태                  │
├─────────────────────────────────┤
│                                 │
│         [로딩 일러스트]          │
│                                 │
│   AI가 의료진 전달 리포트를       │
│   만들고 있어요.                 │
│                                 │
│   약 30초 소요됩니다.            │
│                                 │
│   ▰▰▰▰▰▰░░░░░░░  18 / 30s      │
│                                 │
│   ─────────────────────────     │
│                                 │
│   리포트에 포함되는 내용:         │
│   ✓ 주호소 및 현병력             │
│   ✓ PHQ-9, GAD-7 점수            │
│   ✓ 의료진 확인 필요 사항         │
│   ✓ 원문 근거 인용                │
│                                 │
│   완료되면 알림을 받을 수 있어요. │  ← Phase 2
│   [   알림 받기   ]              │
│                                 │
└─────────────────────────────────┘
```

### Polling 전략
- 진입 직후 `GET /api/v1/sessions/:id/report` 호출 (또는 SSE)
- `status='generating'` → 3초 간격 polling, 최대 60초
- 60초 초과 시 "예상보다 오래 걸리고 있어요. 잠시 후 알림을 보내드릴게요" 안내 + 홈 복귀 허용

### 환자에게 노출되는 정보
- **리포트 본문 미노출** (의료진 전용)
- 환자에게는 "전달 준비 완료" 상태와 항목 카운트만

---

## S-13. `/settings`

| 항목 | 값 |
|------|---|
| Route | `/settings` |
| Audience | patient |
| Auth | Required |
| Linked FRs | FR-002 (프로필 수정), FR-026/034 (동의 관리), FR-029 (탈퇴, Phase 2), FR-014 알림 (Phase 2) |
| States | loading, error, success |
| Phase | 1a (프로필/동의/로그아웃) + Phase 2 (나머지), Demo IN (핵심만) |

### 레이아웃
```
┌─────────────────────────────────┐
│  설정                           │
├─────────────────────────────────┤
│  ┌───────────────────────────┐  │
│  │ 홍길동                    │  │  ← 프로필 카드
│  │ contact@example.com       │  │
│  │ [   프로필 수정   ]       │  │
│  └───────────────────────────┘  │
│                                 │
│  개인정보 및 동의               │
│  ─────────────────────────────  │
│  · 동의 관리              >    │  ← FR-026, FR-034
│  · 약관 / 개인정보 처리방침 >  │
│  · 데이터 다운로드 (Phase 4) >  │
│                                 │
│  앱 설정                        │
│  ─────────────────────────────  │
│  · 알림 (Phase 2)         >    │
│  · 음성 입력 사용  ●      ON   │  ← Toggle
│  · 변환 즉시 삭제  ○      OFF │  ← FR-036 옵션
│                                 │
│  지원                           │
│  ─────────────────────────────  │
│  · 자주 묻는 질문         >    │
│  · 문의하기               >    │
│  · 안전 도움말 (1393/119) >    │
│                                 │
│  계정                           │
│  ─────────────────────────────  │
│  · 로그아웃                    │
│  · 회원 탈퇴 (Phase 2)         │
│                                 │
│  v0.1.0 (Demo)                 │
├─────────────────────────────────┤
│  [🏠 홈] [🏥 병원] [⚙ 설정]    │
└─────────────────────────────────┘
```

### 동의 관리 서브 화면

```
┌─────────────────────────────────┐
│ ←  동의 관리                    │
├─────────────────────────────────┤
│  필수 동의 (가입 시 수집)       │
│  ─────────────────────────────  │
│  · 서비스 이용약관    [내용보기] │  ← 변경 불가
│  · 개인정보 처리방침  [내용보기] │
│  · 민감정보 수집      [내용보기] │
│                                 │
│  변경 가능한 동의               │
│  ─────────────────────────────  │
│  위험 통보 동의 (FR-026)        │
│  ●━━━━ 옵트인                  │
│  ⓘ 위험 감지 시 비상 연락처에   │
│     안내를 보내도록 허용합니다.  │
│                                 │
│  음성 입력 동의 (FR-034)        │
│  ●━━━━ 옵트인                  │
│  ⓘ 음성 입력을 위해 녹음한       │
│     오디오는 48시간 내 삭제됩니다│
│                                 │
└─────────────────────────────────┘
```

### 컴포넌트
| Component | Props |
|-----------|-------|
| `<ProfileCard>` | `name`, `email`, `onEdit` |
| `<SettingsSection>` | `title`, `items` |
| `<SettingsRow>` | `label`, `icon?`, `right: 'arrow'|'toggle'|'text'`, `onPress` |
| `<ConsentToggle>` | `type`, `value`, `onChange`, `disabled?` (필수는 disabled) |
| `<DangerRow>` | `label='회원 탈퇴'` red |

### 동의 변경 모달 카피
| 동의 항목 | 옵트아웃 시 경고 |
|-----------|---------------|
| 위험 통보 (FR-026) | "옵트아웃 시 위험 감지 알림이 환자 본인에게만 표시되며, 비상 연락처/의료진에게 전달되지 않습니다. 계속하시겠습니까?" |
| 음성 입력 (FR-034) | "음성 입력이 비활성화됩니다. 보관 중인 원본 오디오가 있다면 48시간 내 자동 삭제됩니다. 계속하시겠습니까?" |
| 변환 즉시 삭제 (FR-036) | "변환 완료 시점에 원본 오디오를 즉시 삭제합니다 (재변환 불가). 적용하시겠습니까?" |

### 로그아웃
- 진행 중 세션 (`status='in_progress'`) 있으면 모달: "진행 중인 문진이 있어요. 저장 후 로그아웃 [저장 후 로그아웃] [취소]"
- 토큰 폐기 + AsyncStorage clear (단 `hasSeenOnboarding`은 유지) + `/login` replace

---

# 부록 A. 상태 카피 마스터 표 (전체 13 화면)

| 화면 | loading | empty | error | success | 추가 상태 |
|------|---------|-------|-------|---------|----------|
| onboarding | — | — | — | 4 step 순차 노출 | — |
| login | "로그인 중…" | — | "이메일 또는 비밀번호가 일치하지 않아요" | `/home` replace | account-locked, role-mismatch |
| register | "처리 중…" | — | 필드 인라인 + 모달(이메일 중복) | `/home` replace | guardian-required (Phase 2) |
| home | 스켈레톤 카드 | "진료 전 문진을 시작해 주세요" | "잠시 후 다시 시도해 주세요" | 카드 노출 | in-progress, report-pending, report-ready |
| intake/chat | 초기 WS 연결 스피너 | — | "연결이 끊겼어요 [다시 연결]" | 메시지 스트리밍 | recording, transcribing, paused-by-risk |
| intake/phq9 | — | — | 응답 저장 실패 | 다음 문항 자동 전환 | — |
| intake/gad7 | — | — | 동일 | 동일 | — |
| intake/documents | 업로드 진행률 (Phase 2) | "업로드한 문서가 없어요" | "업로드 실패 [다시 시도]" | 카드 목록 | demo-stub |
| intake/submit | "제출 중…" | — | "제출 실패 [다시 시도]" | `/report/status` replace | partial (누락 항목 경고) |
| emergency | — | — | — | 핫라인 노출 | — (전화 실패 시 토스트) |
| hospitals | 위치 / 검색 중 | "주변 병원을 찾을 수 없어요" | "위치 권한이 필요해요" | 지도 + 목록 | demo-stub |
| report/status | 진행 막대 + 카피 | — | "다시 시도" 버튼 | 완료 카드 | generating-overdue |
| settings | — | — | 변경 실패 토스트 | 항목 노출 | logout-confirm, consent-warning |

---

# 부록 B. 컴포넌트 인벤토리 (요약)

`/implement` 단계 RN 컴포넌트 트리 도출 입력.

## B.1 공통 (Shared)
- `<SafeScreen>` (SafeAreaView + 배경)
- `<KeyboardSafeView>` (KeyboardAvoidingView 래퍼)
- `<PrimaryButton>`, `<SecondaryButton>`, `<TextLink>`, `<DangerButton>`
- `<TextInput>`, `<PasswordInput>`, `<EmailInput>`, `<PhoneInput>`, `<RegionPicker>`
- `<Sheet>` (bottom sheet 베이스)
- `<Modal>`, `<ConfirmModal>`
- `<Toast>` (auto-dismiss 3s)
- `<Banner>` (offline, error, info — dismissable)
- `<ProgressBar>`, `<StepIndicator>`, `<SkeletonCard>`
- `<EmptyState>` (icon + 1줄 텍스트 + CTA)
- `<BottomTabBar>` (home/hospitals/settings)

## B.2 도메인 (Domain)
- `<OnboardingPager>`, `<StepIndicator>`
- `<ConsentCheckbox>`, `<ConsentToggle>`, `<ConsentDetailSheet>`
- `<GreetingHeader>`, `<ResumeIntakeCard>`, `<StartIntakeCard>`, `<ReportStatusCard>`, `<EmergencyEntryButton>`
- `<ChatHeader>` (progress + close), `<MessageList>`, `<MessageBubble>`, `<StreamingCursor>`, `<MessageComposer>`, `<MicButton>`, `<RecordingOverlay>`, `<RetryAfterSTTBanner>`, `<WSConnectionBanner>`
- `<QuestionnaireHeader>`, `<QuestionText>`, `<LikertOptions>`, `<NavButtons>`
- `<DocumentCard>`, `<UploadOptionsSheet>` (Phase 2)
- `<SummaryCard>`, `<ComplianceNotice>`
- `<EmergencyHeader>`, `<HotlineCard>`, `<SafetyQuestion>`, `<EmergencyExitButton>`
- `<HospitalListCard>`, `<HospitalMap>` (Phase 2)
- `<ProfileCard>`, `<SettingsSection>`, `<SettingsRow>`, `<DangerRow>`

## B.3 라이브러리 권장
- Navigation: `@react-navigation/native` + `native-stack` + `bottom-tabs` + `material-top-tabs` (옵션)
- 상태: React Query (서버 상태) + Zustand 또는 Context (UI 상태)
- 폼: `react-hook-form` + `zod`
- 미디어: `expo-av` (녹음) — Expo 또는 RN CLI 일관성에 따라
- WebSocket: 자체 클래스 + reconnect with exponential backoff
- 권한: `react-native-permissions`
- 햅틱: `expo-haptics` 또는 `react-native-haptic-feedback`
- 보안 저장: `expo-secure-store` (token), `AsyncStorage` (비민감)

---

# 부록 C. Phase별 화면 가용성 매트릭스

| 화면 | Phase 1a | Phase 1b | Demo Polish | Phase 2 | Phase 3+ |
|------|---------|---------|------------|--------|---------|
| onboarding | ✓ | ✓ | ✓ | ✓ | ✓ |
| login | ✓ | ✓ | ✓ | ✓ | ✓ |
| register | ✓ (4개 동의) | ✓ | ✓ | + FR-027 미성년 | ✓ |
| home | ✓ (기본) | ✓ (Resume) | ✓ | + 알림 카운트 | ✓ |
| intake/chat | △ (Safety만) | ✓ (AI 채팅 + STT) | ✓ | + 컨텍스트 보존(FR-032) | ✓ |
| intake/phq9 | ✗ | ✓ | ✓ | ✓ | ✓ |
| intake/gad7 | ✗ | ✓ | ✓ | ✓ | ✓ |
| intake/documents | ✗ | △ (Stub) | △ (Stub) | ✓ (FR-008/9, OCR) | ✓ |
| intake/submit | ✗ | ✓ | ✓ | ✓ | ✓ |
| emergency | ✓ (UI) | ✓ | ✓ | + 실 SMS (FR-026) | + 외부 딥링크 |
| hospitals | ✗ | △ (Stub) | △ (Stub) | ✓ (FR-012 정적) | + 심평원 API |
| report/status | ✗ | ✓ | ✓ | + 알림 | ✓ |
| settings | ✓ (프로필/동의/로그아웃) | ✓ | ✓ | + 탈퇴/알림 | ✓ |

> △ = 화면 존재하되 Stub 또는 부분 기능
