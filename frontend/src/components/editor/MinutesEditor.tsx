"use client";

import { useState, type ReactNode } from "react";
import { Icon } from "@/components/common/Icon";
import { Alert, Button } from "@/components/common/ui";
import { RowListInput } from "@/components/meeting/ListInput";
import { ACTION_STATUS_LABEL } from "@/lib/format";
import { newId } from "@/lib/id";
import { ACTION_STATUSES, UNKNOWN, type ActionItem, type ActionStatus, type Decision, type DiscussionItem, type MeetingMinutes } from "@/types/meeting";

function Block({ title, children, onAdd, addLabel }: { title: string; children: ReactNode; onAdd?: () => void; addLabel?: string }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{title}</h3>
        {onAdd && (
          <button type="button" onClick={onAdd} className="inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
            <Icon name="plus" className="h-3.5 w-3.5" /> {addLabel}
          </button>
        )}
      </div>
      {children}
    </section>
  );
}

function RemoveBtn({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" aria-label="삭제">
      <Icon name="trash" className="h-4 w-4" />
    </button>
  );
}

const small = "field py-1.5 text-sm";

/** Edits a copy of the minutes; nothing is persisted until onSave. */
export function MinutesEditor({ initial, onSave, onCancel }: { initial: MeetingMinutes; onSave: (m: MeetingMinutes) => Promise<void>; onCancel: () => void }) {
  const [m, setM] = useState<MeetingMinutes>(() => structuredClone(initial));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const patch = <K extends keyof MeetingMinutes>(k: K, v: MeetingMinutes[K]) => setM((p) => ({ ...p, [k]: v }));
  const upd = <T,>(list: T[], i: number, v: Partial<T>) => list.map((x, j) => (j === i ? { ...x, ...v } : x));

  const save = async () => {
    if (!m.meeting_summary.trim()) {
      setError("회의 요약은 비워 둘 수 없습니다.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({
        ...m,
        action_items: m.action_items.filter((a) => a.task.trim()),
        decisions: m.decisions.filter((d) => d.content.trim()),
        discussion_items: m.discussion_items.filter((d) => d.topic.trim() || d.content.trim()),
        open_issues: m.open_issues.map((s) => s.trim()).filter(Boolean),
        next_meeting_checks: m.next_meeting_checks.map((s) => s.trim()).filter(Boolean),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSaving(false);
    }
  };

  return (
    <div className="space-y-7">
      <Block title="회의 요약">
        <textarea className="field min-h-28" value={m.meeting_summary} onChange={(e) => patch("meeting_summary", e.target.value)} aria-label="회의 요약" />
      </Block>

      <Block
        title="주요 논의사항"
        addLabel="논의사항 추가"
        onAdd={() => patch("discussion_items", [...m.discussion_items, { topic: "", content: "", speaker: UNKNOWN, timestamp: UNKNOWN } satisfies DiscussionItem])}
      >
        {m.discussion_items.map((d, i) => (
          <div key={i} className="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="flex gap-2">
              <input className={small} value={d.topic} placeholder="주제" onChange={(e) => patch("discussion_items", upd(m.discussion_items, i, { topic: e.target.value }))} aria-label="주제" />
              <input className={`${small} w-32`} value={d.speaker} placeholder="발언자" onChange={(e) => patch("discussion_items", upd(m.discussion_items, i, { speaker: e.target.value }))} aria-label="발언자" />
              <input className={`${small} w-28 font-mono`} value={d.timestamp} placeholder="00:00:00" onChange={(e) => patch("discussion_items", upd(m.discussion_items, i, { timestamp: e.target.value }))} aria-label="타임스탬프" />
              <RemoveBtn onClick={() => patch("discussion_items", m.discussion_items.filter((_, j) => j !== i))} />
            </div>
            <textarea className={`${small} min-h-16`} value={d.content} placeholder="논의 내용" onChange={(e) => patch("discussion_items", upd(m.discussion_items, i, { content: e.target.value }))} aria-label="논의 내용" />
          </div>
        ))}
      </Block>

      <Block title="의사결정 사항" addLabel="결정사항 추가" onAdd={() => patch("decisions", [...m.decisions, { content: "", evidence: "", timestamp: UNKNOWN } satisfies Decision])}>
        {m.decisions.map((d, i) => (
          <div key={i} className="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="flex gap-2">
              <input className={small} value={d.content} placeholder="결정 내용" onChange={(e) => patch("decisions", upd(m.decisions, i, { content: e.target.value }))} aria-label="결정 내용" />
              <input className={`${small} w-28 font-mono`} value={d.timestamp} onChange={(e) => patch("decisions", upd(m.decisions, i, { timestamp: e.target.value }))} aria-label="타임스탬프" />
              <RemoveBtn onClick={() => patch("decisions", m.decisions.filter((_, j) => j !== i))} />
            </div>
            <input className={`${small} text-xs`} value={d.evidence} placeholder="근거 발언 (전사문 인용)" onChange={(e) => patch("decisions", upd(m.decisions, i, { evidence: e.target.value }))} aria-label="근거 발언" />
          </div>
        ))}
      </Block>

      <Block
        title="담당자별 후속 업무"
        addLabel="업무 추가"
        onAdd={() =>
          patch("action_items", [...m.action_items, { id: newId("a"), task: "", assignee: UNKNOWN, deadline: UNKNOWN, status: "PENDING", evidence: "", timestamp: UNKNOWN } satisfies ActionItem])
        }
      >
        {m.action_items.map((a, i) => (
          <div key={a.id} className="space-y-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <div className="flex gap-2">
              <input className={small} value={a.task} placeholder="업무 내용" onChange={(e) => patch("action_items", upd(m.action_items, i, { task: e.target.value }))} aria-label="업무 내용" />
              <RemoveBtn onClick={() => patch("action_items", m.action_items.filter((_, j) => j !== i))} />
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              <input className={small} value={a.assignee} placeholder="담당자" onChange={(e) => patch("action_items", upd(m.action_items, i, { assignee: e.target.value }))} aria-label="담당자" />
              <input className={small} value={a.deadline} placeholder="기한" onChange={(e) => patch("action_items", upd(m.action_items, i, { deadline: e.target.value }))} aria-label="기한" />
              <select className={small} value={a.status} onChange={(e) => patch("action_items", upd(m.action_items, i, { status: e.target.value as ActionStatus }))} aria-label="상태">
                {ACTION_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {ACTION_STATUS_LABEL[s]}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ))}
      </Block>

      <Block title="미결 사항">
        <RowListInput value={m.open_issues} onChange={(v) => patch("open_issues", v)} numbered={false} addLabel="미결 사항 추가" />
      </Block>

      <Block title="다음 회의 확인사항">
        <RowListInput value={m.next_meeting_checks} onChange={(v) => patch("next_meeting_checks", v)} numbered={false} addLabel="확인사항 추가" />
      </Block>

      <p className="muted text-xs">확인되지 않은 담당자·기한은 &lsquo;{UNKNOWN}&rsquo;로 남겨 두세요.</p>
      {error && <Alert title="저장하지 못했습니다.">{error}</Alert>}
      <div className="sticky bottom-0 -mx-5 -mb-5 flex justify-end gap-2 border-t border-slate-200 bg-white/90 px-5 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90">
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          취소
        </Button>
        <Button icon="check" onClick={save} loading={saving}>
          저장
        </Button>
      </div>
    </div>
  );
}
