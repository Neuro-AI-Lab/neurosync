"""F5 report writer — `save_f5_result` + markdown/PDF/FHIR exporters.

`_archive/plans/f5_quick_dev_plan.md` §5. Deliberately kept OUT of `src/f5.py` (the
pure, zero-file-I/O assembly engine) so a whole-file grep for `open(`/file-
I/O in `src/f5.py` returns 0 hits with zero ambiguity (REV-044 Criterion 6,
`ADR-037` Decision 6 citation fix) — this module is the ONE place F5's OWN
output artifacts (`_handoff.md`/`.pdf`/`_fhir.json`) get written to disk,
the same role `src/services/f4_report.py` already plays for F4. Called by
the harness (`src/continuous_test.py`) AFTER `src.f5.assemble_handoff_
report` returns — never by `src/f5.py` itself.

FHIR claim discipline (`REV-046` MAY/MUST-NOT wording table row 2, binding):
this module and every string it writes MAY say the FHIR bundle is
"structurally valid per this project's own `validate_fhir_bundle` checks" —
it MUST NOT claim "FHIR-conformant", "validated against the FHIR spec",
"`$validate`-passed", or any implication of HL7 Implementation Guide
conformance. No FHIR `$validate` service call anywhere in this module (D3).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from contracts.survey_plan import SI_POSITIVE_ACTION_KO

from src.f1 import OUTPUT_DIR
from src.schemas.handoff_report import (
    A7_NO_CANDIDATES_VALIDATION_DROPPED_KO,
    A8_FHIR_OMISSION_NOTE_KO,
    NARRATIVE_ENABLED_LABEL_KO,
    NON_VALIDATED_ADMINISTRATION_CAVEAT_KO,
    SLOT_NEVER_COLLECTED_KO,
    HandoffReportOutput,
    LongitudinalSection,
    MentalStatusSection,
    QuestionnaireSection,
    RecommendationSection,
    RiskSafetySection,
    SlotOverviewRow,
    SlotOverviewSection,
)
from src.schemas.longitudinal import LongitudinalAnalysisOutput

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# 상세 부록 (detail appendix) + 시스템 참고 (internal-ref audit) collectors
# (CVR-026 Findings 1/2/5/6, this mission) — one fresh instance per
# `build_markdown_report`/`build_pdf_report` call, threaded through every
# helper that truncates a clinically material field or strips an internal
# review/bug ID out of body prose. Never invents text: every entry is the
# SAME string a truncation/strip site already had in hand, just relocated.
# ═══════════════════════════════════════════════════════════════════════


class _AppendixCollector:
    """Collects `(anchor_no, label, full_text)` for one render call.
    `anchor()` is the only mutator; call order fixes the anchor numbering
    (1-based) referenced inline as `(상세 부록 N 참조)` — CVR-026 Finding 1
    (blocking): a truncation marker must point to a REAL entry, never a
    dead `"(상세 아래)"` reference."""

    def __init__(self) -> None:
        self.entries: list[tuple[int, str, str]] = []

    def anchor(self, label: str, full_text: str) -> int:
        n = len(self.entries) + 1
        self.entries.append((n, label, full_text))
        return n


class _SystemNoteCollector:
    """Dedup-preserving list of internal review/bug-ID citations stripped
    out of body prose (CVR-026 Finding 5: `CVR-022`/`REV-045`/`src.f4::`
    etc. must live only in the audit footnote, never the clinical body)."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self.notes: list[str] = []

    def add(self, note: str | None) -> None:
        if note and note not in self._seen:
            self._seen.add(note)
            self.notes.append(note)


