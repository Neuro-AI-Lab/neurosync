import { DashboardHeader } from "../../components/DashboardHeader";
import { getSessionUser } from "../../lib/auth";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await getSessionUser();
  return (
    <div className="min-h-screen bg-surface">
      <DashboardHeader user={user} />
      <div className="max-w-5xl mx-auto px-6 py-8">{children}</div>
    </div>
  );
}
