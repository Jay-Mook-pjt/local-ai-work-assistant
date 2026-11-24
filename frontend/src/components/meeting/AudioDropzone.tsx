"use client";

import { useRef, useState } from "react";
import { Icon } from "@/components/common/Icon";
import { cx } from "@/components/common/ui";
import { ACCEPT_ATTR, MAX_UPLOAD_MB, validateAudioFile } from "@/lib/audioValidation";
import { formatBytes, formatDuration } from "@/lib/format";

export function AudioDropzone({
  file,
  duration,
  error,
  onSelect,
  onClear,
}: {
  file: File | null;
  duration: number | null;
  error?: string;
  onSelect: (file: File, error: string | null) => void;
  onClear: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const pick = (f: File | undefined) => {
    if (!f) return;
    const v = validateAudioFile(f);
    onSelect(f, v.ok ? null : v.error);
  };

  if (file && !error) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-800/50">
        <div className="rounded-lg bg-indigo-100 p-2 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300">
          <Icon name="audio" className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{file.name}</p>
          <p className="muted text-xs">
            {formatBytes(file.size)} · 길이 {duration != null ? formatDuration(duration) : "확인 불가"}
          </p>
        </div>
        <button type="button" onClick={onClear} className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-700" aria-label="파일 제거">
          <Icon name="x" className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        pick(e.dataTransfer.files[0]);
      }}
      onClick={() => input.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
      role="button"
      tabIndex={0}
      className={cx(
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
        drag
          ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10"
          : error
            ? "border-red-300 dark:border-red-500/50"
            : "border-slate-300 hover:border-indigo-400 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800/50",
      )}
    >
      <Icon name="upload" className="h-7 w-7 text-slate-400" />
      <p className="text-sm font-medium">음성 파일을 끌어다 놓거나 클릭해서 선택</p>
      <p className="muted text-xs">MP3 · WAV · M4A · MP4 (오디오 추출) · 최대 {MAX_UPLOAD_MB}MB</p>
      <input
        ref={input}
        type="file"
        accept={ACCEPT_ATTR}
        className="hidden"
        onChange={(e) => {
          pick(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
    </div>
  );
}
