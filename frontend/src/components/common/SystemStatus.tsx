"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/services/api";
import type { HealthResponse } from "@/types/health";

const LABELS: Record<string, string> = {
  database: "데이터베이스 (SQLite)",
  ollama: "LLM (Ollama)",
  stt: "STT (MLX Whisper)",
};

export function SystemStatus() {
  const [data, setData] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Only sets state from promise callbacks, so it is safe to call from an effect.
  const fetchHealth = useCallback(
    () =>
      api
        .health()
        .then((d) => {
          setData(d);
          setError(null);
        })
        .catch((e: unknown) => {
          setData(null);
          setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => setLoading(false)),
    [],
  );

  useEffect(() => {
    void fetchHealth();
  }, [fetchHealth]);

  const load = () => {
    setLoading(true);
    void fetchHealth();
  };

  return (
    <section className="w-full max-w-xl rounded-xl border border-black/10 dark:border-white/15 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">시스템 상태</h2>
        <button
          onClick={load}
          disabled={loading}
          className="text-sm rounded-md border border-black/15 dark:border-white/20 px-3 py-1 hover:bg-black/5 dark:hover:bg-white/10 disabled:opacity-50"
        >
          {loading ? "확인 중…" : "다시 확인"}
        </button>
      </div>

      {error && (
        <p className="text-sm text-red-600 dark:text-red-400">
          Backend에 연결할 수 없습니다: {error}
        </p>
      )}

      {data && (
        <ul className="space-y-3">
          {Object.entries(data.components).map(([key, c]) => (
            <li key={key} className="flex items-start gap-3">
              <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${c.ok ? "bg-emerald-500" : "bg-red-500"}`} />
              <div className="text-sm">
                <div className="font-medium">{LABELS[key] ?? key}</div>
                <div className="text-black/60 dark:text-white/60">
                  {[c.version && `v${c.version}`, c.latency_ms != null && `${c.latency_ms}ms`, c.detail]
                    .filter(Boolean)
                    .join(" · ") || (c.ok ? "정상" : "오류")}
                </div>
              </div>
            </li>
          ))}
          <li className="pt-2 text-xs text-black/50 dark:text-white/50">
            LLM 모델: {data.llm_model} · 환경: {data.env}
          </li>
        </ul>
      )}
    </section>
  );
}
