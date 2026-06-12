import { Suspense } from "react";

import { LoginForm } from "./LoginForm";

export const metadata = {
  title: "로그인 · Neuro-Sync 의료진",
};

export default function LoginPage() {
  return (
    <main className="min-h-screen bg-surface flex items-center justify-center px-6">
      <div className="w-full max-w-sm flex flex-col gap-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-3xl font-semibold text-text-primary">Neuro-Sync</h1>
          <p className="text-text-secondary">의료진 대시보드</p>
        </header>
        <Suspense fallback={<p>로딩 중…</p>}>
          <LoginForm />
        </Suspense>
      </div>
    </main>
  );
}
