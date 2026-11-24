"use client";

import Link from "next/link";
import { Icon } from "@/components/common/Icon";
import { JobStatusBadge } from "@/components/common/ui";
import { formatDate, formatDuration } from "@/lib/format";
import type { Meeting } from "@/types/meeting";

export function MeetingList({ meetings, compact }: { meetings: Meeting[]; compact?: boolean }) {
  return (
    <ul className="divide-y divide-slate-200 dark:divide-slate-800">
      {meetings.map((m) => (
        <li key={m.id}>
          <Link href={`/meetings/${m.id}`} className="group -mx-2 flex items-center gap-4 rounded-lg px-2 py-3 hover:bg-slate-50 dark:hover:bg-slate-800/50">
            <div className="hidden h-10 w-10 shrink-0 flex-col items-center justify-center rounded-lg bg-slate-100 text-slate-600 sm:flex dark:bg-slate-800 dark:text-slate-300">
              <span className="text-[10px] leading-none">{Number(m.meeting_date.slice(5, 7))}월</span>
              <span className="text-sm leading-tight font-semibold">{Number(m.meeting_date.slice(8, 10))}</span>
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium group-hover:text-indigo-600 dark:group-hover:text-indigo-400">{m.title}</p>
              <p className="muted mt-0.5 truncate text-xs">
                {formatDate(m.meeting_date)}
                {m.audio && ` · ${formatDuration(m.audio.duration_seconds)}`}
                {!compact && m.attendees.length > 0 && ` · ${m.attendees.join(", ")}`}
              </p>
            </div>
            <JobStatusBadge status={m.status} />
            <Icon name="chevronRight" className="h-4 w-4 shrink-0 text-slate-400" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
