"use client";

import { useState } from "react";
import { Icon } from "@/components/common/Icon";
import { Alert, Button, ConfirmDialog, EmptyState, Loading } from "@/components/common/ui";
import { useAsync } from "@/hooks/useAsync";
import { createGlossaryTerm, deleteGlossaryTerm, listGlossary, updateGlossaryTerm } from "@/services/meetings";
import type { GlossaryTerm } from "@/types/meeting";

type Draft = { id: string | null; term: string; description: string; aliases: string };
const EMPTY: Draft = { id: null, term: "", description: "", aliases: "" };

/**
 * Project vocabulary. Terms are passed to speech recognition as spelling hints and
 * to the LLM as reference meanings for every new analysis (no model training).
 */
export function GlossaryCard() {
  const { data, error, loading, reload } = useAsync(listGlossary, []);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<GlossaryTerm | null>(null);

  if (error) return <Alert title="용어집을 불러오지 못했습니다.">{error.message}</Alert>;
  if (loading && !data) return <Loading />;

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    setFormError(null);
    const input = { term: draft.term, description: draft.description, aliases: draft.aliases.split(",").map((a) => a.trim()).filter(Boolean) };
    try {
      if (draft.id) await updateGlossaryTerm(draft.id, input);
      else await createGlossaryTerm(input);
      setDraft(null);
      reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4 text-sm">
      <p className="muted">
        업무 용어와 뜻을 등록하면 이후 회의록을 만들 때 음성 인식(표기 참고)과 AI 분석(의미 참고)에 함께 전달됩니다. 이미 만든 회의록에 반영하려면 회의 상세의 &lsquo;다시 분석&rsquo;을 쓰세요.
      </p>

      {data && data.length > 0 ? (
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
          {data.map((t) => (
            <li key={t.id} className="flex items-start gap-3 px-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{t.term}</p>
                <p className="muted text-xs">{t.description || "(설명 없음)"}</p>
                {t.aliases.length > 0 && <p className="muted mt-0.5 text-xs">음성 인식 표기: {t.aliases.join(", ")}</p>}
              </div>
              <button
                onClick={() => setDraft({ id: t.id, term: t.term, description: t.description, aliases: t.aliases.join(", ") })}
                className="rounded p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                aria-label={`${t.term} 수정`}
              >
                <Icon name="edit" className="h-4 w-4" />
              </button>
              <button onClick={() => setToDelete(t)} className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" aria-label={`${t.term} 삭제`}>
                <Icon name="trash" className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        !draft && <EmptyState icon="file" title="등록된 용어가 없습니다." />
      )}

      {draft ? (
        <div className="space-y-2 rounded-lg border border-indigo-200 p-3 dark:border-indigo-500/30">
          <input className="field" placeholder="용어 (예: RPA)" value={draft.term} onChange={(e) => setDraft({ ...draft, term: e.target.value })} maxLength={100} aria-label="용어" />
          <textarea className="field min-h-16" placeholder="뜻 (예: 서버·개발도구·수행봇으로 구성된 온프레미스 업무 자동화)" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} maxLength={1000} aria-label="뜻" />
          <input className="field" placeholder="음성 인식이 잘못 적는 표기 (쉼표로 구분, 선택)" value={draft.aliases} onChange={(e) => setDraft({ ...draft, aliases: e.target.value })} aria-label="잘못 인식되는 표기" />
          {formError && <Alert title={formError} />}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDraft(null)} disabled={saving}>
              취소
            </Button>
            <Button onClick={save} loading={saving} disabled={!draft.term.trim()}>
              {draft.id ? "수정" : "추가"}
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="secondary" icon="plus" onClick={() => setDraft(EMPTY)}>
          용어 추가
        </Button>
      )}

      <ConfirmDialog
        open={toDelete !== null}
        title="용어를 삭제할까요?"
        confirmLabel="삭제"
        tone="danger"
        onCancel={() => setToDelete(null)}
        onConfirm={async () => {
          if (toDelete) await deleteGlossaryTerm(toDelete.id);
          setToDelete(null);
          reload();
        }}
      >
        &lsquo;{toDelete?.term}&rsquo;을(를) 용어집에서 삭제합니다. 이미 만든 회의록은 바뀌지 않습니다.
      </ConfirmDialog>
    </div>
  );
}
