import type {
  EvidencePacket,
  HandoffNarrative,
  HandoffReport,
  QuestionnaireScore,
  ReportRiskSignal,
} from "../lib/api";
import { formatKST } from "../lib/datetime";
import { riskColor } from "../lib/tokens";
import { RiskBadge } from "./RiskBadge";

const QUESTIONNAIRE_LABEL: Record<string, string> = {
  PHQ9: "우울 (PHQ-9)",
  GAD7: "불안 (GAD-7)",
};

const SEVERITY_LABEL: Record<string, string> = {
  minimal: "최소",
  mild: "경도",
  moderate: "중등도",
  moderately_severe: "중등도-중증",
  severe: "중증",
};

function ScoreChip({ q }: { q: QuestionnaireScore }) {
  return (
    <div className="rounded-xl border border-border bg-surface px-4 py-3.5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-faint">
        {QUESTIONNAIRE_LABEL[q.type] ?? q.type}
      </p>
      <p className="mt-1 text-2xl font-semibold tracking-tight text-text-primary tabular-nums">
        {q.totalScore}
        <span className="text-sm font-normal text-text-secondary">
          점 · {SEVERITY_LABEL[q.severity] ?? q.severity}
        </span>
      </p>
    </div>
  );
}

function RiskSignalRow({ r }: { r: ReportRiskSignal }) {
  const c = riskColor[r.level];
  return (
    <div className={`flex items-center gap-2 rounded-lg border ${c.border} ${c.bg} px-3 py-2.5`}>
      <RiskBadge level={r.level} />
      <span className="text-sm text-text-primary">{r.category ?? "—"}</span>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-faint">{label}</dt>
      <dd className="text-text-primary leading-relaxed whitespace-pre-wrap">{value}</dd>
    </div>
  );
}

function ListField({ label, items }: { label: string; items: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-faint">{label}</dt>
      <dd className="flex flex-wrap gap-1.5">
        {items.map((it, i) => (
          <span
            key={i}
            className="rounded-full bg-surface-elevated border border-border px-2.5 py-1 text-[13px] text-text-primary"
          >
            {it}
          </span>
        ))}
      </dd>
    </div>
  );
}

function EvidenceRow({ e }: { e: EvidencePacket }) {
  return (
    <blockquote className="border-l-2 border-state-info pl-3 text-sm text-text-secondary">
      <span className="font-medium text-text-primary">{e.source_type}</span>{" "}
      ({e.source_ref}): {e.content_summary}
    </blockquote>
  );
}

