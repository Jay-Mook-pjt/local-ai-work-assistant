// Low-level HTTP helpers. All calls go to /api/* on the Next.js server, which
// forwards them to the localhost-only FastAPI backend (see next.config.ts).
import type { HealthResponse } from "@/types/health";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export class NotFoundError extends ApiError {}

/** Turns FastAPI error bodies ({detail: string | [{msg, loc}]}) into a readable message. */
function errorMessage(status: number, body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => `${(d.loc ?? []).slice(1).join(".") || "입력값"}: ${d.msg ?? "형식 오류"}`)
      .join("\n");
  }
  if (status === 502 || status === 503 || status === 504) return "Backend 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.";
  return fallback || `요청 실패 (${status})`;
}

export async function request<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  let res: Response;
  try {
    res = await fetch(path, {
      cache: "no-store",
      ...rest,
      headers: json !== undefined ? { "Content-Type": "application/json", ...rest.headers } : rest.headers,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw new ApiError(0, "서버에 연결할 수 없습니다. 네트워크 또는 서버 상태를 확인하세요.");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON error page */
  }
  if (!res.ok) {
    const Err = res.status === 404 ? NotFoundError : ApiError;
    throw new Err(res.status, errorMessage(res.status, body, res.statusText));
  }
  return body as T;
}

/** multipart upload with progress (fetch has no upload progress events). */
export function uploadWithProgress<T>(path: string, form: FormData, onProgress?: (ratio: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError(0, "업로드 중 연결이 끊어졌습니다."));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T);
      else reject(new ApiError(xhr.status, errorMessage(xhr.status, body, xhr.statusText)));
    };
    xhr.send(form);
  });
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
};
