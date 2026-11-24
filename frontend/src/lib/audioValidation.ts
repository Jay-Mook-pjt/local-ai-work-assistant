// Client-side pre-check of audio uploads. The backend re-validates everything
// (extension, MIME, magic bytes, size) in PHASE 3 — this only gives fast feedback.

export const MAX_UPLOAD_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? 500);

export const ALLOWED_AUDIO: Record<string, string[]> = {
  mp3: ["audio/mpeg", "audio/mp3"],
  wav: ["audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"],
  m4a: ["audio/mp4", "audio/x-m4a", "audio/m4a", "audio/aac"],
  mp4: ["video/mp4", "audio/mp4"],
};

export const ACCEPT_ATTR = Object.keys(ALLOWED_AUDIO)
  .map((e) => `.${e}`)
  .join(",");

export type ValidationResult = { ok: true } | { ok: false; error: string };

export function validateAudioFile(
  file: Pick<File, "name" | "size" | "type">,
  maxMb: number = MAX_UPLOAD_MB,
): ValidationResult {
  const name = file.name.normalize("NFC");
  if (/[\\/]/.test(name) || name.includes("..")) {
    return { ok: false, error: "파일 이름에 사용할 수 없는 문자가 있습니다." };
  }
  const ext = name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
  const allowedMimes = ALLOWED_AUDIO[ext];
  if (!allowedMimes) {
    return { ok: false, error: `지원하지 않는 형식입니다. (${Object.keys(ALLOWED_AUDIO).join(", ").toUpperCase()}만 가능)` };
  }
  // Browsers sometimes report an empty type; the backend checks file content.
  if (file.type && !allowedMimes.includes(file.type.toLowerCase())) {
    return { ok: false, error: `파일 형식(${file.type})이 확장자(.${ext})와 맞지 않습니다.` };
  }
  if (file.size === 0) return { ok: false, error: "빈 파일입니다." };
  if (file.size > maxMb * 1024 * 1024) {
    return { ok: false, error: `파일 크기가 ${maxMb}MB를 초과합니다.` };
  }
  return { ok: true };
}

/** Reads the audio duration in the browser. Resolves null if the browser cannot decode it. */
export function readAudioDuration(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const el = document.createElement(file.type.startsWith("video") ? "video" : "audio");
    const done = (v: number | null) => {
      URL.revokeObjectURL(url);
      resolve(v);
    };
    el.preload = "metadata";
    el.onloadedmetadata = () => done(Number.isFinite(el.duration) ? el.duration : null);
    el.onerror = () => done(null);
    setTimeout(() => done(null), 5000);
    el.src = url;
  });
}
