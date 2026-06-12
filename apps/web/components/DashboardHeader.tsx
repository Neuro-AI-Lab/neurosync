"use client";

import { useRouter } from "next/navigation";

import type { SessionUser } from "../lib/auth";

export function DashboardHeader({ user }: { user: SessionUser | null }) {
  const router = useRouter();

  const onLogout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  };

  const roleLabel = user?.role === "org_admin" ? "기관 관리자" : "의료진";

  return (
    <header className="border-b border-border bg-surface">
      <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
        <a href="/dashboard" className="text-lg font-semibold text-text-primary">
          Neuro-Sync 의료진 대시보드
        </a>
        <div className="flex items-center gap-4 text-sm">
          {user ? (
            <span className="text-text-secondary">
              {roleLabel} · {user.email}
            </span>
          ) : null}
          <button
            onClick={onLogout}
            className="text-text-secondary hover:text-text-primary"
          >
            로그아웃
          </button>
        </div>
      </div>
    </header>
  );
}
