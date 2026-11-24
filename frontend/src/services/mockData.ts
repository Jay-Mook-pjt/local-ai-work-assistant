// Seed data for PHASE 2 (UI with mock data). Removed once PHASE 3 wires the real API.
import type {
  DocumentInfo,
  EmailHistoryItem,
  Job,
  Meeting,
  MeetingMinutes,
  Transcript,
} from "@/types/meeting";

export interface MockDb {
  version: number;
  meetings: Meeting[];
  jobs: Job[];
  transcripts: Transcript[];
  minutes: MeetingMinutes[];
  documents: DocumentInfo[];
  emails: EmailHistoryItem[];
}

export const MOCK_DB_VERSION = 1;

const ts = (d: string, t = "10:00:00") => `${d}T${t}+09:00`;

export function seedDb(): MockDb {
  const meetings: Meeting[] = [
    {
      id: "m-1001",
      title: "DB생명 방카슈랑스 테스트 자동화 회의",
      meeting_date: "2026-11-20",
      attendees: ["김민수 과장", "이지은 대리", "박정우 책임"],
      purpose: "방카슈랑스 상품 테스트 자동화 진행 현황 점검 및 일정 확정",
      agenda: ["상품설명서 검증 진행사항", "CheckMATE 테스트 오류 조치", "향후 테스트 자동화 일정"],
      instructions:
        "담당자별 업무와 후속 조치를 중심으로 정리해 줘. 결정사항과 단순 논의사항을 구분하고, 다음 회의에서 확인해야 할 내용도 별도로 작성해 줘.",
      audio: { filename: "20261120_방카테스트회의.m4a", size_bytes: 48_300_000, duration_seconds: 3125, mime_type: "audio/mp4" },
      status: "COMPLETED",
      latest_job_id: "j-1001",
      created_at: ts("2026-11-20", "15:10:00"),
      updated_at: ts("2026-11-20", "15:31:00"),
    },
    {
      id: "m-1002",
      title: "주간 개발 진행 점검",
      meeting_date: "2026-11-18",
      attendees: ["홍길동", "최윤아", "한도현"],
      purpose: "주간 개발 이슈 공유",
      agenda: ["지난주 완료 업무", "이번 주 계획", "이슈 및 리스크"],
      instructions: "",
      audio: { filename: "weekly_1118.mp3", size_bytes: 21_700_000, duration_seconds: 1810, mime_type: "audio/mpeg" },
      status: "COMPLETED",
      latest_job_id: "j-1002",
      created_at: ts("2026-11-18", "11:02:00"),
      updated_at: ts("2026-11-18", "11:20:00"),
    },
    {
      id: "m-1003",
      title: "고객사 요구사항 인터뷰",
      meeting_date: "2026-11-23",
      attendees: ["홍길동", "고객사 담당자"],
      purpose: "신규 요구사항 수집",
      agenda: ["현행 업무 프로세스", "개선 요구사항"],
      instructions: "요구사항을 기능/비기능으로 나눠 정리해 줘.",
      audio: { filename: "interview_1123.wav", size_bytes: 152_000_000, duration_seconds: 2760, mime_type: "audio/wav" },
      status: "TRANSCRIBING",
      latest_job_id: "j-1003",
      created_at: ts("2026-11-23", "16:40:00"),
      updated_at: ts("2026-11-23", "16:44:00"),
    },
    {
      id: "m-1004",
      title: "인프라 점검 회의",
      meeting_date: "2026-11-12",
      attendees: ["한도현", "서버 운영팀"],
      purpose: "분기 인프라 점검 결과 공유",
      agenda: ["서버 자원 사용률", "백업 정책"],
      instructions: "",
      audio: { filename: "infra_1112.m4a", size_bytes: 9_800_000, duration_seconds: 940, mime_type: "audio/mp4" },
      status: "FAILED",
      latest_job_id: "j-1004",
      created_at: ts("2026-11-12", "14:00:00"),
      updated_at: ts("2026-11-12", "14:03:00"),
    },
  ];

  const jobs: Job[] = [
    { id: "j-1001", meeting_id: "m-1001", status: "COMPLETED", progress: 100, message: "회의록 생성 완료", error: null, created_at: ts("2026-11-20", "15:10:00"), updated_at: ts("2026-11-20", "15:31:00") },
    { id: "j-1002", meeting_id: "m-1002", status: "COMPLETED", progress: 100, message: "회의록 생성 완료", error: null, created_at: ts("2026-11-18", "11:02:00"), updated_at: ts("2026-11-18", "11:20:00") },
    { id: "j-1003", meeting_id: "m-1003", status: "TRANSCRIBING", progress: 38, message: "음성 인식 중 (3/8 구간)", error: null, created_at: ts("2026-11-23", "16:40:00"), updated_at: ts("2026-11-23", "16:44:00") },
    { id: "j-1004", meeting_id: "m-1004", status: "FAILED", progress: 12, message: null, error: "ffmpeg 변환 실패: 손상된 오디오 스트림 (예시 오류)", created_at: ts("2026-11-12", "14:00:00"), updated_at: ts("2026-11-12", "14:03:00") },
  ];

  const transcripts: Transcript[] = [
    {
      meeting_id: "m-1001",
      language: "ko",
      model: "mlx-community/whisper-large-v3-turbo",
      created_at: ts("2026-11-20", "15:22:00"),
      segments: [
        { start: 3, end: 11.5, speaker: null, text: "네, 그럼 방카슈랑스 테스트 자동화 회의 시작하겠습니다. 오늘 안건은 세 가지입니다." },
        { start: 12, end: 24.2, speaker: null, text: "먼저 상품설명서 검증 진행사항부터 보겠습니다. 현재 열두 개 상품 중에 아홉 개 검증이 끝났습니다." },
        { start: 25, end: 38.4, speaker: null, text: "남은 세 개는 약관 변경이 있어서 고객사에서 최종본을 받아야 진행할 수 있을 것 같습니다." },
        { start: 920, end: 934, speaker: null, text: "CheckMATE 쪽 오류는 대부분 날짜 형식 변환 문제였고 수정 패치는 적용했습니다." },
        { start: 935, end: 951.3, speaker: null, text: "이지은 대리님이 이번 주 금요일까지 오류 항목 재검증을 해주시기로 하죠." },
        { start: 952, end: 960, speaker: null, text: "네, 금요일까지 재검증하고 결과 공유드리겠습니다." },
        { start: 1820, end: 1836, speaker: null, text: "자동화 일정은 12월 둘째 주까지 전 상품 적용하는 걸 목표로 하겠습니다. 이건 확정으로 하겠습니다." },
        { start: 1837, end: 1850, speaker: null, text: "다만 테스트 서버 증설 여부는 아직 결정이 안 돼서 다음 회의에서 다시 이야기하죠." },
      ],
    },
    {
      meeting_id: "m-1002",
      language: "ko",
      model: "mlx-community/whisper-large-v3-turbo",
      created_at: ts("2026-11-18", "11:15:00"),
      segments: [
        { start: 5, end: 15, speaker: null, text: "지난주에는 로그인 모듈 리팩터링을 마쳤습니다." },
        { start: 16, end: 30, speaker: null, text: "이번 주에는 알림 기능 API 설계를 진행할 예정입니다. 담당은 최윤아 님입니다." },
        { start: 31, end: 44, speaker: null, text: "배포 파이프라인이 가끔 실패하는 문제가 있는데 원인은 아직 모릅니다." },
      ],
    },
  ];

  const minutes: MeetingMinutes[] = [
    {
      meeting_id: "m-1001",
      meeting_summary:
        "방카슈랑스 상품 12종 중 9종의 상품설명서 검증이 완료되었고, 나머지 3종은 약관 변경으로 고객사 최종본 수령 후 진행하기로 했다. CheckMATE 오류는 주로 날짜 형식 변환 문제로 패치가 적용되었으며, 12월 둘째 주까지 전 상품 자동화 적용을 목표로 확정했다.",
      discussion_items: [
        { topic: "상품설명서 검증 진행사항", content: "12개 상품 중 9개 검증 완료. 3개는 약관 변경으로 고객사 최종본 필요.", speaker: "미확인", timestamp: "00:00:12" },
        { topic: "CheckMATE 테스트 오류 조치", content: "오류 대부분이 날짜 형식 변환 문제였으며 수정 패치 적용 완료.", speaker: "미확인", timestamp: "00:15:20" },
        { topic: "향후 테스트 자동화 일정", content: "12월 둘째 주까지 전 상품 적용 목표. 테스트 서버 증설은 미결.", speaker: "미확인", timestamp: "00:30:20" },
      ],
      decisions: [
        { content: "12월 둘째 주까지 전 상품 테스트 자동화 적용 (확정)", evidence: "자동화 일정은 12월 둘째 주까지 전 상품 적용하는 걸 목표로 하겠습니다. 이건 확정으로 하겠습니다.", timestamp: "00:30:20" },
      ],
      action_items: [
        { id: "a-1", task: "CheckMATE 오류 항목 재검증 및 결과 공유", assignee: "이지은 대리", deadline: "이번 주 금요일 (2026-11-27 추정)", status: "IN_PROGRESS", evidence: "이지은 대리님이 이번 주 금요일까지 오류 항목 재검증을 해주시기로 하죠.", timestamp: "00:15:35" },
        { id: "a-2", task: "약관 변경 상품 3종 최종본 고객사에 요청", assignee: "미확인", deadline: "미확인", status: "PENDING", evidence: "고객사에서 최종본을 받아야 진행할 수 있을 것 같습니다.", timestamp: "00:00:25" },
      ],
      open_issues: ["테스트 서버 증설 여부 미결정"],
      next_meeting_checks: ["CheckMATE 재검증 결과", "약관 변경 상품 최종본 수령 여부", "테스트 서버 증설 결정"],
      llm_model: "qwen3:14b",
      edited: false,
      updated_at: ts("2026-11-20", "15:31:00"),
    },
    {
      meeting_id: "m-1002",
      meeting_summary: "로그인 모듈 리팩터링 완료를 공유하고, 이번 주 알림 기능 API 설계 계획을 논의했다. 배포 파이프라인 간헐적 실패 원인은 확인되지 않았다.",
      discussion_items: [
        { topic: "지난주 완료 업무", content: "로그인 모듈 리팩터링 완료", speaker: "미확인", timestamp: "00:00:05" },
        { topic: "이번 주 계획", content: "알림 기능 API 설계", speaker: "미확인", timestamp: "00:00:16" },
      ],
      decisions: [],
      action_items: [
        { id: "a-3", task: "알림 기능 API 설계", assignee: "최윤아", deadline: "미확인", status: "PENDING", evidence: "이번 주에는 알림 기능 API 설계를 진행할 예정입니다. 담당은 최윤아 님입니다.", timestamp: "00:00:16" },
      ],
      open_issues: ["배포 파이프라인 간헐적 실패 원인 미확인"],
      next_meeting_checks: ["배포 파이프라인 실패 원인 분석 결과"],
      llm_model: "qwen3:14b",
      edited: false,
      updated_at: ts("2026-11-18", "11:20:00"),
    },
  ];

  const documents: DocumentInfo[] = [
    { meeting_id: "m-1001", filename: "20261120_DB생명_방카슈랑스_테스트_자동화_회의_회의록.docx", size_bytes: 38_400, created_at: ts("2026-11-20", "15:40:00") },
    { meeting_id: "m-1002", filename: "20261118_주간_개발_진행_점검_회의록.docx", size_bytes: 24_100, created_at: ts("2026-11-18", "11:25:00") },
  ];

  const emails: EmailHistoryItem[] = [
    { id: "e-1", meeting_id: "m-1001", to: ["team@example.com"], subject: "[회의록] DB생명 방카슈랑스 테스트 자동화 회의 (2026-11-20)", status: "SENT", error: null, sent_at: ts("2026-11-20", "15:45:00") },
  ];

  return { version: MOCK_DB_VERSION, meetings, jobs, transcripts, minutes, documents, emails };
}
