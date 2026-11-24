"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { Icon } from "@/components/common/Icon";
import { cx } from "@/components/common/ui";
import { Sidebar } from "@/components/layout/Sidebar";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { api } from "@/services/api";

function SystemDot() {
  const [state, setState] = useState<"checking" | "ok" | "degraded" | "down">("checking");
  useEffect(() => {
    let alive = true;
    const check = () =>
      api
        .health()
        .then((h) => alive && setState(h.status === "ok" ? "ok" : "degraded"))
        .catch(() => alive && setState("down"));
    void check();
    const t = setInterval(check, 30_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  const meta = {
    checking: ["bg-slate-400", "확인 중"],
    ok: ["bg-emerald-500", "AI 엔진 정상"],
    degraded: ["bg-amber-500", "일부 구성요소 오류"],
    down: ["bg-red-500", "Backend 연결 안 됨"],
  }[state];
  return (
    <Link href="/settings" className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" title="설정에서 상세 상태 보기">
      <span className={cx("h-2 w-2 rounded-full", meta[0])} />
      <span className="hidden sm:inline">{meta[1]}</span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-60 border-r border-slate-200 bg-white lg:block dark:border-slate-800 dark:bg-slate-900">
        <Sidebar />
      </aside>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-white shadow-xl dark:bg-slate-900">
            <button className="absolute top-4 right-3 rounded-lg p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800" onClick={() => setOpen(false)} aria-label="메뉴 닫기">
              <Icon name="close" className="h-5 w-5" />
            </button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col lg:pl-60">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur sm:px-6 dark:border-slate-800 dark:bg-slate-900/80">
          <button className="rounded-lg p-2 hover:bg-slate-100 lg:hidden dark:hover:bg-slate-800" onClick={() => setOpen(true)} aria-label="메뉴 열기">
            <Icon name="menu" className="h-5 w-5" />
          </button>
          <div className="flex-1" />
          <SystemDot />
          <ThemeToggle />
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
