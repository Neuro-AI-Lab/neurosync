# `infra/` — 인프라/배포/CI/CD

> **Owner**: Platform 팀 (단독)
> **AI 팀 영향 범위**: `apps/ai-server` 배포 매니페스트의 환경변수·리소스 요구는 AI 팀이 PR로 제안, Platform이 검토·적용

## 구조

```
infra/
├── deploy/
│   ├── docker-compose.yml      # 로컬 개발 (api, ai-server, db, redis, s3-mock)
│   ├── k8s/                    # 배포 매니페스트 (Phase 2~)
│   │   ├── api/
│   │   ├── ai-server/
│   │   ├── postgres/
│   │   └── redis/
│   └── terraform/              # AWS/GCP IaC (Phase 3~)
└── ci/
    ├── github-actions/
    │   ├── platform-ci.yml     # apps/api, apps/mobile, apps/web 변경 시 트리거
    │   ├── ai-ci.yml           # apps/ai-server 변경 시 트리거 (별도 파이프라인)
    │   └── contracts-ci.yml    # packages/shared-contracts 변경 시 양 팀 테스트
    └── secrets/                # KMS·암호화된 시크릿 (env 별)
```

## CI 분리 원칙

- **Platform PR** (apps/api, apps/mobile, apps/web, infra): Platform 파이프라인만 실행
- **AI PR** (apps/ai-server, docs/ai): AI 파이프라인만 실행 (Whisper 모델 다운로드 캐싱 등 AI 특화 step 포함)
- **공유 PR** (packages/shared-contracts): 양 파이프라인 모두 실행 → 통과 시에만 머지

## 시크릿 관리

| 시크릿 | 사용처 | 발급 |
|--------|--------|------|
| DB credentials | apps/api | Platform |
| JWT signing key | apps/api | Platform |
| S3 + KMS keys | apps/api, apps/ai-server (presigned URL 검증) | Platform |
| LLM API Keys (Claude/Solar/A.X K1/Mi:dm/K-EXAONE) | apps/ai-server | AI 팀 발급 → Platform Secret Manager 등록 |
| STT API Keys (A.dot/Whisper/Whisper Local 인증) | apps/ai-server | AI 팀 |
| Upstage API Key | apps/ai-server | AI 팀 |
| LangSmith API Key | apps/ai-server | AI 팀 |
