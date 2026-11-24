import { describe, expect, it } from "vitest";
import { buildEmailDraft, parseEmailList } from "@/lib/emailDraft";
import { seedDb } from "@/services/mockData";

describe("buildEmailDraft", () => {
  const db = seedDb();
  const meeting = db.meetings[0];
  const minutes = db.minutes.find((m) => m.meeting_id === meeting.id)!;

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
