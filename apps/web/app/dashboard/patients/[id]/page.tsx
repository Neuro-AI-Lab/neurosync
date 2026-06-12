import Link from "next/link";
import { notFound } from "next/navigation";

import { SessionCard } from "../../../../components/SessionCard";
import { APIException, getPatient } from "../../../../lib/api";

type Params = { params: Promise<{ id: string }> };

export default async function PatientPage({ params }: Params) {
  const { id } = await params;
  try {
    const patient = await getPatient(id);
    return (
      <div className="flex flex-col gap-8">
        <Link href="/dashboard" className="text-sm text-state-info">
          ← 환자 목록
        </Link>

        <header className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold text-text-primary">
            {patient.name}
          </h1>
          <p className="text-text-secondary">
            {patient.email} · {patient.birthYear}년생
            {patient.isMinor ? " · 만 14세 미만" : ""} ·{" "}
            {patient.gender === "female"
              ? "여성"
              : patient.gender === "male"
              ? "남성"
              : "그 외"}
          </p>
        </header>

        <section className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="연락처" value={patient.phone ?? "—"} />
          <Field label="비상 연락처" value={patient.emergencyContact ?? "—"} />
          <Field label="거주 지역" value={patient.region ?? "—"} />
          <Field
            label="위험 통보 동의"
            value={
              patient.consent
                ? patient.consent.riskNotification
                  ? "옵트인"
                  : "옵트아웃"
                : "—"
            }
          />
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold text-text-primary">
            세션 ({patient.sessions.length})
          </h2>
          {patient.sessions.length === 0 ? (
            <p className="text-text-secondary">아직 세션이 없어요.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {patient.sessions.map((s) => (
                <li key={s.id}>
                  <SessionCard patientId={patient.userId} session={s} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    );
  } catch (e) {
    if (e instanceof APIException && e.status === 404) notFound();
    return (
      <div className="bg-red-50 border border-red-200 rounded-md p-4 text-state-danger">
        환자 정보를 불러오지 못했어요 (코드:{" "}
        {e instanceof APIException ? e.body.code : "NETWORK"}).
      </div>
    );
  }
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface-elevated border border-border rounded-md px-4 py-3">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className="text-text-primary mt-1">{value}</p>
    </div>
  );
}
