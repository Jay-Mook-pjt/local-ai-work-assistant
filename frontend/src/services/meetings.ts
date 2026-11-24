// Meeting data access used by every page, backed by the FastAPI backend.
import { NotFoundError, request, uploadWithProgress } from "@/services/api";
import type {
  ActionItemWithMeeting,
  ActionStatus,
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

export { NotFoundError };

const enc = encodeURIComponent;

export const getDashboard = () => request<DashboardSummary>("/api/dashboard");

export function listMeetings(filters: MeetingFilters = {}): Promise<Meeting[]> {
  const p = new URLSearchParams();
  if (filters.q?.trim()) p.set("q", filters.q.trim());
  if (filters.from) p.set("from", filters.from);
  if (filters.to) p.set("to", filters.to);
  if (filters.status && filters.status !== "ALL") p.set("status", filters.status);
  const qs = p.toString();
  return request<Meeting[]>(`/api/meetings${qs ? `?${qs}` : ""}`);
}

export const getMeeting = (id: string) => request<Meeting>(`/api/meetings/${enc(id)}`);

export type CreateStep = "creating" | "uploading" | "queueing";

/**
 * Registers the meeting, uploads the audio (with progress) and queues analysis.
 * If the upload fails the half-created meeting is removed again.
 */
export async function createMeeting(
  input: MeetingCreateInput,
  file: File,
  onProgress?: (step: CreateStep, ratio?: number) => void,
): Promise<{ meeting: Meeting; job: Job }> {
  onProgress?.("creating");
  const meeting = await request<Meeting>("/api/meetings", { method: "POST", json: input });
  try {
    onProgress?.("uploading", 0);
    const form = new FormData();
    form.append("file", file, file.name.normalize("NFC"));
    await uploadWithProgress<Meeting>(`/api/meetings/${enc(meeting.id)}/audio`, form, (r) => onProgress?.("uploading", r));
  } catch (e) {
    await request(`/api/meetings/${enc(meeting.id)}`, { method: "DELETE" }).catch(() => undefined);
    throw e;
  }
  onProgress?.("queueing");
  const job = await request<Job>(`/api/meetings/${enc(meeting.id)}/analyze`, { method: "POST" });
  return { meeting, job };
}

export const getJob = (id: string) => request<Job>(`/api/jobs/${enc(id)}`);

/** Re-queues the pipeline (after a failure). */
export const retryAnalysis = (meetingId: string) => request<Job>(`/api/meetings/${enc(meetingId)}/analyze`, { method: "POST" });

export const getTranscript = (meetingId: string) => request<Transcript | null>(`/api/meetings/${enc(meetingId)}/transcript`);

export const getMinutes = (meetingId: string) => request<MeetingMinutes | null>(`/api/meetings/${enc(meetingId)}/minutes`);

export function updateMinutes(meetingId: string, m: MeetingMinutes): Promise<MeetingMinutes> {
  const body = {
    meeting_summary: m.meeting_summary,
    discussion_items: m.discussion_items,
    decisions: m.decisions,
    action_items: m.action_items,
    open_issues: m.open_issues,
    next_meeting_checks: m.next_meeting_checks,
  };
  return request<MeetingMinutes>(`/api/meetings/${enc(meetingId)}/minutes`, { method: "PUT", json: body });
}

export async function updateActionItemStatus(meetingId: string, itemId: string, status: ActionStatus): Promise<void> {
  await request(`/api/meetings/${enc(meetingId)}/action-items/${enc(itemId)}`, { method: "PATCH", json: { status } });
}

export const listActionItems = () => request<ActionItemWithMeeting[]>("/api/action-items");

export const listDocuments = (meetingId: string) => request<DocumentInfo[]>(`/api/meetings/${enc(meetingId)}/documents`);

export const listEmailHistory = (meetingId?: string) =>
  request<EmailHistoryItem[]>(meetingId ? `/api/meetings/${enc(meetingId)}/emails` : "/api/emails");

export async function deleteMeeting(meetingId: string): Promise<void> {
  await request(`/api/meetings/${enc(meetingId)}`, { method: "DELETE" });
}
