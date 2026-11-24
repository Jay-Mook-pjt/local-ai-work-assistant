// Meeting data access used by every page. PHASE 2: backed by mockStore.
// PHASE 3: same signatures, implemented with fetch() against /api/*.
import { loadDb, newId, resetDb, saveDb, startSimulation, tickSimulations } from "@/services/mockStore";
import type {
  ActionItem,
  ActionItemWithMeeting,
  ActionStatus,
  AudioFileInfo,
  DashboardSummary,
  DocumentInfo,
  EmailHistoryItem,
  Job,
  Meeting,
  MeetingCreateInput,
  MeetingFilters,
  MeetingMinutes,
  Transcript,
} from "@/types/meeting";
import { isProcessing } from "@/lib/format";

export const USING_MOCK = true;

const delay = (ms = 120) => new Promise((r) => setTimeout(r, ms));
const clone = <T,>(v: T): T => structuredClone(v);

async function db() {
  await delay();
  const d = loadDb();
  if (tickSimulations(d)) saveDb(d);
  return d;
}

export class NotFoundError extends Error {}

export async function getDashboard(): Promise<DashboardSummary> {
  const d = await db();
  const now = new Date();
  const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const byRecent = [...d.meetings].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const titleOf = (id: string) => d.meetings.find((m) => m.id === id)?.title ?? "-";
  const actions = allActionItems(d.meetings, d.minutes);
  return clone({
    total_meetings: d.meetings.length,
    meetings_this_month: d.meetings.filter((m) => m.meeting_date.startsWith(ym)).length,
    processing: d.meetings.filter((m) => isProcessing(m.status)).length,
    open_action_items: actions.filter((a) => a.status !== "DONE").length,
    recent_meetings: byRecent.slice(0, 5),
    active_jobs: d.jobs
      .filter((j) => isProcessing(j.status) || j.status === "FAILED")
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .slice(0, 5)
      .map((j) => ({ ...j, meeting_title: titleOf(j.meeting_id) })),
    recent_documents: [...d.documents]
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, 5)
      .map((doc) => ({ ...doc, meeting_title: titleOf(doc.meeting_id) })),
    recent_action_items: actions.filter((a) => a.status !== "DONE").slice(0, 6),
  });
}

export async function listMeetings(filters: MeetingFilters = {}): Promise<Meeting[]> {
  const d = await db();
  const q = filters.q?.trim().toLowerCase();
  return clone(
    d.meetings
      .filter((m) => {
        if (filters.status && filters.status !== "ALL" && m.status !== filters.status) return false;
        if (filters.from && m.meeting_date < filters.from) return false;
        if (filters.to && m.meeting_date > filters.to) return false;
        if (!q) return true;
        const minutes = d.minutes.find((x) => x.meeting_id === m.id);
        const transcript = d.transcripts.find((x) => x.meeting_id === m.id);
        const haystack = [
          m.title,
          m.purpose,
          m.attendees.join(" "),
          m.agenda.join(" "),
          minutes ? JSON.stringify(minutes) : "",
          transcript ? transcript.segments.map((s) => s.text).join(" ") : "",
        ]
          .join(" ")
          .toLowerCase();
        return haystack.includes(q);
      })
      .sort((a, b) => b.meeting_date.localeCompare(a.meeting_date) || b.created_at.localeCompare(a.created_at)),
  );
}

export async function getMeeting(id: string): Promise<Meeting> {
  const m = (await db()).meetings.find((x) => x.id === id);
  if (!m) throw new NotFoundError("회의를 찾을 수 없습니다.");
  return clone(m);
}

export async function createMeeting(input: MeetingCreateInput, audio: AudioFileInfo): Promise<{ meeting: Meeting; job: Job }> {
  const d = await db();
  const now = new Date().toISOString();
  const meeting: Meeting = {
    ...input,
    id: newId("m"),
    audio,
    status: "UPLOADED",
    latest_job_id: null,
    created_at: now,
    updated_at: now,
  };
  const job: Job = {
    id: newId("j"),
    meeting_id: meeting.id,
    status: "UPLOADED",
    progress: 5,
    message: "음성 파일 업로드 완료",
    error: null,
    created_at: now,
    updated_at: now,
  };
  meeting.latest_job_id = job.id;
  d.meetings.push(meeting);
  d.jobs.push(job);
  saveDb(d);
  startSimulation(job.id);
  return clone({ meeting, job });
}

