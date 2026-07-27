import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Neuro-Sync — 의료진 대시보드",
  description: "Pre-consultation handoff reports for psychiatric clinics.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // suppressHydrationWarning: 브라우저 확장(번역기·Grammarly·비밀번호 관리자 등)이
    // 하이드레이션 전에 <html>/<body>에 속성(data-*, cz-shortcut-listen 등)을 주입해
    // 발생하는 최상위 노드 미스매치를 억제한다(Next.js 공식 권장). 속성 1레벨만 억제하며
    // 하위 트리 내용 미스매치는 그대로 보고된다.
    <html lang="ko" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