def save_f5_result(
    report: HandoffReportOutput,
    output_dir: Path | None = None,
    *,
    vp_id: str | None = None,
    chart_paths: dict[str, Path] | None = None,
) -> dict[str, Path]:
    """Save F5 result as markdown + PDF + FHIR R4 document Bundle (design
    doc §5). Naming mirrors `save_f1_result`/.../`save_f4_result`:
    `<vp_id>_<ts>_handoff.md` / `_handoff.pdf` / `_handoff_fhir.json`, under
    `docs/ai/simulation_results/<vp_id>/` — same directory as every other
    F1-F4 artifact for that VP, no new directory.

    `chart_paths`: optional mapping of the SAME 4 keys as
    `schemas.handoff_report.ChartReferences` (`scales_ctrs_sentiment`/
    `ctrs_zoom`/`disease_similarity`/`domain_confidence`) to the REAL,
    already-on-disk F4 PNG `Path`s — used only by the PDF exporter to embed
    chart bytes (F5 never generates or regenerates chart bytes itself,
    design doc §2.2 B5 row). The markdown/FHIR exporters use only the
    filenames already carried on `report.b_longitudinal.chart_filenames`.
    """
    resolved_vp_id = vp_id or report.vp_id
    base = output_dir or OUTPUT_DIR
    out = base / resolved_vp_id
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{resolved_vp_id}_{ts}"

    paths: dict[str, Path] = {}

    md_path = out / f"{prefix}_handoff.md"
    md_path.write_text(build_markdown_report(report), encoding="utf-8")
    paths["markdown"] = md_path

    pdf_path = out / f"{prefix}_handoff.pdf"
    pdf_path.write_bytes(build_pdf_report(report, chart_paths or {}))
    paths["pdf"] = pdf_path

    fhir_bundle = build_fhir_bundle(report)
    fhir_path = out / f"{prefix}_handoff_fhir.json"
    fhir_path.write_text(json.dumps(fhir_bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["fhir"] = fhir_path

    logger.info("F5 results saved: %s", ", ".join(str(p) for p in paths.values()))
    return paths


# ═══════════════════════════════════════════════════════════════════════
# Markdown (design doc §5.1)
# ═══════════════════════════════════════════════════════════════════════


def _none_marker(value: object, marker: str) -> str:
    return marker if value in (None, "", []) else str(value)


# B5 — human-readable Korean labels for the 4 `ChartReferences` keys, used
# ONLY to name a chart in an explicit per-chart absent-marker line when its
# filename is `None` (never invents a reason for the absence, states the
# fact only — same discipline as every other "정보 없음"/"평가 불가" marker
# in this document, qa's completeness-grep target).
_CHART_TITLES_KO = {
    "scales_ctrs_sentiment": "척도·CTRS·감성 추이 차트",
    "ctrs_zoom": "CTRS 확대 차트",
    "disease_similarity": "질환 유사도 차트",
    "domain_confidence": "진료과 후보 신뢰도 차트",
}

# Task (chart-readability fix, this mission): 1-line Korean caption
# rendered directly UNDER each embedded chart (md + PDF), stating what the
# chart shows and how to read it — never invents a number, `{n}`/`{span}`
# are filled from the SAME `LongitudinalAnalysisOutput` fields the rest of
# this report already cites (`lon.n_sessions`/`lon.session_span_days`).
_CHART_CAPTIONS_KO = {
    "scales_ctrs_sentiment": (
        "설문 총점·위기 단계(CTRS)·정서·문진 충족도 추이 ({n}세션{span}) — "
        "위기 단계는 값이 낮을수록(1에 가까울수록) 위험이 높습니다."
    ),
    "ctrs_zoom": (
        "위기 단계(CTRS) 확대 추이 — 1(최긴급)에 가까울수록 위험, "
        "5(안정)에 가까울수록 안정적입니다."
    ),
    "disease_similarity": (
        "세션별 질환 유사도 추이 — 점선·저채도 선은 참고용 유사도 신호일 뿐이며 "
        "확률·가능성·진단이 아닙니다."
    ),
    "domain_confidence": (
        "세션별 진료과 후보 신뢰도 추이 — 값이 높을수록 해당 진료과 매칭 신뢰도가 높습니다."
    ),
}


def _chart_caption_ko(key: str, lon: LongitudinalAnalysisOutput, fig_no: int) -> str:
    """`그림 N. <1-line Korean caption>` — `fig_no` is the running figure
    index among charts actually rendered this call (never counts an
    absent/`None` chart)."""
    span = f", {lon.session_span_days}일" if lon.session_span_days is not None else ""
    body = _CHART_CAPTIONS_KO[key].format(n=lon.n_sessions, span=span)
    return f"그림 {fig_no}. {body}"


def _slot_fill_all_zero(lon: LongitudinalAnalysisOutput) -> bool:
    """CVR-032 Finding 3 (major): True when the 문진 항목 충족도 (F4 slot-
    fill) series is empty OR every session shows `filled_count == 0` — an
    uncaveated flat-zero completeness chart reads as "nothing was learned
    across N sessions", a stronger/more alarming signal than the underlying
    cause (typically: this run's harness never called `/ai/slots/extract`,
    a known data-collection-scope gap, not an actual absence of dialogue
    content)."""
    if not lon.slot_fill_series:
        return True
    return all(p.filled_count == 0 for p in lon.slot_fill_series)


_SLOT_FILL_FLAT_ZERO_CAVEAT_KO = (
    "⚠ 문진 항목 충족도 데이터가 전체 세션에서 0 또는 미제공입니다 — 대화 내용이 "
    "빈약했다는 의미가 아니라 이번 산출 경로에서 슬롯 데이터가 미수집되었을 가능성을 "
    "나타냅니다 (수집 데이터 미제공/미수집)."
)

# ═══════════════════════════════════════════════════════════════════════
# Readability-layer shared helpers (rendering only — never invents a
# clinical fact; every value below is derived from an existing
# `HandoffReportOutput`/`LongitudinalAnalysisOutput` field). Used by BOTH
# `build_markdown_report` and `build_pdf_report` so the two formats never
# diverge in what they say, only in how they say it.
# ═══════════════════════════════════════════════════════════════════════

_SEVERITY_KO = {
    "minimal": "최소",
    "mild": "경도",
    "moderate": "중등도",
    "moderately_severe": "중등도-중증",
    "severe": "중증",
    "low_risk": "저위험",
    "hazardous_drinking": "위험 음주",
    "low_wellbeing": "낮은 웰빙",
    "adequate_wellbeing": "적정 웰빙",
}

# `src.schemas.common.CTRSLevel`/`CTRS_TO_RISK` is the source of truth: 1 =
# most urgent (EMERGENCY -> RiskLevel.critical) ... 5 = stable (STABLE ->
# RiskLevel.none), the mapping is STRICTLY monotonic urgency-descending.
# The raw enum member comments ("중증/주의" for level 4, etc.) are the
# ENGLISH-adjacent enum-authoring label, not a clinician-facing severity
# claim — level 4 maps to `RiskLevel.low`, so labeling it "중증/주의"
# (severe/caution) here would contradict the very risk_level this report
# renders alongside it. This table instead follows the actual
# `CTRS_TO_RISK` risk gradient (critical/high/medium/low/none), verified
# against `src/schemas/common.py` directly (never invented) —
# `test_f5_report.py::TestCtrsStageLabelMapping` pins this monotonicity so
# it cannot silently drift from the source enum again.
_CTRS_STAGE_KO = {
    1: "최긴급 (즉각 개입)",
    2: "고위험",
    3: "급성 우려",
    4: "경도 우려 (준안정)",
    5: "안정",
}

_DIRECTION_KO = {
    "improved": "개선",
    "worsened": "악화",
    "unchanged": "변화 없음",
    "unknown": "판정 불가",
}

_CONCORDANCE_KO = {"concordant": "일치", "discordant": "불일치", "unknown": "판정 불가"}

# CVR-032 Finding 1 (blocking): `course_shape` (F4's own archetype
# classification, `src.f4._course_shape`) was computed but never surfaced
# anywhere in rendered prose — a scripted `crisis_episode` course could
# read as an unqualified "no crisis session" in text alone.
_COURSE_SHAPE_KO = {
    "gradual_improvement": "점진적 개선",
    "improvement_with_plateau": "개선 후 정체",
    "relapse_after_partial_improvement": "부분 개선 후 재악화",
    "worsening_sustained": "지속적 악화",
    "crisis_episode": "위기 삽화(crisis episode)",
    "unknown": "판정 불가",
}

# Plain-Korean paraphrase of `OVERALL_DIRECTION_SENSITIVITY_NOTE_KO`
# (`schemas.handoff_report`) — that schema constant embeds internal
# refs ("src.f4::_overall_direction", "REV-045 row 2", binding rule 1
# violation). Same meaning, no internal refs; the original (with refs)
# is cited once in the 각주 footnote block for audit traceability.
_OVERALL_DIRECTION_NOTE_PLAIN_KO = (
    "전체 방향은 척도·위기단계·정서 방향의 다수결로 계산되며, 악화 신호가 하나라도 "
    "있으면 악화로 우선 판정합니다. 정서 포함 여부에 따라 결과가 달라질 수 있습니다."
)

_DIMENSION_KO = {
    "phq9_total": "PHQ-9 총점",
    "gad7_total": "GAD-7 총점",
    "auditc_total": "AUDIT-C 총점",
    "session_ctrs": "위기 단계(CTRS)",
    "sentiment": "감성 점수",
    "slot_fill_count": "문진 항목 충족도",
}

# 12 표준 슬롯 중 대화에서 절대 채워지지 않는 시스템 전용 슬롯
# (`grounding.SYSTEM_SLOT_KEYS`) + 이미 A4에서 전문 서술로 다루는
# 관찰 전용 슬롯(`grounding.OBSERVATION_SLOT_KEY`) — 슬롯 표에서 제거
# (binding rule 4: "'진료 기본정보/정신상태검사' 같은 시스템 행 제거").
_SLOT_TABLE_EXCLUDE_KEYS = frozenset(
    {"encounter_metadata", "clinical_assessment", "treatment_plan", "mental_status_exam"}
)

# 주요 경과 불릿 후보 우선순위 — 위험 관련 슬롯을 최우선으로.
_COURSE_BULLET_PRIORITY = (
    "risk_assessment",
    "chief_complaint",
    "history_of_present_illness",
    "personal_social_history",
    "past_psychiatric_history",
    "medical_history",
    "family_history",
    "substance_use_history",
)

_SLOT_HISTORY_SESSION_RE = re.compile(r"^S(\d+):")


def _severity_ko(severity: str | None) -> str:
    if not severity:
        return "미상"
    return _SEVERITY_KO.get(severity, severity)


def _ctrs_stage_ko(ctrs: int | None) -> str:
    if ctrs is None:
        return "미상"
    return f"{ctrs}/5 — {_CTRS_STAGE_KO.get(ctrs, '미상')}"


def _dimension_ko(dimension: str) -> str:
    return _DIMENSION_KO.get(dimension, dimension)


def _truncate(
    text: str | None, limit: int = 80, *, appendix: _AppendixCollector, label: str
) -> str:
    """Truncates *text* for a compact body cell/line — CVR-026 Finding 1
    (blocking): a truncated value's marker now points to a REAL, numbered
    "상세 부록" (detail appendix) entry carrying the SAME full *text*
    (never `"(상세 아래)"`, which pointed nowhere). `appendix`/`label` are
    mandatory — every call site owns an `_AppendixCollector` for its
    render pass."""
    if not text:
        return ""
    t = str(text)
    if len(t) <= limit:
        return t
    n = appendix.anchor(label, t)
    return f"{t[:limit].rstrip()}… (상세 부록 {n} 참조)"


# Some engine-authored free text (F4's own `crisis_f3_gaps` sentences,
# carried verbatim onto `QuestionnaireSection.gap_disclosure`) embeds raw
# `field_name=value` tokens. Binding rule 1 bans internal field names in
# the body — this translates those tokens to Korean clinical labels
# in-place (reformatting only, never invents a new fact).
_INTERNAL_FIELD_TOKEN_RE = re.compile(
    r"\b(crisis_triggered|session_ctrs|probe_event_count|safety_referral|"
    r"critical_item_positive|risk_floor)=([^\s,)]+)"
)
_INTERNAL_FIELD_LABEL_KO = {
    "crisis_triggered": "위기반응",
    "session_ctrs": "위기단계(CTRS)",
    "probe_event_count": "위기확인질문",
    "safety_referral": "안전의뢰",
    "critical_item_positive": "9번문항",
    "risk_floor": "안전최저기준",
}
_BOOL_VALUE_KO = {"True": "있음", "False": "없음", "None": "미상"}

# CVR-026 Finding 5 (minor): internal review/bug-ID citations (`CVR-020
# Finding 4 / binding condition 3`, `REV-045 row 2`, `src.f4::_overall_
# direction`, ...) embedded in engine-authored free text (F4's own
# `crisis_f3_gaps` sentences) — stripped from body prose and relocated to
# the 각주 "시스템 참고" subsection via `_SystemNoteCollector`, never
# dropped outright (audit traceability preserved, just not in front of a
# clinician scanning the body).
_INTERNAL_REF_RE = re.compile(
    r"\s*\((?:CVR|REV|VAL|BUG|ADR|ISS)-\d+[^)]*\)|\bsrc\.\w+(?:\.\w+)*::\w+\b"
)


def _strip_internal_refs(text: str, notes: _SystemNoteCollector) -> str:
    """Removes every internal review/bug-ID citation from *text*, recording
    each stripped citation (trimmed) into *notes* for the 각주 "시스템 참고"
    subsection. Reformatting only — the citation's SURROUNDING clinical
    content is never altered or dropped."""

    def _sub(m: re.Match[str]) -> str:
        notes.add(m.group(0).strip(" ()"))
        return ""

    cleaned = _INTERNAL_REF_RE.sub(_sub, text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _humanize_engine_text(text: str, notes: _SystemNoteCollector) -> str:
    def _sub(m: re.Match[str]) -> str:
        key, val = m.group(1), m.group(2)
        label = _INTERNAL_FIELD_LABEL_KO.get(key, key)
        val_ko = _BOOL_VALUE_KO.get(val, val)
        return f"{label}={val_ko}"

    translated = _INTERNAL_FIELD_TOKEN_RE.sub(_sub, text)
    return _strip_internal_refs(translated, notes)


def _staleness_note_ko(sp) -> str:
    """Rebuilds `StalenessPointer.note` from its own STRUCTURED fields
    (never invents) — the engine's own `.note` text embeds raw
    `safety_referral=`/`critical_item_positive=` tokens (binding rule 1
    bans those in the body); every fact below already exists on `sp`."""
    if not sp.applicable or sp.latest_scored_session_index is None:
        return sp.note  # no internal field tokens in these 2 branches
    item9_label = _a6_item9_or_critical_label(sp.scale_name)
    item9 = (
        "양성"
        if sp.critical_item_positive
        else "음성"
        if sp.critical_item_positive is False
        else "미상"
    )
    referral = "있음" if sp.safety_referral else "없음" if sp.safety_referral is False else "미상"
    stale = f"{sp.sessions_stale}회차" if sp.sessions_stale is not None else "미상"
    if sp.days_stale is not None:
        stale += f"({sp.days_stale}일)"
    return (
        f"당해 세션에는 설문이 시행되지 않았습니다. 가장 최근 시행: "
        f"{sp.latest_scored_session_index}회차({sp.latest_scored_simulated_date}) "
        f"{sp.scale_name} {sp.total_score}/{sp.max_score}점({_severity_ko(sp.severity)}), "
        f"{item9_label} {item9} · 안전 의뢰 신호 {referral} — {stale} 경과."
    )


def _risk_flag_line(a3: RiskSafetySection) -> str:
    """Never parses free-text for a denial/affirmation of suicidal
    ideation (that would be an inference this renderer is not entitled to
    make) — states only the structured item-9-positive count that already
    exists on `longitudinal_risk_signals`, plus the current session's own
    risk-assessment presence."""
    positives = [s for s in a3.longitudinal_risk_signals if s.critical_item_positive]
    if positives:
        sessions = ", ".join(f"{s.session_index}회차" for s in positives)
        line = f"자살사고 문항(9번) 양성 {len(positives)}회 확인 ({sessions}) — 임상 확인 권장"
    elif a3.risk_assessment_present:
        line = "자살사고 문항 양성 이력 없음 (자가보고 기준)"
    else:
        line = "위험평가 정보 없음"
    if a3.crisis_triggered:
        line = f"당해 세션 위기 반응 발생 — {line}"
    return line


def _recommend_administer_mismatch_ko(
    a3: RiskSafetySection, a5: QuestionnaireSection, a7: RecommendationSection
) -> str | None:
    """CVR-032 Finding 5 / CVR-033 Finding 5: 권고-시행 불일치 note.

    Prefers `a5.mismatch_sessions` (`f5.py::_build_a5`'s PER-SESSION
    comparison over the WHOLE arc, from `all_f3_administrations`) — the
    CVR-032 original single latest-vs-latest comparison silently missed
    every earlier mismatched session (e.g. VP-001's GAD-7-recommended /
    PHQ-9-administered sessions). Falls back to the single-session A7-vs-A5
    comparison only when the caller has not supplied per-session F2
    recommendations (`mismatch_sessions` empty, e.g. older callers) —
    `None` when neither source shows a mismatch."""
    if a5.mismatch_sessions:
        total = a3.administered_session_count or len(a5.mismatch_sessions)
        by_pair: dict[tuple[str, str], list[int]] = {}
        for m in a5.mismatch_sessions:
            by_pair.setdefault(
                (m.recommended_questionnaire, m.administered_scale_name), []
            ).append(m.session_index)
        clauses = [
            f"권고 {rec} vs 시행 {adm}: {len(sessions)}/{total}세션"
            f"({', '.join(f'{i}회차' for i in sessions)})"
            for (rec, adm), sessions in by_pair.items()
        ]
        return "권고-시행 불일치 — " + "; ".join(clauses)
    if not a7.recommended_questionnaire or not a5.present or not a5.scale_name:
        return None
    if a7.recommended_questionnaire == a5.scale_name:
        return None
    return (
        f"권고-시행 불일치: F2 추천 설문은 {a7.recommended_questionnaire}이나 "
        f"실제 시행 설문은 {a5.scale_name}입니다."
    )


def _scale_trend_line(a5: QuestionnaireSection, lon: LongitudinalAnalysisOutput) -> str:
    if not a5.present or not a5.scale_name:
        return "시행된 설문 없음"
    base = f"{a5.scale_name} {a5.total_score}/{a5.max_score} ({_severity_ko(a5.severity)})"
    points = sorted(
        (
            p
            for p in lon.scale_series.get(a5.scale_name, [])
            if p.administered and p.total_score is not None
        ),
        key=lambda p: p.session_index,
    )
    if len(points) >= 2:
        first, last = points[0], points[-1]
        if last.total_score == first.total_score:
            arrow = "→"
        elif last.total_score < first.total_score:
            arrow = "↓"
        else:
            arrow = "↑"
        base += f" {arrow} ({first.total_score}→{last.total_score}, {first.session_index}회차 대비)"
    if a5.is_stale_relative_to_header:
        base += " [당해 세션 미시행, 직전 시행값]"
    return base


def _key_concerns(
    a3: RiskSafetySection, a5: QuestionnaireSection, lon: LongitudinalAnalysisOutput
) -> list[str]:
    concerns: list[str] = []
    discordant = [
        s for s in a3.longitudinal_risk_signals if s.discordance_note.startswith("불일치")
    ]
    if discordant:
        concerns.append(f"설문 위험 신호와 CTRS 불일치 {len(discordant)}회 — 임상 확인 권장")
    if a5.present and a5.ceiling_caveat:
        concerns.append("최근 설문 만점(과대추정 가능성)")
    if lon.crisis_f3_gaps:
        concerns.append(f"위기 고조 세션 중 설문 미시행 {len(lon.crisis_f3_gaps)}건")
    # CVR-028 Finding 7 (minor-major, VP-002): the SBAR headline must never
    # read "특이 우려 사항 없음" while B1's own 종단추세 section (three
    # paragraphs later in the same report) computes `overall_direction=
    # worsened` — a time-pressed clinician reading only the headline would
    # get a directly contradicted, falsely reassuring signal. Fires
    # whenever F4's own `overall_direction` (never recomputed here, only
    # juxtaposed) is "worsened" — an honest pointer to the body section,
    # not a re-diagnosis of WHY it is worsened (that reasoning, including
    # any dimension-vote tie-break nuance, lives in B1's own
    # `overall_direction_sensitivity_note`).
    if lon.overall_direction == "worsened":
        concerns.append("추세 판정 혼재 — 본문 종단 추세 참조")
    return concerns or ["특이 우려 사항 없음"]


def _summary_box_lines(report: HandoffReportOutput, appendix: _AppendixCollector) -> list[str]:
    """핵심 요약 (SBAR식, ≤8줄) — binding rule 2."""
    a0, a1, a3, a5 = (
        report.a0_header,
        report.a1_chief_complaint,
        report.a3_risk_safety,
        report.a5_questionnaires,
    )
    lon = report.b_longitudinal.analysis
    span = f" · {lon.session_span_days}일" if lon.session_span_days is not None else ""
    return [
        f"환자: {a0.persona_name} ({a0.persona_id}) — {a0.session_index}회차 "
        f"({a0.simulated_date}), 총 {lon.n_sessions}세션{span}",
        "주호소: "
        + (
            _truncate(a1.text, 80, appendix=appendix, label="주호소 전문")
            if a1.present
            else "미수집"
        ),
        f"위험 플래그: {_risk_flag_line(a3)}",
        f"최신 설문: {_scale_trend_line(a5, lon)}",
        # CVR-032 Finding 1-2 (blocking/major): course_shape + worst-session
        # (nadir) disclosure in the headline itself, not only deep in the
        # 종단 추세 body section — the SBAR box is where a time-pressed
        # clinician reads first.
        "경과 형태: "
        + _COURSE_SHAPE_KO.get(lon.course_shape, lon.course_shape)
        + (f" — {_worst_session_callout_ko(lon, a3)}" if _min_ctrs_disclosed(a3) else ""),
        f"주요 우려: {'; '.join(_key_concerns(a3, a5, lon))}",
    ]


_DISCLAIMER_BOX_KO = [
    "자가보고(AI 대화형 문진) 기반 비공식 문서이며 공식 의무기록·의학적 진단이 아닙니다.",
    "AI 예상질환(하단)은 유사도 기반 참고 정보일 뿐 확률·가능성·진단이 아닙니다.",
    "최종 진단과 치료 방향은 반드시 의료진의 판단에 따라 결정되어야 합니다.",
]


def _risk_prose(
    lon: LongitudinalAnalysisOutput, a3: RiskSafetySection, appendix: _AppendixCollector
) -> str:
    # CVR-026 Finding 1 (blocking, 최우선): the current-session risk
    # narrative's own patient-quote — a truncated, dead-referenced cut of
    # this exact quote was the single highest-severity finding. Full text
    # now always lands in the 상세 부록.
    risk_text = (
        _truncate(
            a3.risk_assessment_text, 100, appendix=appendix, label="위험평가 발화 원문 (당해 세션)"
        )
        if a3.risk_assessment_present
        else "정보 없음"
    )
    session_ref = f"당해 세션({a3.current_session_index}회차, {a3.current_simulated_date})"
    parts = [
        f"{session_ref} 위험평가: {risk_text}.",
        f"위기 단계(CTRS) {_ctrs_stage_ko(a3.session_ctrs)}.",
    ]
    # CVR-032 Finding 1-2 (blocking/major): worst-session (nadir) disclosure
    # in the risk section itself, not only the current/latest session's own
    # CTRS above — the same gating condition as the 종단 추세 section's
    # qualified sentence (`_min_ctrs_disclosed`).
    if _min_ctrs_disclosed(a3):
        parts.append(f"전체 세션 중 최저 위기 단계: {_worst_session_callout_ko(lon, a3)}.")
    discordant = [
        s for s in a3.longitudinal_risk_signals if s.discordance_note.startswith("불일치")
    ]
    if discordant:
        parts.append(
            f"과거 {len(discordant)}회 세션에서 설문 자살사고 문항(9번) 양성/안전 의뢰 신호가 "
            "동일 세션 CTRS 상승에 반영되지 않아 불일치가 확인됩니다 — 임상 확인이 권장됩니다."
        )
    return " ".join(parts)


def _risk_discordance_verdict(discordance_note: str, appendix: _AppendixCollector) -> str:
    if discordance_note.startswith("불일치"):
        return "불일치"
    if discordance_note.startswith("일치"):
        return "일치"
    return _truncate(discordance_note, 20, appendix=appendix, label="위험 신호 판정 원문")


def _risk_table_rows(
    a3: RiskSafetySection, appendix: _AppendixCollector
) -> list[tuple[str, str, str, str, str]]:
    rows = []
    for sig in a3.longitudinal_risk_signals:
        if sig.critical_item_positive is True:
            item9 = "양성"
        elif sig.critical_item_positive is False:
            item9 = "음성"
        else:
            item9 = "미상"
        verdict = _risk_discordance_verdict(sig.discordance_note, appendix)
        if sig.ceiling_caveat:
            verdict += " · 만점"
        score = f"{sig.total_score}/{sig.max_score}" if sig.total_score is not None else "-"
        rows.append((str(sig.session_index), sig.simulated_date, score, item9, verdict))
    return rows


def _absent_session_rows(
    a3: RiskSafetySection, lon: LongitudinalAnalysisOutput
) -> list[tuple[str, str, str, str, str]]:
    """Renderer polish (F5 conductor-output review, VP-004): the risk table
    only ever carried FLAGGED (item-9-positive/`safety_referral`) sessions
    (`longitudinal_risk_signals`), so any session without a flagged signal
    vanished from the visible sequence with no trace (e.g. session 6 absent
    between 5 and 7) -- indistinguishable from a data gap to a reader.
    Every session index F1 ever scored a CTRS for (`lon.ctrs_series`, always
    populated once per session regardless of F3) that is NOT already a row
    in `risk_rows` gets an explicit placeholder row here instead, silence
    never being an acceptable rendering. The reason is derived only from
    data this module already has in hand -- an administered-but-unflagged
    scale (`lon.scale_series`, e.g. a session where GAD-7 ran instead of
    PHQ-9 and so has no item-9 concept at all) or a same-session crisis
    trigger -- never invented; falls back to "미시행" when neither applies.
    """
    shown = {sig.session_index for sig in a3.longitudinal_risk_signals}
    admin_by_session: dict[int, tuple[str | None, int | None, int | None]] = {}
    for points in lon.scale_series.values():
        for p in points:
            if p.administered:
                admin_by_session.setdefault(
                    p.session_index, (p.scale_name, p.total_score, p.max_score)
                )
    rows: list[tuple[str, str, str, str, str]] = []
    for point in lon.ctrs_series:
        if point.session_index in shown:
            continue
        admin = admin_by_session.get(point.session_index)
        if admin is not None:
            scale_name, _total, _max = admin
            reason = f"설문 시행({scale_name or '척도명 미상'}) — 항목9 위험 신호 없음"
        elif point.crisis_triggered:
            reason = "위기 조기종료"
        else:
            reason = "미시행"
        rows.append((str(point.session_index), point.simulated_date, "미시행", "-", reason))
    return rows


def _full_risk_table_rows(
    a3: RiskSafetySection, lon: LongitudinalAnalysisOutput, appendix: _AppendixCollector
) -> list[tuple[str, str, str, str, str]]:
    """`_risk_table_rows` (flagged sessions) merged with `_absent_session_rows`
    (every remaining ledger session), sorted back into session order -- the
    table renders every session once, never a silent gap."""
    combined = _risk_table_rows(a3, appendix) + _absent_session_rows(a3, lon)
    return sorted(combined, key=lambda row: int(row[0]))


def _ceiling_caveat_summary(a3: RiskSafetySection) -> str | None:
    """CVR-028 near-ceiling caveat coverage (`ADR-038` Decision 2c) previously
    repeated the identical `CEILING_SCORE_CAVEAT_KO` sentence once per
    affected session as N near-identical blockquote/paragraph lines --
    consolidated here into ONE line naming every affected session and its
    score range, the per-row "· 만점" table-cell marker is untouched (still
    written by `_risk_table_rows`)."""
    affected = [sig for sig in a3.longitudinal_risk_signals if sig.ceiling_caveat]
    if not affected:
        return None
    session_str = "·".join(str(sig.session_index) for sig in affected)
    scores = [sig.total_score for sig in affected if sig.total_score is not None]
    max_scores = [sig.max_score for sig in affected if sig.max_score is not None]
    if scores and max_scores:
        lo, hi = min(scores), max(scores)
        top = max(max_scores)
        if lo == hi:
            range_label = "만점" if lo == top else f"근접({lo}/{top})"
        elif hi == top:
            range_label = f"만점/근접({lo}-{hi}/{top})"
        else:
            range_label = f"근접({lo}-{hi}/{top})"
    else:
        range_label = "만점/근접"
    caveat_text = affected[0].ceiling_caveat
    return f"[세션 {session_str} — {range_label}] {caveat_text}"


def _mse_lines(a4: MentalStatusSection) -> list[str]:
    assessable = [d for d in a4.domain_checklist if d.assessable]
    if not a4.present and not assessable:
        return ["텍스트 문진 특성상 관찰 기반 MSE는 평가 불가; 대화에서 도출된 소견 없음"]
    lines = [f"{a4.label}: {a4.raw_text}"] if a4.present else []
    if assessable:
        lines += [f"- {d.domain}: {d.note}" for d in assessable]
    elif a4.present:
        lines.append("개별 영역(mood/insight 등) 평가는 이 슬롯 특성상 불가")
    return lines


def _slot_table_rows(so: SlotOverviewSection) -> list[SlotOverviewRow]:
    return [r for r in so.rows if r.key not in _SLOT_TABLE_EXCLUDE_KEYS]


def _change_history_summary(row: SlotOverviewRow) -> str:
    if not row.change_history:
        return "-"
    sessions = [m.group(1) for h in row.change_history if (m := _SLOT_HISTORY_SESSION_RE.match(h))]
    base = (
        f"{len(row.change_history)}회 변화 (S{'→S'.join(sessions)})"
        if sessions
        else f"{len(row.change_history)}회 변화"
    )
    # CVR-026 Finding 2: the table cell stays compact (60-char-per-entry
    # preview), but every distinct-change slot now has a real pointer to
    # its own full, untruncated quotes in the 상세 부록.
    if row.change_history_full:
        base += " · 상세 부록 참조"
    return base


_SCALE_SCORE_RE = re.compile(r"(PHQ-?9|GAD-?7|CTRS)\D{0,10}?(\d+)\s*/\s*(\d+)", re.IGNORECASE)


def _history_entry_scale_score(entry: str) -> tuple[str, int, int] | None:
    """Extracts an embedded (scale_name, total_score, max_score) triple from
    one `change_history` entry when the slot's own text states a scored
    dimension (PHQ-9/GAD-7/CTRS) verbatim -- `None` for the ordinary case of
    free-form qualitative text with no numeric score axis, and `None` (never
    a crash) on any malformed/non-numeric match."""
    match = _SCALE_SCORE_RE.search(entry)
    if not match:
        return None
    scale_name, total_str, max_str = match.groups()
    try:
        total, top = int(total_str), int(max_str)
    except ValueError:
        return None
    if top <= 0 or total < 0:
        return None
    return scale_name.upper().replace("-", ""), total, top


def _scale_nadir_index(history: list[str]) -> int | None:
    """Value-based extremum selection for dimensions carrying a numeric
    score (PHQ-9/GAD-7/CTRS) embedded in their own text. CTRS is a 0-5
    stability scale where LOWER is clinically worse (closer to crisis);
    PHQ-9/GAD-7 are symptom scales where a HIGHER score/max ratio is worse.
    Returns `None` (no scored axis to compare) unless at least 2 entries
    carry a parseable score -- callers must fall back to the qualitative
    selection principle in that case."""
    scored = [
        (i, score)
        for i, entry in enumerate(history)
        if (score := _history_entry_scale_score(entry)) is not None
    ]
    if len(scored) < 2:
        return None

    def _severity(item: tuple[int, tuple[str, int, int]]) -> float:
        scale_name, total, top = item[1]
        ratio = total / top
        return (1 - ratio) if scale_name == "CTRS" else ratio

    return max(scored, key=_severity)[0]


def _qualitative_nadir_index(history: list[str], min_ctrs_session_index: int | None) -> int:
    """Non-positional selection principle for slots with no numeric score
    axis (CC/HPI/PSH/etc.): picks the `change_history` entry whose own
    session is closest to the arc's min-CTRS ("위험-인접") session -- the
    same nadir marker already computed for A3/F4 (`RiskSafetySection.
    min_ctrs_session_index`) -- instead of the list's positional midpoint.
    Falls back to the old positional midpoint only as a last resort, when no
    CTRS nadir session is known at all (e.g. no F3 administration occurred
    anywhere in the arc) or no entry carries a parseable session marker."""
    if min_ctrs_session_index is None:
        return len(history) // 2
    candidates = [
        (i, int(m.group(1)))
        for i, entry in enumerate(history)
        if (m := _SLOT_HISTORY_SESSION_RE.match(entry))
    ]
    if not candidates:
        return len(history) // 2
    return min(candidates, key=lambda pair: abs(pair[1] - min_ctrs_session_index))[0]


def _major_course_bullets(
    so: SlotOverviewSection, a3: RiskSafetySection, limit: int = 5
) -> list[str]:
    """CVR-026 Finding 3 (major): a first/last-only selection can silently
    drop a clinically material EARLY signal (e.g. an HPI slot's original
    precipitant, only ever stated in session 1) into the elided middle.
    Selects first + one material MIDDLE change point (whenever >=3 change
    points exist — every `change_history` entry is already a materially
    DISTINCT value, the engine collapses non-changes before this list is
    built, `f5.py::_slot_row`) + last, instead of first/last with an
    ellipsis placeholder.

    D2 (#6) fix: the MIDDLE point is no longer the positional midpoint
    (`history[len(history)//2]`), which can silently miss the clinically
    most-severe (nadir) session. Dimensions that carry a numeric score
    (PHQ-9/GAD-7/CTRS) embedded in their own text select the true value-
    based extremum (`_scale_nadir_index`); qualitative dimensions with no
    score axis (CC/HPI/etc.) select the entry nearest the arc's min-CTRS
    ("위험-인접") session instead (`_qualitative_nadir_index`), falling back
    to the positional midpoint only when no nadir reference is available."""
    rows_by_key = {r.key: r for r in so.rows}
    bullets: list[str] = []
    for key in _COURSE_BULLET_PRIORITY:
        row = rows_by_key.get(key)
        if row and len(row.change_history) >= 2:
            history = row.change_history
            if len(history) >= 3:
                nadir_idx = _scale_nadir_index(history)
                if nadir_idx is None:
                    nadir_idx = _qualitative_nadir_index(history, a3.min_ctrs_session_index)
                nadir = history[nadir_idx]
                arrow = f"{history[0]} → {nadir} → {history[-1]}"
            else:
                arrow = f"{history[0]} → {history[-1]}"
            bullets.append(f"{row.label}: {arrow}")
        if len(bullets) >= limit:
            break
    return bullets


def _compact_evidence(evidence: list[str], dimension: str) -> str:
    """`evidence[0]` (F4's own text) is prefixed `"{label}: "` where
    `label` is often the RAW internal dimension name verbatim
    (`session_ctrs`/`slot_fill_count` — `src/f4.py::_first_last_slope_
    trend`'s own `label=` argument, confirmed by direct read). The row's
    own '항목' column already shows the Korean dimension label, so this
    strips that redundant (and sometimes internal-token) prefix rather
    than translating it in place — reformatting only, drops no fact."""
    if not evidence:
        return "(근거 없음)"
    line = evidence[0].replace("->", "→").replace("first-vs-last delta session", "세션")
    prefix = f"{dimension}: "
    if line.startswith(prefix):
        line = line[len(prefix) :]
    return line


def _trend_table_rows(lon: LongitudinalAnalysisOutput) -> list[tuple[str, str, str]]:
    return [
        (
            _dimension_ko(tv.dimension),
            _DIRECTION_KO.get(tv.direction, tv.direction),
            _compact_evidence(tv.evidence, tv.dimension),
        )
        for tv in lon.trend_verdicts
    ]


def _ctrs_table_rows(
    lon: LongitudinalAnalysisOutput,
) -> tuple[list[tuple[str, str, str, str, str | None]], bool]:
    any_probe = any(p.probe_event_count for p in lon.ctrs_series)
    rows = [
        (
            str(p.session_index),
            p.simulated_date,
            _ctrs_stage_ko(p.session_ctrs),
            "위기 반응" if p.crisis_triggered else "-",
            str(p.probe_event_count) if any_probe else None,
        )
        for p in lon.ctrs_series
    ]
    return rows, any_probe


_GAP_ACUITY_FRAMING_POINTER_KO = "※ 위 '시행된 설문 · F3 공백' 참조 (동일 안내)"

# CVR-026 Finding 8 (minor): within A3 alone, the exact-ceiling caveat
# previously repeated in full between the risk-signal table and the
# staleness-pointer note immediately below it.
_CEILING_POINTER_KO = "※ 위 표 참조 (동일 세션 만점 캐비앗)"


def _min_ctrs_disclosed(a3: RiskSafetySection) -> bool:
    """True whenever there is anything worth disclosing about the arc's
    worst point — a min CTRS below "안정"(4), a safety_net administration,
    or any item-9 positive. False only for a genuinely quiet series (CVR-032
    Finding 1's exact gating condition for the blanket "없음" line)."""
    return (
        (a3.min_ctrs_value is not None and a3.min_ctrs_value < 4)
        or bool(a3.safety_net_sessions)
        or a3.item9_positive_count > 0
    )


def _secondary_signals_ko(a3: RiskSafetySection) -> str:
    """safety_net + item-9 clauses ONLY — no CTRS clause (used by the
    CVR-033 Finding A honesty-qualifier branch, which states the CTRS band
    itself separately, and by `_worst_session_callout_ko` below)."""
    parts: list[str] = []
    if a3.safety_net_sessions:
        sessions = ", ".join(f"{i}회차" for i in a3.safety_net_sessions)
        parts.append(f"안전망(safety_net) 설문 시행 {len(a3.safety_net_sessions)}건({sessions})")
    if a3.item9_positive_count:
        parts.append(
            f"자살사고 문항(9번) 양성 {a3.item9_positive_count}/{a3.administered_session_count}세션"
        )
    return ", ".join(parts)


class _NadirScale(NamedTuple):
    scale_name: str | None
    total_score: int
    max_score: int | None
    severity: str | None


def _nadir_scale_point(
    lon: LongitudinalAnalysisOutput, a3: RiskSafetySection
) -> _NadirScale | None:
    """CVR-033 Finding 3: the nadir (min-CTRS) session's own administered
    scale score. Checks `a3.longitudinal_risk_signals` first (already
    reliably derived from `all_f3_administrations` by `_build_a3` for any
    flagged — item-9-positive or `safety_referral` — session), then falls
    back to `lon.scale_series` (ALL scales across the arc, flagged or not)
    so a nadir session whose administered scale was unflagged is never
    silently skipped. `None` when the nadir session had no administered
    scale in either source."""
    if a3.min_ctrs_session_index is None:
        return None
    signal = next(
        (
            s
            for s in a3.longitudinal_risk_signals
            if s.session_index == a3.min_ctrs_session_index and s.total_score is not None
        ),
        None,
    )
    if signal is not None:
        return _NadirScale(signal.scale_name, signal.total_score, signal.max_score, signal.severity)
    for points in lon.scale_series.values():
        for p in points:
            if (
                p.session_index == a3.min_ctrs_session_index
                and p.administered
                and p.total_score is not None
            ):
                return _NadirScale(p.scale_name, p.total_score, p.max_score, p.severity)
    return None


def _worst_session_callout_ko(lon: LongitudinalAnalysisOutput, a3: RiskSafetySection) -> str:
    """Compact worst-session clause — the SAME components (min-CTRS
    session, safety_net sessions, item-9 N/M) in every rendering location
    (headline/risk-section/trend-section), never independently recomputed
    per call site. CVR-033 Finding 3 (partial): includes the nadir
    session's own administered scale score when one exists — the arc's
    worst CTRS point is exactly where a clinician most needs the co-located
    scale reading, not a cross-reference to a table elsewhere."""
    parts: list[str] = []
    if a3.min_ctrs_value is not None:
        ctrs_clause = (
            f"{a3.min_ctrs_session_index}회차({a3.min_ctrs_simulated_date})에서 "
            f"CTRS {a3.min_ctrs_value}/5({_CTRS_STAGE_KO.get(a3.min_ctrs_value, '미상')})"
        )
        nadir_point = _nadir_scale_point(lon, a3)
        if nadir_point is not None:
            mode_label = "안전망 " if a3.min_ctrs_session_index in a3.safety_net_sessions else ""
            ctrs_clause += (
                f", {mode_label}{nadir_point.scale_name} "
                f"{nadir_point.total_score}/{nadir_point.max_score} "
                f"({_severity_ko(nadir_point.severity)})"
            )
        parts.append(ctrs_clause)
    secondary = _secondary_signals_ko(a3)
    if secondary:
        parts.append(secondary)
    return ", ".join(parts)


def _events_and_concordance_lines(
    lon: LongitudinalAnalysisOutput,
    b: LongitudinalSection,
    a3: RiskSafetySection,
    *,
    gap_framing_already_shown: bool,
    notes: _SystemNoteCollector,
) -> list[str]:
    lines: list[str] = []
    # CVR-032 Finding 1 (blocking): course_shape was computed (F4) but never
    # surfaced anywhere in rendered prose.
    lines.append(
        f"경과 형태(course_shape): {_COURSE_SHAPE_KO.get(lon.course_shape, lon.course_shape)}"
    )
    crisis_sessions = [p for p in lon.ctrs_series if p.crisis_triggered]
    if crisis_sessions:
        s = ", ".join(f"{p.session_index}회차({p.simulated_date})" for p in crisis_sessions)
        lines.append(f"위기 반응 발생 세션: {s}")
    elif a3.min_ctrs_value is not None and a3.min_ctrs_value <= 2:
        # CVR-033 Finding 1 (major): the old "위기 전환(CTRS 1-2) 세션은
        # 없었으나" sentence self-contradicted whenever min CTRS itself fell
        # in the 1-2 band it just denied (`crisis_triggered` only reflects
        # whether the orchestrator's bypass actually fired, not the CTRS
        # value). State the crisis-band session plainly and flag the flow
        # mismatch instead of denying it.
        secondary = _secondary_signals_ko(a3)
        tail = f", {secondary}" if secondary else ""
        lines.append(
            f"{a3.min_ctrs_session_index}회차({a3.min_ctrs_simulated_date})에 위기 수준"
            f"(CTRS {a3.min_ctrs_value}/5, "
            f"{_CTRS_STAGE_KO.get(a3.min_ctrs_value, '미상')}) 세션 발생{tail} — "
            "위기 전환 플로우 미발동: 기록 불일치 가능성, 임상 확인 필요"
        )
    elif a3.min_ctrs_value == 3:
        # CVR-032 Finding 1: the blanket "없음" line must not render while
        # there IS a worse-than-stable interim signal — replace with a
        # qualified sentence naming the actual worst point. Safe here since
        # CTRS 3 genuinely falls outside the 1-2 band the sentence denies.
        callout = _worst_session_callout_ko(lon, a3)
        lines.append(f"위기 전환(CTRS 1-2) 세션은 없었으나, {callout} — 임상 확인 권장")
    elif _min_ctrs_disclosed(a3):
        # min CTRS unknown/4/5 (no low-CTRS clause to assert) but a
        # safety_net administration or item-9 positive still warrants
        # disclosure — state the crisis band is clear, then the secondary
        # signal, never re-asserting a CTRS value that doesn't apply here.
        secondary = _secondary_signals_ko(a3)
        lines.append(f"위기 전환(CTRS 1-2) 세션 없음 — 다만 {secondary} — 임상 확인 권장")
    else:
        lines.append("위기 반응 발생 세션 없음")
    if lon.crisis_f3_gaps:
        lines.append(f"위험 고조 세션 중 설문 미시행: {len(lon.crisis_f3_gaps)}건")
        if b.gap_acuity_framing_note:
            # CVR-026 Finding 6 (major): the near-identical F3-gap-acuity
            # caveat previously repeated verbatim in BOTH "시행된 설문"
            # (F3 공백) and here — collapsed to one canonical rendering
            # (there, if it already showed) plus a short back-pointer here.
            lines.append(
                _GAP_ACUITY_FRAMING_POINTER_KO
                if gap_framing_already_shown
                else _strip_internal_refs(b.gap_acuity_framing_note, notes)
            )
    else:
        lines.append("위험 고조 세션 중 설문 미시행 사례 없음")
    concordance = _CONCORDANCE_KO.get(lon.concordance_flag, lon.concordance_flag)
    lines.append(f"종단 추세 일관성(설문·CTRS·감성): {concordance}")
    return lines


def _a6_item9_or_critical_label(scale_name: str | None) -> str:
    return "자살사고 문항(9번)" if scale_name == "PHQ-9" else "심각 문항(critical item)"


# CVR-026 Finding 4 (major): A6's `reason_summary` is surfaced VERBATIM
# from `src.f2`'s own English engineering prose (schema docstring,
# `handoff_report.py::AIPredictedDiseaseSection.reason_summary`) whenever
# Stage 1 produced zero candidates outside `rag_live` mode — exposing raw
# English pipeline internals in the highest-acuity artifacts (an
# unpopulated A6 tends to co-occur with a crisis-heavy case, CVR-024/026's
# own repeated observation). Matched by EXACT string equality only (a
# regex/substring guess could silently misrender a FUTURE f2.py wording
# change) — an unrecognized string falls through to the generic fallback,
# never guessed at, with the original preserved in the 각주 시스템 참고
# subsection for audit traceability.
_A6_REASON_SUMMARY_KO_MAP: dict[str, str] = {
    (
        "Stage 1 ran in llm_only mode (no RAG chunks retrieved this run) — the "
        "AI-disease container has no chunk-derived evidence to populate from"
    ): "1단계 분석이 RAG(근거 검색) 없이 대화 기반으로만 진행되어 질환 후보를 생성하지 못했습니다.",
}
_A6_REASON_SUMMARY_FALLBACK_KO = "검색 보조 없이 대화 기반으로만 산출됨 — 원문은 각주 참조."


def _a6_reason_summary_ko(reason_summary: str, notes: _SystemNoteCollector) -> str:
    known = _A6_REASON_SUMMARY_KO_MAP.get(reason_summary)
    if known is not None:
        return known
    notes.add(f"AI 참고정보(A6) 사유 원문(미매칭, 감사용): {reason_summary}")
    return _A6_REASON_SUMMARY_FALLBACK_KO


# CVR-026 Finding 5 (major): A7's own "no candidates" absence note embeds
# an internal bug-ticket ID (`VAL-016/BUG-031`) inline in clinician-facing
# prose whenever the upstream cause is a schema-validation drop — rendered
# here as honest, ID-free Korean; the ID-bearing original moves to the
# 각주 시스템 참고 subsection (never dropped, just relocated).
_A7_ABSENCE_VALIDATION_DROPPED_PLAIN_KO = (
    "이번 실행에서는 진료과 후보가 산출되지 않았습니다(후보 검증 단계에서 제외됨). "
    "원 데이터는 각주 참조."
)


def _si_referral_note_ko(a3: RiskSafetySection) -> str | None:
    """CVR-032 Finding 2 (major): when any session this arc had a
    positive item-9 (suicidal ideation), the referral/follow-up section
    must include SI-specific follow-up wording — reuses `contracts.
    survey_plan.SI_POSITIVE_ACTION_KO` (the SAME 109/119 hotline text
    `/ai/survey/plan`'s own SI gating already ships) verbatim, never a
    newly authored clinical sentence. `None` when no session was item-9
    positive. CVR-033 Finding 4 (minor): the section this note renders into
    ("권장 진료과 및 후속 조치") is clinician-facing, but `SI_POSITIVE_ACTION_KO`
    is written as patient-directed script — wrapped here as an explicit
    clinician instruction ("환자에게 다음 안내 권장: ...") rather than a bare
    quote, WITHOUT altering the constant's own text."""
    if a3.item9_positive_count == 0:
        return None
    return (
        f"자살사고 문항(9번) 양성 세션 확인됨 ({a3.item9_positive_count}/"
        f"{a3.administered_session_count}세션) — 환자에게 다음 안내 권장: {SI_POSITIVE_ACTION_KO}"
    )


def _a7_absence_note_ko(a7: RecommendationSection, notes: _SystemNoteCollector) -> str:
    note = a7.department_candidates_absence_note
    if note is None:
        return "정보 없음"
    if note == A7_NO_CANDIDATES_VALIDATION_DROPPED_KO:
        notes.add(f"권장 진료과 미산출 원문(감사용): {note}")
        return _A7_ABSENCE_VALIDATION_DROPPED_PLAIN_KO
    return note


def build_markdown_report(report: HandoffReportOutput) -> str:
    """Clinician-first hand-off report — SBAR summary + risk up front, no
    internal field/ID names in the body, ≤2-min read (binding rules 1-10,
    this mission's readability redesign). Every underlying fact still
    traces to a `HandoffReportOutput` field; this function only reorders,
    translates, and compresses — it never invents. `appendix`/`notes`
    (CVR-026, this mission) collect the full-text/internal-ID material this
    function relocates rather than drops — rendered as "## 상세 부록" and
    the 각주's "시스템 참고" subsection, both near the end."""
    appendix = _AppendixCollector()
    notes = _SystemNoteCollector()

    a0, a1, a2, a3 = (
        report.a0_header,
        report.a1_chief_complaint,
        report.a2_hpi,
        report.a3_risk_safety,
    )
    a4, a5, a6, a7, a8 = (
        report.a4_mental_status,
        report.a5_questionnaires,
        report.a6_ai_predicted_disease,
        report.a7_recommendations,
        report.a8_narrative,
    )
    b = report.b_longitudinal
    lon = b.analysis
    so = report.slot_overview

    lines: list[str] = [f"# F5 인계 요약 보고서 — {report.vp_id}", ""]

    # ── 핵심 요약 (SBAR box) ──
    lines += ["> **핵심 요약**", ">"]
    lines += [f"> - {line}" for line in _summary_box_lines(report, appendix)]
    lines.append("")

    # ── 면책 조항 (3줄 이내 박스) ──
    lines += ["> **면책 조항**", ">"]
    lines += [f"> - {line}" for line in _DISCLAIMER_BOX_KO]
    lines.append("")

    # ── 위험/안전 평가 ──
    lines += ["## 위험/안전 평가", "", _risk_prose(lon, a3, appendix), ""]
    risk_rows = _risk_table_rows(a3, appendix)
    # CVR-026 Finding 8 (minor): the exact-ceiling caveat previously
    # repeated verbatim BOTH adjacent to the risk table AND in the
    # staleness-pointer note directly below it (same fact, same session,
    # same section) — first full occurrence wins, the second collapses to
    # a short back-pointer. A5's OWN occurrence (ADR-038 Decision 2c,
    # locked by test) is untouched — this dedup is scoped to within A3.
    ceiling_shown_in_a3 = False
    if risk_rows:
        lines += [
            f"> {NON_VALIDATED_ADMINISTRATION_CAVEAT_KO} '판정'은 설문 위험 신호와 동일 세션 "
            "CTRS 평가의 일치 여부입니다.",
            "",
            "| 세션 | 일자 | 점수 | 9번 문항 | 판정 |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {sid} | {date} | {score} | {item9} | {verdict} |"
            for sid, date, score, item9, verdict in _full_risk_table_rows(a3, lon, appendix)
        ]
        # ADR-038 Decision 2c / renderer polish (VP-004 review): full
        # ceiling caveat text still rendered adjacent to the table (never
        # dropped to the "· 만점" table abbreviation alone), now as ONE
        # consolidated line naming every affected session instead of one
        # near-identical line per session.
        ceiling_summary = _ceiling_caveat_summary(a3)
        lines.append("")
        if ceiling_summary:
            ceiling_shown_in_a3 = True
            lines.append(f"> {ceiling_summary}")
            lines.append("")
    else:
        lines += ["해당 없음 — 전체 세션 중 item-9 양성/안전 의뢰 이력이 없습니다.", ""]
    lines += [f"> 최신 시행 척도 안내: {_staleness_note_ko(a3.staleness_pointer)}"]
    if a3.staleness_pointer.total_score is not None:
        lines.append(f"> {NON_VALIDATED_ADMINISTRATION_CAVEAT_KO}")
    if a3.staleness_pointer.ceiling_caveat:
        staleness_ceiling_text = (
            _CEILING_POINTER_KO if ceiling_shown_in_a3 else a3.staleness_pointer.ceiling_caveat
        )
        lines.append(f"> {staleness_ceiling_text}")
    lines.append("")

    # ── 주호소 및 현병력 (+ MSE) ──
    lines += [
        "## 주호소 및 현병력",
        "",
        f"**주호소**: {a1.text if a1.present else '미수집'}",
        "",
        f"**현병력**: {a2.text if a2.present else '미수집'}",
        "",
        "### 정신상태검사 (MSE)",
        "",
    ]
    lines += _mse_lines(a4)
    lines.append("")

    # ── 전체 세션 요약 (슬롯) + 주요 경과 ──
    lines += [
        "## 전체 세션 요약",
        "",
        f"> {so.non_validated_caveat}",
        "",
        "| 슬롯 | 최신값 | 출처 | 변화 | 비고 |",
        "|---|---|---|---|---|",
    ]
    for row in _slot_table_rows(so):
        if not row.collected:
            value_cell, source_cell = SLOT_NEVER_COLLECTED_KO, "-"
        else:
            value_cell = _truncate(
                row.latest_value, 80, appendix=appendix, label=f"{row.label} 최신값 전문"
            )
            source_cell = f"{row.source_session_index}회차/{row.source_simulated_date}"
        lines.append(
            f"| {row.label} | {value_cell} | {source_cell} | {_change_history_summary(row)} | "
            f"{row.section_pointer or '-'} |"
        )
    lines.append("")
    lines.append("**주요 경과**")
    lines.append("")
    course_bullets = _major_course_bullets(so, a3)
    if course_bullets:
        lines += [f"- {b_}" for b_ in course_bullets]
    else:
        lines.append("- 표시할 주요 경과 변화 없음")
    lines.append("")

    # ── 시행된 설문 ──
    lines += ["## 시행된 설문", ""]
    gap_framing_shown = False
    if not a5.present:
        lines += ["정보 없음 (전체 세션 중 시행된 설문 없음)", ""]
    else:
        lines += [
            f"> {a5.non_validated_caveat}",
            "",
            f"**{a5.scale_name} {a5.total_score}/{a5.max_score} "
            f"({_severity_ko(a5.severity)})** — {a5.administering_session_index}회차 "
            f"({a5.administering_simulated_date})"
            + (" [당해 세션 미시행, 직전 시행값]" if a5.is_stale_relative_to_header else ""),
            "",
            f"- 응답: {','.join(str(v) for v in a5.responses)}",
            f"- {_a6_item9_or_critical_label(a5.scale_name)}: "
            + (
                "양성"
                if a5.critical_item_positive
                else "음성"
                if a5.critical_item_positive is False
                else "미상"
            ),
            f"- 문진 방식: {a5.administration_mode or '미상'}",
        ]
        mismatch_note = _recommend_administer_mismatch_ko(a3, a5, a7)
        if mismatch_note:
            lines.append(f"- {mismatch_note}")
        if a5.threshold_caveat:
            lines.append(f"- {a5.threshold_caveat}")
        if a5.threshold_caveat_asymmetry_note:
            lines.append(f"- {a5.threshold_caveat_asymmetry_note}")
        if a5.ceiling_caveat:
            # A5 stays the canonical cross-section occurrence (ADR-038
            # Decision 2c, locked by test) — never deduped away.
            lines.append(f"- {a5.ceiling_caveat}")
        lines.append("")
        if a5.gap_disclosure:
            lines.append("**F3 공백 (당해 세션까지):**")
            lines.append("")
            if a5.gap_acuity_framing_note:
                lines += [f"> {_strip_internal_refs(a5.gap_acuity_framing_note, notes)}", ""]
                gap_framing_shown = True
            lines += [f"- {_humanize_engine_text(g, notes)}" for g in a5.gap_disclosure]
            lines.append("")

    # ── 종단 추세 + 차트 ──
    lines += [
        "## 종단 추세",
        "",
        f"전체 방향: **{_DIRECTION_KO.get(lon.overall_direction, lon.overall_direction)}** "
        f"({lon.n_sessions}세션"
        + (f", {lon.session_span_days}일" if lon.session_span_days is not None else "")
        + ")",
        "",
        f"> {_OVERALL_DIRECTION_NOTE_PLAIN_KO}",
        "",
        "| 항목 | 방향 | 근거 |",
        "|---|---|---|",
    ]
    for dim, direction, evidence in _trend_table_rows(lon):
        lines.append(f"| {dim} | {direction} | {evidence} |")
    lines.append("")
    lines += _events_and_concordance_lines(
        lon, b, a3, gap_framing_already_shown=gap_framing_shown, notes=notes
    )
    lines.append("")
    lines.append("### 추세 차트")
    lines.append("")
    # CVR-032 Finding 7 (minor): "ctrs_zoom" rendered visually identical to
    # the full "scales_ctrs_sentiment" panel (no added resolution) —
    # dropped from the report entirely rather than shipping a redundant,
    # mislabeled-as-"확대" page. Chart PIXEL generation is out of this
    # renderer's scope either way (`trend_plotter.py`); this only stops
    # embedding the reference.
    chart_map = {
        "scales_ctrs_sentiment": b.chart_filenames.scales_ctrs_sentiment,
        "disease_similarity": b.chart_filenames.disease_similarity,
        "domain_confidence": b.chart_filenames.domain_confidence,
    }
    any_chart = False
    fig_no = 0
    for key, filename in chart_map.items():
        if filename:
            any_chart = True
            fig_no += 1
            lines.append(f"![{key}]({filename})")
            lines.append("")
            lines.append(f"*{_chart_caption_ko(key, lon, fig_no)}*")
            # CVR-032 Finding 3 (major): an uncaveated flat-zero 문진 항목
            # 충족도 sub-panel (part of this SAME combined chart) risks
            # reading as "nothing was learned" — state the data-collection
            # fact plainly instead of leaving a bare chart to imply it.
            if key == "scales_ctrs_sentiment" and _slot_fill_all_zero(lon):
                lines.append("")
                lines.append(f"*{_SLOT_FILL_FLAT_ZERO_CAVEAT_KO}*")
            lines.append("")
        else:
            lines.append(f"{_CHART_TITLES_KO[key]}: 생성되지 않음")
    if not any_chart:
        lines.append("정보 없음 (차트 없음)")
    lines.append("")

    # ── AI 참고 정보 (비진단) ──
    lines += [
        "## AI 참고 정보 (비진단)",
        "",
        "> ⚠ 유사도(similarity)일 뿐 확률·가능성·신뢰도가 아닙니다 — 임상 판단 대체 불가.",
        "",
    ]
    if not a6.present:
        lines += [_none_marker(a6.no_data_note, "정보 없음"), ""]
        if a6.mode:
            lines.append(f"mode: {a6.mode}")
        if a6.reason_summary:
            lines += ["", f"사유: {_a6_reason_summary_ko(a6.reason_summary, notes)}"]
        lines.append("")
    else:
        top, rest = a6.candidates[:3], a6.candidates[3:]
        lines += ["| 순위 | 질환 | 유사도 |", "|---|---|---|"]
        for rc in top:
            rank_cell = rc.tie_marker or str(rc.rank)
            score = f"{rc.candidate.similarity_score:.3f}"
            lines.append(f"| {rank_cell} | {rc.candidate.disease} | {score} |")
        lines.append("")
        if rest:
            rest_txt = ", ".join(
                f"{rc.candidate.disease}({rc.candidate.similarity_score:.3f})" for rc in rest
            )
            lines.append(f"기타 후보: {rest_txt}")
            lines.append("")
        lines.append(f"> {a6.disclaimer}")
        if a6.recommended_questionnaire:
            lines.append(
                f"> 추천 설문: {a6.recommended_questionnaire}"
                + (f" — {a6.recommendation_caveat}" if a6.recommendation_caveat else "")
            )
        lines.append("")

    # ── 권장 진료과 및 후속 조치 ──
    lines += ["## 권장 진료과 및 후속 조치", ""]
    if a7.department_candidates:
        lines += ["| 진료과 | 사유 |", "|---|---|"]
        lines += [f"| {d.department} | {d.reason} |" for d in a7.department_candidates]
        lines.append("")
    else:
        lines += [_a7_absence_note_ko(a7, notes), ""]
    if a7.recommended_questionnaire:
        lines.append(
            f"추천 설문: {a7.recommended_questionnaire}"
            + (f" — {a7.recommendation_caveat}" if a7.recommendation_caveat else "")
        )
        lines.append("")
    si_note = _si_referral_note_ko(a3)
    if si_note:
        lines += [f"> {si_note}", ""]
    lines += [f"> {a7.medication_note}", ""]

    # ── 임상 종합 소견 (own top-level section — same structural-separation
    # discipline as AI 참고 정보/A6, never nested inside another section) ──
    lines += ["## 임상 종합 소견", ""]
    if a8.narrative_enabled and a8.text:
        lines += [f"> {NARRATIVE_ENABLED_LABEL_KO}", "", a8.text, ""]
    else:
        lines += [a8.absent_marker, ""]

    # ── 상세 부록 (CVR-026 Finding 1/2/3) ──
    lines += ["## 상세 부록", ""]
    if appendix.entries:
        for n, label, text in appendix.entries:
            lines += [f"**{n}. {label}**", "", text, ""]
    slot_history_sections = [
        (row.label, " → ".join(row.change_history_full))
        for row in _slot_table_rows(so)
        if len(row.change_history_full) >= 2
    ]
    if slot_history_sections:
        lines += ["### 슬롯별 전체 변화 이력 (미압축)", ""]
        for label, text in slot_history_sections:
            lines += [f"**{label}**", "", text, ""]
    if not appendix.entries and not slot_history_sections:
        lines += ["해당 없음 — 본문에서 잘린 항목이 없습니다.", ""]

    # ── 각주 (감사용 메타) ──
    lines += ["## 각주", ""]
    footnote = f"모델: {a0.model} · 생성 시각: {report.generated_at} · 세션ID: {a0.session_id}"
    lines.append(footnote)
    if a5.present:
        lines.append(f"설문 문항 출처: {a5.item_bank_provenance or '미상'}")
    lines.append("")
    # CVR-026 Finding 5/7: internal review/bug-ID citations + code-path
    # audit refs live ONLY here, separated from the clinical footnote line
    # above (Finding 7's own recommendation) — never in the scannable body.
    lines.append("### 시스템 참고 (내부 감사용, 임상 판단 근거 아님)")
    lines.append("")
    lines.append(f"종단 추세 판정 근거: {b.overall_direction_sensitivity_note}")
    for note in notes.notes:
        lines.append(note)
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Narrative input (Task 2, `handoff_generator` v3) — the ONLY function
# responsible for turning a `HandoffReportOutput` into that agent's user
# message. A6 (AI-predicted-disease) is DELIBERATELY never included here —
# the narrative-generation LLM call never receives disease-candidate text
# at all, the strongest available defense against an A6->A8 leak (on top
# of `src.f5`'s own code-level containment check on the RETURNED
# narrative, `f5.py::_build_a8`). This module still performs zero LLM
# calls itself — it only builds the TEXT a caller passes to
# `HandoffGeneratorAgent.generate_narrative`.
# ═══════════════════════════════════════════════════════════════════════


def build_narrative_input_text(report: HandoffReportOutput) -> str:
    """Compact plain-text summary of A0-A5/A7/B, EXCLUDING A6 and A8
    themselves, matching `apps/ai-server/prompts/handoff_generator/v3.system.md`'s
    documented input format."""
    a0, a1, a2, a3 = (
        report.a0_header,
        report.a1_chief_complaint,
        report.a2_hpi,
        report.a3_risk_safety,
    )
    a4, a5, a7 = report.a4_mental_status, report.a5_questionnaires, report.a7_recommendations
    lon = report.b_longitudinal.analysis

    if a5.present:
        questionnaire_line = f"{a5.scale_name} {a5.total_score}/{a5.max_score} ({a5.severity})"
    else:
        questionnaire_line = "없음"
    if a7.department_candidates:
        department_line = ", ".join(d.department for d in a7.department_candidates)
    else:
        department_line = "없음"

    return "\n".join(
        [
            f"세션: {a0.session_index}회차, {a0.simulated_date}",
            f"CTRS: {a0.session_ctrs} ({a0.risk_level})",
            f"주호소: {a1.text if a1.present else '미수집'}",
            f"현병력: {a2.text if a2.present else '미수집'}",
            f"위험 평가 존재 여부: {a3.risk_assessment_present}",
            f"정신상태 메모: {a4.raw_text if a4.present else '미수집'}",
            f"시행된 설문: {questionnaire_line}",
            f"권장 진료과: {department_line}",
            f"종단 추세: overall_direction={lon.overall_direction}, "
            f"course_shape={lon.course_shape}",
        ]
    )


# ═══════════════════════════════════════════════════════════════════════
# PDF (design doc §5.2 — reportlab, EMBEDDED Korean TTF subsets)
# ═══════════════════════════════════════════════════════════════════════
#
# `ADR-038` Decision 1 / `BUG-044`: the previous choice (`ADR-037` Decision
# 7, reportlab's built-in `UnicodeCIDFont` predefined CID fonts) shipped
# NON-embedded (`emb=no`, confirmed via `pdffonts`) — rendering depended
# entirely on the CONSUMING viewer's own font substitution, which qa's
# multi-renderer adjudication (`error.md` BUG-044) confirmed produces
# near-total Hangul dropout on a no-Korean-font-package host AND under
# Ghostscript, even though this project's own default host renders fine.
#
# Fix: EMBED a subsetted TrueType (`glyf`-outline) Korean font instead —
# glyph outlines ship inside the PDF itself, independent of any consuming
# renderer's installed fonts. Built by `scripts/build_korean_fonts.py`
# (run from `apps/ai-server/`) from this host's Noto Sans/Serif CJK KR
# (`fc-list`-confirmed installed, Noto CJK KR family) — those system fonts
# are themselves `CFF `/OTTO-flavored (verified via `fontTools`, NOT
# `glyf`), which reportlab's `TTFont` loader explicitly rejects
# ("postscript outlines are not supported"); no TrueType-glyf Korean font
# (e.g. Nanum/Baekmuk) is installed on this host (swept via `find`, none
# found) — so the build script converts Noto's cubic (CFF) outlines to
# quadratic (TrueType) outlines via `fontTools.pens.cu2quPen`, verified
# both to cover `·` (U+00B7) and `⚠` (U+26A0) — BUG-044's 2 tofu-glyph
# targets — and, separately, end-to-end via a real reportlab-built PDF
# rasterized under 3 renderer configurations (default poppler, a
# restricted no-CJK-fontconfig poppler, and Ghostscript 9.55 — the exact 2
# configurations BUG-044's adjudication found broken) — all 3 now render
# correctly. No ASCII/text substitution was needed for either target
# glyph (both are present in the chosen font); nothing in this module
# substitutes them.
#
# Asset provenance (`ADR-038` "font path + SHA256" requirement): the two
# built files are committed at `assets/fonts/` (repo-relative to
# `apps/ai-server/`); their SHA256 is pinned below and verified at
# registration time — a missing OR content-mismatched asset raises
# `RuntimeError` naming the exact requirement, never a silent fallback to
# the old non-embedded CID fonts.

_FONT_ASSET_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

_BODY_FONT = "NotoSansKR-Subset"
_BODY_FONT_PATH = _FONT_ASSET_DIR / "NotoSansKR-Subset.ttf"
_BODY_FONT_SHA256 = "4fc4ff8e7afe3170ecce9f947021abcafa17a0fd37723de66ce74503cdf41846"

_HEADING_FONT = "NotoSerifKR-Subset"
_HEADING_FONT_PATH = _FONT_ASSET_DIR / "NotoSerifKR-Subset.ttf"
_HEADING_FONT_SHA256 = "6afa567f91cd3879754d7f05e2c9d48a02b270d0f988a6b6a42bffc255979710"


def _register_korean_fonts() -> None:
    """Registers the 2 embedded Korean TTF subset fonts (`ADR-038`
    Decision 1). Raises `RuntimeError` — never silently falls back to a
    non-Hangul-capable or non-embedded font — if either asset is missing
    or its SHA256 does not match the pinned constant above (regenerate via
    `scripts/build_korean_fonts.py` and update the constant deliberately
    if this is an intentional font update)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont as ReportLabTTFont

    for face_name, path, expected_sha256 in (
        (_BODY_FONT, _BODY_FONT_PATH, _BODY_FONT_SHA256),
        (_HEADING_FONT, _HEADING_FONT_PATH, _HEADING_FONT_SHA256),
    ):
        if face_name in pdfmetrics.getRegisteredFontNames():
            continue
        if not path.exists():
            raise RuntimeError(
                f"F5 PDF export requires the embedded Korean font asset at "
                f"{path}, which is missing (ADR-038 Decision 1 / BUG-044). "
                f"Run `uv run python scripts/build_korean_fonts.py` from "
                f"apps/ai-server/ to generate it. F5 will NOT fall back to "
                f"the old non-embedded CID fonts."
            )
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"F5 PDF export's embedded Korean font asset at {path} has "
                f"SHA256={actual_sha256}, expected {expected_sha256} "
                f"(ADR-038 Decision 1 / BUG-044 provenance check — "
                f"regenerate via scripts/build_korean_fonts.py and update "
                f"the pinned hash if this font change is intentional)."
            )
        pdfmetrics.registerFont(ReportLabTTFont(face_name, str(path)))


def build_pdf_report(
    report: HandoffReportOutput, chart_paths: dict[str, Path] | None = None
) -> bytes:
    """Renders the SAME clinician-first structure as `build_markdown_report`
    (핵심요약 → 위험 → 주호소/현병력 → 슬롯표+경과 → 설문 → 종단추세+차트 →
    AI참고 → 권고 → 각주) into a paginated PDF (reportlab platypus),
    embedding the 4 F4 PNG charts directly (a PDF has no reliable
    external-file reference convention). AI 참고(A6) stays visually fenced
    with a bordered/shaded table (decision-support, structurally
    separate)."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    _register_korean_fonts()
    chart_paths = chart_paths or {}
    appendix = _AppendixCollector()
    notes = _SystemNoteCollector()

    styles = {
        "title": ParagraphStyle(
            "title", fontName=_HEADING_FONT, fontSize=16, leading=20, spaceAfter=10
        ),
        "h2": ParagraphStyle(
            "h2", fontName=_HEADING_FONT, fontSize=13, leading=17, spaceBefore=12, spaceAfter=6
        ),
        "h3": ParagraphStyle(
            "h3", fontName=_HEADING_FONT, fontSize=11, leading=15, spaceBefore=8, spaceAfter=4
        ),
        "body": ParagraphStyle("body", fontName=_BODY_FONT, fontSize=9.5, leading=14),
        "meta": ParagraphStyle(
            "meta", fontName=_BODY_FONT, fontSize=8.5, leading=12, textColor=colors.grey
        ),
        "warn": ParagraphStyle(
            "warn",
            fontName=_BODY_FONT,
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor("#B00020"),
        ),
    }

    def P(text: str, style: str = "body") -> Paragraph:
        safe = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(safe.replace("\n", "<br/>"), styles[style])

    def _table(rows: list[list[str]], font_size: float = 7.5) -> Table:
        t = Table(rows, hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), _BODY_FONT),
                    ("FONTSIZE", (0, 0), (-1, -1), font_size),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                ]
            )
        )
        return t

    def _boxed(flow: list, border: str = "#4A6FA5", fill: str = "#F1F5FB") -> Table:
        fence = Table([[flow]], hAlign="LEFT")
        fence.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor(border)),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(fill)),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return fence

    story: list = []
    a0, a1, a2, a3 = (
        report.a0_header,
        report.a1_chief_complaint,
        report.a2_hpi,
        report.a3_risk_safety,
    )
    a4, a5, a6, a7, a8 = (
        report.a4_mental_status,
        report.a5_questionnaires,
        report.a6_ai_predicted_disease,
        report.a7_recommendations,
        report.a8_narrative,
    )
    b = report.b_longitudinal
    lon = b.analysis
    so = report.slot_overview

    # ── Title ──
    story.append(P(f"F5 인계 요약 보고서 — {report.vp_id}", "title"))

    # ── 핵심 요약 (SBAR box) ──
    summary_flow = [P("핵심 요약", "h3")]
    summary_flow += [P(f"- {line}", "body") for line in _summary_box_lines(report, appendix)]
    story.append(_boxed(summary_flow))
    story.append(Spacer(1, 0.2 * cm))

    # ── 면책 조항 (3줄 이내 박스) ──
    disclaimer_flow = [P("면책 조항", "h3")]
    disclaimer_flow += [P(f"- {line}", "body") for line in _DISCLAIMER_BOX_KO]
    story.append(_boxed(disclaimer_flow, border="#B00020", fill="#FFF3F3"))
    story.append(Spacer(1, 0.2 * cm))

    # ── 위험/안전 평가 ──
    story.append(P("위험/안전 평가", "h2"))
    story.append(P(_risk_prose(lon, a3, appendix), "body"))
    risk_rows = _risk_table_rows(a3, appendix)
    ceiling_shown_in_a3 = False
    if risk_rows:
        story.append(P(NON_VALIDATED_ADMINISTRATION_CAVEAT_KO, "warn"))
        rows = [["세션", "일자", "점수", "9번 문항", "판정"]] + [
            list(r) for r in _full_risk_table_rows(a3, lon, appendix)
        ]
        story.append(_table(rows))
        # ADR-038 Decision 2c / renderer polish (VP-004 review): full
        # ceiling caveat text still rendered adjacent to the table (never
        # dropped to the "· 만점" table abbreviation alone), now as ONE
        # consolidated line naming every affected session.
        ceiling_summary = _ceiling_caveat_summary(a3)
        if ceiling_summary:
            ceiling_shown_in_a3 = True
            story.append(P(ceiling_summary, "warn"))
    else:
        story.append(P("해당 없음 — item-9 양성/안전 의뢰 이력 없음", "body"))
    if a3.staleness_pointer.total_score is not None:
        story.append(P(NON_VALIDATED_ADMINISTRATION_CAVEAT_KO, "warn"))
    story.append(P(f"최신 시행 척도 안내: {_staleness_note_ko(a3.staleness_pointer)}", "warn"))
    if a3.staleness_pointer.ceiling_caveat:
        # CVR-026 Finding 8 (minor): collapse the within-A3 duplicate (see
        # markdown builder's identical comment) — A5's own occurrence is
        # untouched (ADR-038 Decision 2c, locked by test).
        staleness_ceiling_text = (
            _CEILING_POINTER_KO if ceiling_shown_in_a3 else a3.staleness_pointer.ceiling_caveat
        )
        story.append(P(staleness_ceiling_text, "warn"))

    # ── 주호소 및 현병력 (+ MSE) ──
    story.append(P("주호소 및 현병력", "h2"))
    story.append(P(f"주호소: {a1.text if a1.present else '미수집'}", "body"))
    story.append(P(f"현병력: {a2.text if a2.present else '미수집'}", "body"))
    story.append(P("정신상태검사 (MSE)", "h3"))
    for line in _mse_lines(a4):
        story.append(P(line, "body"))

    # ── 전체 세션 요약 (슬롯) + 주요 경과 ──
    story.append(P("전체 세션 요약", "h2"))
    story.append(P(so.non_validated_caveat, "warn"))
    rows = [["슬롯", "최신값", "출처", "변화", "비고"]]
    for row in _slot_table_rows(so):
        if not row.collected:
            value_cell, source_cell = SLOT_NEVER_COLLECTED_KO, "-"
        else:
            value_cell = _truncate(
                row.latest_value, 80, appendix=appendix, label=f"{row.label} 최신값 전문"
            )
            source_cell = f"{row.source_session_index}회차/{row.source_simulated_date}"
        rows.append(
            [
                row.label,
                value_cell,
                source_cell,
                _change_history_summary(row),
                row.section_pointer or "-",
            ]
        )
    story.append(_table(rows, font_size=7))
    story.append(P("주요 경과", "h3"))
    course_bullets = _major_course_bullets(so, a3)
    if course_bullets:
        for line in course_bullets:
            story.append(P(f"- {line}", "body"))
    else:
        story.append(P("표시할 주요 경과 변화 없음", "body"))

    # ── 시행된 설문 ──
    story.append(P("시행된 설문", "h2"))
    gap_framing_shown = False
    if not a5.present:
        story.append(P("정보 없음 (전체 세션 중 시행된 설문 없음)", "body"))
    else:
        story.append(P(a5.non_validated_caveat, "warn"))
        stale = " [당해 세션 미시행, 직전 시행값]" if a5.is_stale_relative_to_header else ""
        story.append(
            P(
                f"{a5.scale_name} {a5.total_score}/{a5.max_score} ({_severity_ko(a5.severity)}) — "
                f"{a5.administering_session_index}회차 ({a5.administering_simulated_date}){stale}",
                "body",
            )
        )
        item9_label = _a6_item9_or_critical_label(a5.scale_name)
        item9_value = (
            "양성"
            if a5.critical_item_positive
            else "음성"
            if a5.critical_item_positive is False
            else "미상"
        )
        story.append(P(f"응답: {','.join(str(v) for v in a5.responses)}", "body"))
        story.append(
            P(
                f"{item9_label}: {item9_value} | 문진 방식: {a5.administration_mode or '미상'}",
                "body",
            )
        )
        mismatch_note = _recommend_administer_mismatch_ko(a3, a5, a7)
        if mismatch_note:
            story.append(P(mismatch_note, "warn"))
        if a5.threshold_caveat:
            story.append(P(a5.threshold_caveat, "body"))
        if a5.threshold_caveat_asymmetry_note:
            story.append(P(a5.threshold_caveat_asymmetry_note, "body"))
        if a5.ceiling_caveat:
            story.append(P(a5.ceiling_caveat, "warn"))
        if a5.gap_disclosure and a5.gap_acuity_framing_note:
            story.append(P(_strip_internal_refs(a5.gap_acuity_framing_note, notes), "warn"))
            gap_framing_shown = True
        for g in a5.gap_disclosure:
            story.append(P(f"- {_humanize_engine_text(g, notes)}", "body"))

    story.append(PageBreak())

    # ── 종단 추세 + 차트 ──
    overall_direction_ko = _DIRECTION_KO.get(lon.overall_direction, lon.overall_direction)
    story.append(
        P(
            f"종단 추세 — 전체 방향: {overall_direction_ko}",
            "h2",
        )
    )
    story.append(P(_OVERALL_DIRECTION_NOTE_PLAIN_KO, "body"))
    rows = [["항목", "방향", "근거"]] + [list(r) for r in _trend_table_rows(lon)]
    story.append(_table(rows, font_size=7.5))
    for line in _events_and_concordance_lines(
        lon, b, a3, gap_framing_already_shown=gap_framing_shown, notes=notes
    ):
        story.append(P(f"- {line}", "body"))

    story.append(P("추세 차트", "h3"))
    # CVR-032 Finding 7 (minor): "ctrs_zoom" dropped — rendered visually
    # identical to the full "scales_ctrs_sentiment" panel, no added
    # resolution (see markdown renderer's own comment for the same fix).
    chart_map = {
        "scales_ctrs_sentiment": b.chart_filenames.scales_ctrs_sentiment,
        "disease_similarity": b.chart_filenames.disease_similarity,
        "domain_confidence": b.chart_filenames.domain_confidence,
    }
    any_chart = False
    fig_no = 0
    for key, filename in chart_map.items():
        if not filename:
            story.append(P(f"{_CHART_TITLES_KO[key]}: 생성되지 않음", "body"))
            continue
        path = chart_paths.get(key)
        if path is not None and Path(path).exists():
            any_chart = True
            fig_no += 1
            story.append(P(filename, "meta"))
            # Chart-readability fix (this mission): embed near A4 usable
            # width (18cm minus margin buffer) rather than a small fixed
            # box — `trend_plotter.py`'s own font constants are sized for
            # THIS exact box width (see its module-level comment); a
            # smaller box here would silently re-shrink the fix below
            # clinician-readable size. Height is a generous cap, not a
            # binding constraint at this figure's aspect ratio.
            story.append(Image(str(path), width=17 * cm, height=24 * cm, kind="proportional"))
            story.append(P(_chart_caption_ko(key, lon, fig_no), "meta"))
            # CVR-032 Finding 3 (major): flat-zero 문진 항목 충족도 caveat,
            # same gating/text as the markdown renderer.
            if key == "scales_ctrs_sentiment" and _slot_fill_all_zero(lon):
                story.append(P(_SLOT_FILL_FLAT_ZERO_CAVEAT_KO, "warn"))
            story.append(Spacer(1, 0.3 * cm))
    if not any_chart:
        story.append(P("정보 없음 (차트 없음 또는 chart_paths 미전달)", "body"))

    # ── AI 참고 정보 (비진단, 시각적으로 분리된 박스) ──
    story.append(P("AI 참고 정보 (비진단)", "h2"))
    a6_flow: list = [
        P(
            "⚠ 유사도(similarity)일 뿐 확률·가능성·신뢰도가 아닙니다 — 임상 판단 대체 불가.",
            "warn",
        )
    ]
    if not a6.present:
        a6_flow.append(P(a6.no_data_note or "정보 없음", "body"))
        if a6.mode:
            a6_flow.append(P(f"mode: {a6.mode}", "body"))
        if a6.reason_summary:
            a6_flow.append(P(f"사유: {_a6_reason_summary_ko(a6.reason_summary, notes)}", "body"))
    else:
        top, rest = a6.candidates[:3], a6.candidates[3:]
        rows = [["순위", "질환", "유사도"]]
        for rc in top:
            rank_cell = rc.tie_marker or str(rc.rank)
            rows.append([rank_cell, rc.candidate.disease, f"{rc.candidate.similarity_score:.3f}"])
        a6_flow.append(_table(rows, font_size=8))
        if rest:
            rest_txt = ", ".join(
                f"{rc.candidate.disease}({rc.candidate.similarity_score:.3f})" for rc in rest
            )
            a6_flow.append(P(f"기타 후보: {rest_txt}", "meta"))
        a6_flow.append(P(f"disclaimer: {a6.disclaimer}", "meta"))
    story.append(_boxed(a6_flow, border="#B00020", fill="#FFF3F3"))

    # ── 권장 진료과 및 후속 조치 ──
    story.append(P("권장 진료과 및 후속 조치", "h2"))
    if a7.department_candidates:
        rows = [["진료과", "사유"]] + [[d.department, d.reason] for d in a7.department_candidates]
        story.append(_table(rows, font_size=8))
    else:
        story.append(P(_a7_absence_note_ko(a7, notes), "body"))
    if a7.recommended_questionnaire:
        story.append(
            P(
                f"추천 설문: {a7.recommended_questionnaire}"
                + (f" — {a7.recommendation_caveat}" if a7.recommendation_caveat else ""),
                "body",
            )
        )
    si_note = _si_referral_note_ko(a3)
    if si_note:
        story.append(P(si_note, "warn"))
    story.append(P(a7.medication_note, "meta"))

    # ── 임상 종합 소견 (own top-level section, same as markdown) ──
    story.append(P("임상 종합 소견", "h2"))
    if a8.narrative_enabled and a8.text:
        story.append(P(NARRATIVE_ENABLED_LABEL_KO, "meta"))
        story.append(P(a8.text, "body"))
    else:
        story.append(P(a8.absent_marker, "body"))

    # ── 상세 부록 (CVR-026 Finding 1/2/3) ──
    story.append(PageBreak())
    story.append(P("상세 부록", "h2"))
    if appendix.entries:
        for n, label, full_text in appendix.entries:
            story.append(P(f"{n}. {label}", "h3"))
            story.append(P(full_text, "body"))
    slot_history_sections = [
        (row.label, " → ".join(row.change_history_full))
        for row in _slot_table_rows(so)
        if len(row.change_history_full) >= 2
    ]
    if slot_history_sections:
        story.append(P("슬롯별 전체 변화 이력 (미압축)", "h3"))
        for label, full_text in slot_history_sections:
            story.append(P(label, "meta"))
            story.append(P(full_text, "body"))
    if not appendix.entries and not slot_history_sections:
        story.append(P("해당 없음 — 본문에서 잘린 항목이 없습니다.", "body"))

    # ── 각주 (감사용 메타) ──
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        P(f"모델: {a0.model} · 생성 시각: {report.generated_at} · 세션ID: {a0.session_id}", "meta")
    )
    if a5.present:
        story.append(P(f"설문 문항 출처: {a5.item_bank_provenance or '미상'}", "meta"))
    # CVR-026 Finding 5/7: internal review/bug-ID citations relocated here,
    # separated from the clinical footnote line above.
    story.append(P("시스템 참고 (내부 감사용, 임상 판단 근거 아님)", "meta"))
    story.append(P(f"종단 추세 판정 근거: {b.overall_direction_sensitivity_note}", "meta"))
    for note in notes.notes:
        story.append(P(note, "meta"))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
    )
    doc.build(story)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════
