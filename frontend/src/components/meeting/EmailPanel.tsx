"use client";

import { useState } from "react";
import { Icon } from "@/components/common/Icon";
import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, Field, Loading } from "@/components/common/ui";
import { useAsync } from "@/hooks/useAsync";
import { parseEmailList } from "@/lib/emailDraft";
import { formatBytes, formatDateTime } from "@/lib/format";
import {
  deleteDocument,
  documentDownloadUrl,
  exportDocx,
  getEmailDraft,
  previewEmail,
  sendEmail,
} from "@/services/meetings";
import type { DocumentInfo, EmailHistoryItem, EmailPreview, Meeting, MeetingMinutes } from "@/types/meeting";

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

function DocumentsCard({ meetingId, documents, onChanged }: { meetingId: string; documents: DocumentInfo[]; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<DocumentInfo | null>(null);
  const [deleting, setDeleting] = useState(false);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      await exportDocx(meetingId);
      onChanged();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="회의록 문서 (DOCX)">
      <Button icon="file" onClick={create} loading={busy} className="mb-4 w-full">
        현재 회의록으로 DOCX 생성
      </Button>
      {error && (
        <div className="mb-3">
          <Alert title={error} />
        </div>
      )}
      {documents.length ? (
        <ul className="space-y-2">
          {documents.map((d, i) => (
            <li key={d.id} className="flex items-center gap-2 text-sm">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium" title={d.filename}>
                  {d.filename}
                </p>
                <p className="muted text-xs">
                  {formatDateTime(d.created_at)} · {formatBytes(d.size_bytes)}
                  {i === 0 && " · 최신"}
                </p>
              </div>
              <a href={documentDownloadUrl(d.id)} download className="rounded-lg p-2 text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-500/10" title="다운로드" aria-label={`${d.filename} 다운로드`}>
                <Icon name="download" className="h-4 w-4" />
              </a>
              <button onClick={() => setToDelete(d)} className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" title="삭제" aria-label={`${d.filename} 삭제`}>
                <Icon name="trash" className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted text-sm">아직 생성된 문서가 없습니다. 회의록을 검토·수정한 뒤 생성하세요.</p>
      )}
      <ConfirmDialog
        open={toDelete !== null}
        title="문서를 삭제할까요?"
        confirmLabel="삭제"
        tone="danger"
        loading={deleting}
        onCancel={() => setToDelete(null)}
        onConfirm={async () => {
          if (!toDelete) return;
          setDeleting(true);
          try {
            await deleteDocument(toDelete.id);
            onChanged();
          } catch (e) {
            setError(errText(e));
          } finally {
            setDeleting(false);
            setToDelete(null);
          }
        }}
      >
        &lsquo;{toDelete?.filename}&rsquo; 파일이 삭제됩니다. 회의록 내용은 그대로이며 언제든 다시 생성할 수 있습니다.
      </ConfirmDialog>
    </Card>
  );
}

function HistoryCard({ history }: { history: EmailHistoryItem[] }) {
  return (
    <Card title="발송 이력">
      {history.length ? (
        <ul className="space-y-3">
          {history.map((h) => (
            <li key={h.id} className="text-sm">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate font-medium">{h.subject}</p>
                <Badge className={h.status === "SENT" ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300" : "bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300"}>
                  {h.status === "SENT" ? "발송" : "실패"}
                </Badge>
              </div>
              <p className="muted text-xs">
                {formatDateTime(h.sent_at)} · {[...h.to, ...h.cc].join(", ")}
                {h.attachment && ` · 첨부 ${h.attachment}`}
              </p>
              {h.error && <p className="text-xs text-red-600 dark:text-red-400">{h.error}</p>}
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState icon="mail" title="발송 이력이 없습니다." />
      )}
    </Card>
  );
}

/**
 * Compose → server preview → explicit confirmation → send.
 * The send request carries the preview's content hash, so the server refuses
 * anything the user did not see (e.g. minutes edited after the preview).
 */
export function EmailPanel({
  meeting,
  minutes,
  documents,
  history,
  onChanged,
}: {
  meeting: Meeting;
  minutes: MeetingMinutes;
  documents: DocumentInfo[];
  history: EmailHistoryItem[];
  onChanged: () => void;
}) {
  const draft = useAsync(() => getEmailDraft(meeting.id), [meeting.id, minutes.updated_at]);
  const [to, setTo] = useState("");
  const [cc, setCc] = useState("");
  const [subject, setSubject] = useState<string | null>(null);
  const [body, setBody] = useState<string | null>(null);
  const [attach, setAttach] = useState(true);
  const [previewState, setPreviewState] = useState<{ preview: EmailPreview; minutesVersion: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmSend, setConfirmSend] = useState(false);
  const [sent, setSent] = useState<string | null>(null);

  // A preview is only valid for the minutes version it was made from (edits elsewhere make it stale).
  const preview = previewState && previewState.minutesVersion === minutes.updated_at ? previewState.preview : null;
  const setPreview = (p: EmailPreview | null) => setPreviewState(p ? { preview: p, minutesVersion: minutes.updated_at } : null);

  if (draft.error) return <Alert title="메일 초안을 불러오지 못했습니다.">{draft.error.message}</Alert>;
  if (!draft.data) return <Loading />;
  const d = draft.data;
  const subj = subject ?? d.subject;
  const text = body ?? d.body;
  const toList = parseEmailList(to);
  const ccList = parseEmailList(cc);
  const canPreview = toList.valid.length > 0 && toList.invalid.length + ccList.invalid.length === 0 && subj.trim() !== "" && text.trim() !== "";

  const doPreview = async () => {
    setBusy(true);
    setError(null);
    setSent(null);
    try {
      setPreview(await previewEmail(meeting.id, { to: toList.valid, cc: ccList.valid, subject: subj, body: text, attach_docx: attach }));
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const doSend = async () => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const h = await sendEmail(meeting.id, preview);
      setSent(`${[...h.to, ...h.cc].length}명에게 발송했습니다.`);
      setPreview(null);
      onChanged();
    } catch (e) {
      setError(errText(e));
      onChanged(); // a failed attempt is recorded in the history too
    } finally {
      setBusy(false);
      setConfirmSend(false);
    }
  };

  return (
    <div className="grid gap-6 xl:grid-cols-3">
      <div className="space-y-6 xl:col-span-2">
        {!d.smtp_ready && (
          <Alert tone="warning" title="메일 서버(SMTP)가 아직 설정되지 않았습니다.">
            {d.smtp_problem} 작성과 미리보기는 지금도 할 수 있습니다. 설정 방법은 README의 &lsquo;이메일 발송 설정&rsquo;을 참고하세요.
          </Alert>
        )}
        {sent && <Alert tone="success" title={sent} />}
        {error && <Alert title={error} />}
        <Card title={preview ? "발송 전 확인" : "이메일 작성"}>
          {!preview ? (
            <div className="space-y-4">
              <Field label="받는 사람" required htmlFor="to" hint="쉼표로 여러 명 입력" error={toList.invalid.length ? `잘못된 주소: ${toList.invalid.join(", ")}` : undefined}>
                <input id="to" className="field" value={to} onChange={(e) => setTo(e.target.value)} placeholder="name@company.com" autoComplete="off" />
              </Field>
              <Field label="참조 (CC)" htmlFor="cc" error={ccList.invalid.length ? `잘못된 주소: ${ccList.invalid.join(", ")}` : undefined}>
                <input id="cc" className="field" value={cc} onChange={(e) => setCc(e.target.value)} autoComplete="off" />
              </Field>
              <Field label="제목" required htmlFor="subject">
                <input id="subject" className="field" value={subj} onChange={(e) => setSubject(e.target.value)} maxLength={300} />
              </Field>
              <Field label="본문" required htmlFor="body" hint="회의록 내용으로 자동 작성되었습니다. 자유롭게 수정하세요.">
                <textarea id="body" className="field min-h-72 font-mono text-[13px]" value={text} onChange={(e) => setBody(e.target.value)} />
              </Field>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={attach} onChange={(e) => setAttach(e.target.checked)} className="h-4 w-4 accent-indigo-600" />
                회의록 DOCX 첨부 (발송 시 현재 회의록으로 생성)
              </label>
              <div className="flex justify-between gap-2">
                <Button
                  variant="ghost"
                  onClick={() => {
                    setSubject(null);
                    setBody(null);
                  }}
                >
                  자동 작성 내용으로 되돌리기
                </Button>
                <Button icon="mail" disabled={!canPreview} loading={busy} onClick={doPreview}>
                  미리보기
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <dl className="grid grid-cols-[5rem_1fr] gap-y-1.5 text-sm">
                <dt className="muted">보내는 사람</dt>
                <dd>{preview.sender ?? "(미설정)"}</dd>
                <dt className="muted">받는 사람</dt>
                <dd>{preview.to.join(", ")}</dd>
                {preview.cc.length > 0 && (
                  <>
                    <dt className="muted">참조</dt>
                    <dd>{preview.cc.join(", ")}</dd>
                  </>
                )}
                <dt className="muted">제목</dt>
                <dd className="font-medium">{preview.subject}</dd>
                <dt className="muted">첨부</dt>
                <dd>{preview.attachment_name ?? "없음"}</dd>
              </dl>
              <pre className="max-h-96 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-4 font-sans text-sm whitespace-pre-wrap dark:border-slate-800 dark:bg-slate-800/50">{preview.body}</pre>
              <p className="muted text-xs">위 내용 그대로 발송됩니다. 미리보기 이후 회의록이 수정되면 발송이 거부되며 다시 확인해야 합니다.</p>
              <div className="flex justify-between gap-2">
                <Button variant="secondary" onClick={() => setPreview(null)} disabled={busy}>
                  수정하기
                </Button>
                <Button icon="mail" disabled={!preview.smtp_ready} onClick={() => setConfirmSend(true)} title={preview.smtp_ready ? undefined : preview.smtp_problem ?? undefined}>
                  발송
                </Button>
              </div>
            </div>
          )}
        </Card>
      </div>

      <div className="space-y-6">
        <DocumentsCard meetingId={meeting.id} documents={documents} onChanged={onChanged} />
        <HistoryCard history={history} />
      </div>

      <ConfirmDialog
        open={confirmSend}
        title="이메일을 발송할까요?"
        confirmLabel="발송"
        loading={busy}
        onCancel={() => setConfirmSend(false)}
        onConfirm={doSend}
      >
        {preview && (
          <>
            <strong>{[...preview.to, ...preview.cc].length}명</strong>({[...preview.to, ...preview.cc].join(", ")})에게 &lsquo;{preview.subject}&rsquo;을(를) 보냅니다
            {preview.attachment_name ? `. 첨부: ${preview.attachment_name}` : ""}. 발송한 메일은 취소할 수 없습니다.
          </>
        )}
      </ConfirmDialog>
    </div>
  );
}
