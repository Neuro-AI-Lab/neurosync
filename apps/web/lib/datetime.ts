/**
 * ISO 시각 문자열을 항상 **한국 시간(KST, Asia/Seoul)**으로 포맷한다.
 *
 * API는 타임스탬프를 UTC(`...Z`)로 내려주는데, `toLocaleString("ko-KR")`은 실행
 * 런타임의 기본 타임존을 쓴다 — DGX 배포 컨테이너의 Node는 TZ 미설정이라 UTC로
 * 동작해 시각이 9시간 어긋나 보였다(BUG). `timeZone: "Asia/Seoul"`을 명시하면
 * Node/브라우저 내장 ICU가 컨테이너 TZ와 무관하게 KST로 변환하며, 서버(SSR)와
 * 클라이언트가 동일 문자열을 내므로 하이드레이션에도 안전하다.
 */
export function formatKST(
  iso: string | null | undefined,
  opts?: Intl.DateTimeFormatOptions,
): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", ...opts });
}
