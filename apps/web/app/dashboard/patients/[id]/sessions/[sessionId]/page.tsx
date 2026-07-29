import Link from "next/link";
import { formatKST } from "../../../../../../lib/datetime";
import { notFound } from "next/navigation";

import { AutoRefresh } from "../../../../../../components/AutoRefresh";
import { HandoffReportView } from "../../../../../../components/HandoffReportView";
import { MessageRow } from "../../../../../../components/MessageRow";
import { ReportActions } from "../../../../../../components/ReportActions";
import { RiskEventCard } from "../../../../../../components/RiskEventCard";
import { TrendChart } from "../../../../../../components/TrendChart";
import { APIException, getReport, getReportTrend, getSession } from "../../../../../../lib/api";

type Params = { params: Promise<{ id: string; sessionId: string }> };

export default async function SessionPage({ params }: Params) {
  const { id, sessionId } = await params;
  try {
    const [sess, report, trend] = await Promise.all([
      getSession(sessionId),
      getReport(sessionId),
      getReportTrend(sessionId),
    ]);
    return (
      <div className="flex flex-col gap-8">
        <Link
          href={`/dashboard/patients/${id}`}
          className="text-[13px] text-text-secondary hover:text-text-primary transition-colors w-fit"
        >
          ← 환자 상세
        </Link>

        <header className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1.5">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
              사전 문진 세션
            </p>
            <h1 className="text-[26px] font-semibold tracking-tight text-text-primary">세션</h1>
            <p className="text-text-secondary tabular-nums">
              상태: {sess.status} · 시작 {formatKST(sess.createdAt)}
            </p>
          </div>
          {report && report.status === "ready" ? (
            <ReportActions report={report} patientName={report.patient?.name ?? "환자"} />
          ) : null}
        </header>

        {/* FR-019 인쇄 대상 영역 — @media print 로 이 블록만 남긴다 */}
        <div className="print-report flex flex-col gap-8">
          {/* 인쇄 시에만 보이는 문서 헤더(환자 맥락) */}
          <div className="hidden print:block border-b border-border-strong pb-3 mb-2">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">
              Neuro-Sync · 사전 문진 핸드오프
            </p>
            <p className="text-lg font-semibold tracking-tight text-text-primary mt-1">
              {report?.patient?.name ?? "환자"}
              {report?.patient?.birthYear ? ` · ${report.patient.birthYear}년생` : ""}
            </p>
          </div>
          {report ? <HandoffReportView report={report} /> : null}
          {trend && trend.plotData.length >= 2 ? <TrendChart trend={trend} /> : null}
        </div>

        {/* 생성 중이면 자동 갱신(수동 새로고침 제거) */}
        {report && report.status === "generating" ? <AutoRefresh /> : null}

        {sess.riskEvents.length > 0 ? (
          <section className="flex flex-col gap-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-faint">
              위험 이벤트 ({sess.riskEvents.length})
            </h2>
            <div className="flex flex-col gap-3">
              {sess.riskEvents.map((r) => (
                <RiskEventCard key={r.id} event={r} />
              ))}
            </div>
          </section>
        ) : null}

        <section className="flex flex-col gap-3">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-faint">
            메시지 ({sess.messages.length})
          </h2>
          {sess.messages.length === 0 ? (
            <p className="text-text-secondary">아직 메시지가 없어요.</p>
          ) : (
            <div className="bg-surface border border-border rounded-xl px-4">
              {sess.messages.map((m) => (
                <MessageRow key={m.id} msg={m} />
              ))}
            </div>
          )}
        </section>
      </div>
    );
  } catch (e) {
    if (e instanceof APIException && e.status === 404) notFound();
    return (
      <div className="bg-danger-soft border border-danger-line rounded-xl p-4 text-danger-ink">
        세션 정보를 불러오지 못했어요 (코드:{" "}
        {e instanceof APIException ? e.body.code : "NETWORK"}).
      </div>
    );
  }
}
