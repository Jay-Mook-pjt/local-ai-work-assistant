"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/common/Icon";
import { Button, EmptyState, cx } from "@/components/common/ui";
import { formatTimestamp } from "@/lib/format";
import type { Transcript } from "@/types/meeting";
import { speakerColor, speakerName } from "@/components/meeting/speakers";

function parseTs(ts: string): number | null {
  const m = /^(\d{1,2}):(\d{2}):(\d{2})$/.exec(ts.trim());
  return m ? Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]) : null;
}

function highlight(text: string, q: string) {
  if (!q) return text;
  const parts = text.split(new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));
  return parts.map((p, i) =>
    p.toLowerCase() === q.toLowerCase() ? (
      <mark key={i} className="rounded bg-amber-200 px-0.5 dark:bg-amber-500/40 dark:text-white">
        {p}
      </mark>
    ) : (
      p
    ),
  );
}

export function TranscriptView({ transcript, focusTs, speakerNames }: { transcript: Transcript | null; focusTs: string | null; speakerNames?: Record<string, string> | null }) {
  const [q, setQ] = useState("");
  const [copied, setCopied] = useState(false);
  const refs = useRef<(HTMLLIElement | null)[]>([]);

  const focusIdx = useMemo(() => {
    const t = focusTs ? parseTs(focusTs) : null;
    if (t == null || !transcript) return -1;
    let best = -1;
    transcript.segments.forEach((s, i) => {
      if (s.start <= t + 1) best = i;
    });
    return best;
  }, [focusTs, transcript]);

  useEffect(() => {
    if (focusIdx >= 0) refs.current[focusIdx]?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focusIdx]);

  if (!transcript) return <EmptyState icon="audio" title="전사문이 아직 없습니다." description="음성 인식이 끝나면 여기에 표시됩니다." />;

  const visible = transcript.segments.map((s, i) => ({ s, i })).filter(({ s }) => !q || s.text.toLowerCase().includes(q.toLowerCase()));

  const copyAll = async () => {
    const text = transcript.segments.map((s) => `[${formatTimestamp(s.start)}] ${s.speaker ? `${speakerName(s.speaker, speakerNames)}: ` : ""}${s.text}`).join("\n");
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-48 flex-1">
          <Icon name="search" className="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input className="field pl-9" placeholder="전사문 검색" value={q} onChange={(e) => setQ(e.target.value)} aria-label="전사문 검색" />
        </div>
        <Button variant="secondary" icon={copied ? "check" : "file"} onClick={copyAll}>
          {copied ? "복사됨" : "전체 복사"}
        </Button>
      </div>
      <p className="muted text-xs">
        {transcript.segments.length}개 구간 · 모델 {transcript.model} · 언어 {transcript.language}
        {q && ` · 검색 결과 ${visible.length}개`}
      </p>
      <ul className="space-y-1">
        {visible.map(({ s, i }) => (
          <li
            key={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            className={cx("flex gap-3 rounded-lg px-3 py-2 text-sm leading-relaxed", i === focusIdx ? "bg-indigo-50 ring-1 ring-indigo-300 dark:bg-indigo-500/10 dark:ring-indigo-500/40" : "hover:bg-slate-50 dark:hover:bg-slate-800/50")}
          >
            <span className="w-16 shrink-0 pt-0.5 font-mono text-xs text-slate-500">{formatTimestamp(s.start)}</span>
            <span>
              {s.speaker && <span className={`mr-1.5 rounded px-1.5 py-0.5 text-xs font-medium ${speakerColor(s.speaker)}`}>{speakerName(s.speaker, speakerNames)}</span>}
              {highlight(s.text, q)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
