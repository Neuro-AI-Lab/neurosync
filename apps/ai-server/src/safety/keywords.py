"""Korean keyword dictionary for Safety Guard v1.

Phase 1a Demo scope — small starter set, hand-curated. Phase 3 replaces
this with a learned classifier + curated taxonomy reviewed by clinicians.

Each entry: (phrase, level, category, confidence).

Conservative bias: false positives (medium when low was right) cost less
than false negatives (low when high was right). PRD §8.1: 위험 발화 false
negative = 치명적.
"""

from __future__ import annotations

from contracts.safety import RiskCategory, RiskLevel

# (phrase, level, category, confidence)
# Match is case-insensitive substring; the longest matching phrase wins.
KEYWORDS: list[tuple[str, RiskLevel, RiskCategory, float]] = [
    # ─── 자살 직접 의도 (critical) ───
    ("죽고 싶", RiskLevel.CRITICAL, RiskCategory.SUICIDE, 0.95),
    ("자살하고 싶", RiskLevel.CRITICAL, RiskCategory.SUICIDE, 0.97),
    ("자살할 거", RiskLevel.CRITICAL, RiskCategory.SUICIDE, 0.97),
    ("살고 싶지 않", RiskLevel.CRITICAL, RiskCategory.SUICIDE, 0.95),
    ("끝내고 싶", RiskLevel.CRITICAL, RiskCategory.SUICIDE, 0.9),
    ("목숨을 끊", RiskLevel.CRITICAL, RiskCategory.SUICIDE, 0.97),
    # ─── 자해 (high) ───
    ("자해", RiskLevel.HIGH, RiskCategory.SELF_HARM, 0.85),
    ("손목을 그", RiskLevel.HIGH, RiskCategory.SELF_HARM, 0.9),
    ("칼로 그", RiskLevel.HIGH, RiskCategory.SELF_HARM, 0.85),
    # ─── 타해 (high) ───
    ("죽이고 싶", RiskLevel.HIGH, RiskCategory.OTHER_HARM, 0.9),
    ("해치고 싶", RiskLevel.HIGH, RiskCategory.OTHER_HARM, 0.85),
    # ─── 급성 고통 (medium) ───
    ("못 견디", RiskLevel.MEDIUM, RiskCategory.ACUTE_DISTRESS, 0.75),
    ("버틸 수가 없", RiskLevel.MEDIUM, RiskCategory.ACUTE_DISTRESS, 0.75),
    ("아무것도 의미가 없", RiskLevel.MEDIUM, RiskCategory.ACUTE_DISTRESS, 0.7),
    ("혼자 있고 싶", RiskLevel.MEDIUM, RiskCategory.ACUTE_DISTRESS, 0.6),
]
