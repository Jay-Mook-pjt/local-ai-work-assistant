"use client";

import { useSyncExternalStore } from "react";
import { Icon, type IconName } from "@/components/common/Icon";

export type ThemePref = "light" | "dark" | "system";
const KEY = "lawa.theme";
const listeners = new Set<() => void>();

/** Inline script run before hydration so the page never flashes the wrong theme. */
export const THEME_INIT_SCRIPT = `(function(){try{var p=localStorage.getItem('${KEY}')||'system';var d=p==='dark'||(p==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.classList.toggle('dark',d);}catch(e){}})();`;

function readPref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(pref: ThemePref) {
  try {
    localStorage.setItem(KEY, pref);
  } catch {
    /* ignore */
  }
  const dark = pref === "dark" || (pref === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  const mq = matchMedia("(prefers-color-scheme: dark)");
  const onSystem = () => readPref() === "system" && applyTheme("system");
  mq.addEventListener("change", onSystem);
  return () => {
    listeners.delete(cb);
    mq.removeEventListener("change", onSystem);
  };
}

export function useThemePref(): ThemePref {
  return useSyncExternalStore(subscribe, readPref, () => "system");
}

const ORDER: ThemePref[] = ["light", "dark", "system"];
const META: Record<ThemePref, { icon: IconName; label: string }> = {
  light: { icon: "sun", label: "라이트" },
  dark: { icon: "moon", label: "다크" },
  system: { icon: "monitor", label: "시스템" },
};

export function ThemeToggle() {
  const pref = useThemePref();
  const next = ORDER[(ORDER.indexOf(pref) + 1) % ORDER.length];
  return (
    <button
      onClick={() => applyTheme(next)}
      className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      title={`테마: ${META[pref].label} (클릭 시 ${META[next].label})`}
      aria-label={`테마 변경, 현재 ${META[pref].label}`}
    >
      <Icon name={META[pref].icon} className="h-5 w-5" />
    </button>
  );
}
