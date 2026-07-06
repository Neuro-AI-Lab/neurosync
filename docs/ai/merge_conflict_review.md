# Fix Branch Merge Conflict 심층 리뷰

> 대상: `fix/iss-19-safety-failopen`, `fix/iss-20-handoff-dataloss`, `fix/iss-21-risk-cap`
> 기준: `origin/Master` (F1 pipeline merge 포함)
> 작성일: 2026-07-06

---

## 1. 충돌 요약

| Branch | 총 충돌 파일 | 내용 충돌 | modify/delete | lint only |
|--------|-------------|-----------|---------------|-----------|
| ISS-19 | 31 | 5 | 26 | ~50 files (ruff) |
| ISS-20 | 30 | 4 | 26 | ~50 files (ruff) |
| ISS-21 | 30 | 4 | 26 | ~50 files (ruff) |

**충돌 대부분(26개)은 F1에서 삭제한 레거시 파일을 fix 브랜치가 lint 수정한 modify/delete 충돌.**

---

## 2. 각 Fix의 실제 비즈니스 로직 변경

### ISS-19: SafetyClassifier fail-closed

**문제**: LLM 응답 파싱 실패 또는 LLM 전체 장애 시 `RiskLevel.none`(safe) 반환 → 위험 환자가 빠져나감

**Fix 내용**: 파싱 실패/LLM 장애 시 `RiskLevel.high`(CTRS 2, crisis) 반환

**F1 현재 상태 (safety_classifier.py)**:
- Line 243: parse failure → `RiskLevel.none` ← **취약 (fail-open)**
- Line 284: LLM unavailable → `RiskLevel.none` ← **취약 (fail-open)**
- Line 352: LLM unavailable 시 rule result fallback → rule도 none이면 최종 none

**평가**: ISS-19의 fail-closed 의도는 **반드시 채택해야 함**. 현재 F1은 LLM 장애 시 위험 환자를 safe로 처리하는 보안 취약점이 있음.

**권장 해결**: F1 코드에 ISS-19 의도를 수동 적용
```
Line 243: RiskLevel.none → RiskLevel.high  (parse failure)
Line 284: RiskLevel.none → RiskLevel.high  (LLM unavailable)
```
단, F1의 아키텍처(C 방식: Rule→LLM)에서는 LLM 장애 시 rule result가 fallback이므로, rule이 none인 경우에만 high로 올려야 함. **Rule이 이미 위험을 감지했으면 rule 결과가 유지되므로 중복 상향 불필요.**

---

### ISS-20: Handoff data loss (scale_scores + risk_events 미전달)

**문제**: Orchestrator가 HandoffInput 생성 시 `scale_scores`와 `risk_events`를 누락

**Fix 내용**: `orchestrator.py`의 `HandoffInput()` 호출에 `scale_scores`, `risk_events` 파라미터 추가

**F1 현재 상태 (orchestrator.py line 464-487)**:
```python
HandoffInput(
    session_id=state.session_id,
    slots=SlotData(...),
    conversation_history=state.conversation_history,
    is_first_visit=state.is_first_visit,
    # scale_scores 없음 ← 데이터 유실
    # risk_events 없음 ← 데이터 유실
)
```

**평가**: F1 파이프라인은 `f1.py`가 orchestrator 역할을 직접 수행하므로 `orchestrator.py`를 직접 호출하지 않음. 하지만 **프로덕션 경로(routes/chat.py → OrchestratorAgent)에서는 여전히 이 버그가 존재**. fix 채택 필요.

**권장 해결**: fix 브랜치의 orchestrator.py 변경을 그대로 채택. F1 코드와 충돌 없음 (f1.py는 orchestrator.py를 사용하지 않음).

---

### ISS-21: Risk level cap (always medium)

**문제**: `handoff_generator.py`의 `_detect_risk_level()`이 risk event 유무만 확인하고 항상 `RiskLevel.medium` 반환

**Fix 내용**: 이벤트별 severity를 확인하여 max를 반환하는 로직으로 교체

**F1 현재 상태 (handoff_generator.py line 77-81)**:
```python
def _detect_risk_level(risk_events):
    if not risk_events:
        return RiskLevel.none
    return RiskLevel.medium  # ← 항상 medium, high/critical 무시
```

**평가**: F1의 `f1.py`는 자체 handoff 생성(`generate_handoff_from_result`)을 사용하므로 직접 영향 없음. 하지만 프로덕션 경로에서는 이 버그가 존재. fix 채택 필요.

**권장 해결**: fix 브랜치의 `_detect_risk_level()` + `_event_risk()` 함수를 그대로 채택. F1 코드와 충돌 없음.

---

## 3. 공통 lint 커밋 (ruff debt cleanup)

3개 브랜치 모두 `chore: clear pre-existing ruff lint debt + declare openai/matplotlib deps` 커밋 포함.

**변경 범위**: 56 files, import 정렬, `Optional` → `X | None`, unused import 제거, line length

