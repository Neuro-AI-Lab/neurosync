import type {
  HandoffNarrative,
  HandoffReport,
  QuestionnaireScore,
  ReportRiskSignal,
} from "../lib/api";
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

function Narrative({ n }: { n: HandoffNarrative }) {
  const saa = n.sleep_appetite_activity;
  const saaText = [
    saa.sleep ? `수면: ${saa.sleep}` : null,
    saa.appetite ? `식욕: ${saa.appetite}` : null,
    saa.activity ? `활동: ${saa.activity}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <dl className="flex flex-col gap-4">
      <Field label="주호소" value={n.chief_complaint} />
      <Field label="현병력" value={n.present_illness} />
      <ListField label="주요 증상" items={n.symptoms} />
      <Field label="시작 시점" value={n.onset} />
      <Field label="최근 변화" value={n.recent_changes} />
      <ListField label="유발 요인" items={n.triggers} />
      <Field label="수면 / 식욕 / 활동" value={saaText || null} />
      <Field label="과거 정신건강 이력" value={n.psych_history} />
      <Field label="복용약" value={n.medications} />
      <ListField label="업로드 문서 요약" items={n.documents_summary} />
      <ListField label="의료진 확인 필요" items={n.clinician_attention} />

      {n.evidence && n.evidence.length > 0 ? (
        <div className="flex flex-col gap-2">
          <dt className="text-[11px] font-medium uppercase tracking-wide text-faint">
            원문 근거 ({n.evidence.length})
          </dt>
          <dd className="flex flex-col gap-2.5">
            {n.evidence.map((e, i) => (
              <blockquote
                key={i}
                className="border-l-2 border-ink2 pl-3 text-[13px] leading-relaxed text-text-secondary"
              >
                <span className="font-semibold text-text-primary">{e.field}</span>:{" "}
                “{e.quote}”
              </blockquote>
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
            생성 {new Date(report.generatedAt).toLocaleString("ko-KR")}
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