# FHIR R4 document Bundle (design doc §5.3 — file export only, D3)
# ═══════════════════════════════════════════════════════════════════════

_LOCAL_CODE_SYSTEM = "urn:neurosync:f5-local-codes"

# `system`/`code` pairs VERIFIED against the design doc §5.3 mapping table
# (research note + brainstorm's own LOINC lookups). `display` is
# deliberately OMITTED wherever the plan did not hand us an independently
# confirmed LOINC long-common-name string — never fabricate an official
# display text; free-text labeling instead lives in `CodeableConcept.text`
# / `Composition.section.title`, which FHIR treats as ordinary prose, not
# an authority claim.
_LOINC = {
    "composition_type": "57143-0",
    "cc": "10154-3",
    "hpi": "10164-2",
    "risk": "84209-6",
    "mse": "10190-7",
    "phq9_total": "44261-6",
    "phq9_panel": "44249-1",
    "gad7_total": "70274-6",
    "auditc_total": "75626-2",
    "eval_plan": "51847-2",
}

_SCALE_TOTAL_LOINC = {
    "PHQ-9": _LOINC["phq9_total"],
    "GAD-7": _LOINC["gad7_total"],
    "AUDIT-C": _LOINC["auditc_total"],
}


def _new_entry(resource: dict) -> tuple[str, dict]:
    full_url = f"urn:uuid:{uuid.uuid4()}"
    return full_url, {"fullUrl": full_url, "resource": resource}


