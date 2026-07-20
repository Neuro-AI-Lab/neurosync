# 실기기 Expo Go 실행 가이드

Neuro-Sync 모바일 앱(`apps/mobile`)을 **내 폰의 Expo Go**로 띄워서 보는 방법.

- **Expo SDK 54** (React Native 0.81 · expo-router 6). 실기기 Expo Go는 최신(SDK 54)만
  설치되므로 이 버전이어야 폰에서 열립니다.
- 네이티브 빌드가 필요 없습니다 — 코드만 QR로 불러옵니다.
- 기본은 **MOCK 모드**(서버 없이 화면 흐름 확인). 실서버를 붙이려면 §4를 참고하세요.

---

## 0. 준비물 (1회)

| 항목 | 확인 |
|---|---|
| **폰에 Expo Go 설치** | App Store / Play Store에서 "Expo Go" |
| **맥에 Node 20+** | `node -v` |
| **pnpm 9+** | `pnpm -v` (없으면 `npm i -g pnpm`) |
| **의존성 설치** | 레포 루트에서 `pnpm install` (최초 1회) |
| **폰과 맥이 같은 Wi-Fi** | LAN 모드로 붙는 기본 조건 (안 되면 §3 터널) |

> ⚠️ 사내/카페 Wi-Fi는 기기 간 통신을 막는 경우가 많습니다(AP isolation).
> 그럴 땐 §3의 **터널 모드**를 쓰세요.

---

## 1. 가장 빠른 방법 (MOCK 모드, 같은 Wi-Fi)

```bash
cd apps/mobile
npx expo start
```

1. 터미널에 **QR 코드**가 뜹니다.
2. **iPhone**: 기본 카메라 앱으로 QR 스캔 → "Expo Go로 열기".
   **Android**: Expo Go 앱 안의 "Scan QR code"로 스캔.
3. 잠시 번들링(첫 실행은 30초~1분) 후 앱이 뜹니다.

이 상태는 **MOCK 모드**라 백엔드 없이 화면·플로우(대화→문진→리포트, 기록 탭 등)가
전부 목 데이터로 동작합니다. 실제 AI/DB 없이 UX를 확인하기에 좋습니다.

> `npm run dev`(= `expo start --dev-client`)는 **개발 빌드용**이라 Expo Go에선
> 안 됩니다. 반드시 `npx expo start` (또는 `npm start`)를 쓰세요.

---

## 2. 자주 겪는 문제

| 증상 | 원인 / 해결 |
|---|---|
| `Project is incompatible with this version of Expo Go` | 프로젝트가 폰 Expo Go보다 낮은 SDK. 이 레포는 이미 SDK 54라 최신 Expo Go면 정상. Expo Go를 업데이트하세요. |
| QR 스캔해도 계속 로딩/타임아웃 | 같은 Wi-Fi인지 확인 → 안 되면 §3 **터널 모드** |
| `Unable to resolve module …` | 캐시 문제. `npx expo start -c` (캐시 클리어) |
| `Metro`가 딴 폴더에서 뜸 / `../../App` 못 찾음 | 반드시 **`apps/mobile`에서** 실행 (모노레포 루트 아님) |
| 번들은 되는데 화면이 하양 | 폰에서 Expo Go 앱을 완전히 종료 후 재접속, 또는 앱 내 흔들어서 **Reload** |

---

## 3. 같은 Wi-Fi가 안 될 때 — 터널 모드

회사 Wi-Fi·게스트망 등으로 LAN 연결이 막히면:

```bash
cd apps/mobile
npx expo start --tunnel
```

Expo가 임시 공개 URL(ngrok 기반)을 만들어 폰이 인터넷을 통해 접속합니다.
느릴 수 있지만 어떤 네트워크에서도 됩니다. (최초 실행 시 `@expo/ngrok` 설치 프롬프트에 `y`)

---

## 4. 실서버 붙이기 (MOCK 끄기)

