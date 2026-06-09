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
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