def _loinc_concept(key: str, text: str) -> dict:
    return {"coding": [{"system": "http://loinc.org", "code": _LOINC[key]}], "text": text}


def _local_concept(code: str, text: str) -> dict:
    return {"coding": [{"system": _LOCAL_CODE_SYSTEM, "code": code}], "text": text}


def _div(text: str) -> dict:
    """`Narrative` (status=generated) wrapping free text in the required
    xhtml div — used for every `Composition.section.text` below."""
    return {"status": "generated", "div": f"<div xmlns='http://www.w3.org/1999/xhtml'>{text}</div>"}


def build_fhir_bundle(report: HandoffReportOutput) -> dict:
    """R4 `Bundle(type="document")`, `Composition` first entry (design doc
    §5.3). File-export only — no `$validate` call, no server round-trip
    (D3). Structural validity only — see `validate_fhir_bundle` and the
    module-level FHIR claim discipline note above."""
    a0, a1, a2, a3 = (
        report.a0_header,
        report.a1_chief_complaint,
        report.a2_hpi,
        report.a3_risk_safety,
    )
    a4, a5, a6, a7 = (
        report.a4_mental_status,
        report.a5_questionnaires,
        report.a6_ai_predicted_disease,
        report.a7_recommendations,
    )
    b = report.b_longitudinal
    lon = b.analysis

    entries: list[dict] = []
    full_urls: dict[str, str] = {}

    def add(key: str, resource: dict) -> str:
        full_url, entry = _new_entry(resource)
        entries.append(entry)
        full_urls[key] = full_url
        return full_url

    # ── Patient (minimal, flagged simulated) ──
    patient_url = add(
        "patient",
        {
            "resourceType": "Patient",
            "id": a0.persona_id,
            "meta": {
                "tag": [{"system": "urn:neurosync:simulation-flag", "code": "simulated-patient"}]
            },
            "identifier": [{"system": "urn:neurosync:vp-id", "value": report.vp_id}],
            "name": [{"text": a0.persona_name}],
        },
    )

    sections: list[dict] = []

    # ── A1 CC ──
    sections.append(
        {
            "title": "A1. 주호소 (Chief complaint)",
            "code": _loinc_concept("cc", "chief complaint"),
            "text": _div(a1.text or "정보 없음"),
        }
    )

    # ── A2 HPI ──
    sections.append(
        {
            "title": "A2. 현병력 (HPI)",
            "code": _loinc_concept("hpi", "history of present illness"),
            "text": _div(a2.text or "정보 없음"),
        }
    )

    # ── All-session slot overview (Task 1, extends A1/A2) — text-only,
    # no dedicated resource; a local CodeSystem (no LOINC applies to a
    # cross-slot summary table). ──
    so = report.slot_overview
    slot_lines = []
    for row in so.rows:
        if not row.collected:
            slot_lines.append(f"{row.label}: {SLOT_NEVER_COLLECTED_KO}")
            continue
        change = f" (변화: {' -> '.join(row.change_history)})" if row.change_history else ""
        slot_lines.append(
            f"{row.label}: {row.latest_value} [{row.source_session_index}회차/"
            f"{row.source_simulated_date}]{change}"
        )
    sections.append(
        {
            "title": "A1-A2 확장. 전체 세션 슬롯 요약 (12개 표준 슬롯)",
            "code": _local_concept("slot-overview", "all-session canonical slot overview"),
            "text": _div(f"{so.non_validated_caveat} " + " | ".join(slot_lines)),
        }
    )

    # ── A3 Risk/safety: RiskAssessment + CTRS Observation ──
    ctrs_obs_url = add(
        "ctrs_observation",
        {
            "resourceType": "Observation",
            "id": str(uuid.uuid4()),
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "survey",
                        }
                    ]
                }
            ],
            "code": _local_concept("ctrs", "Crisis Triage Rating Scale (session_ctrs, local)"),
            "subject": {"reference": patient_url},
            "effectiveDateTime": a3.current_simulated_date,
            "valueInteger": a3.session_ctrs,
            "note": [
                {
                    "text": (
                        f"probe_event_count={a3.probe_event_count}, "
                        f"risk_floor={a3.risk_floor}, crisis_triggered={a3.crisis_triggered}"
                    )
                }
            ],
        },
    )
    risk_assessment_url = add(
        "risk_assessment",
        {
            "resourceType": "RiskAssessment",
            "id": str(uuid.uuid4()),
            "status": "final",
            "subject": {"reference": patient_url},
            "basis": [{"reference": ctrs_obs_url}],
            "prediction": [
                {
                    "qualitativeRisk": {"text": a3.risk_level or "unknown"},
                    "rationale": a3.risk_assessment_text or "정보 없음",
                }
            ],
            "note": [
                {
                    "text": (
                        f"trend concordance_flag(F4)={a3.trend_concordance_flag}; "
                        f"staleness_pointer={a3.staleness_pointer.note}"
                        + (
                            f" — {NON_VALIDATED_ADMINISTRATION_CAVEAT_KO}"
                            if a3.staleness_pointer.total_score is not None
                            else ""
                        )
                        + (
                            f" {a3.staleness_pointer.ceiling_caveat}"
                            if a3.staleness_pointer.ceiling_caveat
                            else ""
                        )
                    )
                }
            ],
        },
    )
    risk_narrative = "; ".join(
        [
            f"session_ctrs={a3.session_ctrs}({a3.risk_level})",
            f"safety_referral={a3.current_session_safety_referral}",
            *[
                f"[{s.session_index}] {s.discordance_note}"
                + (f" {s.ceiling_caveat}" if s.ceiling_caveat else "")
                for s in a3.longitudinal_risk_signals
            ],
        ]
    )
    sections.append(
        {
            "title": "A3. 위험/안전 평가",
            "code": {"coding": [{"system": "http://loinc.org", "code": _LOINC["risk"]}]},
            "text": _div(risk_narrative),
            "entry": [{"reference": risk_assessment_url}, {"reference": ctrs_obs_url}],
        }
    )

    # ── A4 MSE (partial — disclosure non-optional) ──
    mse_obs_url = add(
        "mse_observation",
        {
            "resourceType": "Observation",
            "id": str(uuid.uuid4()),
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "exam",
                        }
                    ]
                }
            ],
            "code": {"coding": [{"system": "http://loinc.org", "code": _LOINC["mse"]}]},
            "subject": {"reference": patient_url},
            "valueString": a4.raw_text or "정보 없음",
            "note": [
                {
                    "text": (
                        "PARTIAL / TEXT-ONLY MSE — 이 관찰은 완전한 임상 관찰 기반 MSE가 아니라 "
                        f"단일 텍스트 슬롯({a4.label})에서만 도출되었습니다. 5개 관찰-의존 영역은 "
                        "평가 불가로 표시됩니다."
                    )
                }
            ],
        },
    )
    sections.append(
        {
            "title": "A4. 정신상태 검사 (부분, MSE)",
            "code": {"coding": [{"system": "http://loinc.org", "code": _LOINC["mse"]}]},
            "text": _div(a4.raw_text or "정보 없음"),
            "entry": [{"reference": mse_obs_url}],
        }
    )

    # ── A5 Questionnaires: QuestionnaireResponse + Observation(total) ──
    a5_entries: list[dict] = []
    if a5.present:
        qr_url = add(
            "questionnaire_response",
            {
                "resourceType": "QuestionnaireResponse",
                "id": str(uuid.uuid4()),
                "status": "completed",
                "subject": {"reference": patient_url},
                "authored": a5.administering_simulated_date,
                "item": [
                    {"linkId": f"item_{i + 1}", "answer": [{"valueInteger": v}]}
                    for i, v in enumerate(a5.responses)
                ],
                "note": [{"text": a5.non_validated_caveat}],
            },
        )
        a5_entries.append({"reference": qr_url})
        total_code = _SCALE_TOTAL_LOINC.get(a5.scale_name or "")
        obs_code = (
            {
                "coding": [{"system": "http://loinc.org", "code": total_code}],
                "text": f"{a5.scale_name} total",
            }
            if total_code
            else _local_concept("scale-total", f"{a5.scale_name} total")
        )
        notes = [{"text": a5.non_validated_caveat}]
        if a5.threshold_caveat:
            notes.append({"text": a5.threshold_caveat})
        if a5.threshold_caveat_asymmetry_note:
            notes.append({"text": a5.threshold_caveat_asymmetry_note})
        if a5.ceiling_caveat:
            notes.append({"text": a5.ceiling_caveat})
        obs_url = add(
            "a5_total_observation",
            {
                "resourceType": "Observation",
                "id": str(uuid.uuid4()),
                "status": "final",
                "category": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                "code": "survey",
                            }
                        ]
                    }
                ],
                "code": obs_code,
                "subject": {"reference": patient_url},
                "effectiveDateTime": a5.administering_simulated_date,
                "valueQuantity": {"value": a5.total_score, "unit": "score"},
                "note": notes,
            },
        )
        a5_entries.append({"reference": obs_url})
        a5_text = (
            f"{a5.scale_name} {a5.total_score}/{a5.max_score} ({a5.severity}) — "
            f"{a5.non_validated_caveat}"
        )
        if a5.ceiling_caveat:
            a5_text = f"{a5_text} {a5.ceiling_caveat}"
    else:
        a5_text = "정보 없음 (시행된 설문 없음)"
    sections.append(
        {
            "title": "A5. 시행된 설문",
            "code": _local_concept("questionnaires", "administered questionnaires"),
            "text": _div(a5_text),
            **({"entry": a5_entries} if a5_entries else {}),
        }
    )

    # ── A6 AI-predicted-disease (hard red line — own section/resource) ──
    a6_entries: list[dict] = []
    if a6.present:
        components = [
            {
                "code": {"text": rc.candidate.disease},
                "valueQuantity": {"value": rc.candidate.similarity_score, "unit": "similarity"},
            }
            for rc in a6.candidates
        ]
        a6_obs_url = add(
            "ai_predicted_disease_observation",
            {
                "resourceType": "Observation",
                "id": str(uuid.uuid4()),
                "status": "final",
                "category": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                "code": "survey",
                            }
                        ]
                    }
                ],
                "code": _local_concept(
                    "ai-predicted-disease", "AI-predicted disease candidates (non-diagnostic)"
                ),
                "subject": {"reference": patient_url},
                "component": components,
                "note": [
                    {"text": "NOT A DIAGNOSIS, NOT A PROBABILITY — similarity_score only."},
                    {"text": a6.disclaimer or ""},
                ],
            },
        )
        a6_entries.append({"reference": a6_obs_url})
        a6_text = "; ".join(
            f"{rc.tie_marker or f'#{rc.rank}'} {rc.candidate.disease} "
            f"(similarity={rc.candidate.similarity_score:.3f})"
            for rc in a6.candidates
        )
    else:
        a6_obs_url = None
        a6_text = a6.no_data_note or "정보 없음"
        if a6.reason_summary:
            a6_text = f"{a6_text} (reason_summary: {a6.reason_summary})"
    sections.append(
        {
            "title": "A6. AI 예상질환 (비진단적 의사결정 지원)",
            "code": _local_concept(
                "ai-predicted-disease-section", "AI-predicted disease (non-diagnostic)"
            ),
            "text": _div(f"NOT A DIAGNOSIS. {a6_text}"),
            **({"entry": a6_entries} if a6_entries else {}),
        }
    )

    # ── A7 Department recommendation: ServiceRequest ──
    a7_entries: list[dict] = []
    for d in a7.department_candidates:
        sr_url = add(
            f"service_request_{len(a7_entries)}",
            {
                "resourceType": "ServiceRequest",
                "id": str(uuid.uuid4()),
                "status": "active",
                "intent": "proposal",
                "subject": {"reference": patient_url},
                "category": [{"text": "department-referral"}],
                "performer": [{"display": d.department}],
                "reasonCode": [{"text": d.reason}],
                **({"reasonReference": [{"reference": a6_obs_url}]} if a6_obs_url else {}),
            },
        )
        a7_entries.append({"reference": sr_url})
    a7_text = "; ".join(f"{d.department}: {d.reason}" for d in a7.department_candidates) or (
        a7.department_candidates_absence_note or "정보 없음"
    )
    sections.append(
        {
            "title": "A7. 권장 진료과 / 설문",
            "code": _local_concept("department-recommendation", "recommended department"),
            "text": _div(f"{a7_text}. {a7.medication_note}"),
            **({"entry": a7_entries} if a7_entries else {}),
        }
    )

    # ── B1-B3: repeated Observation per scale_series/ctrs_series point ──
    b_entries: list[dict] = []
    for scale_name, points in lon.scale_series.items():
        total_code = _SCALE_TOTAL_LOINC.get(scale_name)
        code = (
            {
                "coding": [{"system": "http://loinc.org", "code": total_code}],
                "text": f"{scale_name} total",
            }
            if total_code
            else _local_concept("scale-total", f"{scale_name} total")
        )
        for p in points:
            if not p.administered or p.total_score is None:
                continue
            b_url = add(
                f"b1_{scale_name}_{p.session_index}",
                {
                    "resourceType": "Observation",
                    "id": str(uuid.uuid4()),
                    "status": "final",
                    "category": [
                        {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                    "code": "survey",
                                }
                            ]
                        }
                    ],
                    "code": code,
                    "subject": {"reference": patient_url},
                    "effectiveDateTime": p.simulated_date,
                    "valueQuantity": {"value": p.total_score, "unit": "score"},
                    "note": [{"text": NON_VALIDATED_ADMINISTRATION_CAVEAT_KO}],
                },
            )
            b_entries.append({"reference": b_url})
    for p in lon.ctrs_series:
        if p.session_ctrs is None:
            continue
        b_url = add(
            f"b2_ctrs_{p.session_index}",
            {
                "resourceType": "Observation",
                "id": str(uuid.uuid4()),
                "status": "final",
                "category": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                "code": "survey",
                            }
                        ]
                    }
                ],
                "code": _local_concept("ctrs", "Crisis Triage Rating Scale (local)"),
                "subject": {"reference": patient_url},
                "effectiveDateTime": p.simulated_date,
                "valueInteger": p.session_ctrs,
            },
        )
        b_entries.append({"reference": b_url})
    sections.append(
        {
            "title": "B1-B3. 종단 추세 / CTRS 추이 / 사건 타임라인",
            "code": _local_concept("longitudinal-trend", "longitudinal trend"),
            "text": _div(
                f"overall_direction={lon.overall_direction}, course_shape={lon.course_shape}. "
                f"{b.overall_direction_sensitivity_note}"
            ),
            **({"entry": b_entries} if b_entries else {}),
        }
    )

    # ── B4 Discordance ──
    sections.append(
        {
            "title": "B4. 불일치 신호",
            "code": _local_concept("discordance-flag", "trend concordance/discordance (local)"),
            "text": _div(
                f"trend concordance_flag={lon.concordance_flag} "
                "(trend-level only, distinct from A3's same-session co-display)"
            ),
        }
    )

    # ── A8 (Task 2, opt-in only — omitted entirely when disabled/rejected,
    # REV-047 Criterion 6a precedent unchanged for that case) ──
    a8 = report.a8_narrative
    if a8.narrative_enabled and a8.text:
        sections.append(
            {
                "title": "A8. 임상 종합 소견 (AI narrative synthesis)",
                "code": _loinc_concept("eval_plan", "evaluation and plan note"),
                "text": _div(f"{NARRATIVE_ENABLED_LABEL_KO}. {a8.text}"),
            }
        )

    # ── Cross-cutting non-diagnostic disclosure (dedicated section) ──
    disclaimer_text = report.disclaimer
    if not (a8.narrative_enabled and a8.text):
        # ADR-038 Decision 2d / CVR-024 Recommendation 6 -- one-line note,
        # not a new A8-titled section (REV-047 Criterion 6a precedent) --
        # still applies whenever A8 is OMITTED, whether disabled by
        # default or refused by the Task 2 disease-leak guard alike.
        disclaimer_text = f"{disclaimer_text} {A8_FHIR_OMISSION_NOTE_KO}"
    sections.append(
        {
            "title": "면책 조항 (Disclaimer)",
            "code": {"text": "disclaimer"},
            "text": _div(disclaimer_text),
        }
    )

    composition = {
        "resourceType": "Composition",
        "id": str(uuid.uuid4()),
        "status": "final",
        "type": _loinc_concept("composition_type", "Mental health referral note"),
        "subject": {"reference": patient_url},
        "date": report.generated_at,
        "author": [{"display": "F5 자동 조합 엔진 (neurosync, is_diagnostic=false)"}],
        "title": f"F5 정신건강 인계 요약 — {report.vp_id}",
        "section": sections,
    }
    comp_full_url, comp_entry = _new_entry(composition)
    entries.insert(0, comp_entry)

    return {
        "resourceType": "Bundle",
        "type": "document",
        "timestamp": report.generated_at,
        "identifier": {
            "system": "urn:neurosync:f5-bundle-id",
            "value": f"{report.vp_id}-{report.generated_at}",
        },
        "entry": entries,
    }


