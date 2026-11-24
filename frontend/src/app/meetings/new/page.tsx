"use client";

import { useRouter } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { Alert, Button, Card, Field, LinkButton, Loading, PageHeader } from "@/components/common/ui";
import { AudioDropzone } from "@/components/meeting/AudioDropzone";
import { ChipInput, RowListInput } from "@/components/meeting/ListInput";
import { readAudioDuration } from "@/lib/audioValidation";
import { todayIso } from "@/lib/format";
import { createMeeting, USING_MOCK } from "@/services/meetings";

const INSTRUCTION_PRESETS = [
  "담당자별 업무와 후속 조치를 중심으로 정리해 줘.",
  "결정사항과 단순 논의사항을 구분해 줘.",
  "다음 회의에서 확인해야 할 내용을 별도로 작성해 줘.",
  "기술적인 이슈와 리스크를 따로 정리해 줘.",
];

type Errors = Partial<Record<"title" | "meeting_date" | "agenda" | "audio", string>>;

function NewMeetingForm() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [date, setDate] = useState(todayIso);
  const [attendees, setAttendees] = useState<string[]>([]);
  const [purpose, setPurpose] = useState("");
  const [agenda, setAgenda] = useState<string[]>([""]);
  const [instructions, setInstructions] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const onFile = (f: File, err: string | null) => {
    setFile(f);
    setFileError(err);
    setDuration(null);
    if (!err) void readAudioDuration(f).then(setDuration);
  };

  const addPreset = (p: string) => setInstructions((v) => (v.includes(p) ? v : v ? `${v.trimEnd()} ${p}` : p));

  const validate = (): Errors => {
    const e: Errors = {};
    if (!title.trim()) e.title = "회의 제목을 입력하세요.";
    else if (title.trim().length > 200) e.title = "제목은 200자 이내로 입력하세요.";
    if (!date) e.meeting_date = "회의 날짜를 선택하세요.";
    if (!agenda.some((a) => a.trim())) e.agenda = "안건을 1개 이상 입력하세요.";
    if (!file) e.audio = "음성 파일을 선택하세요.";
    else if (fileError) e.audio = fileError;
    return e;
  };

  // After the first submit attempt, errors update live as the user fixes them.
  const errors: Errors = submitted ? validate() : {};

  const submit = async (ev: FormEvent) => {
    ev.preventDefault();
    setSubmitted(true);
    const e = validate();
    if (Object.keys(e).length || !file) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const { meeting } = await createMeeting(
        {
          title: title.trim(),
          meeting_date: date,
          attendees,
          purpose: purpose.trim(),
          agenda: agenda.map((a) => a.trim()).filter(Boolean),
          instructions: instructions.trim(),
        },
        { filename: file.name.normalize("NFC"), size_bytes: file.size, duration_seconds: duration, mime_type: file.type || "application/octet-stream" },
      );
      router.push(`/meetings/${meeting.id}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <>
      <PageHeader title="새 회의록 생성" description="회의 정보와 음성 파일을 입력하면 로컬 AI가 회의록 초안을 만듭니다." />
      <form onSubmit={submit} noValidate className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card title="회의 기본정보">
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Field label="회의 제목" required htmlFor="title" error={errors.title}>
                  <input id="title" className="field" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="예: DB생명 방카슈랑스 테스트 자동화 회의" maxLength={200} />
                </Field>
              </div>
              <Field label="회의 날짜" required htmlFor="date" error={errors.meeting_date}>
                <input id="date" type="date" className="field" value={date} onChange={(e) => setDate(e.target.value)} />
              </Field>
              <Field label="참석자" htmlFor="attendees" hint="Enter 또는 쉼표로 구분">
                <ChipInput id="attendees" value={attendees} onChange={setAttendees} placeholder="예: 김민수 과장" />
              </Field>
              <div className="sm:col-span-2">
                <Field label="회의 목적" htmlFor="purpose">
                  <input id="purpose" className="field" value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="예: 테스트 자동화 진행 현황 점검 및 일정 확정" />
                </Field>
              </div>
            </div>
          </Card>

          <Card title="회의 안건">
            <RowListInput value={agenda} onChange={setAgenda} placeholder="예: 상품설명서 검증 진행사항" addLabel="안건 추가" />
            {errors.agenda && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{errors.agenda}</p>}
          </Card>

          <Card title="AI 추가 지시사항">
            <textarea
              className="field min-h-28 resize-y"
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="회의록을 어떻게 정리할지 AI에게 알려주세요."
              maxLength={2000}
              aria-label="AI 추가 지시사항"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              {INSTRUCTION_PRESETS.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => addPreset(p)}
                  className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 hover:border-indigo-400 hover:text-indigo-700 dark:border-slate-700 dark:text-slate-300 dark:hover:text-indigo-300"
                >
                  + {p}
                </button>
              ))}
            </div>
            <p className="muted mt-3 text-xs">AI는 회의에서 언급되지 않은 담당자·날짜·결정사항을 만들지 않으며, 불확실한 내용은 &lsquo;미확인&rsquo;으로 표시합니다.</p>
          </Card>
        </div>

        <div className="space-y-6">
          <Card title="음성 파일">
            <AudioDropzone
              file={file}
              duration={duration}
              error={fileError ?? undefined}
              onSelect={onFile}
              onClear={() => {
                setFile(null);
                setFileError(null);
                setDuration(null);
              }}
            />
            {(fileError || errors.audio) && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{fileError ?? errors.audio}</p>}
          </Card>

          <Card title="생성">
            <ol className="muted mb-4 list-decimal space-y-1 pl-5 text-xs">
              <li>음성 파일 업로드 및 변환</li>
              <li>MLX Whisper 음성 인식 (타임스탬프 포함)</li>
              <li>Ollama 구간별 분석 및 통합</li>
              <li>회의록 초안 생성 → 검토·수정</li>
            </ol>
            {USING_MOCK && (
              <div className="mb-4">
                <Alert tone="warning" title="Mock 모드">
                  파일은 업로드되지 않고, 처리 과정은 약 20초 동안 시뮬레이션됩니다.
                </Alert>
              </div>
            )}
            {submitError && (
              <div className="mb-4">
                <Alert title="회의 등록에 실패했습니다.">{submitError}</Alert>
              </div>
            )}
            <div className="flex gap-2">
              <Button type="submit" icon="cpu" loading={submitting} className="flex-1">
                회의록 생성
              </Button>
              <LinkButton href="/meetings" variant="secondary">
                취소
              </LinkButton>
            </div>
          </Card>
        </div>
      </form>
    </>
  );
}

// The form defaults the date to "today", which must be computed per visit,
// not at build time — so it renders behind a Suspense boundary.
export default function NewMeetingPage() {
  return (
    <Suspense fallback={<Loading />}>
      <NewMeetingForm />
    </Suspense>
  );
}
