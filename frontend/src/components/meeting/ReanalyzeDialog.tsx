"use client";

import { useEffect, useState } from "react";
import { Alert, ConfirmDialog } from "@/components/common/ui";
import { analyzeMeeting, getSettings } from "@/services/meetings";

/**
 * Re-runs the AI analysis, optionally with another LLM, to compare models.
 * The existing transcript is reused when the audio has not changed.
 */
export function ReanalyzeDialog({
  open,
  meetingId,
  currentModel,
  edited,
  hasTranscript,
  onClose,
  onQueued,
}: {
  open: boolean;
  meetingId: string;
  currentModel: string | null;
  edited: boolean;
  hasTranscript: boolean;
  onClose: () => void;
  onQueued: () => void;
}) {
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    getSettings()
      .then((s) => {
        if (!alive) return;
        setModels(s.available_models);
        setModel(s.llm_model);
      })
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [open]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await analyzeMeeting(meetingId, { llm_model: model || undefined, overwrite_edited: confirmOverwrite });
      onQueued();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ConfirmDialog
      open={open}
      title="AI 분석 다시 실행"
      confirmLabel="다시 분석"
      tone={edited ? "danger" : "primary"}
      loading={busy}
      onCancel={onClose}
      onConfirm={() => void (edited && !confirmOverwrite ? setError("수정한 내용을 덮어쓰는 데 동의해야 합니다.") : submit())}
    >
      <div className="space-y-3 text-slate-700 dark:text-slate-300">
        <label className="block space-y-1.5">
          <span className="text-xs font-medium">LLM 모델</span>
          <select className="field" value={model} onChange={(e) => setModel(e.target.value)}>
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
                {m === currentModel ? " (현재 회의록)" : ""}
              </option>
            ))}
          </select>
        </label>
        <p className="text-xs">{hasTranscript ? "음성 인식 결과는 그대로 쓰고 AI 분석만 다시 실행합니다." : "음성 인식부터 다시 실행합니다."}</p>
        {edited && (
          <label className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
            <input type="checkbox" className="mt-0.5 h-4 w-4 accent-red-600" checked={confirmOverwrite} onChange={(e) => setConfirmOverwrite(e.target.checked)} />
            직접 수정한 회의록이 새 분석 결과로 바뀝니다. 수정 내용은 복구할 수 없습니다.
          </label>
        )}
        {error && <Alert title={error} />}
      </div>
    </ConfirmDialog>
  );
}
