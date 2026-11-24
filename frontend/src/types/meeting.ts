// Domain types shared by the UI. They mirror the backend API contract planned
// for PHASE 3 (see README "Backend API 설계").

export const JOB_STATUSES = [
  "PENDING",
  "UPLOADED",
  "PREPROCESSING",
  "TRANSCRIBING",
  "ANALYZING",
  "GENERATING",
  "COMPLETED",
  "FAILED",
] as const;
export type JobStatus = (typeof JOB_STATUSES)[number];

export const ACTION_STATUSES = ["PENDING", "IN_PROGRESS", "DONE"] as const;
export type ActionStatus = (typeof ACTION_STATUSES)[number];

/** Literal used by the AI (and the UI) for anything not stated in the meeting. */
export const UNKNOWN = "미확인";

export interface AudioFileInfo {
  filename: string;
  size_bytes: number;
  duration_seconds: number | null;
  mime_type: string;
}

export interface Job {
  id: string;
  meeting_id: string;
  status: JobStatus;
  /** 0–100 */
  progress: number;
  message: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface Meeting {
  id: string;
  title: string;
  /** YYYY-MM-DD */
  meeting_date: string;
  attendees: string[];
  purpose: string;
  agenda: string[];
  instructions: string;
  audio: AudioFileInfo | null;
  status: JobStatus;
  latest_job_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface TranscriptSegment {
  /** seconds */
  start: number;
  end: number;
  text: string;
  speaker: string | null;
}

export interface Transcript {
  meeting_id: string;
  language: string;
  model: string;
  segments: TranscriptSegment[];
  created_at: string;
}

export interface DiscussionItem {
  topic: string;
  content: string;
  speaker: string;
  /** HH:MM:SS or 미확인 */
  timestamp: string;
}

export interface Decision {
  content: string;
  /** Supporting quote from the transcript */
  evidence: string;
  timestamp: string;
}

export interface ActionItem {
  id: string;
  task: string;
  assignee: string;
  deadline: string;
  status: ActionStatus;
  evidence: string;
  timestamp: string;
}

export interface MeetingMinutes {
  meeting_id: string;
  meeting_summary: string;
  discussion_items: DiscussionItem[];
  decisions: Decision[];
  action_items: ActionItem[];
  open_issues: string[];
  next_meeting_checks: string[];
  llm_model: string;
  edited: boolean;
  updated_at: string;
}

export interface DocumentInfo {
  meeting_id: string;
  filename: string;
  size_bytes: number;
  created_at: string;
}

export interface EmailDraft {
  to: string[];
  cc: string[];
  subject: string;
  body: string;
  attach_docx: boolean;
}

export interface EmailHistoryItem {
  id: string;
  meeting_id: string;
  to: string[];
  subject: string;
  status: "SENT" | "FAILED";
  error: string | null;
  sent_at: string;
}

export interface MeetingCreateInput {
  title: string;
  meeting_date: string;
  attendees: string[];
  purpose: string;
  agenda: string[];
  instructions: string;
}

export interface MeetingFilters {
  q?: string;
  from?: string;
  to?: string;
  status?: JobStatus | "ALL";
}

/** Action item joined with its meeting, for cross-meeting views. */
export interface ActionItemWithMeeting extends ActionItem {
  meeting_id: string;
  meeting_title: string;
  meeting_date: string;
}

export interface DashboardSummary {
  total_meetings: number;
  meetings_this_month: number;
  processing: number;
  open_action_items: number;
  recent_meetings: Meeting[];
  active_jobs: (Job & { meeting_title: string })[];
  recent_documents: (DocumentInfo & { meeting_title: string })[];
  recent_action_items: ActionItemWithMeeting[];
}
