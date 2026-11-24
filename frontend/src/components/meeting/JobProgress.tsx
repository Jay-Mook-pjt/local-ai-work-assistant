"use client";

import { Icon } from "@/components/common/Icon";
import { Alert, Button, Card, ProgressBar, cx } from "@/components/common/ui";
import { JOB_STATUS_LABEL, formatDateTime } from "@/lib/format";
import type { Job, JobStatus } from "@/types/meeting";

const STEPS: JobStatus[] = ["UPLOADED", "PREPROCESSING", "TRANSCRIBING", "ANALYZING", "GENERATING", "COMPLETED"];

export function JobProgress({ job, onRetry, retrying }: { job: Job; onRetry: () => void; retrying: boolean }) {
  const failed = job.status === "FAILED";
  const current = failed ? -1 : job.status === "PENDING" ? 0 : STEPS.indexOf(job.status);

  return (
    <Card title={failed ? "처리 실패" : job.status === "PENDING" ? "처리 대기 중" : "AI 처리 진행 중"} action={<span className="muted text-xs">{formatDateTime(job.updated_at)}</span>}>
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <ProgressBar value={job.progress} failed={failed} />
          <span className="w-10 text-right text-sm font-medium tabular-nums">{job.progress}%</span>
        </div>
        <ol className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          {STEPS.map((s, i) => {
            const done = current > i || job.status === "COMPLETED";
            const active = current === i && job.status !== "COMPLETED";
            return (
              <li key={s} className="flex flex-col items-center gap-1.5 text-center">
                <span
                  className={cx(
                    "flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold",
                    done && "bg-indigo-600 text-white",
                    active && "bg-indigo-100 text-indigo-700 ring-2 ring-indigo-500 dark:bg-indigo-500/20 dark:text-indigo-300",
                    !done && !active && "bg-slate-100 text-slate-400 dark:bg-slate-800",
                  )}
                >
                  {done ? <Icon name="check" className="h-3.5 w-3.5" /> : i + 1}
                </span>
                <span className={cx("text-xs", active ? "font-medium" : "muted")}>{JOB_STATUS_LABEL[s]}</span>
              </li>
            );
          })}
        </ol>
        {failed ? (
          <>
            <Alert title="오류 원인">{job.error ?? "알 수 없는 오류"}</Alert>
            <Button icon="refresh" onClick={onRetry} loading={retrying}>
              다시 처리
            </Button>
          </>
        ) : (
          job.message && <p className="muted text-sm">{job.message}</p>
        )}
      </div>
    </Card>
  );
}
