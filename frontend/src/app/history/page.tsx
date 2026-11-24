"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ActionStatusBadge, Alert, Badge, Card, EmptyState, Loading, MaybeUnknown, PageHeader, Tabs } from "@/components/common/ui";
import { MeetingList } from "@/components/meeting/MeetingList";
import { useAsync } from "@/hooks/useAsync";
import { ACTION_STATUS_LABEL, formatDate, formatDateTime } from "@/lib/format";
import { listActionItems, listEmailHistory, listMeetings, updateActionItemStatus } from "@/services/meetings";
import { ACTION_STATUSES, type ActionStatus, type Meeting } from "@/types/meeting";

type Tab = "actions" | "timeline" | "emails";

function ActionsTab() {
  const [filter, setFilter] = useState<ActionStatus | "OPEN" | "ALL">("OPEN");
  const [assignee, setAssignee] = useState("");
  const { data, error, loading, setData } = useAsync(listActionItems, []);
  if (error) return <Alert title="후속 업무를 불러오지 못했습니다.">{error.message}</Alert>;
  if (loading && !data) return <Loading />;
  if (!data) return null;

  const assignees = [...new Set(data.map((a) => a.assignee))].sort();
  const rows = data.filter(
    (a) => (filter === "ALL" || (filter === "OPEN" ? a.status !== "DONE" : a.status === filter)) && (!assignee || a.assignee === assignee),
  );

  const change = async (meetingId: string, id: string, status: ActionStatus) => {
    setData(data.map((a) => (a.meeting_id === meetingId && a.id === id ? { ...a, status } : a)));
    await updateActionItemStatus(meetingId, id, status);
  };

  return (
    <Card>
      <div className="mb-4 flex flex-wrap gap-3">
        <select className="field w-40" value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)} aria-label="상태 필터">
          <option value="OPEN">미완료</option>
          <option value="ALL">전체</option>
          {ACTION_STATUSES.map((s) => (
            <option key={s} value={s}>
              {ACTION_STATUS_LABEL[s]}
            </option>
          ))}
        </select>
        <select className="field w-48" value={assignee} onChange={(e) => setAssignee(e.target.value)} aria-label="담당자 필터">
          <option value="">전체 담당자</option>
          {assignees.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
        <span className="muted self-center text-xs">{rows.length}건</span>
      </div>
      {rows.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="muted border-b border-slate-200 text-xs dark:border-slate-800">
              <tr>
                <th className="py-2 pr-3 font-medium">업무</th>
                <th className="py-2 pr-3 font-medium">담당자</th>
                <th className="py-2 pr-3 font-medium">기한</th>
                <th className="py-2 pr-3 font-medium">회의</th>
                <th className="py-2 font-medium">상태</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {rows.map((a) => (
                <tr key={`${a.meeting_id}-${a.id}`} className="align-top">
                  <td className="py-3 pr-3">{a.task}</td>
                  <td className="py-3 pr-3 whitespace-nowrap">
                    <MaybeUnknown value={a.assignee} />
                  </td>
                  <td className="py-3 pr-3">
                    <MaybeUnknown value={a.deadline} />
                  </td>
                  <td className="py-3 pr-3">
                    <Link href={`/meetings/${a.meeting_id}`} className="text-indigo-600 hover:underline dark:text-indigo-400">
                      {a.meeting_title}
                    </Link>
                    <p className="muted text-xs">{formatDate(a.meeting_date)}</p>
                  </td>
                  <td className="py-3">
                    <select
                      className="field w-28 py-1 text-xs"
                      value={a.status}
                      onChange={(e) => void change(a.meeting_id, a.id, e.target.value as ActionStatus)}
                      aria-label={`${a.task} 상태`}
                    >
                      {ACTION_STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {ACTION_STATUS_LABEL[s]}
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState icon="tasks" title="조건에 맞는 후속 업무가 없습니다." />
      )}
      <p className="muted mt-4 text-xs">
        상태 표시: <ActionStatusBadge status="PENDING" /> <ActionStatusBadge status="IN_PROGRESS" /> <ActionStatusBadge status="DONE" />
      </p>
    </Card>
  );
}

function TimelineTab() {
  const { data, error, loading } = useAsync(() => listMeetings(), []);
  if (error) return <Alert title="회의 이력을 불러오지 못했습니다.">{error.message}</Alert>;
  if (loading && !data) return <Loading />;
  if (!data?.length) return <EmptyState icon="meetings" title="회의 이력이 없습니다." />;
  const groups = data.reduce<Record<string, Meeting[]>>((acc, m) => {
    const k = m.meeting_date.slice(0, 7);
    (acc[k] ??= []).push(m);
    return acc;
  }, {});
  return (
    <div className="space-y-6">
      {Object.entries(groups).map(([ym, ms]) => (
        <Card key={ym} title={`${ym.slice(0, 4)}년 ${Number(ym.slice(5))}월 · ${ms.length}건`}>
          <MeetingList meetings={ms} />
        </Card>
      ))}
    </div>
  );
}

function EmailsTab() {
  const { data, error, loading } = useAsync(() => Promise.all([listEmailHistory(), listMeetings()]), []);
  if (error) return <Alert title="발송 이력을 불러오지 못했습니다.">{error.message}</Alert>;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  const [emails, meetings] = data;
  if (!emails.length) return <EmptyState icon="mail" title="발송 이력이 없습니다." />;
  return (
    <Card>
      <ul className="divide-y divide-slate-200 dark:divide-slate-800">
        {emails.map((e) => (
          <li key={e.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{e.subject}</p>
              <p className="muted text-xs">
                {formatDateTime(e.sent_at)} · {e.to.join(", ")} ·{" "}
                <Link href={`/meetings/${e.meeting_id}`} className="text-indigo-600 hover:underline dark:text-indigo-400">
                  {meetings.find((m) => m.id === e.meeting_id)?.title ?? "삭제된 회의"}
                </Link>
              </p>
            </div>
            <Badge className={e.status === "SENT" ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300" : "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300"}>
              {e.status === "SENT" ? "발송" : "실패"}
            </Badge>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function History() {
  const initial = useSearchParams().get("tab");
  const [tab, setTab] = useState<Tab>(initial === "timeline" || initial === "emails" ? initial : "actions");
  return (
    <>
      <PageHeader title="이력 · 후속 업무" description="회의에서 나온 후속 업무와 지난 회의, 이메일 발송 이력을 확인합니다." />
      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "actions", label: "후속 업무" },
          { id: "timeline", label: "회의 타임라인" },
          { id: "emails", label: "이메일 발송 이력" },
        ]}
      />
      <div className="mt-6">
        {tab === "actions" && <ActionsTab />}
        {tab === "timeline" && <TimelineTab />}
        {tab === "emails" && <EmailsTab />}
      </div>
    </>
  );
}

export default function HistoryPage() {
  return (
    <Suspense fallback={<Loading />}>
      <History />
    </Suspense>
  );
}
