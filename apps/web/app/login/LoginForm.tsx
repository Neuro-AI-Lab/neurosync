"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") ?? "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"clinician" | "org_admin">("clinician");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, role }),
      });
      const body = (await res.json()) as { ok: boolean; code?: string };
      if (!res.ok || !body.ok) {
        if (body.code === "INVALID_CREDENTIALS")
          setError("이메일 또는 비밀번호가 일치하지 않아요");
        else if (body.code === "ROLE_MISMATCH")
          setError("선택한 권한으로는 접근할 수 없어요");
        else setError(`다시 시도해 주세요 (코드: ${body.code ?? "UNKNOWN"})`);
        return;
      }
      router.push(next);
      router.refresh();
    } catch {
      setError("연결이 불안정해요. 잠시 후 다시 시도해 주세요");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-text-primary">이메일</span>
        <input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="border border-border rounded-md px-3 py-2 text-base focus:outline-none focus:border-state-info"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-text-primary">비밀번호</span>
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="border border-border rounded-md px-3 py-2 text-base focus:outline-none focus:border-state-info"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-sm font-medium text-text-primary">권한</span>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as "clinician" | "org_admin")}
          className="border border-border rounded-md px-3 py-2 text-base"
        >
          <option value="clinician">의료진</option>
          <option value="org_admin">기관 관리자</option>
        </select>
      </label>

      {error ? (
        <p className="text-sm text-state-danger bg-red-50 border border-red-200 rounded-md px-3 py-2">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={submitting || !email || !password}
        className="bg-state-info text-white font-semibold rounded-md py-2.5 disabled:opacity-50"
      >
        {submitting ? "로그인 중…" : "로그인"}
      </button>
    </form>
  );
}
