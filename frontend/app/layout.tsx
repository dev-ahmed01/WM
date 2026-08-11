import "./globals.css";
import React from "react";
import { AppShell } from "@/components/shared/AppShell";

export const metadata = {
  title: "WorkMate · Operational Intelligence",
  description: "Verified operational guidance for every shift.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
