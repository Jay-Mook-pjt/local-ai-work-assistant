"use client";

import { useDeferredValue, useState } from "react";
import { Icon } from "@/components/common/Icon";
import { Alert, Button, Card, EmptyState, LinkButton, Loading, PageHeader } from "@/components/common/ui";
import { MeetingList } from "@/components/meeting/MeetingList";
import { useAsync } from "@/hooks/useAsync";
import { JOB_STATUS_LABEL, isProcessing } from "@/lib/format";
import { listMeetings } from "@/services/meetings";
import { JOB_STATUSES, type JobStatus } from "@/types/meeting";

export default function MeetingsPage() {
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [status, setStatus] = useState<JobStatus | "ALL">("ALL");
  const deferredQ = useDeferredValue(q);

  const { data, error, loading } = useAsync(() => listMeetings({ q: deferredQ, from, to, status }), [deferredQ, from, to, status], {
    pollMs: 3000,
    shouldPoll: (d) => !!d?.some((m) => isProcessing(m.status)),
  });
  const filtered = q || from || to || status !== "ALL";

  return (
    <>
      <PageHeader
        title="회의록"
        description="제목·참석자·안건·회의 내용으로 검색할 수 있습니다."
        actions={
          <LinkButton href="/meetings/new" icon="plus">
            새 회의록 생성
          </LinkButton>
        }
      />
      <Card>
        <div className="mb-4 grid gap-3 md:grid-cols-[1fr_auto_auto_auto_auto]">
          <div className="relative">
            <Icon name="search" className="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input className="field pl-9" placeholder="제목, 참석자, 회의 내용 검색" value={q} onChange={(e) => setQ(e.target.value)} aria-label="검색어" />
          </div>
          <input type="date" className="field md:w-40" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} aria-label="시작일" />
          <input type="date" className="field md:w-40" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} aria-label="종료일" />
          <select className="field md:w-36" value={status} onChange={(e) => setStatus(e.target.value as JobStatus | "ALL")} aria-label="상태">
            <option value="ALL">전체 상태</option>
            {JOB_STATUSES.map((s) => (
              <option key={s} value={s}>
                {JOB_STATUS_LABEL[s]}
              </option>
            ))}
          </select>
          <Button
            variant="ghost"
            disabled={!filtered}
            onClick={() => {
              setQ("");
              setFrom("");
              setTo("");
              setStatus("ALL");
            }}
          >
            초기화
          </Button>
        </div>
        {error && <Alert title="목록을 불러오지 못했습니다.">{error.message}</Alert>}
        {loading && !data && <Loading />}
        {data &&
          (data.length ? (
            <>
              <p className="muted mb-1 text-xs">{data.length}건</p>
              <MeetingList meetings={data} />
            </>
          ) : filtered ? (
            <EmptyState icon="search" title="조건에 맞는 회의가 없습니다." />
          ) : (
            <EmptyState icon="meetings" title="아직 회의가 없습니다." action={<LinkButton href="/meetings/new" icon="plus">첫 회의록 만들기</LinkButton>} />
          ))}
      </Card>
    </>
  );
}
