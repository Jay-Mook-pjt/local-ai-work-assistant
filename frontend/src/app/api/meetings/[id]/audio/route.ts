// Streams audio uploads straight through to the backend.
//
// The generic /api/* rewrite in next.config.ts buffers request bodies in memory
// and truncates them at 10 MB, which breaks meeting recordings (often 100+ MB).
// This Route Handler takes precedence over that rewrite for this one path and
// pipes the multipart body without buffering. Validation (size, type, content)
// happens in the backend.
import { BACKEND_URL } from "@/lib/backend";

const ID = /^[0-9a-f]{32}$/;

export async function POST(request: Request, ctx: RouteContext<"/api/meetings/[id]/audio">) {
  const { id } = await ctx.params;
  if (!ID.test(id)) return Response.json({ detail: "잘못된 회의 ID입니다." }, { status: 422 });

  const contentType = request.headers.get("content-type");
  if (!contentType?.startsWith("multipart/form-data") || !request.body) {
    return Response.json({ detail: "multipart/form-data 업로드만 허용됩니다." }, { status: 415 });
  }
  const headers: Record<string, string> = { "content-type": contentType };
  const length = request.headers.get("content-length");
  if (length) headers["content-length"] = length;

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/api/meetings/${id}/audio`, {
      method: "POST",
      headers,
      body: request.body,
      // Required by Node's fetch to send a streaming request body.
      duplex: "half",
    } as RequestInit & { duplex: "half" });
  } catch {
    return Response.json({ detail: "Backend 서버에 연결할 수 없습니다." }, { status: 502 });
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
