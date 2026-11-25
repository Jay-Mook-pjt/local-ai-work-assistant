"use client";

import { useMemo, useState } from "react";
import { Alert, Button } from "@/components/common/ui";
import { formatTimestamp } from "@/lib/format";
import { setSpeakerNames } from "@/services/meetings";
import type { Meeting, Transcript } from "@/types/meeting";
import { speakerColor } from "@/components/meeting/speakers";

/**
 * Lets the user name automatically separated speakers ("화자 1" → "김민수 과장").
 * Saving also updates the current minutes; later analyses receive the names.
 */
export function SpeakerPanel({ meeting, transcript, onSaved }: { meeting: Meeting; transcript: Transcript; onSaved: () => void }) {
  const stats = useMemo(() => {
    const m = new Map<string, { seconds: number; lines: { start: number; text: string }[] }>();
    for (const s of transcript.segments) {
      if (!s.speaker) continue;
      const e = m.get(s.speaker) ?? { seconds: 0, lines: [] };
      e.seconds += s.end - s.start;
      if (s.text.length > 12 && e.lines.length < 3) e.lines.push({ start: s.start, text: s.text });
      m.set(s.speaker, e);
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0], "ko", { numeric: true }));
  }, [transcript]);

  const [names, setNames] = useState<Record<string, string>>(() => ({ ...(meeting.speaker_names ?? {}) }));
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  if (!stats.length) return null;
  const changed = JSON.stringify(names) !== JSON.stringify(meeting.speaker_names ?? {});
  const listId = `attendees-${meeting.id}`;

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      await setSpeakerNames(meeting.id, Object.fromEntries(Object.entries(names).filter(([, v]) => v.trim())));
      setMsg({ ok: true, text: "화자 이름을 저장했습니다. 회의록의 화자 표기도 함께 바뀌었습니다." });
      onSaved();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <div>
        <p className="text-sm font-semibold">화자 이름 지정</p>
        <p className="muted text-xs">목소리로 자동 구분한 결과입니다. 발언을 보고 이름을 지정하세요. 같은 사람이 두 화자로 나뉘었다면 같은 이름을 넣으면 됩니다.</p>
      </div>
      <datalist id={listId}>
        {meeting.attendees.map((a) => (
          <option key={a} value={a} />
        ))}
      </datalist>
      <ul className="space-y-3">
        {stats.map(([label, st]) => (
          <li key={label} className="grid gap-2 sm:grid-cols-[9rem_1fr]">
            <div>
              <span className={`inline-block rounded-md px-2 py-0.5 text-xs font-medium ${speakerColor(label)}`}>{label}</span>
              <p className="muted mt-1 text-xs">발언 {Math.round(st.seconds / 60)}분</p>
              <input
                className="field mt-1 py-1 text-sm"
                list={listId}
                placeholder="이름 (예: 참석자)"
                value={names[label] ?? ""}
                onChange={(e) => setNames({ ...names, [label]: e.target.value })}
                aria-label={`${label} 이름`}
                maxLength={100}
              />
            </div>
            <ul className="muted space-y-1 text-xs">
              {st.lines.map((l) => (
                <li key={l.start}>
                  <span className="font-mono">{formatTimestamp(l.start)}</span> {l.text}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      {msg && <Alert tone={msg.ok ? "success" : "error"} title={msg.text} />}
      <div className="flex justify-end">
        <Button onClick={save} loading={saving} disabled={!changed}>
          화자 이름 저장
        </Button>
      </div>
    </div>
  );
}
