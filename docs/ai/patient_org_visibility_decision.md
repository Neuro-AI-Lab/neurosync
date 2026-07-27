# 환자-기관(organization) 연결 구조 — 실 앱 가입 경로 결정 보고서

**작성일:** 2026-07-27
**기준 커밋:** Master `6c73d1b` (PR #96, #97 머지 직후)
**근거 entry:** BUG-092, ADR-049, ADR-050(moot 처리 경위 포함), PLAN-2026-W31-WEBDASH
**조사 담당:** developer (본 문서는 writer가 해당 RESULT를 재구성)

## 배경

BUG-092(qa 라이브 E2E, PLAN-2026-W31-WEBDASH step 4)는 데모 시드 환자 5명 전원의
`PatientProfile.target_hospital_id=NULL` 상태에서 org-scope 필터(`clinician.py`, PRD FR-015
"기관별 접근 제한", ISS-022/PR #22)가 이들을 전부 걸러내 의료진 웹 대시보드에 환자 0명이 보이는
문제로 확정되었다. ADR-049는 이 문제를 "시드 백필"로 즉시 해소하되, **실 앱을 통해 신규 가입하는
환자가 동일하게 비가시 상태가 되는 구조적 문제는 별도 조사·보고 후 사용자 결정**으로 남겨두었다.
본 문서는 그 조사 결과와 결정 옵션을 정리한다.

## 1. PR #96 / #97이 이 문제에 미친 영향

PR #96(F4/F5 통합)과 #97(hospital_finder)은 이 문제의 지형을 바꾸지 않았다.

- PR #96은 org-scope 게이트를 이미 통과한 이후의 리포트 콘텐츠 조립만 다룬다. org-scope 판정 지점
  자체(`apps/api/src/api/v1/sessions.py:764`, `apps/api/src/api/v1/handoff.py:436`)는 diff에서
  변경되지 않았다.
- PR #97은 `nearby.py`를 Kakao Local 직접 조회로 바꾼 것뿐이다
  (`apps/api/src/api/v1/nearby.py:35-58`, `apps/api/src/services/hospital_finder.py:33-87`).
  인증·DB 쓰기·계정 연결이 전혀 없다 — 두 파일 모두 DB/User/PatientProfile import 자체가 없다.
- 결론: 병원 선택이 가입/프로필/문진 흐름에 배선된 지점은 신·구 코드 어디에도 없다. BUG-092가
  드러낸 구조적 공백은 #96/#97 이후에도 그대로 남아 있다.

## 2. 경로 인벤토리 (실 앱 가입 → 대시보드 가시성)

| 지점 | 상태 | 근거 |
|:--|:--|:--|
| `target_hospital_id` 필드 정의 | `PatientProfile` 상의 선택(optional) 필드, alias `targetHospitalId` | `apps/api/src/schemas/auth.py:90` |
| 유일한 프로덕션 writer | `POST /auth/register` | `apps/api/src/api/v1/auth.py:241` |
| 모바일 클라이언트 register 입력 | 해당 필드 부재 — 서버 필드는 있으나 클라이언트가 절대 채우지 못함 | `apps/mobile/lib/api.ts:169-193` (`RegisterInput`) |
| org-scope 판정 로직 | `patient_hospital_id is not None and == actor.organization_id` — NULL은 super_admin 제외 누구에게도 안 보임 | `apps/api/src/services/clinician.py:55-66, 69-75` |
| org-scope 적용 지점 | 3곳 (report/session/handoff 조회 경로) | `clinician.py:163`, `sessions.py:764`, `handoff.py:436` (ISS-022) |
| 병원 선택 UI (FR-049) | 표시 전용 — api/register/profile 어디도 참조하지 않음 | `apps/mobile` `hospitals.tsx` (181줄) |
| claim/invite류 엔드포인트 | 전무 — `clinician.py`는 GET 3개뿐, PATCH/POST 없음, apps/web에도 organization 참조 0 | `apps/api/src/api/v1/clinician.py` |
| 데모 전용 writer | 시드 스크립트(로컬 미커밋) + 일회성 백필 | `seed_demo.py:308-312` (`target_hospital_id=org_id`), `backfill_bug092_target_hospital.py` |

## 3. 데이터 모델 실측

- `hospitals` 테이블은 존재하지 않는다. 실체는 `organizations`뿐이다
  (`apps/api/alembic/versions/0001_initial_auth_schema.py:49-61`, `apps/api/src/models/user.py:15-26`;
  DB 실측 13테이블 중 `hospitals` 없음).
- `PatientProfile.target_hospital_id`(`apps/api/src/models/patient_profile.py:61`)는 FK 제약 없는
  bare UUID 컬럼이다 — `organizations.id`를 참조하는 것은 관례일 뿐 DB 레벨 제약이 아니다.
- `User.organization_id`는 실제 FK다.
- 즉 "hospital"과 "organization"은 동일 엔티티이며, `target_hospital_id`는 역사적 misnomer다.
- DB 실측: `organizations` 1행(`데모 정신건강의학과`, type=clinic) — 사실상 단일 기관(single-tenant)
  데모 상태다. 환자 5명 전원 BUG-092 백필이 반영되어 있다. patient의 `users.organization_id`는
  전부 NULL인데 이는 정상 동작이다(patient 엔티티는 `target_hospital_id`만 사용).

## 4. 옵션 비교

| 옵션 | FR-015 정합 | 기존 NULL 환자 해결 | 규모 | 리스크 |
|:--|:--|:--|:--|:--|
| ① 온보딩 병원 선택 배선 | 유지 | 못함 — 별도 백필 병행 필요 | M (모바일 측 + 기관 목록 조회 API 신설 필요 — 현재 org 목록 endpoint 없음) | 단일 org 데모에선 select-one UI 과잉 |
| ② 가입 시 기본 org 배정 | 문언상 유지(사실상 1:1 배정) | 즉시 해결 — 기존 백필 스크립트 재사용 | S (`auth.py` register에 `payload.target_hospital_id or settings.default_organization_id` 한 줄 + config 1개) | 다기관 도입 시 즉시 무효화되는 기간 한정 해법(현 실측 org 1행과 정확히 맞물림) |
| ③ 의료진/관리자 claim·invite 흐름 | 가장 정합적 — 배정을 임상 측 권한으로 명시 통제, `audit_logs` 연결 가능 | 정확히 이 흐름으로 해결 | L (신규 PATCH 엔드포인트 + 권한 + 감사 + 웹 UI 2+) | 오배정(타 병원 환자 가로채기) — super_admin 제한/이중 확인 필요, 임상 측 새 UI 부담("미배정 환자" 큐) |
| ④ org-scope 완화(NULL 전 기관 노출) | **FR-015 정면 위반** | 즉시 해결 | S (2줄) | ADR-049가 이미 명시 기각한 선택지(재론 시 별도 ADR 필요), 다기관 시 구조적 프라이버시 사고 |
| ⑤ 문진/병원찾기 흐름 사후 선택(신규 `PATCH /auth/me/target-hospital`, `hospitals.tsx` 확장, `ProfileDemographicsUpdate` 패턴 재사용 — `schemas/auth.py:118-130`) | 유지, 자연스러운 UX | 환자가 능동 선택 안 하면 여전히 NULL | M | Kakao Local 장소↔`organizations` 매핑 부재 문제 별도 발생 |

## 5. 권고안 (developer 조사, writer 재구성)

**옵션 ②+③ 순차 조합**을 권고한다.

1. 현재 DB 실측(`organizations` 1행)이 단일 기관 데모 상태임을 보여준다 — 옵션①/⑤가 전제하는
   "여러 기관 중 선택"은 지금 시점에는 과잉 설계다.
2. 옵션②는 기존 BUG-092 백필 스크립트와 대칭 구조로, 기존 환자와 신규 가입 환자를 S 규모 변경
   한 쌍(`auth.py:241` 한 줄 + config 1개)으로 동시에 닫을 수 있다.
3. 옵션②는 다기관 전환 전까지의 임시 조치다. 따라서 옵션③(claim/invite, L 규모)을 다기관 로드맵
   항목으로 병행 계획할 것을 제안한다 — ADR-049가 잡은 방향("org-scope 정책 불변, 배정 경로를
   조사 후 결정")과 정합한다.
4. 옵션④는 ADR-049가 이미 기각한 선택지이므로 재론하려면 별도 ADR이 필요하다.

## 결정 요청

사용자가 선택해야 할 사항:

1. **즉시 조치**: 옵션② (가입 시 기본 org 배정, S 규모)를 채택하여 신규 가입 환자의 구조적
   비가시성을 지금 닫을 것인가?
2. **로드맵 편성**: 옵션③ (claim/invite 흐름, L 규모)을 다기관 지원 로드맵의 어느 시점에 넣을
   것인가 — 즉시 착수 vs 추후 백로그?
3. **범위 확정**: 옵션①과 ⑤는 폐기하고 ②+③ 조합만 진행하는 것으로 확정할 것인가, 아니면 온보딩
   단계 선택 UX(①)를 다기관 전환 시점에 별도로 재검토할 것인가?
4. 위 결정이 나면 orchestrator가 해당 ADR을 작성하고 developer에게 구현 브리프를 발행한다.
---
