"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";
import { Icon, type IconName } from "@/components/common/Icon";
import { cx } from "@/components/common/ui";

const NAV: { href: string; label: string; icon: IconName; match: (p: string) => boolean }[] = [
  { href: "/", label: "대시보드", icon: "dashboard", match: (p) => p === "/" },
  { href: "/meetings", label: "회의록", icon: "meetings", match: (p) => p === "/meetings" || /^\/meetings\/(?!new)/.test(p) },
  { href: "/meetings/new", label: "새 회의록 생성", icon: "plus", match: (p) => p === "/meetings/new" },
  { href: "/history", label: "이력 · 후속 업무", icon: "history", match: (p) => p.startsWith("/history") },
  { href: "/settings", label: "설정", icon: "settings", match: (p) => p.startsWith("/settings") },
];

type Props = { onNavigate?: () => void };

// usePathname() is request-time data on dynamic routes (e.g. /meetings/[id]),
// so the highlighted nav streams in behind a Suspense boundary.
export function Sidebar(props: Props) {
  return (
    <Suspense fallback={<SidebarView pathname="" {...props} />}>
      <SidebarWithPath {...props} />
    </Suspense>
  );
}

function SidebarWithPath(props: Props) {
  return <SidebarView pathname={usePathname()} {...props} />;
}

function SidebarView({ pathname, onNavigate }: Props & { pathname: string }) {
  return (
    <nav className="flex h-full flex-col">
      <div className="flex h-16 items-center gap-2.5 px-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
          <Icon name="audio" className="h-4 w-4" />
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold">AI Work Assistant</p>
          <p className="muted text-xs">Local Meeting Agent</p>
        </div>
      </div>
      <ul className="flex-1 space-y-0.5 px-3 py-2">
        {NAV.map((item) => {
          const active = item.match(pathname);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100",
                )}
              >
                <Icon name={item.icon} className="h-[18px] w-[18px]" />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
      <p className="muted px-5 py-4 text-xs">모든 처리는 이 Mac 안에서만 수행됩니다.</p>
    </nav>
  );
}
