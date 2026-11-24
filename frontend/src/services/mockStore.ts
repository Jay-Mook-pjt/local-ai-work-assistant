// PHASE 2 mock backend: keeps data in localStorage so the UI flows (create, edit,
// delete, retry) really work end-to-end in the browser. PHASE 3 replaces the
// functions in meetings.ts with fetch() calls to FastAPI; pages do not change.
import { MOCK_DB_VERSION, seedDb, type MockDb } from "@/services/mockData";
import type { Job, JobStatus, MeetingMinutes, Transcript } from "@/types/meeting";
import { UNKNOWN } from "@/types/meeting";

const KEY = "lawa.mockdb";
const SIM_KEY = "lawa.mocksim"; // job id -> simulation start (ms)

let memory: MockDb | null = null;

export function loadDb(): MockDb {
  if (memory) return memory;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as MockDb;
      if (parsed.version === MOCK_DB_VERSION) return (memory = parsed);
    }
  } catch {
    /* storage unavailable or corrupt: fall back to seed */
  }
  memory = seedDb();
  saveDb(memory);
  return memory;
}

export function saveDb(db: MockDb): void {
  memory = db;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(db));
  } catch {
    /* quota or private mode: keep in memory only */
  }
}

export function resetDb(): void {
  try {
    window.localStorage.removeItem(KEY);
    window.localStorage.removeItem(SIM_KEY);
  } catch {
    /* ignore */
  }
  memory = null;
}

function loadSims(): Record<string, number> {
  try {
    return JSON.parse(window.localStorage.getItem(SIM_KEY) ?? "{}") as Record<string, number>;
  } catch {
    return {};
  }
}

export function startSimulation(jobId: string): void {
  const sims = loadSims();
  sims[jobId] = Date.now();
  try {
    window.localStorage.setItem(SIM_KEY, JSON.stringify(sims));
  } catch {
    /* ignore */
  }
}

// Simulated pipeline: [status, seconds from start, progress at that point]
const STAGES: [JobStatus, number, number, string][] = [
  ["UPLOADED", 0, 5, "음성 파일 업로드 완료"],
  ["PREPROCESSING", 2, 10, "오디오 변환 및 구간 분할 중"],
  ["TRANSCRIBING", 5, 20, "음성 인식 중"],
  ["ANALYZING", 12, 60, "구간별 AI 분석 중"],
  ["GENERATING", 18, 85, "회의록 통합 및 검증 중"],
  ["COMPLETED", 21, 100, "회의록 생성 완료 (Mock)"],
];

/** Advances simulated jobs based on elapsed time. Returns true if anything changed. */
export function tickSimulations(db: MockDb): boolean {
  const sims = loadSims();
  let changed = false;
  for (const job of db.jobs) {
    const started = sims[job.id];
    if (started == null || job.status === "COMPLETED" || job.status === "FAILED") continue;
    const elapsed = (Date.now() - started) / 1000;
    let idx = 0;
    for (let i = 0; i < STAGES.length; i++) if (elapsed >= STAGES[i][1]) idx = i;
    const [status, t0, p0, message] = STAGES[idx];
    const next = STAGES[idx + 1];
    const progress = next ? Math.round(p0 + ((next[2] - p0) * (elapsed - t0)) / (next[1] - t0)) : 100;
    if (job.status !== status || job.progress !== progress) {
      Object.assign(job, { status, progress, message, updated_at: new Date().toISOString() });
      const meeting = db.meetings.find((m) => m.id === job.meeting_id);
      if (meeting) meeting.status = status;
      if (status === "COMPLETED") materializeMockResult(db, job);
      changed = true;
    }
  }
  return changed;
}

/** Creates clearly-labelled placeholder results for a simulated job. */
function materializeMockResult(db: MockDb, job: Job): void {
  const meeting = db.meetings.find((m) => m.id === job.meeting_id);
  if (!meeting) return;
  const now = new Date().toISOString();
  const transcript: Transcript = {
    meeting_id: meeting.id,
    language: "ko",
    model: "(Mock)",
    created_at: now,
    segments: [
      { start: 0, end: 6, speaker: null, text: "[Mock] 실제 음성 인식 결과는 PHASE 4에서 MLX Whisper로 생성됩니다." },
      { start: 6, end: 12, speaker: null, text: `[Mock] 업로드한 파일: ${meeting.audio?.filename ?? "-"}` },
    ],
  };
  const minutes: MeetingMinutes = {
    meeting_id: meeting.id,
    meeting_summary: "[Mock] 실제 회의 분석은 PHASE 4에서 Ollama로 생성됩니다. 아래 항목은 입력한 안건으로 만든 자리표시자입니다.",
    discussion_items: meeting.agenda.map((topic) => ({ topic, content: UNKNOWN, speaker: UNKNOWN, timestamp: UNKNOWN })),
    decisions: [],
    action_items: [],
    open_issues: [],
    next_meeting_checks: [],
    llm_model: "(Mock)",
    edited: false,
    updated_at: now,
  };
  db.transcripts = db.transcripts.filter((t) => t.meeting_id !== meeting.id).concat(transcript);
  db.minutes = db.minutes.filter((m) => m.meeting_id !== meeting.id).concat(minutes);
}

export { newId } from "@/lib/id";
