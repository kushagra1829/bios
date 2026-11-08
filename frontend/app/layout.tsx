import type { Metadata } from "next";
import "./globals.css";
import Shell from "@/components/layout/Shell";

export const metadata: Metadata = {
  title: "BIOS — Business Intelligence Optimization System",
  description: "Enterprise Analytics Lifecycle & Governance Operating System for Bayer",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}

