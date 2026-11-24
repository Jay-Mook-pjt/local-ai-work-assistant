"use client";

import Link from "next/link";
import { useEffect, useRef, type ButtonHTMLAttributes, type ComponentProps, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/common/Icon";
import { ACTION_STATUS_LABEL, JOB_STATUS_LABEL } from "@/lib/format";
import type { ActionStatus, JobStatus } from "@/types/meeting";
import { UNKNOWN } from "@/types/meeting";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-500 disabled:bg-indigo-600/50",
  secondary:
    "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800",
  ghost: "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
  danger: "bg-red-600 text-white hover:bg-red-500 disabled:bg-red-600/50",
};
const BTN_BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/40";

export function Button({
  variant = "primary",
  icon,
  loading,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; icon?: IconName; loading?: boolean }) {
  return (
    <button {...rest} disabled={rest.disabled || loading} className={cx(BTN_BASE, VARIANTS[variant], className)}>
      {loading ? <Spinner className="h-4 w-4" /> : icon && <Icon name={icon} />}
      {children}
    </button>
  );
}

export function LinkButton({
  variant = "primary",
  icon,
  className,
  children,
  ...rest
}: ComponentProps<typeof Link> & { variant?: Variant; icon?: IconName }) {
  return (
    <Link {...rest} className={cx(BTN_BASE, VARIANTS[variant], className)}>
      {icon && <Icon name={icon} />}
      {children}
    </Link>
  );
}

export function Card({ title, action, children, className }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("card", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-2 border-b border-slate-200 px-5 py-3.5 dark:border-slate-800">
          <h2 className="text-sm font-semibold">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-bold tracking-tight">{title}</h1>
        {description && <p className="muted mt-1 text-sm">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const JOB_COLORS: Record<JobStatus, string> = {
  PENDING: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  UPLOADED: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300",
  PREPROCESSING: "bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300",
  TRANSCRIBING: "bg-violet-100 text-violet-800 dark:bg-violet-500/15 dark:text-violet-300",
  ANALYZING: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  GENERATING: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  COMPLETED: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
  FAILED: "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300",
};

export function Badge({ className, children }: { className?: string; children: ReactNode }) {
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", className)}>{children}</span>;
}

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const active = status !== "COMPLETED" && status !== "FAILED" && status !== "PENDING";
  return (
    <Badge className={JOB_COLORS[status]}>
      {active && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
      {JOB_STATUS_LABEL[status]}
    </Badge>
  );
}

const ACTION_COLORS: Record<ActionStatus, string> = {
  PENDING: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  IN_PROGRESS: "bg-indigo-100 text-indigo-800 dark:bg-indigo-500/15 dark:text-indigo-300",
  DONE: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300",
};

export function ActionStatusBadge({ status }: { status: ActionStatus }) {
  return <Badge className={ACTION_COLORS[status]}>{ACTION_STATUS_LABEL[status]}</Badge>;
}

/** Renders a value, highlighting the "미확인" sentinel so it is never mistaken for real data. */
export function MaybeUnknown({ value }: { value: string }) {
  if (!value || value === UNKNOWN) return <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">{UNKNOWN}</span>;
  return <>{value}</>;
}

export function ProgressBar({ value, failed }: { value: number; failed?: boolean }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <div className={cx("h-full rounded-full transition-all duration-500", failed ? "bg-red-500" : "bg-indigo-500")} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={cx("animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M22 12a10 10 0 00-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Loading({ label = "불러오는 중…" }: { label?: string }) {
  return (
    <div className="muted flex items-center justify-center gap-2 py-12 text-sm">
      <Spinner className="h-4 w-4" /> {label}
    </div>
  );
}

export function EmptyState({ icon = "file", title, description, action }: { icon?: IconName; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <div className="rounded-full bg-slate-100 p-3 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
        <Icon name={icon} className="h-5 w-5" />
      </div>
      <p className="text-sm font-medium">{title}</p>
      {description && <p className="muted max-w-sm text-sm">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Alert({ tone = "error", title, children }: { tone?: "error" | "warning" | "info" | "success"; title?: string; children?: ReactNode }) {
  const tones = {
    error: "border-red-200 bg-red-50 text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300",
    warning: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200",
    info: "border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-200",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200",
  };
  const icon: IconName = tone === "success" ? "check" : "alert";
  return (
    <div className={cx("flex gap-2.5 rounded-lg border px-4 py-3 text-sm", tones[tone])} role={tone === "error" ? "alert" : "status"}>
      <Icon name={icon} className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={title ? "mt-0.5 opacity-90" : ""}>{children}</div>}
      </div>
    </div>
  );
}

export function Field({ label, required, hint, error, children, htmlFor }: { label: string; required?: boolean; hint?: string; error?: string; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-medium">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </label>
      {children}
      {error ? <p className="text-xs text-red-600 dark:text-red-400">{error}</p> : hint && <p className="muted text-xs">{hint}</p>}
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; count?: number }[]; value: T; onChange: (id: T) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-200 [scrollbar-width:none] dark:border-slate-800 [&::-webkit-scrollbar]:hidden" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            "-mb-px flex items-center gap-1.5 border-b-2 px-3.5 py-2.5 text-sm font-medium whitespace-nowrap transition-colors",
            value === t.id
              ? "border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200",
          )}
        >
          {t.label}
          {t.count != null && <span className="rounded-full bg-slate-100 px-1.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** Modal confirmation built on the native <dialog> element. */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel = "확인",
  tone = "primary",
  loading,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children?: ReactNode;
  confirmLabel?: string;
  tone?: "primary" | "danger";
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      className="card m-auto w-[min(92vw,28rem)] p-0 text-slate-900 backdrop:bg-black/40 dark:text-slate-100"
    >
      <div className="p-5">
        <h3 className="text-base font-semibold">{title}</h3>
        {children && <div className="muted mt-2 text-sm">{children}</div>}
      </div>
      <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-800">
        <Button variant="secondary" onClick={onCancel} disabled={loading}>
          취소
        </Button>
        <Button variant={tone === "danger" ? "danger" : "primary"} onClick={onConfirm} loading={loading}>
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}

export { cx };
