"use client";

import { useState } from "react";
import { Alert, Button, Card, ConfirmDialog, Loading, PageHeader, cx } from "@/components/common/ui";
import { SystemStatus } from "@/components/common/SystemStatus";
import { applyTheme, useThemePref, type ThemePref } from "@/components/layout/ThemeToggle";
import { useAsync } from "@/hooks/useAsync";
import { MAX_UPLOAD_MB } from "@/lib/audioValidation";
import { api } from "@/services/api";
import { resetMockData, USING_MOCK } from "@/services/meetings";

function ModelCard() {
  const { data, error, loading } = useAsync(api.health, []);
  if (error) return <Alert title="Backend에 연결할 수 없어 모델 정보를 가져오지 못했습니다.">{error.message}</Alert>;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  const installed = data.components.ollama.models ?? [];
  return (
    <div className="space-y-4 text-sm">
      <dl className="grid grid-cols-[7rem_1fr] gap-y-2">
        <dt className="muted">LLM 모델</dt>
        <dd className="font-mono">{data.llm_model}</dd>
        <dt className="muted">STT</dt>
        <dd className="font-mono break-all">{data.components.stt.detail ?? "-"}</dd>
        <dt className="muted">업로드 한도</dt>
        <dd>{MAX_UPLOAD_MB}MB</dd>
      </dl>
      <div>
        <p className="muted mb-2 text-xs">Ollama에 설치된 모델</p>
        <ul className="flex flex-wrap gap-2">
          {installed.map((m) => (
            <li
              key={m}
              className={cx(
                "rounded-md border px-2 py-1 font-mono text-xs",
                m === data.llm_model ? "border-indigo-400 bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300" : "border-slate-200 dark:border-slate-700",
              )}
            >
              {m}
              {m === data.llm_model && " (사용 중)"}
            </li>
          ))}
        </ul>
      </div>
      <p className="muted text-xs">
        모델 변경은 현재 프로젝트 루트의 <code className="font-mono">.env</code>에서 <code className="font-mono">LLM_MODEL</code>을 바꾼 뒤 Backend를 재시작하세요. 화면에서 바꾸는 기능은 PHASE 4에서 추가합니다.
      </p>
    </div>
  );
}

const THEMES: { id: ThemePref; label: string }[] = [
  { id: "light", label: "라이트" },
  { id: "dark", label: "다크" },
  { id: "system", label: "시스템 설정 따름" },
];

export default function SettingsPage() {
  const theme = useThemePref();
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetDone, setResetDone] = useState(false);

  return (
    <>
      <PageHeader title="설정" description="시스템 상태, AI 모델, 화면 설정을 확인합니다." />
      <div className="grid gap-6 xl:grid-cols-2">
        <SystemStatus />

        <Card title="AI 모델">
          <ModelCard />
        </Card>

        <Card title="화면 테마">
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="테마">
            {THEMES.map((t) => (
              <button
                key={t.id}
                role="radio"
                aria-checked={theme === t.id}
                onClick={() => applyTheme(t.id)}
                className={cx(
                  "rounded-lg border px-4 py-2 text-sm",
                  theme === t.id ? "border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300" : "border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        </Card>

        <Card title="보안 · 네트워크">
          <ul className="muted list-disc space-y-1.5 pl-5 text-sm">
            <li>외부 AI API를 사용하지 않으며, 음성과 텍스트는 이 Mac 안에서만 처리합니다.</li>
            <li>Ollama와 Backend는 127.0.0.1에서만 접속됩니다. 같은 LAN에서는 이 웹 화면(3000번 포트)만 접속할 수 있습니다.</li>
            <li>이메일은 미리보기 후 발송 버튼을 직접 눌렀을 때만 전송됩니다. SMTP 계정은 .env에서 관리합니다 (PHASE 5).</li>
          </ul>
        </Card>

        {USING_MOCK && (
          <Card title="Mock 데이터">
            <p className="muted mb-4 text-sm">PHASE 2 화면 확인용 예시 데이터는 이 브라우저에만 저장됩니다. 처음 상태로 되돌릴 수 있습니다.</p>
            {resetDone && (
              <div className="mb-4">
                <Alert tone="success" title="예시 데이터를 초기화했습니다." />
              </div>
            )}
            <Button variant="secondary" icon="refresh" onClick={() => setConfirmReset(true)}>
              예시 데이터 초기화
            </Button>
          </Card>
        )}
      </div>

      <ConfirmDialog
        open={confirmReset}
        title="예시 데이터를 초기화할까요?"
        confirmLabel="초기화"
        tone="danger"
        loading={resetting}
        onCancel={() => setConfirmReset(false)}
        onConfirm={async () => {
          setResetting(true);
          await resetMockData();
          setResetting(false);
          setConfirmReset(false);
          setResetDone(true);
        }}
      >
        이 브라우저에서 추가·수정한 Mock 회의 데이터가 모두 사라지고 처음 예시 데이터로 돌아갑니다. 실제 파일이나 DB에는 영향이 없습니다.
      </ConfirmDialog>
    </>
  );
}