export async function getJob(id: string): Promise<Job> {
  const j = (await db()).jobs.find((x) => x.id === id);
  if (!j) throw new NotFoundError("작업을 찾을 수 없습니다.");
  return clone(j);
}

export async function retryAnalysis(meetingId: string): Promise<Job> {
  const d = await db();
  const meeting = d.meetings.find((m) => m.id === meetingId);
  if (!meeting) throw new NotFoundError("회의를 찾을 수 없습니다.");
  const now = new Date().toISOString();
  const job: Job = { id: newId("j"), meeting_id: meetingId, status: "UPLOADED", progress: 5, message: "재시도 대기", error: null, created_at: now, updated_at: now };
  d.jobs.push(job);
  Object.assign(meeting, { status: job.status, latest_job_id: job.id, updated_at: now });
  saveDb(d);
  startSimulation(job.id);
  return clone(job);
}

export async function getTranscript(meetingId: string): Promise<Transcript | null> {
  return clone((await db()).transcripts.find((t) => t.meeting_id === meetingId) ?? null);
}

export async function getMinutes(meetingId: string): Promise<MeetingMinutes | null> {
  return clone((await db()).minutes.find((m) => m.meeting_id === meetingId) ?? null);
}

export async function updateMinutes(meetingId: string, minutes: MeetingMinutes): Promise<MeetingMinutes> {
  const d = await db();
  const saved: MeetingMinutes = { ...minutes, meeting_id: meetingId, edited: true, updated_at: new Date().toISOString() };
  d.minutes = d.minutes.filter((m) => m.meeting_id !== meetingId).concat(saved);
  saveDb(d);
  return clone(saved);
}

export async function updateActionItemStatus(meetingId: string, itemId: string, status: ActionStatus): Promise<void> {
  const d = await db();
  const item = d.minutes.find((m) => m.meeting_id === meetingId)?.action_items.find((a) => a.id === itemId);
  if (!item) throw new NotFoundError("후속 업무를 찾을 수 없습니다.");
  item.status = status;
  saveDb(d);
}

export async function listActionItems(): Promise<ActionItemWithMeeting[]> {
  const d = await db();
  return clone(allActionItems(d.meetings, d.minutes));
}

export async function listDocuments(meetingId?: string): Promise<DocumentInfo[]> {
  const d = await db();
  return clone(d.documents.filter((x) => !meetingId || x.meeting_id === meetingId).sort((a, b) => b.created_at.localeCompare(a.created_at)));
}

export async function listEmailHistory(meetingId?: string): Promise<EmailHistoryItem[]> {
  const d = await db();
  return clone(d.emails.filter((x) => !meetingId || x.meeting_id === meetingId).sort((a, b) => b.sent_at.localeCompare(a.sent_at)));
}

export async function deleteMeeting(meetingId: string): Promise<void> {
  const d = await db();
  const jobIds = new Set(d.jobs.filter((j) => j.meeting_id === meetingId).map((j) => j.id));
  d.meetings = d.meetings.filter((m) => m.id !== meetingId);
  d.jobs = d.jobs.filter((j) => !jobIds.has(j.id));
  d.transcripts = d.transcripts.filter((t) => t.meeting_id !== meetingId);
  d.minutes = d.minutes.filter((m) => m.meeting_id !== meetingId);
  d.documents = d.documents.filter((x) => x.meeting_id !== meetingId);
  d.emails = d.emails.filter((x) => x.meeting_id !== meetingId);
  saveDb(d);
}

export async function resetMockData(): Promise<void> {
  resetDb();
  await db();
}

function allActionItems(meetings: Meeting[], minutes: MeetingMinutes[]): ActionItemWithMeeting[] {
  const rank: Record<ActionItem["status"], number> = { IN_PROGRESS: 0, PENDING: 1, DONE: 2 };
  return minutes
    .flatMap((mn) => {
      const m = meetings.find((x) => x.id === mn.meeting_id);
      if (!m) return [];
      return mn.action_items.map((a) => ({ ...a, meeting_id: m.id, meeting_title: m.title, meeting_date: m.meeting_date }));
    })
    .sort((a, b) => rank[a.status] - rank[b.status] || b.meeting_date.localeCompare(a.meeting_date));
}
