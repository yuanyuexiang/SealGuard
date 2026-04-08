import type { Metadata } from "next";
import { DM_Sans, Fraunces } from "next/font/google";

import AppShell from "@/components/AppShell";
import Providers from "@/components/Providers";
import "./globals.css";

const dmSans = DM_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
});

const fraunces = Fraunces({
  variable: "--font-display",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "SealGuard Admin",
  description: "SealGuard management console with Coca-Cola brand style",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className={`${dmSans.variable} ${fraunces.variable}`}>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
