"use client";

import Link from "next/link";
import { Icon, type IconName } from "@/components/common/Icon";
import {
  ActionStatusBadge,
  Alert,
  Card,
  EmptyState,
  JobStatusBadge,
  LinkButton,
  Loading,
  MaybeUnknown,
  PageHeader,
  ProgressBar,
} from "@/components/common/ui";
import { MeetingList } from "@/components/meeting/MeetingList";
import { useAsync } from "@/hooks/useAsync";
import { formatBytes, formatDateTime } from "@/lib/format";
import { getDashboard } from "@/services/meetings";

function Stat({ icon, label, value, tone }: { icon: IconName; label: string; value: number; tone: string }) {
  return (
    <div className="card flex items-center gap-4 p-5">
      <div className={`rounded-lg p-2.5 ${tone}`}>
        <Icon name={icon} className="h-5 w-5" />
      </div>
      <div>
        <p className="muted text-xs">{label}</p>
        <p className="text-2xl font-bold tabular-nums">{value}</p>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { data, error, loading } = useAsync(getDashboard, [], {
    pollMs: 3000,
    shouldPoll: (d) => !!d && d.processing > 0,
  });

  return (
    <>
      <PageHeader
        title="대시보드"
        description="회의록 처리 현황과 후속 업무를 한눈에 확인합니다."
        actions={
          <LinkButton href="/meetings/new" icon="plus">
            새 회의록 생성
          </LinkButton>
        }
      />
      {error && <Alert title="데이터를 불러오지 못했습니다.">{error.message}</Alert>}
      {loading && !data && <Loading />}
      {data && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
            <Stat icon="meetings" label="전체 회의" value={data.total_meetings} tone="bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300" />
            <Stat icon="file" label="이번 달 회의" value={data.meetings_this_month} tone="bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300" />
            <Stat icon="cpu" label="AI 처리 중" value={data.processing} tone="bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300" />
            <Stat icon="tasks" label="미완료 후속 업무" value={data.open_action_items} tone="bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300" />
          </div>

          <div className="grid gap-6 xl:grid-cols-3">
            <Card
              className="xl:col-span-2"
              title="최근 회의"
              action={
                <Link href="/meetings" className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                  전체 보기
                </Link>
              }
            >
              {data.recent_meetings.length ? (
                <MeetingList meetings={data.recent_meetings} compact />
              ) : (
                <EmptyState icon="meetings" title="아직 회의가 없습니다." action={<LinkButton href="/meetings/new" icon="plus">첫 회의록 만들기</LinkButton>} />
              )}
            </Card>

            <Card title="AI 처리 상태">
              {data.active_jobs.length ? (
                <ul className="space-y-4">
                  {data.active_jobs.map((j) => (
                    <li key={j.id}>
                      <Link href={`/meetings/${j.meeting_id}`} className="block space-y-1.5 hover:opacity-80">
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-sm font-medium">{j.meeting_title}</p>
                          <JobStatusBadge status={j.status} />
                        </div>
                        <ProgressBar value={j.progress} failed={j.status === "FAILED"} />
                        <p className={`text-xs ${j.status === "FAILED" ? "text-red-600 dark:text-red-400" : "muted"}`}>{j.error ?? j.message}</p>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState icon="check" title="처리 중인 작업이 없습니다." />
              )}
            </Card>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card
              title="최근 후속 업무"
              action={
                <Link href="/history?tab=actions" className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                  전체 보기
                </Link>
              }
            >
              {data.recent_action_items.length ? (
                <ul className="divide-y divide-slate-200 dark:divide-slate-800">
                  {data.recent_action_items.map((a) => (
                    <li key={`${a.meeting_id}-${a.id}`} className="flex items-start gap-3 py-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">{a.task}</p>
                        <p className="muted mt-0.5 text-xs">
                          담당 <MaybeUnknown value={a.assignee} /> · 기한 <MaybeUnknown value={a.deadline} />
                        </p>
                        <Link href={`/meetings/${a.meeting_id}`} className="mt-0.5 block truncate text-xs text-indigo-600 hover:underline dark:text-indigo-400">
                          {a.meeting_title}
                        </Link>
                      </div>
                      <ActionStatusBadge status={a.status} />
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState icon="tasks" title="미완료 후속 업무가 없습니다." />
              )}
            </Card>

            <Card title="최근 생성된 문서">
              {data.recent_documents.length ? (
                <ul className="divide-y divide-slate-200 dark:divide-slate-800">
                  {data.recent_documents.map((d) => (
                    <li key={d.filename}>
                      <Link href={`/meetings/${d.meeting_id}?tab=documents`} className="flex items-center gap-3 py-3 hover:opacity-80">
                        <div className="rounded-lg bg-sky-50 p-2 text-sky-600 dark:bg-sky-500/15 dark:text-sky-300">
                          <Icon name="file" className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">{d.filename}</p>
                          <p className="muted text-xs">
                            {formatDateTime(d.created_at)} · {formatBytes(d.size_bytes)}
                          </p>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState icon="file" title="생성된 문서가 없습니다." />
              )}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