// BUG-066 fix: `HandoffResponse` (contracts.handoff, apps/api<->ai-server)
// was realigned to ai-server's real `HandoffOutput` shape — the previous
// chief_complaint/present_illness/... fields this component read were never
// actually produced by ai-server (BUG-066's root cause: silent request-side
// field drop + response-side ValidationError, "status":"failed" every time
// live). `report_markdown` is the primary rendering surface going forward;
// `report_json`'s internal shape is UNVERIFIED (ai-server does not appear to
// populate it) so it is not parsed here.
function Narrative({ n }: { n: HandoffNarrative }) {
  return (
    <dl className="flex flex-col gap-4">
      {/* 의료진용 핸드오프: editorial PDF가 있으면 페이지에 인라인 렌더(1차 뷰),
          raw markdown 은 접이식 원문으로 내린다. PDF가 없는 리포트(단일세션 서사
          폴백 등)에서만 markdown 을 본문으로 표시. */}
      {n.pdf_base64 ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <dt className="text-xs font-semibold text-text-secondary">의료진 인계 보고서</dt>
            <a
              href={`data:application/pdf;base64,${n.pdf_base64}`}
              download="handoff_report.pdf"
              className="inline-flex items-center rounded-md border border-line px-3 py-1.5 text-sm font-medium text-text-primary hover:bg-surface-hover print:hidden"
            >
              PDF 다운로드
            </a>
          </div>
          <dd>
            <object
              data={`data:application/pdf;base64,${n.pdf_base64}`}
              type="application/pdf"
              className="w-full h-[1000px] rounded-lg border border-border bg-surface-elevated"
              aria-label="의료진 인계 보고서 PDF"
            >
              <p className="p-4 text-sm text-text-secondary">
                이 브라우저에서 PDF를 인라인으로 표시할 수 없어요.{" "}
                <a
                  href={`data:application/pdf;base64,${n.pdf_base64}`}
                  download="handoff_report.pdf"
                  className="underline"
                >
                  PDF 다운로드
                </a>
              </p>
            </object>
          </dd>
          {n.report_markdown ? (
            <details className="mt-1">
              <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-wide text-faint">
                원문 (markdown)
              </summary>
              <pre className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-text-secondary">
                {n.report_markdown}
              </pre>
            </details>
          ) : null}
        </div>
      ) : (
        <div className="flex flex-col gap-0.5">
          <dt className="text-xs font-semibold text-text-secondary">리포트</dt>
          <dd className="text-text-primary whitespace-pre-wrap">{n.report_markdown}</dd>
        </div>
      )}

      {/* F4 종단 차트 (있을 때만) */}
      {n.chart_pngs_base64 && n.chart_pngs_base64.length > 0 ? (
        <div className="flex flex-col gap-2">
          <dt className="text-[11px] font-medium uppercase tracking-wide text-faint">
            종단 추이 차트 ({n.chart_pngs_base64.length})
          </dt>
          <dd className="flex flex-col gap-3">
            {n.chart_pngs_base64.map((png, i) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={i}
                src={`data:image/png;base64,${png}`}
                alt={`종단 차트 ${i + 1}`}
                className="w-full rounded-md border border-line"
              />
            ))}
          </dd>
        </div>
      ) : null}

      {n.missing_slots && n.missing_slots.length > 0 ? (
        <ListField label="누락된 항목" items={n.missing_slots} />
      ) : null}

      {n.evidence_packets && n.evidence_packets.length > 0 ? (
        <div className="flex flex-col gap-2">
          <dt className="text-[11px] font-medium uppercase tracking-wide text-faint">
            원문 근거 ({n.evidence_packets.length})
          </dt>
          <dd className="flex flex-col gap-2.5">
            {n.evidence_packets.map((e, i) => (
              <EvidenceRow key={i} e={e} />
            ))}
          </dd>
        </div>
      ) : null}
    </dl>
  );
}

export function HandoffReportView({ report }: { report: HandoffReport }) {
  return (
    <section className="flex flex-col gap-5 rounded-2xl border border-border bg-surface p-6">
      <header className="flex items-center justify-between gap-2 border-b border-sep pb-4">
        <div className="flex flex-col gap-0.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-faint">
            Pre-consult
          </span>
          <h2 className="text-lg font-semibold tracking-tight text-text-primary">
            Handoff 리포트
          </h2>
        </div>
        {report.status === "ready" && report.generatedAt ? (
          <time className="text-xs text-text-secondary tabular-nums">
            생성 {formatKST(report.generatedAt)}
          </time>
        ) : null}
      </header>

      {report.status === "generating" ? (
        <p className="rounded-xl bg-surface-elevated border border-border px-4 py-3 text-text-secondary">
          ⏳ 리포트를 생성하고 있어요. 잠시 후 새로고침해 주세요.
        </p>
      ) : null}
      {report.status === "failed" ? (
        <p className="rounded-xl bg-danger-soft border border-danger-line px-4 py-3 text-danger-ink">
          리포트 생성에 실패했어요
          {report.failureReason ? ` (사유: ${report.failureReason})` : ""}. 아래
          문진 점수와 위험 신호는 그대로 확인할 수 있어요.
        </p>
      ) : null}

      {report.questionnaires.length > 0 ? (
        <div className="grid grid-cols-2 gap-2.5">
          {report.questionnaires.map((q) => (
            <ScoreChip key={q.type} q={q} />
          ))}
        </div>
      ) : null}

      {report.riskSignals.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-faint">
            위험 신호
          </h3>
          {report.riskSignals.map((r, i) => (
            <RiskSignalRow key={i} r={r} />
          ))}
        </div>
      ) : null}

      {report.status === "ready" && report.narrative ? (
        <Narrative n={report.narrative} />
      ) : null}
    </section>
  );
}
