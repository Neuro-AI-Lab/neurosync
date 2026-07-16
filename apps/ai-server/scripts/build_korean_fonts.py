"""Build embeddable, glyf-outline (TrueType) Korean font subsets for F5's
PDF exporter (`src/services/f5_report.py`) — `ADR-038` Decision 1,
`BUG-044`.

Why this script exists: `reportlab.pdfbase.ttfonts.TTFont` (the ONLY
embeddable-font loader reportlab offers) requires a `glyf`/`loca`
(quadratic TrueType outline) font. This host's only installed Korean-
capable font family (`Noto Sans/Serif CJK KR`, confirmed via `fc-list`) is
packaged as `.ttc` collections whose subfonts carry `CFF ` (PostScript/
cubic-outline, "OTTO"-flavored OpenType) tables, NOT `glyf` — reportlab's
own `TTFontFile.extractInfo` raises `TTFError('... postscript outlines are
not supported')` for these. There is no Nanum/Baekmuk/other TrueType-glyf
Korean font installed on this host (`find` swept the filesystem, only
`swcatalog` icon PNGs matched, no actual font files) — so the previous
non-embedded `reportlab.pdfbase.cidfonts.UnicodeCIDFont` choice (`ADR-037`
Decision 7) cannot simply be replaced by pointing `TTFont` at an
already-usable system file (`BUG-044`'s "another system Korean TTF"
candidate direction is unavailable on THIS host, verified before writing
this converter).

What this script does (pure `fontTools`, already an installed transitive
dependency via `matplotlib` — no new project dependency added):
  1. Opens the source `.ttc`, selects the named KR subfont.
  2. Subsets it (`fontTools.subset`) to `TARGET_UNICODE_RANGES` below — a
     fixed, deterministic Unicode coverage set chosen from an actual scan
     of every Korean string this project's F5 renderer emits (source code
     constants + every EXP-023/024 generated artifact), see the ranges'
     inline comments. Confirmed to include BOTH `·` (U+00B7) and `⚠`
     (U+26A0), BUG-044's specific tofu-glyph targets, plus the full
     precomposed Hangul syllable block (every syllable this system could
     ever emit, not just the ones observed so far).
  3. Converts every subsetted glyph's cubic (CFF) outline to a quadratic
     (TrueType) outline via `fontTools.pens.cu2quPen.Cu2QuPen` +
     `fontTools.pens.ttGlyphPen.TTGlyphPen` — the same cubic->quadratic
     technique standalone OTF->TTF converter tools use.
  4. Assembles a fresh `glyf`/`loca`-bearing sfnt (drops `CFF `/`VORG`/
     `BASE`/`GSUB`/`GPOS`/`GDEF`/`vhea`/`vmtx` — vertical metrics and
     complex-shaping layout tables are not needed for this project's
     horizontal, precomposed-Hangul-only text), sets `sfntVersion` to the
     TrueType tag, and writes the result.

Output is verified end-to-end in THIS script (not merely assumed): the
freshly-built file is round-tripped through
`reportlab.pdfbase.ttfonts.TTFont` + a real one-page PDF build, and the
specific `·`/`⚠` codepoints are confirmed present in the font's own cmap.

Usage (idempotent, re-run any time the Noto CJK package changes):
    uv run python scripts/build_korean_fonts.py

Run from `apps/ai-server/` (uses relative default paths). Writes both
`assets/fonts/NotoSansKR-Subset.ttf` (body) and
`assets/fonts/NotoSerifKR-Subset.ttf` (heading), plus prints each file's
SHA256 — `src/services/f5_report.py`'s `_BODY_FONT_SHA256`/
`_HEADING_FONT_SHA256` constants must match these exactly (checked at
import time; a mismatch raises, never silently falls back).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont

# ── Deterministic Unicode coverage (BUG-044 root-cause scope + a real scan
# of every Korean string src/f5.py, src/services/f5_report.py, and every
# EXP-023/024 generated artifact under experiments/ actually contain — see
# module docstring). No CJK Unified Ideographs (Hanja): zero occurrences
# found across that entire scan, confirmed by a dedicated grep before this
# range list was fixed — this project's Korean text is Hangul-only. ─────

TARGET_UNICODE_RANGES: tuple[tuple[int, int], ...] = (
    (0x0020, 0x007E),  # Basic Latin (printable ASCII)
    (0x00A0, 0x00FF),  # Latin-1 Supplement
    (0x2000, 0x27BF),  # General Punctuation .. Dingbats (covers U+2022,
    # U+2026 …, arrows, math operators, and MISCELLANEOUS SYMBOLS
    # U+2600-26FF -- includes U+26A0 WARNING SIGN, BUG-044's 2nd target)
    (0x3000, 0x303F),  # CJK Symbols and Punctuation
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x3130, 0x318F),  # Hangul Compatibility Jamo
    (0xAC00, 0xD7A3),  # Hangul Syllables (full block, all 11,172)
    (0xFF00, 0xFFEF),  # Halfwidth and Fullwidth Forms
)
# U+00B7 MIDDLE DOT (BUG-044's 1st target) is covered by the Latin-1
# Supplement range above.

_NOTO_DIR = Path("/usr/share/fonts/opentype/noto")


def _target_unicodes() -> set[int]:
    out: set[int] = set()
    for lo, hi in TARGET_UNICODE_RANGES:
        out.update(range(lo, hi + 1))
    return out


def _load_kr_subfont(ttc_path: Path, family_name: str) -> TTFont:
    """Open `ttc_path` (a `.ttc` collection) and return the subfont whose
    `name` table ID-1 (family) matches `family_name` exactly. Raises
    `ValueError` (never guesses/falls back) if no subfont matches."""
    from fontTools.ttLib import TTCollection

    tc = TTCollection(str(ttc_path))
    for font in tc.fonts:
        if font["name"].getDebugName(1) == family_name:
            return font
    available = [f["name"].getDebugName(1) for f in tc.fonts]
    raise ValueError(f"no subfont named {family_name!r} in {ttc_path} (available: {available})")


def _subset(font: TTFont, unicodes: set[int]) -> None:
    """In-place subset via `fontTools.subset` — keeps only the glyphs
    reachable from `unicodes` (plus `.notdef`). Drops GSUB/GPOS layout
    features: this project's rendered text is precomposed Hangul + ASCII,
    which needs no complex reordering/substitution shaping."""
    from fontTools import subset

    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recalc_bounds = True
    options.recalc_timestamp = False
    options.layout_features = []
    options.glyph_names = True
    options.legacy_kern = False
    options.symbol_cmap = True
    options.recommended_glyphs = False

    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(font)


def _cff_to_truetype(font: TTFont) -> None:
    """In-place: convert every glyph's CFF cubic outline to a TrueType
    quadratic outline (`Cu2QuPen`), replace `CFF ` with `glyf`/`loca`, drop
    tables that only make sense for the CFF/OTTO flavor or for features
    this project's renderer never uses (vertical metrics, GSUB/GPOS/GDEF —
    already emptied by `_subset`'s `layout_features=[]`, but the table
    shells can remain and are harmless to drop explicitly)."""
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import newTable

    glyph_order = font.getGlyphOrder()
    glyph_set = font.getGlyphSet()
    upm = font["head"].unitsPerEm
    max_err = upm * 0.001  # 0.1% of em -- standard cu2qu approximation error

    glyphs = {}
    for name in glyph_order:
        tt_pen = TTGlyphPen(glyph_set)
        cu2qu_pen = Cu2QuPen(tt_pen, max_err, reverse_direction=True)
        glyph_set[name].draw(cu2qu_pen)
        glyphs[name] = tt_pen.glyph()

    glyf = newTable("glyf")
    glyf.glyphOrder = glyph_order
    glyf.glyphs = glyphs
    font["glyf"] = glyf
    font["loca"] = newTable("loca")

    for tag in ("CFF ", "VORG", "BASE", "GSUB", "GPOS", "GDEF", "vhea", "vmtx"):
        if tag in font:
            del font[tag]

    font.sfntVersion = "\x00\x01\x00\x00"

    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    maxp.numGlyphs = len(glyph_order)
    for field in (
        "maxPoints",
        "maxContours",
        "maxCompositePoints",
        "maxCompositeContours",
        "maxTwilightPoints",
        "maxStorage",
        "maxFunctionDefs",
        "maxInstructionDefs",
        "maxStackElements",
        "maxSizeOfInstructions",
        "maxComponentElements",
        "maxComponentDepth",
    ):
        setattr(maxp, field, 0)
    maxp.maxZones = 1

    head = font["head"]
    head.indexToLocFormat = 1  # long (32-bit) loca offsets -- safe default
    head.glyphDataFormat = 0

    post = font["post"]
    post.formatType = 3.0  # no per-glyph PostScript names needed

    font.recalcBBoxes = True
    # Determinism (`experiment-reproducibility` skill): without this,
    # `head.compile()` stamps `head.modified` with the current wall-clock
    # time on every save, making two builds from identical inputs differ
    # byte-for-byte (confirmed empirically -- `head.created` is untouched,
    # only `modified` drifts). `head.created`/`modified` are left exactly
    # as inherited from the source Noto CJK KR font (unmodified by
    # subsetting), so re-running this script against the same source
    # produces a byte-identical, same-SHA256 output file.
    font.recalcTimestamp = False


def _verify_with_reportlab(ttf_path: Path, sample_text: str) -> None:
    """Round-trip the freshly built file through reportlab's OWN font
    loader + a real one-page PDF build — never trust the fontTools-side
    save alone. Raises on any failure (never silently accepted)."""
    import io

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont as RLTTFont
    from reportlab.pdfgen import canvas

    face_name = f"_verify_{ttf_path.stem}"
    pdfmetrics.registerFont(RLTTFont(face_name, str(ttf_path)))
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setFont(face_name, 14)
    c.drawString(50, 700, sample_text)
    c.save()
    pdf_bytes = buf.getvalue()
    if len(pdf_bytes) < 500:
        raise RuntimeError(f"reportlab verification PDF for {ttf_path} looks empty")


def build_one(ttc_path: Path, family_name: str, out_path: Path, *, verify_text: str) -> str:
    """Build one embeddable subset TTF; returns its SHA256 hex digest."""
    font = _load_kr_subfont(ttc_path, family_name)
    unicodes = _target_unicodes()
    _subset(font, unicodes)

    cmap = font.getBestCmap()
    missing = [cp for cp in (0x00B7, 0x26A0) if cp not in cmap]
    if missing:
        raise RuntimeError(
            f"{ttc_path}::{family_name} is missing required glyph(s) after "
            f"subsetting: {[hex(m) for m in missing]}"
        )

    _cff_to_truetype(font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(out_path))

    _verify_with_reportlab(out_path, verify_text)

    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    return digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--noto-dir",
        type=Path,
        default=_NOTO_DIR,
        help="directory containing NotoSansCJK-Regular.ttc / NotoSerifCJK-Medium.ttc",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "assets" / "fonts",
        help="output directory for the built .ttf files",
    )
    args = parser.parse_args(argv)

    sans_ttc = args.noto_dir / "NotoSansCJK-Regular.ttc"
    serif_ttc = args.noto_dir / "NotoSerifCJK-Medium.ttc"
    for p in (sans_ttc, serif_ttc):
        if not p.exists():
            print(f"ERROR: source font not found: {p}", file=sys.stderr)
            return 1

    body_out = args.out_dir / "NotoSansKR-Subset.ttf"
    heading_out = args.out_dir / "NotoSerifKR-Subset.ttf"

    body_sha = build_one(
        sans_ttc,
        "Noto Sans CJK KR",
        body_out,
        verify_text="확률·가능성이 아니며 ⚠ 경고 테스트",
    )
    print(f"{body_out}  sha256={body_sha}")

    heading_sha = build_one(
        serif_ttc,
        "Noto Serif CJK KR Medium",
        heading_out,
        verify_text="F5 인계 요약 보고서 ⚠",
    )
    print(f"{heading_out}  sha256={heading_sha}")

    print()
    print("Update src/services/f5_report.py constants to:")
    print(f'  _BODY_FONT_SHA256 = "{body_sha}"')
    print(f'  _HEADING_FONT_SHA256 = "{heading_sha}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
