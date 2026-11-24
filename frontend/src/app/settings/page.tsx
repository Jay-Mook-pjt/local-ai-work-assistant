"use client";

import { useState } from "react";
import { Alert, Button, Card, Loading, PageHeader, cx } from "@/components/common/ui";
import { GlossaryCard } from "@/components/common/GlossaryCard";
import { SystemStatus } from "@/components/common/SystemStatus";
import { applyTheme, useThemePref, type ThemePref } from "@/components/layout/ThemeToggle";
import { useAsync } from "@/hooks/useAsync";
import { getSettings, testSmtpConnection, updateSettings } from "@/services/meetings";

function ModelCard() {
  const { data, error, loading, setData } = useAsync(getSettings, []);
  const [choice, setChoice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  if (error) return <Alert title="Backend에 연결할 수 없어 모델 정보를 가져오지 못했습니다.">{error.message}</Alert>;
  if (loading && !data) return <Loading />;
  if (!data) return null;
  const selected = choice ?? data.llm_model;

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      setData(await updateSettings(selected));
      setChoice(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4 text-sm">
      <div className="space-y-1.5">
        <label htmlFor="llm-model" className="text-xs font-medium">
          기본 LLM 모델 (새 분석에 사용)
        </label>
        <div className="flex gap-2">
          <select id="llm-model" className="field" value={selected} onChange={(e) => setChoice(e.target.value)}>
            {!data.available_models.includes(data.llm_model) && <option value={data.llm_model}>{data.llm_model} (미설치)</option>}
            {data.available_models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <Button onClick={save} loading={saving} disabled={selected === data.llm_model}>
            저장
          </Button>
        </div>
        <p className="muted text-xs">
          {data.llm_model_source === "user" ? "화면에서 선택한 모델입니다." : ".env의 LLM_MODEL 기본값입니다."} 회의 상세의 &lsquo;다시 분석&rsquo;에서 모델을 바꿔 결과를 비교할 수 있습니다.
        </p>
        {saveError && <Alert title={saveError} />}
        {saved && <Alert tone="success" title="기본 모델을 저장했습니다." />}
      </div>
      <dl className="grid grid-cols-[7rem_1fr] gap-y-2">
        <dt className="muted">STT</dt>
        <dd className="font-mono break-all">
          {data.stt_model} ({data.stt_language})
        </dd>
        <dt className="muted">업로드 한도</dt>
        <dd>{data.max_upload_mb}MB</dd>
        <dt className="muted">SMTP</dt>
        <dd>{data.smtp_configured ? "설정됨" : "미설정"}</dd>
      </dl>
    </div>
  );
}

function SmtpCard() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const run = async () => {
    setBusy(true);
    setResult(null);
    try {
      setResult({ ok: true, message: (await testSmtpConnection()).message });
    } catch (e) {
      setResult({ ok: false, message: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-3 text-sm">
      <p className="muted">
        SMTP 계정은 프로젝트 루트의 <code className="font-mono">.env</code>(또는 macOS 키체인)에서 관리하며 화면에 표시하지 않습니다. 연결 테스트는 로그인만 하고 메일은 보내지 않습니다.
      </p>
      <Button variant="secondary" icon="mail" onClick={run} loading={busy}>
        SMTP 연결 테스트
      </Button>
      {result && <Alert tone={result.ok ? "success" : "error"} title={result.message} />}
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

        <Card title="프로젝트 용어집" className="xl:col-span-2">
          <GlossaryCard />
        </Card>

        <Card title="이메일 (SMTP)">
          <SmtpCard />
        </Card>

        <Card title="보안 · 네트워크">
          <ul className="muted list-disc space-y-1.5 pl-5 text-sm">
            <li>외부 AI API를 사용하지 않으며, 음성과 텍스트는 이 Mac 안에서만 처리합니다.</li>
            <li>Ollama와 Backend는 127.0.0.1에서만 접속됩니다. 같은 LAN에서는 이 웹 화면(3000번 포트)만 접속할 수 있습니다.</li>
            <li>이메일은 미리보기 후 발송 버튼을 누르고 한 번 더 확인했을 때만 전송됩니다. 미리보기 이후 내용이 바뀌면 발송되지 않습니다.</li>
          </ul>
        </Card>
      </div>
    </>
  );
}
