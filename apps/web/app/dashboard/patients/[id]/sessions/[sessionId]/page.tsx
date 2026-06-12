import Link from "next/link";
import { notFound } from "next/navigation";

import { MessageRow } from "../../../../../../components/MessageRow";
import { RiskEventCard } from "../../../../../../components/RiskEventCard";
import { APIException, getSession } from "../../../../../../lib/api";

type Params = { params: Promise<{ id: string; sessionId: string }> };

export default async function SessionPage({ params }: Params) {
  const { id, sessionId } = await params;
  try {
    const sess = await getSession(sessionId);
    return (
      <div className="flex flex-col gap-8">
        <Link
          href={`/dashboard/patients/${id}`}
          className="text-sm text-state-info"
        >
          ← 환자 상세
        </Link>

        <header className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold text-text-primary">세션</h1>
          <p className="text-text-secondary">
            상태: {sess.status} · 시작{" "}
            {new Date(sess.createdAt).toLocaleString("ko-KR")}
          </p>
        </header>

        {sess.riskEvents.length > 0 ? (
          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold text-text-primary">
              위험 이벤트 ({sess.riskEvents.length})
            </h2>
            <div className="flex flex-col gap-3">
              {sess.riskEvents.map((r) => (
                <RiskEventCard key={r.id} event={r} />
              ))}
            </div>
          </section>
        ) : null}

        <section className="flex flex-col">
          <h2 className="text-lg font-semibold text-text-primary mb-2">
            메시지 ({sess.messages.length})
          </h2>
          {sess.messages.length === 0 ? (
            <p className="text-text-secondary">아직 메시지가 없어요.</p>
          ) : (
            <div className="bg-surface border border-border rounded-lg px-4">
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
      <div className="bg-red-50 border border-red-200 rounded-md p-4 text-state-danger">
        세션 정보를 불러오지 못했어요 (코드:{" "}
        {e instanceof APIException ? e.body.code : "NETWORK"}).
      </div>
    );
  }
}
