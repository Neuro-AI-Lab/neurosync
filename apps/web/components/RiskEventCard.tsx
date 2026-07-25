import type { RiskEventOut } from "../lib/api";
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

export function RiskEventCard({ event }: { event: RiskEventOut }) {
  const c = riskColor[event.level];
  return (
    <article className={`rounded-xl border border-l-4 ${c.border} ${c.bg} p-4 flex flex-col gap-2.5`}>
      <header className="flex items-center justify-between gap-2">
        <RiskBadge level={event.level} />
        <time className="text-xs text-text-secondary tabular-nums">
          {new Date(event.detectedAt).toLocaleString("ko-KR")}
        </time>
      </header>
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
