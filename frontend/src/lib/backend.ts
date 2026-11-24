// Server-side only: where the Next.js server reaches the localhost-only FastAPI backend.
export const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
