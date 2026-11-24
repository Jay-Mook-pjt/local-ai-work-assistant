import { formatDate } from "@/lib/format";
import type { EmailDraft, Meeting, MeetingMinutes } from "@/types/meeting";

/** Builds the default email subject/body from the (possibly edited) minutes. */
export function buildEmailDraft(meeting: Meeting, minutes: MeetingMinutes): EmailDraft {
  const lines: string[] = [];
  lines.push("안녕하세요.", "", `${formatDate(meeting.meeting_date)} 진행된 "${meeting.title}" 회의록을 공유드립니다.`, "");
  lines.push("■ 회의 요약", minutes.meeting_summary, "");
  if (minutes.decisions.length) {
    lines.push("■ 의사결정 사항", ...minutes.decisions.map((d, i) => `${i + 1}. ${d.content}`), "");
  }
  if (minutes.action_items.length) {
    lines.push(
      "■ 후속 업무",
      ...minutes.action_items.map((a, i) => `${i + 1}. ${a.task} — 담당: ${a.assignee} / 기한: ${a.deadline}`),
      "",
    );
  }
  if (minutes.open_issues.length) lines.push("■ 미결 사항", ...minutes.open_issues.map((x) => `- ${x}`), "");
  lines.push("자세한 내용은 첨부한 회의록을 확인해 주세요.", "", "감사합니다.");
  return {
    to: [],
    cc: [],
    subject: `[회의록] ${meeting.title} (${meeting.meeting_date})`,
    body: lines.join("\n"),
    attach_docx: true,
  };
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function parseEmailList(raw: string): { valid: string[]; invalid: string[] } {
  const items = raw
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  return { valid: items.filter((e) => EMAIL_RE.test(e)), invalid: items.filter((e) => !EMAIL_RE.test(e)) };
}
