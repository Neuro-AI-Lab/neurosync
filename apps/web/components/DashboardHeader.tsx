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
    <header className="sticky top-0 z-10 border-b border-border bg-canvas/85 backdrop-blur-md">
      <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
        <a href="/dashboard" className="flex items-center gap-2.5">
          {/* 모바일 ConcentricMark 에코 — 링 + 점 */}
          <span
            className="h-[18px] w-[18px] rounded-full border-2 border-ink flex items-center justify-center"
            aria-hidden
          >
            <span className="h-[5px] w-[5px] rounded-full bg-ink" />
          </span>
          <span className="text-[15px] font-semibold tracking-tight text-text-primary">
            의료진용 대시보드
          </span>
        </a>
        <div className="flex items-center gap-4 text-[13px]">
          {user ? (
            <span className="text-text-secondary">
              {roleLabel} · {user.email}
            </span>
          ) : null}
          <button
            onClick={onLogout}
            className="text-text-secondary hover:text-text-primary transition-colors"
          >
            로그아웃
          </button>
        </div>
      </div>
    </header>
  );
}
