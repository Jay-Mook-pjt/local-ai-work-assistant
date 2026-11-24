import { describe, expect, it } from "vitest";
import { formatBytes, formatDate, formatDuration, formatTimestamp, isProcessing } from "@/lib/format";

describe("format", () => {
  it("formatTimestamp", () => {
    expect(formatTimestamp(0)).toBe("00:00:00");
    expect(formatTimestamp(920.7)).toBe("00:15:20");
    expect(formatTimestamp(3725)).toBe("01:02:05");
    expect(formatTimestamp(-5)).toBe("00:00:00");
  });

  it("formatDuration", () => {
    expect(formatDuration(null)).toBe("-");
    expect(formatDuration(3)).toBe("3초");
    expect(formatDuration(0.2)).toBe("1초");
    expect(formatDuration(1810)).toBe("30분");
    expect(formatDuration(3725)).toBe("1시간 2분");
  });

  it("formatBytes", () => {
    expect(formatBytes(500)).toBe("500 B");
    expect(formatBytes(48_300_000)).toBe("46.1 MB");
    expect(formatBytes(1024 ** 3 * 1.5)).toBe("1.5 GB");
  });

  it("formatDate treats YYYY-MM-DD as a local date", () => {
    expect(formatDate("2026-11-20")).toBe("2026.11.20");
  });

  it("isProcessing", () => {
    expect(isProcessing("TRANSCRIBING")).toBe(true);
    expect(isProcessing("COMPLETED")).toBe(false);
    expect(isProcessing("FAILED")).toBe(false);
  });
});
