"use client";

import { useState, type KeyboardEvent } from "react";
import { Icon } from "@/components/common/Icon";

/** Chip-style input: Enter or comma adds an item. Used for attendees. */
export function ChipInput({ id, value, onChange, placeholder }: { id?: string; value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [draft, setDraft] = useState("");
  const commit = () => {
    const items = draft
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s && !value.includes(s));
    if (items.length) onChange([...value, ...items]);
    setDraft("");
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return; // Korean IME: wait for composition end
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };
  return (
    <div className="field flex flex-wrap items-center gap-1.5 py-1.5">
      {value.map((v) => (
        <span key={v} className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-2 py-0.5 text-sm text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300">
          {v}
          <button type="button" onClick={() => onChange(value.filter((x) => x !== v))} aria-label={`${v} 삭제`} className="hover:text-indigo-900 dark:hover:text-white">
            <Icon name="x" className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKey}
        onBlur={commit}
        placeholder={value.length ? "" : placeholder}
        className="min-w-[8rem] flex-1 bg-transparent py-0.5 text-sm outline-none placeholder:text-slate-400"
      />
    </div>
  );
}

/** Ordered, editable list of text rows. Used for the meeting agenda and minutes lists. */
export function RowListInput({
  value,
  onChange,
  placeholder,
  addLabel = "항목 추가",
  numbered = true,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  addLabel?: string;
  numbered?: boolean;
}) {
  const set = (i: number, v: string) => onChange(value.map((x, j) => (j === i ? v : x)));
  const move = (i: number, d: -1 | 1) => {
    const j = i + d;
    if (j < 0 || j >= value.length) return;
    const next = [...value];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };
  return (
    <div className="space-y-2">
      {value.map((v, i) => (
        <div key={i} className="flex items-center gap-2">
          {numbered && <span className="muted w-5 text-right text-sm tabular-nums">{i + 1}.</span>}
          <input className="field" value={v} onChange={(e) => set(i, e.target.value)} placeholder={placeholder} aria-label={`${i + 1}번 항목`} />
          <div className="flex shrink-0">
            <button type="button" onClick={() => move(i, -1)} disabled={i === 0} className="rounded p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:hover:bg-slate-800" aria-label="위로">
              ↑
            </button>
            <button type="button" onClick={() => move(i, 1)} disabled={i === value.length - 1} className="rounded p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:hover:bg-slate-800" aria-label="아래로">
              ↓
            </button>
            <button type="button" onClick={() => onChange(value.filter((_, j) => j !== i))} className="rounded p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" aria-label="삭제">
              <Icon name="trash" className="h-4 w-4" />
            </button>
          </div>
        </div>
      ))}
      <button type="button" onClick={() => onChange([...value, ""])} className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400">
        <Icon name="plus" className="h-4 w-4" /> {addLabel}
      </button>
    </div>
  );
}
