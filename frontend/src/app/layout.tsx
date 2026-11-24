import type { Metadata } from "next";
import Script from "next/script";
import { AppShell } from "@/components/layout/AppShell";
import { THEME_INIT_SCRIPT } from "@/components/layout/ThemeToggle";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Personal AI Work Assistant", template: "%s · AI Work Assistant" },
  description: "로컬 AI 회의록 비서",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full">
        {/* Applies the saved theme before hydration to avoid a light/dark flash. */}
        <Script id="theme-init" strategy="beforeInteractive">
          {THEME_INIT_SCRIPT}
        </Script>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
