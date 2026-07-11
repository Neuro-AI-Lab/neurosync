# Task 1 버전 이력

> 주요 마일스톤 달성 시 버전을 범프합니다.

## 작성 규칙

1. 형식: `## vX.Y (YYYY-MM-DD)`
2. 포함 항목: scope, changes, completed checklist IDs, known issues
3. v0.x = 개발 진행 중
4. v1.0 = 기능 1-1 ~ 1-5 전체 통합 완료 및 VP-001~VP-004 검증 통과
5. 버전 범프 기준:
   - v0.1: 기능 1-1 (자율 대화) 단독 동작
   - v0.2: 기능 1-3 (구조화 문진 + slot 추출) 연동
   - v0.3: 기능 1-2 (RAG retrieval) 연동
   - v0.4: 기능 1-4 (종단적 추론) 연동
   - v0.5: 기능 1-5 (handoff report) 전체 파이프라인
   - v0.9: 전체 VP 4명 통합 검증 통과
   - v1.0: production-ready

---

## Versions

### v0.0 (2026-06-18)

**Scope**: 초기 PRD 및 계획 수립
**Changes**:
- PRD_task1_development.md 작성
- checklist_task1.md 작성
- Agent spec 12개 재작성 (docs/ai/agents/01-12)
- System prompt 12개 재작성 (docs/ai/prompts/)
- report.md, version.md 초기화
**Completed**: T1-F0-DOC-001, T1-F0-DOC-002
**Known issues**: 없음

---

### v0.1 (2026-06-24)

**Scope**: 기능 1-1 (자율 대화 + Safety) 단독 동작 + ClinicalSlotAgent + Survey Scoring
**Changes**:
- CTRSLevel enum + CTRS↔RiskLevel 양방향 매핑
- SafetyClassifier CTRS 통합: crisis=CTRS 1-2, review=CTRS 1-3
- Rule-based survey scoring: PHQ-9, GAD-7, PHQ-4, WHO-5, AUDIT-C (39 tests)
- ClinicalSlotAgent: 13 slot 정밀 추출 + evidence 연결
- Dialogue slot coverage tracking: missing slots → prompt 주입
- SentimentAnalyzer agent spec + prompt (13th agent)
- Patient LLM simulation framework + VP-001/VP-003 검증
- Registry 13 agents 확인 + PromptLoader 검증
- Checklist 의존성 수정 + ClinicalSlot 스키마 분리

**Completed** (16/70):
- DEV: T1-F0-DEV-002/003/004, T1-F1-DEV-001/005/013, T1-F3-DEV-001/003
- VER: T1-F1-VER-001/002/003, T1-F3-VER-001/002
- DOC: T1-F0-DOC-001/002/003/004

**Verification**:
- VP-001: 10턴, no crisis, ClinicalSlot 69% (9/13), essential 5/5
- VP-003: 3턴, "죽고 싶다" → CTRS 1 → crisis 즉시 발동
- All tests: 40/40 pass

**Known issues**:
- VP-001 CTRS 3-4 과잉 판정 (safety prompt 조정 필요)
- Dialogue 질문 반복 패턴 (T1-F1-DEV-010)
- Orchestrator state machine 미구현 (T1-F0-DEV-001)

---

### v0.2 (2026-06-24)

**Scope**: TemporalSummaryAgent + SentimentAnalyzer route + VP-002/VP-004 + ISS-008 closed

**Changes**:
- TemporalSummaryAgent: rule-based direction classification (PHQ-9/GAD-7 delta≥5, CTRS inverted, sentiment polarity) + plot-ready data
- POST /ai/temporal/summarize route (9th AI endpoint)
- POST /ai/sentiment/utterance + /ai/sentiment/session routes (7th, 8th endpoints)
- VP-002 (이준호, 재진 경증) + VP-004 (최하은, 재진 중증) personas in simulation
- ISS-008 closed: VP-001 CTRS now 4-5 (no more medium overfitting)
- VP-001/VP-003 re-simulated with Sprint 2 prompt fixes

**Completed** (32/70, 46%):
- DEV: 23/35 (+4 temporal, +2 sentiment schema/route already counted)
- VER: 8/28 (+1 temporal first-visit, ISS-008 verification)
- DOC: 4/4
- CFG: 0/3

**Tests**: 102/102 passed
**Endpoints**: 9/10 (90%)
**Agents coded**: 8/13 (62%)

**Known issues**:
- ISS-009 (dialogue echo) — simulation framework issue, not clinical agent
- ISS-010 (Orchestrator) — major blocker for route integration
- ISS-011 (STT/OCR) — vendor blocked
- ISS-012 (VP-002/VP-004 revisit sim) — personas ready, TemporalSummary integration in runner pending