def validate_fhir_bundle(bundle: dict) -> list[str]:
    """Structural self-check only (design doc §5.3 last paragraph) — NEVER
    an HL7 `$validate` call (D3). Returns a list of violation strings
    (empty = structurally OK per this project's own checks). Checks:
    (a) required fields present per resource type used, (b) every
    `urn:uuid` reference resolves to an actual bundle entry, (c) bundle
    type is "document" with a Composition first entry, (d) `is_diagnostic`/
    disclaimer text present verbatim (dedicated Composition section)."""
    violations: list[str] = []

    if bundle.get("resourceType") != "Bundle":
        violations.append("bundle.resourceType must be 'Bundle'")
    if bundle.get("type") != "document":
        violations.append("bundle.type must be 'document'")

    entries = bundle.get("entry") or []
    if not entries:
        violations.append("bundle.entry must be non-empty")
        return violations

    first = entries[0].get("resource", {})
    if first.get("resourceType") != "Composition":
        violations.append(
            "first bundle entry must be a Composition resource (document Bundle rule)"
        )

    full_urls = [e.get("fullUrl") for e in entries]
    if any(not u for u in full_urls):
        violations.append("every bundle entry must carry a non-empty fullUrl")
    if len(set(full_urls)) != len(full_urls):
        violations.append("every bundle entry must carry a UNIQUE fullUrl")
    full_url_set = set(full_urls)

    required_fields: dict[str, list[str]] = {
        "Composition": ["status", "type", "date", "author", "title", "section", "subject"],
        "Patient": ["resourceType", "id"],
        "Observation": ["status", "code"],
        "RiskAssessment": ["status", "subject"],
        "ServiceRequest": ["status", "intent", "subject"],
        "QuestionnaireResponse": ["status", "subject"],
    }
    for e in entries:
        res = e.get("resource", {})
        rtype = res.get("resourceType")
        for f in required_fields.get(rtype, []):
            if f not in res or res[f] in (None, "", []):
                violations.append(
                    f"{rtype} (fullUrl={e.get('fullUrl')}) missing required field '{f}'"
                )

    def _walk(obj: object) -> None:
        if isinstance(obj, dict):
            ref = obj.get("reference")
            if isinstance(ref, str) and ref.startswith("urn:uuid:") and ref not in full_url_set:
                violations.append(f"unresolved reference: {ref}")
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(bundle)

    for sec in first.get("section", []):
        if not sec.get("title"):
            violations.append("Composition.section missing title")
        if not sec.get("text") and not sec.get("entry"):
            violations.append(
                f"Composition.section '{sec.get('title')}' has neither text nor entry"
            )

    disclaimer_section = next(
        (s for s in first.get("section", []) if s.get("code", {}).get("text") == "disclaimer"), None
    )
    if disclaimer_section is None:
        violations.append(
            "Composition must carry a dedicated disclaimer section (code.text=='disclaimer')"
        )

    return violations
