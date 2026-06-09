import { CONTRACTS_VERSION } from "@neuro-sync/contracts";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8 gap-4">
      <h1 className="text-3xl font-semibold">Neuro-Sync · 의료진 대시보드</h1>
      <p className="text-text-secondary">Phase 1a Day 1~2 bootstrap</p>
      <p className="text-sm text-text-secondary">
        Shared contracts version: <code>{CONTRACTS_VERSION}</code>
      </p>
    </main>
  );
}
