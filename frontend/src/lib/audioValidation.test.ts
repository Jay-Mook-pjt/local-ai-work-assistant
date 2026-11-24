import { describe, expect, it } from "vitest";
import { validateAudioFile } from "@/lib/audioValidation";

const f = (name: string, type: string, size = 1024) => ({ name, type, size });
const MB = 1024 * 1024;

describe("validateAudioFile", () => {
  it.each([
    ["meeting.mp3", "audio/mpeg"],
    ["meeting.wav", "audio/wav"],
    ["meeting.m4a", "audio/x-m4a"],
    ["meeting.M4A", "audio/mp4"],
    ["meeting.mp4", "video/mp4"],
    ["회의 녹음.m4a", ""], // browsers may report an empty MIME type
  ])("accepts %s (%s)", (name, type) => {
    expect(validateAudioFile(f(name, type)).ok).toBe(true);
  });

  it("rejects unsupported extensions", () => {
    const r = validateAudioFile(f("notes.txt", "text/plain"));
    expect(r).toEqual({ ok: false, error: expect.stringContaining("지원하지 않는 형식") });
  });

  it("rejects files without an extension", () => {
    expect(validateAudioFile(f("meeting", "audio/mpeg")).ok).toBe(false);
  });

  it("rejects a MIME type that does not match the extension", () => {
    const r = validateAudioFile(f("evil.mp3", "application/x-msdownload"));
    expect(r).toEqual({ ok: false, error: expect.stringContaining("맞지 않습니다") });
  });

  it.each(["../../etc/passwd.mp3", "a/b.mp3", "a\\b.wav"])("rejects path-like names: %s", (name) => {
    expect(validateAudioFile(f(name, "audio/mpeg")).ok).toBe(false);
  });

  it("rejects empty files", () => {
    expect(validateAudioFile(f("a.mp3", "audio/mpeg", 0)).ok).toBe(false);
  });

  it("enforces the size limit", () => {
    expect(validateAudioFile(f("a.mp3", "audio/mpeg", 10 * MB), 10).ok).toBe(true);
    expect(validateAudioFile(f("a.mp3", "audio/mpeg", 10 * MB + 1), 10)).toEqual({ ok: false, error: expect.stringContaining("10MB") });
  });
});
