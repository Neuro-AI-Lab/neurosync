import { CTRS_META, type CtrsStage } from "../lib/tokens";

/**
 * CTRS(위기분류척도, Crisis Triage Rating Scale) 참고 범례.
 * 환자 목록의 CTRS 단계 배지는 **위험성(Rating A)** 기준으로 자동 산출된다.
 * 지지체계(Rating B)는 별도 축으로, 현재 자동 산출 대상은 아니며 임상 참고용.
 */

// Rating A: 위험성(Dangerousness) — 배지 단계와 직접 대응.
const RATING_A: Record<CtrsStage, string> = {
  1: "자살·자해 사고/관련 환청, 현병력 중 자살시도, 예측 불가한 폭력·충동",
  2: "자살 사고·행동으로 스스로 고통, 폭력·충동 과거력(현재 징후 없음)",
  3: "자·타해 사고를 양가적으로 표현하거나 비효과적 몸짓만 있음",
  4: "자·타해 사고/행동이 부분적·기왕력, 행동조절 욕구 분명·조절 가능",
  5: "자·타해 사고나 행동의 과거력·위험 없음",
};

// Rating B: 지지체계(Support System) — 참고 축.
const RATING_B: Record<CtrsStage, string> = {
  1: "가족·친구 등 지지체계 전무, 기관의 즉각 지지도 불가",
  2: "동원 가능한 지지체계는 있으나 효과가 제한적",
  3: "잠재적 지지체계는 있으나 제대로 기능하기 어려움",
  4: "관심 있는 지지체계 있으나 지지 제공 능력·의지 다소 불명확",
  5: "관심 있는 지지체계가 지지 제공 능력·의지를 갖춤",
};

const STAGES: CtrsStage[] = [1, 2, 3, 4, 5];

export function CtrsLegend() {
  return (
    <aside className="w-full md:w-72 shrink-0 rounded-xl border border-border bg-surface p-4 flex flex-col gap-3 h-fit md:sticky md:top-20">
      <div className="flex flex-col gap-0.5">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">참고</p>
        <h2 className="text-sm font-semibold tracking-tight text-text-primary">
          CTRS · 위기분류척도
        </h2>
        <p className="text-[11px] text-text-secondary leading-snug">
          단계는 <span className="font-medium">위험성(Rating A)</span> 기준 자동 산출.
        </p>
      </div>

      <ul className="flex flex-col gap-2">
        {STAGES.map((s) => {
          const { label, badge } = CTRS_META[s];
          return (
            <li key={s} className="flex gap-2.5">
              <span
                className={`mt-0.5 inline-flex h-fit items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold shrink-0 ${badge.bg} ${badge.border} ${badge.text}`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${badge.dot}`} aria-hidden />
                {s} {label}
              </span>
              <span className="text-[11px] text-text-secondary leading-snug">{RATING_A[s]}</span>
            </li>
          );
        })}
      </ul>

      <details className="border-t border-border pt-2.5">
        <summary className="cursor-pointer text-[11px] font-medium text-text-secondary">
          지지체계(Rating B) — 임상 참고 축
        </summary>
        <ul className="mt-2 flex flex-col gap-1.5">
          {STAGES.map((s) => (
            <li key={s} className="text-[11px] text-text-secondary leading-snug">
              <span className="font-medium text-text-primary">{s}</span> · {RATING_B[s]}
            </li>
          ))}
        </ul>
      </details>
    </aside>
  );
}