**F1 코드의 현재 ruff 상태**: 36 errors (E501 line length, I001 import sort, F401 unused import, UP045 Optional)

**평가**: lint 수정은 코드 품질에 기여하지만, F1에서 재작성한 파일(safety_classifier.py, clinical_slot.py, dialogue.py)에서는 **F1 버전을 유지하고 별도로 ruff fix 적용하는 것이 안전**. fix 브랜치의 lint 변경을 그대로 merge하면 F1 로직이 덮어써질 위험.

**권장 해결**: 
1. F1 재작성 파일 → Master(F1) 버전 유지, 이후 `ruff check --fix` 별도 적용
2. F1 미수정 파일 → fix 브랜치 lint 변경 채택

---

## 4. 충돌 파일별 해결 전략

### Category A: modify/delete (26개) — F1에서 삭제한 레거시 파일

```
apps/ai-server/src/services/report_renderer.py
apps/ai-server/src/services/trend_plotter.py
apps/ai-server/tests/simulation/run_full_simulation.py
apps/ai-server/tests/simulation/run_simulation.py
apps/ai-server/tests/simulation/runner.py
apps/ai-server/tests/test_*.py (21개)
```

**결정**: Master(삭제) 선택. F1 파이프라인으로 대체 완료된 코드.

### Category B: F1 재작성 파일 (5개) — 내용 충돌

| File | Fix 변경 | F1 변경 | 결정 |
|------|---------|---------|------|
| `safety_classifier.py` | fail-closed + lint | 전면 재작성 (C-arch) | **F1 유지 + ISS-19 fail-closed 수동 적용 (2줄)** |
| `clinical_slot.py` | lint only | 전면 재작성 (flat 12-key) | **F1 유지** |
| `patient_llm.py` | lint only | persona MD 로딩 재작성 | **F1 유지** |
| `routes/chat.py` | lint only | import 정리 | **F1 유지** |
| `schemas/clinical_slot.py` | lint only | safety_flag 필드 제거 | **F1 유지** |

### Category C: F1 미수정 파일 — fix 로직 채택

| File | Fix | 결정 |
|------|-----|------|
| `orchestrator.py` | ISS-20 scale_scores 전달 | **fix 채택** |
| `handoff_generator.py` | ISS-21 risk cap 수정 | **fix 채택** |
| `schemas/handoff.py` | ISS-20 ScaleScore import | **fix 채택** (이미 존재 확인) |

### Category D: lint only 파일 (F1 미수정, ~40개)

**결정**: fix 브랜치의 lint 변경 채택. F1이 건드리지 않은 파일이므로 안전.

---

## 5. 병합 실행 계획

**권장 순서**:

1. ISS-21 먼저 (가장 단순, handoff_generator.py만 실질 변경)
2. ISS-20 다음 (orchestrator.py에 scale_scores 추가)
3. ISS-19 마지막 (safety_classifier.py와 F1 충돌 → 수동 resolution 필요)

**각 브랜치 merge 시**:
1. `git merge --no-commit origin/fix/iss-XX`
2. modify/delete 충돌 → `git rm` (삭제 선택)
3. F1 재작성 파일 충돌 → `git checkout HEAD -- <file>` (F1 유지)
4. F1 미수정 파일 → fix 변경 채택
5. ISS-19의 경우: safety_classifier.py F1 유지 후 fail-closed 2줄 수동 적용
6. `git commit`

---

## 6. ISS-19 fail-closed 수동 적용 상세

F1의 `safety_classifier.py`에서 변경할 2곳:

**Line 243 (parse failure)**:
```python
# Before (fail-open):
classification = SafetyClassification(
    risk_level=RiskLevel.none,
    confidence=0.0,
    reason_summary="LLM response parse failure",
)

# After (fail-closed, ISS-19):
classification = SafetyClassification(
    risk_level=RiskLevel.high,
    confidence=0.0,
    reason_summary="LLM response parse failure — fail-closed to high",
)
```

**Line 284 (LLM unavailable)**:
```python
# Before (fail-open):
return (
    SafetyClassification(
        risk_level=RiskLevel.none,
        ...
        reason_summary="LLM unavailable",
    ),
    "none",
    0.0,
)

# After (fail-closed, ISS-19):
return (
    SafetyClassification(
        risk_level=RiskLevel.high,
        ...
        reason_summary="LLM unavailable — fail-closed to high",
    ),
    "none",
    0.0,
)
```

**주의**: F1의 `run()` 메서드 (line 340-354)에서 LLM unavailable 시 `final_level = rule_level`로 fallback한다. Rule이 이미 위험을 감지했으면 rule 결과가 유지되므로, LLM fallback의 `RiskLevel.high`가 최종 결과를 불필요하게 높이지는 않는다. Rule이 none이고 LLM도 unavailable인 경우에만 `high`가 적용되어 fail-closed 동작을 보장한다.
