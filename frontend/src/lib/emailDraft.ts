// Client-side recipient parsing for instant feedback; the backend re-validates.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function parseEmailList(raw: string): { valid: string[]; invalid: string[] } {
  const items = raw
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  return { valid: items.filter((e) => EMAIL_RE.test(e)), invalid: items.filter((e) => !EMAIL_RE.test(e)) };
}
