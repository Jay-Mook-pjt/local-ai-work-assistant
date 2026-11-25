// Speaker colours/names shared by the transcript and the naming panel.
const COLORS = [
  "bg-indigo-100 text-indigo-800 dark:bg-indigo-500/20 dark:text-indigo-200",
  "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-200",
  "bg-amber-100 text-amber-900 dark:bg-amber-500/20 dark:text-amber-200",
  "bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-200",
  "bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-200",
  "bg-violet-100 text-violet-800 dark:bg-violet-500/20 dark:text-violet-200",
];

/** "화자 3" → colour index 2 (stable per label). */
export function speakerColor(label: string): string {
  const n = Number(label.replace(/\D/g, "")) || 1;
  return COLORS[(n - 1) % COLORS.length];
}

export function speakerName(label: string | null, names: Record<string, string> | null | undefined): string | null {
  if (!label) return null;
  return names?.[label] ?? label;
}