목 데이터가 아니라 **실제 백엔드**(회원가입·대화·문진 채점 등)로 돌리려면
맥에서 서버를 띄우고, 폰이 맥의 LAN IP로 접속하게 합니다.

### 4-1. 서버 실행 (맥, 터미널 2개)

```bash
# ① 플랫폼 API (:8000)
cd apps/api
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
# uv가 없으면: source .venv/bin/activate && uvicorn src.main:app --host 0.0.0.0 --port 8000

# ② AI 서버 (:8001)  — 대화/안전/문진 채점 등에 필요
cd apps/ai-server
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8001
```

> `--host 0.0.0.0`가 중요합니다. 기본 `127.0.0.1`은 폰에서 접근 못 합니다.
> Postgres·AI 키가 없으면 일부 기능은 제한됩니다(아래 §5 참고).

### 4-2. 맥 LAN IP 확인

```bash
ipconfig getifaddr en0     # 예: 192.168.0.71
```

### 4-3. 앱을 실서버로 실행

```bash
cd apps/mobile
EXPO_PUBLIC_MOCK=0 \
EXPO_PUBLIC_API_BASE_URL=http://192.168.0.71:8000 \
EXPO_PUBLIC_WS_BASE_URL=ws://192.168.0.71:8000 \
npx expo start -c
```

(위 IP는 4-2에서 확인한 값으로 바꾸세요.)

**동작 원리** — 앱은 `EXPO_PUBLIC_*` 환경변수를 번들에 인라인합니다.
- `EXPO_PUBLIC_MOCK=0` → 목 대신 실제 API 호출
- `EXPO_PUBLIC_API_BASE_URL` → REST 서버 주소
- `EXPO_PUBLIC_WS_BASE_URL` → 실시간 채팅(WebSocket) 주소
지정 안 하면 자동으로 `localhost:8000`을 쓰는데, 실기기에선 localhost가 폰 자신을
가리켜 접속이 안 됩니다.

---

## 5. 기능별 필요 조건 (실서버 모드)

| 기능 | 추가로 필요한 것 |
|---|---|
| 회원가입·로그인·세션·문진 저장 | **Postgres** + 마이그레이션 `alembic upgrade head` (apps/api) |
| AI 대화 응답·안전 분류·도메인 추정 | **LLM API 키** (`SKT_A_X_API_KEY`) — 없으면 안전 폴백/기본 문진으로 동작 |
| 문진 채점(PHQ-9/GAD-7/AUDIT-C/PHQ-4) | ai-server만 있으면 동작 (LLM 불필요) |
| STT 음성 입력 | ai-server STT 어댑터 설정 |

키·DB가 없어도 앱은 **안 죽고** 폴백합니다. UX만 볼 거면 §1의 MOCK 모드로 충분합니다.

---

## 6. 참고

- 코드 저장하면 **자동 리로드**됩니다. 큰 변경 후엔 앱 흔들어 **Reload** 또는 `-c`로 재시작.
- 개발 메뉴: 실기기에서 **폰 흔들기**(shake) → Reload / Debug 등.
- 프로덕션 배포(앱스토어/EAS) 시엔 `MOCK`이 강제로 꺼지고 `https://`·`wss://`만 허용됩니다
  (`apps/mobile/lib/config.ts`의 릴리스 가드).

### 자주 쓰는 명령 요약

```bash
cd apps/mobile
npx expo start          # MOCK 모드, 같은 Wi-Fi (기본)
npx expo start -c       # 캐시 클리어 후 실행
npx expo start --tunnel # 어떤 네트워크에서도 (느림)

# 실서버 모드
EXPO_PUBLIC_MOCK=0 EXPO_PUBLIC_API_BASE_URL=http://<맥IP>:8000 \
EXPO_PUBLIC_WS_BASE_URL=ws://<맥IP>:8000 npx expo start -c
```
