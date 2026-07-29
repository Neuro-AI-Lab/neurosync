import type { RiskEventOut } from "../lib/api";
import { formatKST } from "../lib/datetime";
import { riskColor } from "../lib/tokens";
import { RiskBadge } from "./RiskBadge";

const categoryLabel: Record<string, string> = {
  suicide: "자살 의도",
  self_harm: "자해",
  acute_distress: "급성 고통",
  other_harm: "타해",
  none: "없음",
};

const legalBasisLabel: Record<string, string> = {
  "consent:risk_notification": "옵트인 (비상 연락 통보)",
  self_hotline_only: "옵트아웃 (본인용 안내)",
};

// CVR-051 (RM-13/RM-16 follow-up): `RiskEvent.ai_evidence.matched_keywords`
// carries the FULL ai-server category list as sentinel strings (see
// `apps/api/src/services/chat.py::_crisis_evidence_keywords`) so a
// co-occurring category (e.g. `harm_to_others` alongside a `SUICIDE`
// primary) survives `_map_crisis_category`'s single-value collapse. Prior
// to this fix that survived list was only visible as raw JSON in a
// collapsed `<details>` block — invisible at a glance. This map + parser
// surface it as structured Korean badges at the top of the card instead.
//
// NOTE: this is a DIFFERENT tag namespace than `categoryLabel` above
// (`RiskEventOut.category`, the single collapsed value) — these are the
// raw ai-server category tags. Korean wording here is risk-TYPE phrasing
// (not disease names) per NFR v3-2; exact wording pending clinical-
// validator confirmation (CVR-051 RM-18 follow-up).
const AI_CATEGORY_PREFIX = "ai_category:";
const SOURCE_DETECTED = "category_source:detected";
const SOURCE_FALLBACK_DEFAULT = "category_source:fallback_default";

const aiCategoryLabel: Record<string, string> = {
  suicidal_ideation: "자살 사고",
  self_harm: "자해",
  self_harm_overdose: "자해(과다복용)",
  harm_to_others: "타해 위험",
  distress: "정서적 고통",
  despair: "절망감",
};

// Categories rendered with a visually distinct (stronger) badge style so a
// co-occurring duty-to-warn-relevant tag isn't lost behind the primary
// `RiskBadge`. Currently just `harm_to_others` per CVR-051's finding;
// extend here if clinical-validator flags another tag as needing the same
// treatment.
const AI_CATEGORY_EMPHASIS = new Set(["harm_to_others"]);

export type ParsedAiCategoryEvidence = {
  /** Recognized `ai_category:<tag>` tags, in the order ai-server sent them. */
  categories: string[];
  /** `detected` | `fallback_default` | null (no recognized source tag present). */
  source: "detected" | "fallback_default" | null;
  /** Anything that didn't match a known sentinel shape — triggers the raw-JSON fallback. */
  unrecognized: string[];
};

/**
 * Parse the `ai_category:*` / `category_source:*` sentinel strings out of
 * `RiskEvent.ai_evidence.matched_keywords`. Pure and side-effect free so it
 * can be unit-tested without a running frontend.
 */
export function parseAiCategoryEvidence(matchedKeywords: unknown): ParsedAiCategoryEvidence {
  const result: ParsedAiCategoryEvidence = { categories: [], source: null, unrecognized: [] };
  if (!Array.isArray(matchedKeywords)) {
    return result;
  }
  for (const raw of matchedKeywords) {
    if (typeof raw !== "string") {
      result.unrecognized.push(String(raw));
      continue;
    }
    if (raw === SOURCE_DETECTED) {
      result.source = "detected";
    } else if (raw === SOURCE_FALLBACK_DEFAULT) {
      result.source = "fallback_default";
    } else if (raw.startsWith(AI_CATEGORY_PREFIX)) {
      const tag = raw.slice(AI_CATEGORY_PREFIX.length);
      if (tag && aiCategoryLabel[tag]) {
        result.categories.push(tag);
      } else {
        result.unrecognized.push(raw);
      }
    } else {
      result.unrecognized.push(raw);
    }
  }
  return result;
}

function AiCategoryBadges({ evidence }: { evidence: ParsedAiCategoryEvidence }) {
  if (evidence.categories.length === 0 && evidence.source === null) {
    return null;
  }
  return (
    <div className="flex flex-wrap items-center gap-1" data-testid="ai-category-badges">
      {evidence.categories.map((tag) => {
        const emphasized = AI_CATEGORY_EMPHASIS.has(tag);
        return (
          <span
            key={tag}
            className={
              emphasized
                ? "inline-flex items-center gap-1 px-2 py-0.5 rounded-md border-2 border-red-400 bg-red-50 text-red-800 text-xs font-bold"
                : "inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-slate-300 bg-slate-50 text-slate-700 text-xs font-semibold"
            }
          >
            {emphasized ? <span aria-hidden>⚠</span> : null}
            {aiCategoryLabel[tag]}
          </span>
        );
      })}
      {evidence.source === "fallback_default" ? (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-dashed border-slate-300 bg-transparent text-slate-500 text-xs italic">
          기본값(미검출)
        </span>
      ) : null}
    </div>
  );
}

export function RiskEventCard({ event }: { event: RiskEventOut }) {
  const c = riskColor[event.level];
  const matchedKeywords = event.aiEvidence ? (event.aiEvidence as { matched_keywords?: unknown }).matched_keywords : undefined;
  const aiCategoryEvidence = parseAiCategoryEvidence(matchedKeywords);
  return (
    <article className={`rounded-xl border border-l-4 ${c.border} ${c.bg} p-4 flex flex-col gap-2.5`}>
      <header className="flex items-center justify-between gap-2">
        <RiskBadge level={event.level} />
        <time className="text-xs text-text-secondary tabular-nums">
          {formatKST(event.detectedAt)}
        </time>
      </header>
      <AiCategoryBadges evidence={aiCategoryEvidence} />
      <p className="text-text-primary font-semibold tracking-tight">
        {event.category ? categoryLabel[event.category] ?? event.category : ""}
      </p>
      <p className="text-[13px] text-text-secondary">
        법적 근거: {event.legalBasis ? legalBasisLabel[event.legalBasis] ?? event.legalBasis : "—"}
        {" · "}
        상태: {event.status}
      </p>
      {event.aiEvidence ? (
        <details className="text-xs text-text-secondary">
          <summary className="cursor-pointer select-none hover:text-text-primary transition-colors">
            분류 근거
          </summary>
          <pre className="mt-2 bg-surface border border-border rounded-lg p-3 overflow-x-auto text-[11px] leading-relaxed">
            {JSON.stringify(event.aiEvidence, null, 2)}
          </pre>
        </details>
      ) : null}
    </article>
  );
}
