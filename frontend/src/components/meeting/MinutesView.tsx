"use client";

import type { ReactNode } from "react";
import { ActionStatusBadge, MaybeUnknown } from "@/components/common/ui";
import { formatDate } from "@/lib/format";
import type { Meeting, MeetingMinutes } from "@/types/meeting";
import { UNKNOWN } from "@/types/meeting";

function Section({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">
        {n}. {title}
      </h3>
      <div className="text-sm leading-relaxed">{children}</div>
    </section>
  );
}

function None() {
  return <p className="muted text-sm">없음</p>;
}

/** Clickable timestamp that jumps to the transcript. */
export function TimeLink({ ts, onJump }: { ts: string; onJump?: (ts: string) => void }) {
  if (!ts || ts === UNKNOWN) return <MaybeUnknown value={UNKNOWN} />;
  return (
    <button type="button" onClick={() => onJump?.(ts)} className="font-mono text-xs text-indigo-600 hover:underline dark:text-indigo-400" title="전사문에서 보기">
      {ts}
    </button>
  );
}

function Evidence({ text, ts, onJump }: { text: string; ts: string; onJump?: (ts: string) => void }) {
  if (!text) return null;
  return (
    <blockquote className="muted mt-1.5 border-l-2 border-slate-300 pl-3 text-xs dark:border-slate-700">
      &ldquo;{text}&rdquo; <TimeLink ts={ts} onJump={onJump} />
    </blockquote>
  );
}

function ReviewNotes({ notes, edited }: { notes: string[]; edited: boolean }) {
  if (!notes.length) return null;
  return (
    <details className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200" open={!edited}>
      <summary className="cursor-pointer font-medium">검토가 필요한 항목 {notes.length}개 — AI 결과를 전사문과 대조해 자동으로 표시했습니다</summary>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
        {notes.map((n, i) => (
          <li key={i}>{n}</li>
        ))}
      </ul>
    </details>
  );
}

/** Read-only minutes in the same 8-section order as the DOCX export. */
export function MinutesView({ meeting, minutes, onJump }: { meeting: Meeting; minutes: MeetingMinutes; onJump?: (ts: string) => void }) {
  return (
    <div className="space-y-7">
      <ReviewNotes notes={minutes.review_notes} edited={minutes.edited} />
      <Section n={1} title="회의 개요">
        <dl className="grid grid-cols-[5rem_1fr] gap-y-1">
          <dt className="muted">회의명</dt>
          <dd>{meeting.title}</dd>
          <dt className="muted">일시</dt>
          <dd>{formatDate(meeting.meeting_date)}</dd>
          <dt className="muted">안건</dt>
          <dd>
            <ol className="list-decimal pl-4">
              {meeting.agenda.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ol>
          </dd>
        </dl>
        <p className="mt-3 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/50">{minutes.meeting_summary}</p>
      </Section>

      <Section n={2} title="회의 목적">
        {meeting.purpose ? <p>{meeting.purpose}</p> : <None />}
      </Section>

      <Section n={3} title="참석자">
        {meeting.attendees.length ? <p>{meeting.attendees.join(", ")}</p> : <None />}
      </Section>

      <Section n={4} title="주요 논의사항">
        {minutes.discussion_items.length ? (
          <ul className="space-y-3">
            {minutes.discussion_items.map((d, i) => (
              <li key={i} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">{d.topic}</p>
                  <span className="muted text-xs">
                    발언자 <MaybeUnknown value={d.speaker} /> · <TimeLink ts={d.timestamp} onJump={onJump} />
                  </span>
                </div>
                <p className="mt-1">
                  <MaybeUnknown value={d.content} />
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <None />
        )}
      </Section>

      <Section n={5} title="의사결정 사항">
        {minutes.decisions.length ? (
          <ol className="list-decimal space-y-2 pl-5">
            {minutes.decisions.map((d, i) => (
              <li key={i}>
                {d.content}
                <Evidence text={d.evidence} ts={d.timestamp} onJump={onJump} />
              </li>
            ))}
          </ol>
        ) : (
          <None />
        )}
      </Section>

      <Section n={6} title="담당자별 후속 업무">
        {minutes.action_items.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[36rem] text-left text-sm">
              <thead className="muted border-b border-slate-200 text-xs dark:border-slate-800">
                <tr>
                  <th className="py-2 pr-3 font-medium">업무</th>
                  <th className="py-2 pr-3 font-medium">담당자</th>
                  <th className="py-2 pr-3 font-medium">기한</th>
                  <th className="py-2 font-medium">상태</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {minutes.action_items.map((a) => (
                  <tr key={a.id} className="align-top">
                    <td className="py-2.5 pr-3">
                      {a.task}
                      <Evidence text={a.evidence} ts={a.timestamp} onJump={onJump} />
                    </td>
                    <td className="py-2.5 pr-3 whitespace-nowrap">
                      <MaybeUnknown value={a.assignee} />
                    </td>
                    <td className="py-2.5 pr-3">
                      <MaybeUnknown value={a.deadline} />
                    </td>
                    <td className="py-2.5">
                      <ActionStatusBadge status={a.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <None />
        )}
      </Section>

      <Section n={7} title="미결 사항">
        {minutes.open_issues.length ? (
          <ul className="list-disc space-y-1 pl-5">
            {minutes.open_issues.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        ) : (
          <None />
        )}
      </Section>

      <Section n={8} title="다음 회의 확인사항">
        {minutes.next_meeting_checks.length ? (
          <ul className="list-disc space-y-1 pl-5">
            {minutes.next_meeting_checks.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        ) : (
          <None />
        )}
      </Section>
    </div>
  );
}
