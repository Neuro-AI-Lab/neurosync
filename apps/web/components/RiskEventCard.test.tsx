import { parseAiCategoryEvidence } from "./RiskEventCard";

// Regression test for CVR-051 / RM-16 fix (BRIEF: PLAN-2026-W30-INTEG-REV4, qa RM-17).
// `parseAiCategoryEvidence` is pure and side-effect free; these cases mirror the
// scenarios independently re-executed via plain Node during the RM-17 gate because
// jest could not run in the sandbox (pre-existing Bun/node shim `TypeError:
// Attempted to assign to readonly property`, reproduces identically on the
// untouched RiskBadge.test.tsx).
describe("parseAiCategoryEvidence", () => {
  it("recovers co-occurring categories and the detected source", () => {
    expect(
      parseAiCategoryEvidence([
        "ai_category:suicidal_ideation",
        "ai_category:harm_to_others",
        "category_source:detected",
      ])
    ).toEqual({
      categories: ["suicidal_ideation", "harm_to_others"],
      source: "detected",
      unrecognized: [],
    });
  });

  it("reports fallback_default with no recognized category", () => {
    expect(parseAiCategoryEvidence(["category_source:fallback_default"])).toEqual({
      categories: [],
      source: "fallback_default",
      unrecognized: [],
    });
  });

  it("routes unknown or malformed entries to unrecognized only", () => {
    expect(parseAiCategoryEvidence(["unknown_tag", 123, null])).toEqual({
      categories: [],
      source: null,
      unrecognized: ["unknown_tag", "123", "null"],
    });
  });

  it("returns empty result for undefined or empty input", () => {
    expect(parseAiCategoryEvidence(undefined)).toEqual({
      categories: [],
      source: null,
      unrecognized: [],
    });
    expect(parseAiCategoryEvidence([])).toEqual({
      categories: [],
      source: null,
      unrecognized: [],
    });
  });

  it("treats an unmapped ai_category:* tag as unrecognized, not a category", () => {
    expect(parseAiCategoryEvidence(["ai_category:not_a_real_tag"])).toEqual({
      categories: [],
      source: null,
      unrecognized: ["ai_category:not_a_real_tag"],
    });
  });
});
