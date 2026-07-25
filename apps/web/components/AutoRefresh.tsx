"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * 리포트 생성 중일 때 서버 컴포넌트를 주기적으로 새로고침한다(수동 새로고침 제거).
 * generating 상태에서만 마운트하고, ready/failed가 되면 부모가 언마운트한다.
 */
export function AutoRefresh({ intervalMs = 5000 }: { intervalMs?: number }) {
  const router = useRouter();
  useEffect(() => {
    const id = setInterval(() => router.refresh(), intervalMs);
    return () => clearInterval(id);
  }, [router, intervalMs]);
  return null;
}
