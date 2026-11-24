"use client";

import { useState } from "react";
import { Alert, Badge, Button, Card, EmptyState, Field } from "@/components/common/ui";
import { buildEmailDraft, parseEmailList } from "@/lib/emailDraft";
import { formatBytes, formatDateTime } from "@/lib/format";
import type { DocumentInfo, EmailHistoryItem, Meeting, MeetingMinutes } from "@/types/meeting";

/**
 * DOCX export + email compose/preview. Sending requires an explicit click on
 * the final confirmation; the actual DOCX/SMTP backends arrive in PHASE 5.
 */
export function EmailPanel({
  meeting,
  minutes,
  documents,
  history,
}: {
  meeting: Meeting;
  minutes: MeetingMinutes;
  documents: DocumentInfo[];
  history: EmailHistoryItem[];
}) {
  const initial = buildEmailDraft(meeting, minutes);
  const [to, setTo] = useState("");
  const [cc, setCc] = useState("");
  const [subject, setSubject] = useState(initial.subject);
  const [body, setBody] = useState(initial.body);
  const [attach, setAttach] = useState(true);
  const [preview, setPreview] = useState(false);

  const toList = parseEmailList(to);
  const ccList = parseEmailList(cc);
  const invalid = [...toList.invalid, ...ccList.invalid];
  const canPreview = toList.valid.length > 0 && invalid.length === 0 && subject.trim() && body.trim();

  return (
    <div className="grid gap-6 xl:grid-cols-3">
      <div className="space-y-6 xl:col-span-2">
        <Card title="이메일 작성">
          {!preview ? (
            <div className="space-y-4">
              <Field label="받는 사람" required htmlFor="to" hint="쉼표로 여러 명 입력" error={toList.invalid.length ? `잘못된 주소: ${toList.invalid.join(", ")}` : undefined}>
                <input id="to" className="field" value={to} onChange={(e) => setTo(e.target.value)} placeholder="name@company.com" />
              </Field>
              <Field label="참조 (CC)" htmlFor="cc" error={ccList.invalid.length ? `잘못된 주소: ${ccList.invalid.join(", ")}` : undefined}>
                <input id="cc" className="field" value={cc} onChange={(e) => setCc(e.target.value)} />
              </Field>
              <Field label="제목" required htmlFor="subject">
                <input id="subject" className="field" value={subject} onChange={(e) => setSubject(e.target.value)} />
              </Field>
              <Field label="본문" required htmlFor="body" hint="회의록 내용으로 자동 작성되었습니다. 자유롭게 수정하세요.">
                <textarea id="body" className="field min-h-72 font-mono text-[13px]" value={body} onChange={(e) => setBody(e.target.value)} />
              </Field>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={attach} onChange={(e) => setAttach(e.target.checked)} className="h-4 w-4 accent-indigo-600" />
                회의록 DOCX 첨부
              </label>
              <div className="flex justify-between gap-2">
                <Button
                  variant="ghost"
                  onClick={() => {
                    setSubject(initial.subject);
                    setBody(initial.body);
                  }}
                >
                  자동 작성 내용으로 되돌리기
                </Button>
                <Button icon="mail" disabled={!canPreview} onClick={() => setPreview(true)}>
                  미리보기
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <dl className="grid grid-cols-[5rem_1fr] gap-y-1.5 text-sm">
                <dt className="muted">받는 사람</dt>
                <dd>{toList.valid.join(", ")}</dd>
                {ccList.valid.length > 0 && (
                  <>
                    <dt className="muted">참조</dt>
                    <dd>{ccList.valid.join(", ")}</dd>
                  </>
                )}
                <dt className="muted">제목</dt>
                <dd className="font-medium">{subject}</dd>
                <dt className="muted">첨부</dt>
                <dd>{attach ? `${meeting.meeting_date.replaceAll("-", "")}_${meeting.title}_회의록.docx` : "없음"}</dd>
              </dl>
              <pre className="max-h-96 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-4 font-sans text-sm whitespace-pre-wrap dark:border-slate-800 dark:bg-slate-800/50">{body}</pre>
              <Alert tone="warning" title="이메일 발송은 PHASE 5에서 연결됩니다.">
                SMTP 연동 후에는 이 화면에서 발송 버튼을 직접 눌렀을 때만 메일이 전송됩니다. AI가 자동으로 발송하지 않습니다.
              </Alert>
              <div className="flex justify-between gap-2">
                <Button variant="secondary" onClick={() => setPreview(false)}>
                  수정하기
                </Button>
                <Button icon="mail" disabled title="PHASE 5에서 SMTP 연동 후 활성화">
                  발송 (PHASE 5)
                </Button>
              </div>
            </div>
          )}
        </Card>
      </div>

      <div className="space-y-6">
        <Card title="회의록 문서 (DOCX)">
          {documents.length ? (
            <ul className="mb-4 space-y-2">
              {documents.map((d) => (
                <li key={d.filename} className="text-sm">
                  <p className="truncate font-medium">{d.filename}</p>
                  <p className="muted text-xs">
                    {formatDateTime(d.created_at)} · {formatBytes(d.size_bytes)}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted mb-4 text-sm">아직 생성된 문서가 없습니다.</p>
          )}
          <Button variant="secondary" icon="download" disabled className="w-full" title="PHASE 5에서 python-docx 연동 후 활성화">
            DOCX 생성·다운로드 (PHASE 5)
          </Button>
        </Card>

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
                    {formatDateTime(h.sent_at)} · {h.to.join(", ")}
                  </p>
                  {h.error && <p className="text-xs text-red-600 dark:text-red-400">{h.error}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon="mail" title="발송 이력이 없습니다." />
          )}
        </Card>
      </div>
    </div>
  );
}
