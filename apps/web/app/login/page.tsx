import { Suspense } from "react";

import { LoginForm } from "./LoginForm";

export const metadata = {
  title: "로그인 · Neuro-Sync 의료진",
};

export default function LoginPage() {
  return (
    <main className="min-h-screen bg-canvas flex items-center justify-center px-6">
      <div className="w-full max-w-sm flex flex-col gap-7">
        <header className="flex flex-col items-start gap-3">
          <span
            className="h-8 w-8 rounded-full border-2 border-ink flex items-center justify-center"
            aria-hidden
          >
            <span className="h-2 w-2 rounded-full bg-ink" />
          </span>
          <div className="flex flex-col gap-1">
            <h1 className="text-[28px] font-semibold tracking-tight text-text-primary">
              Neuro-Sync
            </h1>
            <p className="text-text-secondary">의료진 대시보드</p>
          </div>
        </header>
        <div className="rounded-2xl border border-border bg-surface p-6">
          <Suspense fallback={<p className="text-text-secondary">로딩 중…</p>}>
            <LoginForm />
          </Suspense>
        </div>
      </div>
    </main>
  );
}
