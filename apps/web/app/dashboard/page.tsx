import { PatientListItem } from "../../components/PatientListItem";
import { APIException, listPatients, type PatientListItem as Item } from "../../lib/api";

export const metadata = {
  title: "환자 목록 · Neuro-Sync",
};

export default async function DashboardPage() {
  let patients: Item[] = [];
  let errorCode: string | null = null;
  try {
    patients = await listPatients();
  } catch (e) {
    errorCode = e instanceof APIException ? e.body.code : "NETWORK";
  }

  if (errorCode) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-md p-4 text-state-danger">
        환자 목록을 불러오지 못했어요 (코드: {errorCode}).
      </div>
    );
  }

  // PRD §A 보수적 탐지 — 위험 환자 먼저.
  const riskOrder = { critical: 0, high: 1, medium: 2, low: 3 } as const;
  const sorted = [...patients].sort((a, b) => {
    const ra = a.latestRisk ? riskOrder[a.latestRisk.level] : 4;
    const rb = b.latestRisk ? riskOrder[b.latestRisk.level] : 4;
    if (ra !== rb) return ra - rb;
    const ta = a.latestSessionAt ? new Date(a.latestSessionAt).getTime() : 0;
    const tb = b.latestSessionAt ? new Date(b.latestSessionAt).getTime() : 0;
    return tb - ta;
  });

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold text-text-primary">환자 목록</h1>
        <p className="text-sm text-text-secondary">{patients.length}명</p>
      </header>
      {patients.length === 0 ? (
        <p className="text-text-secondary">아직 등록된 환자가 없어요.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {sorted.map((p) => (
            <li key={p.userId}>
              <PatientListItem item={p} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
