import Link from "next/link";
import { notFound } from "next/navigation";

import { SessionCard } from "../../../../components/SessionCard";
import { APIException, getPatient } from "../../../../lib/api";

type Params = { params: Promise<{ id: string }> };

// v3 수정 1 — 확장 인적사항 코드 → 한국어. 모바일 lib/demographics.ts와 동일 코드셋.
const DEMO_LABELS: Record<string, Record<string, string>> = {
  maritalStatus: {
    single: "미혼", married: "기혼", divorced: "이혼", bereaved: "사별",
    separated: "별거", other: "기타",
  },
  householdType: {
    alone: "1인 가구", spouse: "배우자와", parents: "부모와", children: "자녀와",
    relatives: "친척과", other: "기타",
  },
  educationLevel: {
    middle_or_below: "중졸 이하", high_school: "고졸", college: "대졸",
    graduate: "대학원 이상", other: "기타",
  },
  employmentStatus: {
    employed: "재직", self_employed: "자영업", unemployed: "무직", student: "학생",
    retired: "은퇴", homemaker: "주부", other: "기타",
  },
  incomeLevel: {
    low: "하", mid_low: "중하", mid: "중", mid_high: "중상", high: "상",
    prefer_not: "응답 안 함",
  },
  religion: {
    none: "무교", protestant: "개신교", catholic: "천주교", buddhist: "불교",
    won: "원불교", other: "기타", prefer_not: "응답 안 함",
  },
};

function demoLabel(field: string, code: string | null): string {
  if (!code) return "—";
  return DEMO_LABELS[field]?.[code] ?? code;
}

export default async function PatientPage({ params }: Params) {
  const { id } = await params;
  try {
    const patient = await getPatient(id);
    return (
      <div className="flex flex-col gap-8">
        <Link
          href="/dashboard"
          className="text-[13px] text-text-secondary hover:text-text-primary transition-colors w-fit"
        >
          ← 환자 목록
        </Link>

        <header className="flex flex-col gap-2">
          <div className="flex items-center gap-2.5">
            <h1 className="text-[28px] font-semibold tracking-tight text-text-primary">
              {patient.name}
            </h1>
            {patient.isMinor ? (
              <span className="text-[10px] font-semibold uppercase tracking-wider text-warn border border-warn-line bg-warn-soft rounded-full px-2 py-0.5">
                만 14세 미만
              </span>
            ) : null}
          </div>
          <p className="text-text-secondary tabular-nums">
            {patient.email} · {patient.birthYear}년생 ·{" "}
            {patient.gender === "female"
              ? "여성"
              : patient.gender === "male"
              ? "남성"
              : "그 외"}
          </p>
        </header>

        <Section title="연락 · 동의">
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
        </Section>

        <Section title="사회인구학적 정보">
          <Field label="혼인 상태" value={demoLabel("maritalStatus", patient.maritalStatus)} />
          <Field label="동거 형태" value={demoLabel("householdType", patient.householdType)} />
          <Field label="학력" value={demoLabel("educationLevel", patient.educationLevel)} />
          <Field label="직업" value={patient.occupation ?? "—"} />
          <Field label="고용 상태" value={demoLabel("employmentStatus", patient.employmentStatus)} />
          <Field label="소득 수준" value={demoLabel("incomeLevel", patient.incomeLevel)} />
          <Field label="종교" value={demoLabel("religion", patient.religion)} />
        </Section>

        <section className="flex flex-col gap-3">
          <SectionLabel>세션 ({patient.sessions.length})</SectionLabel>
          {patient.sessions.length === 0 ? (
            <p className="text-text-secondary">아직 세션이 없어요.</p>
          ) : (
            <ul className="flex flex-col gap-2.5">
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
      <div className="bg-danger-soft border border-danger-line rounded-xl p-4 text-danger-ink">
        환자 정보를 불러오지 못했어요 (코드:{" "}
        {e instanceof APIException ? e.body.code : "NETWORK"}).
      </div>
    );
  }
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-wider text-faint">{children}</p>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <SectionLabel>{title}</SectionLabel>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">{children}</div>
    </section>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface border border-border rounded-xl px-4 py-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-faint">{label}</p>
      <p className="text-text-primary mt-1">{value}</p>
    </div>
  );
}
