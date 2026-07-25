import type { ReportTrend, TrendPoint } from "../lib/api";

/**
 * 점수 추이 차트 (F4 종단 추론) — 의료진 리포트용. 모바일 앱 TrendChart의
 * 웹 포트. 색은 위험에만 쓰는 모노크롬 규율에 따라 PHQ-9=실선·채운 점,
 * GAD-7=점선·빈 점으로 구분한다. 점수는 높을수록 중증이라 선이 내려가면 호전.
 * CTRS는 "숫자 낮을수록 위험"이라 라인에 섞지 않고 하단 배지로 둔다.
 *
 * 반응형: viewBox 좌표계 + width:100% 로 컨테이너에 맞춰 스케일(클라이언트 JS 불필요).
 */

const W = 640;
const H = 176;
const PAD_X = 16;
const PAD_T = 16;
const PAD_B = 30;
const Y_MAX = 27; // PHQ-9 최고점 기준 공통 상한

const DIRECTION_KO: Record<ReportTrend["overallDirection"], string> = {
  improved: "호전 추세",
  worsened: "악화 추세",
  unchanged: "유지",
  unknown: "추이 정보 부족",
};

function mmdd(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`;
}

function xAt(i: number, n: number): number {
  if (n <= 1) return W / 2;
  return PAD_X + (i * (W - PAD_X * 2)) / (n - 1);
}
function yAt(v: number): number {
  const plot = H - PAD_T - PAD_B;
  return PAD_T + plot * (1 - Math.min(v, Y_MAX) / Y_MAX);
}

function series(points: TrendPoint[], pick: (p: TrendPoint) => number | null) {
  const dots: { x: number; y: number }[] = [];
  const coords: string[] = [];
  points.forEach((p, i) => {
    const v = pick(p);
    if (v == null) return;
    const x = xAt(i, points.length);
    const y = yAt(v);
    coords.push(`${x},${y}`);
    dots.push({ x, y });
  });
  return { line: coords.join(" "), dots };
}

export function TrendChart({ trend }: { trend: ReportTrend }) {
  const points = trend.plotData;
  if (points.length < 2) return null;

  const phq = series(points, (p) => p.phq9);
  const gad = series(points, (p) => p.gad7);
  const hasCtrs = points.some((p) => p.ctrsLevel != null);

  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-border bg-surface p-6">
      <header className="flex items-center justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-faint">
            Longitudinal · F4
          </span>
          <h3 className="text-base font-semibold tracking-tight text-text-primary">점수 추이</h3>
        </div>
        <span className="rounded-full border border-border-strong px-2.5 py-1 text-[11px] font-medium text-text-secondary">
          {DIRECTION_KO[trend.overallDirection]}
        </span>
      </header>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="점수 추이 차트">
        {/* 기준선 */}
        <line x1={PAD_X} y1={PAD_T} x2={W - PAD_X} y2={PAD_T} stroke="#ECECE8" strokeWidth={1} />
        <line
          x1={PAD_X}
          y1={H - PAD_B}
          x2={W - PAD_X}
          y2={H - PAD_B}
          stroke="#ECECE8"
          strokeWidth={1}
        />

        {/* GAD-7 — 점선 + 빈 점 */}
        <polyline
          points={gad.line}
          fill="none"
          stroke="#8C8C86"
          strokeWidth={1.75}
          strokeDasharray="5 4"
          strokeLinejoin="round"
        />
        {gad.dots.map((d, i) => (
          <circle key={`g${i}`} cx={d.x} cy={d.y} r={4} fill="#FFFFFF" stroke="#8C8C86" strokeWidth={1.75} />
        ))}

        {/* PHQ-9 — 실선 + 채운 점 */}
        <polyline points={phq.line} fill="none" stroke="#121210" strokeWidth={2.25} strokeLinejoin="round" />
        {phq.dots.map((d, i) => (
          <circle key={`p${i}`} cx={d.x} cy={d.y} r={4} fill="#121210" />
        ))}

        {/* 날짜 라벨 */}
        {points.map((p, i) => (
          <text
            key={`x${i}`}
            x={xAt(i, points.length)}
            y={H - 10}
            fontSize={11}
            fill="#B3B3AD"
            textAnchor="middle"
          >
            {mmdd(p.date)}
          </text>
        ))}
      </svg>

      {/* 범례 */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px] text-text-secondary">
        <span className="flex items-center gap-2">
          <span className="inline-block h-0.5 w-4 rounded bg-ink" />
          PHQ-9 (우울)
        </span>
        <span className="flex items-center gap-2">
          <span
            className="inline-block h-0.5 w-4 rounded"
            style={{ backgroundImage: "repeating-linear-gradient(90deg,#8C8C86 0 4px,transparent 4px 7px)" }}
          />
          GAD-7 (불안)
        </span>
        <span className="ml-auto text-[11px] text-faint">점수 낮을수록 호전</span>
      </div>

      {/* CTRS — 낮을수록 위험이라 별도 표기 */}
      {hasCtrs ? (
        <div className="flex items-center gap-3 border-t border-sep pt-3">
          <span className="text-[11px] font-medium text-text-secondary">CTRS 위험단계</span>
          <div className="flex flex-1 justify-around">
            {points.map((p, i) => {
              const danger = p.ctrsLevel != null && p.ctrsLevel <= 2;
              return (
                <span
                  key={`c${i}`}
                  className={`flex h-6 w-6 items-center justify-center rounded-md border text-[11px] font-semibold tabular-nums ${
                    danger
                      ? "border-danger-line bg-danger-soft text-danger-ink"
                      : "border-border-strong text-text-primary"
                  }`}
                >
                  {p.ctrsLevel ?? "–"}
                </span>
              );
            })}
          </div>
          <span className="text-[10px] text-faint">숫자 낮을수록 위험</span>
        </div>
      ) : null}
    </section>
  );
}
