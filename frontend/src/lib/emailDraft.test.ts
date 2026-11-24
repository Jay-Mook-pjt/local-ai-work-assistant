import { describe, expect, it } from "vitest";
import { parseEmailList } from "@/lib/emailDraft";

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
