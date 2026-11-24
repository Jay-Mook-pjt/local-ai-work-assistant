"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { MinutesEditor } from "@/components/editor/MinutesEditor";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  JobStatusBadge,
  LinkButton,
  Loading,
  PageHeader,
  Tabs,
} from "@/components/common/ui";
import { EmailPanel } from "@/components/meeting/EmailPanel";
import { JobProgress } from "@/components/meeting/JobProgress";
import { MinutesView } from "@/components/meeting/MinutesView";
import { TranscriptView } from "@/components/meeting/TranscriptView";
import { useAsync } from "@/hooks/useAsync";
import { formatBytes, formatDate, formatDateTime, formatDuration, isProcessing } from "@/lib/format";
import {
  NotFoundError,
  deleteMeeting,
  getJob,
  getMeeting,
  getMinutes,
  getTranscript,
  listDocuments,
  listEmailHistory,
  retryAnalysis,
  updateMinutes,
} from "@/services/meetings";
import type { MeetingMinutes } from "@/types/meeting";

type Tab = "minutes" | "transcript" | "documents" | "info";
const TAB_IDS: Tab[] = ["minutes", "transcript", "documents", "info"];

async function loadBundle(id: string) {
  const meeting = await getMeeting(id);
  const [job, transcript, minutes, documents, emails] = await Promise.all([
    meeting.latest_job_id ? getJob(meeting.latest_job_id) : Promise.resolve(null),
    getTranscript(id),
    getMinutes(id),
    listDocuments(id),
    listEmailHistory(id),
  ]);
  return { meeting, job, transcript, minutes, documents, emails };
}

function MeetingDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const initialTab = search.get("tab");
  const [tab, setTab] = useState<Tab>(TAB_IDS.includes(initialTab as Tab) ? (initialTab as Tab) : "minutes");
  const [editing, setEditing] = useState(false);
  const [focusTs, setFocusTs] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const { data, error, loading, reload, setData } = useAsync(() => loadBundle(id), [id], {
    pollMs: 2000,
    shouldPoll: (d) => !!d && isProcessing(d.meeting.status),
  });

  if (error instanceof NotFoundError)
    return <EmptyState icon="alert" title="회의를 찾을 수 없습니다." description="삭제되었거나 잘못된 주소입니다." action={<LinkButton href="/meetings" variant="secondary">목록으로</LinkButton>} />;
  if (error) return <Alert title="회의 정보를 불러오지 못했습니다.">{error.message}</Alert>;
  if (loading && !data) return <Loading />;
  if (!data) return null;

  const { meeting, job, transcript, minutes, documents, emails } = data;

  const jump = (ts: string) => {
    setFocusTs(ts);
    setTab("transcript");
  };

  const save = async (m: MeetingMinutes) => {
    const saved = await updateMinutes(meeting.id, m);
    setData({ ...data, minutes: saved });
    setEditing(false);
    setNotice("회의록을 저장했습니다.");
    setTimeout(() => setNotice(null), 2500);
  };

  const retry = async () => {
    setRetrying(true);
    try {
      await retryAnalysis(meeting.id);
      reload();
    } finally {
      setRetrying(false);
    }
  };

  const remove = async () => {
    setDeleting(true);
    await deleteMeeting(meeting.id);
    router.replace("/meetings");
  };

  return (
    <>
      <PageHeader
        title={meeting.title}
        description={
          <span className="inline-flex flex-wrap items-center gap-2">
            <JobStatusBadge status={meeting.status} />
            <span>{formatDate(meeting.meeting_date)}</span>
            {meeting.attendees.length > 0 && <span>· {meeting.attendees.join(", ")}</span>}
            {minutes?.edited && <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">수정됨</Badge>}
          </span>
        }
        actions={
          <Button variant="secondary" icon="trash" onClick={() => setConfirmDelete(true)}>
            삭제
          </Button>
        }
      />

      {notice && (
        <div className="mb-4">
          <Alert tone="success" title={notice} />
        </div>
      )}

      {job && job.status !== "COMPLETED" && (
        <div className="mb-6">
          <JobProgress job={job} onRetry={retry} retrying={retrying} />
        </div>
      )}

      <Tabs<Tab>
        value={tab}
        onChange={(t) => {
          setTab(t);
          setEditing(false);
        }}
        tabs={[
          { id: "minutes", label: "회의록" },
          { id: "transcript", label: "전사문", count: transcript?.segments.length },
          { id: "documents", label: "문서 · 이메일" },
          { id: "info", label: "회의 정보" },
        ]}
      />

      <div className="mt-6">
        {tab === "minutes" &&
          (minutes ? (
            <Card
              title={editing ? "회의록 편집" : `회의록 · ${minutes.llm_model}`}
              action={
                !editing && (
                  <Button variant="secondary" icon="edit" onClick={() => setEditing(true)}>
                    편집
                  </Button>
                )
              }
            >
              {editing ? <MinutesEditor initial={minutes} onSave={save} onCancel={() => setEditing(false)} /> : <MinutesView meeting={meeting} minutes={minutes} onJump={jump} />}
            </Card>
          ) : (
            <Card>
              <EmptyState icon="cpu" title="회의록이 아직 생성되지 않았습니다." description={isProcessing(meeting.status) ? "AI 처리가 끝나면 자동으로 표시됩니다." : "처리에 실패했습니다. 위에서 다시 처리할 수 있습니다."} />
            </Card>
          ))}

        {tab === "transcript" && (
          <Card>
            <TranscriptView transcript={transcript} focusTs={focusTs} />
          </Card>
        )}

        {tab === "documents" &&
          (minutes ? (
            <EmailPanel meeting={meeting} minutes={minutes} documents={documents} history={emails} />
          ) : (
            <Card>
              <EmptyState icon="file" title="회의록이 생성된 뒤 문서와 이메일을 만들 수 있습니다." />
            </Card>
          ))}

        {tab === "info" && (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="회의 정보">
              <dl className="grid grid-cols-[6rem_1fr] gap-y-2 text-sm">
                <dt className="muted">목적</dt>
                <dd>{meeting.purpose || "-"}</dd>
                <dt className="muted">안건</dt>
                <dd>
                  <ol className="list-decimal pl-4">
                    {meeting.agenda.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ol>
                </dd>
                <dt className="muted">AI 지시사항</dt>
                <dd className="whitespace-pre-wrap">{meeting.instructions || "-"}</dd>
                <dt className="muted">등록</dt>
                <dd>{formatDateTime(meeting.created_at)}</dd>
              </dl>
            </Card>
            <Card title="음성 파일">
              {meeting.audio ? (
                <dl className="grid grid-cols-[6rem_1fr] gap-y-2 text-sm">
                  <dt className="muted">파일명</dt>
                  <dd className="break-all">{meeting.audio.filename}</dd>
                  <dt className="muted">크기</dt>
                  <dd>{formatBytes(meeting.audio.size_bytes)}</dd>
                  <dt className="muted">길이</dt>
                  <dd>{formatDuration(meeting.audio.duration_seconds)}</dd>
                  <dt className="muted">형식</dt>
                  <dd>{meeting.audio.mime_type}</dd>
                </dl>
              ) : (
                <p className="muted text-sm">없음</p>
              )}
              <p className="muted mt-4 text-xs">원본 음성 파일은 삭제하기 전까지 보존됩니다.</p>
            </Card>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="회의를 삭제할까요?"
        confirmLabel="영구 삭제"
        tone="danger"
        loading={deleting}
        onConfirm={remove}
        onCancel={() => setConfirmDelete(false)}
      >
        &lsquo;{meeting.title}&rsquo;의 회의 정보, 전사문, 회의록, 문서, 발송 이력이 모두 삭제됩니다. 이 작업은 되돌릴 수 없습니다.
      </ConfirmDialog>
    </>
  );
}

export default function MeetingDetailPage() {
  return (
    <Suspense fallback={<Loading />}>
      <MeetingDetail />
    </Suspense>
  );
}
