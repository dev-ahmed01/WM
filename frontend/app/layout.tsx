import "./globals.css";
import React from "react";
import { Bricolage_Grotesque, Poppins } from "next/font/google";
import { AppShell } from "@/components/shared/AppShell";

// Type evaluation (see docs/design-research.md): Bricolage Grotesque gives headings character at a readable weight;
// Poppins carries body text because it is the only candidate that ships a real Devanagari design, so Hindi and English
// share one family instead of Hindi falling back to a system font. Both are self-hosted at build time.
const display = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-display", display: "swap" });
const body = Poppins({
  subsets: ["latin", "devanagari"], weight: ["400", "500", "600"], variable: "--font-body", display: "swap",
});

export const metadata = {
  title: "WorkMate",
  description: "Answers from your company's approved procedures, whenever you need them.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
