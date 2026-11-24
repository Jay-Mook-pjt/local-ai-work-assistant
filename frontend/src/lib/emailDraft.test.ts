import { describe, expect, it } from "vitest";
import { buildEmailDraft, parseEmailList } from "@/lib/emailDraft";
import type { Meeting, MeetingMinutes } from "@/types/meeting";

describe("buildEmailDraft", () => {
  const meeting: Meeting = {
    id: "m1",
    title: "DB생명 방카슈랑스 테스트 자동화 회의",
    meeting_date: "2026-11-20",
    attendees: ["김민수", "이지은"],
    purpose: "점검",
    agenda: ["상품설명서 검증"],
    instructions: "",
    audio: null,
    status: "COMPLETED",
    latest_job_id: null,
    created_at: "2026-11-20T06:00:00Z",
    updated_at: "2026-11-20T06:00:00Z",
  };
  const minutes: MeetingMinutes = {
    meeting_id: "m1",
    meeting_summary: "12종 중 9종 검증 완료.",
    discussion_items: [],
    decisions: [{ content: "12월 둘째 주 적용 확정", evidence: "", timestamp: "00:30:20" }],
    action_items: [
      { id: "a1", task: "오류 재검증", assignee: "이지은", deadline: "금요일", status: "IN_PROGRESS", evidence: "", timestamp: "00:15:35" },
      { id: "a2", task: "최종본 요청", assignee: "미확인", deadline: "미확인", status: "PENDING", evidence: "", timestamp: "미확인" },
    ],
    open_issues: ["테스트 서버 증설 여부"],
    next_meeting_checks: [],
    llm_model: "qwen3:14b",
    edited: false,
    updated_at: "2026-11-20T06:00:00Z",
  };

  it("creates subject from title and date", () => {
    expect(buildEmailDraft(meeting, minutes).subject).toBe(`[회의록] ${meeting.title} (${meeting.meeting_date})`);
  });

  it("includes summary, decisions, action items with assignee/deadline, and open issues", () => {
    const { body } = buildEmailDraft(meeting, minutes);
    expect(body).toContain(minutes.meeting_summary);
    expect(body).toContain("■ 의사결정 사항");
    for (const a of minutes.action_items) expect(body).toContain(`${a.task} — 담당: ${a.assignee} / 기한: ${a.deadline}`);
    expect(body).toContain("■ 미결 사항");
  });

  it("omits empty sections", () => {
    const { body } = buildEmailDraft(meeting, { ...minutes, decisions: [], action_items: [], open_issues: [] });
    expect(body).not.toContain("■ 의사결정 사항");
    expect(body).not.toContain("■ 후속 업무");
    expect(body).not.toContain("■ 미결 사항");
  });

  it("never pre-fills recipients", () => {
    const d = buildEmailDraft(meeting, minutes);
    expect(d.to).toEqual([]);
    expect(d.cc).toEqual([]);
  });
});

describe("parseEmailList", () => {
  it("splits on commas, semicolons and whitespace", () => {
    expect(parseEmailList("a@x.com, b@y.co.kr; c@z.io\nd@w.net").valid).toEqual(["a@x.com", "b@y.co.kr", "c@z.io", "d@w.net"]);
  });

  it("reports invalid addresses", () => {
    expect(parseEmailList("ok@x.com, nope, also@bad")).toEqual({ valid: ["ok@x.com"], invalid: ["nope", "also@bad"] });
  });

  it("handles empty input", () => {
    expect(parseEmailList("  ")).toEqual({ valid: [], invalid: [] });
  });
});
