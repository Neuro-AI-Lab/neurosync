# `apps/web` — 의료진 웹 대시보드

> **Owner**: Platform 팀 (단독)
> **언어/프레임워크**: Next.js 16 + TypeScript + Tailwind
> **PRD**: 마스터 PRD §5.4 Pages (`/dashboard*` 행), §5.5 Flow B

## 책임 범위

- 의료진 로그인 + 2FA (TOTP) (FR-015, FR-031)
- 환자 목록 (FR-016, FR-021)
- 환자 상세 + Handoff 리포트 뷰 (FR-017)
- PDF 다운로드 (FR-019)
- EMR 복사용 텍스트 (FR-020)
- 위험 이벤트 모니터링 (FR-022)
- 기관 관리자 화면 (FR-015 org_admin)

## AI는 호출하지 않음
모든 호출은 Platform API(`apps/api`) 경유.

## 디렉토리 구조 (예정)

```
apps/web/
├── package.json
├── next.config.ts
├── app/
│   ├── (auth)/login/
│   ├── dashboard/
│   ├── dashboard/patients/[id]/
│   └── dashboard/admin/
├── components/
└── lib/api/
```
