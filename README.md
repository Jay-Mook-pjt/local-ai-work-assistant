# Personal AI Work Assistant — Local AI Meeting Agent

Mac mini에서 동작하는 개인용 로컬 AI 업무 비서입니다. 회의 음성을 업로드하면 로컬 STT(MLX Whisper)와 로컬 LLM(Ollama)이 회의록을 만들고, 사용자가 검토·승인한 뒤에만 이메일로 발송합니다. 외부 AI API는 사용하지 않습니다.

> 현재 진행 단계: **PHASE 5 — DOCX·이메일 완료**. 음성 업로드부터 AI 회의록 생성, 검토·수정, DOCX 생성·다운로드, 이메일 미리보기·승인 발송까지 MVP 흐름이 동작합니다. 이메일을 실제로 보내려면 아래 '이메일 발송 설정'으로 SMTP 계정을 입력해야 합니다.

## 실행 환경 (PHASE 0 점검 결과, 2026-11-23)

| 항목 | 값 |
|---|---|
| 하드웨어 | Mac mini (Mac17,16), Apple M5 Pro (CPU 15코어, GPU 16코어), 24GB 통합 메모리 |
| OS | macOS 27.2.1 |
| Homebrew | 7.0.15 (`/opt/homebrew`) |
| Node.js / npm | 22.23.5 / 10.9.9 (`brew install node@22`, keg-only → `~/.zprofile`에 PATH 추가) |
| Frontend | Next.js 16.4.6, React 19.3, Tailwind CSS 4.3, vitest 5 (단위 테스트) |
| Python | 3.12.16 (uv 관리, 프로젝트 `.venv`), 시스템 Python 3.9는 사용하지 않음 |
| uv | 0.13.9 |
| ffmpeg | 9.0.2 |
| Ollama | 0.40.17 (`brew services`로 로그인 시 자동 실행, `127.0.0.1:11434` 전용) |
| MLX | 0.32.4, GPU 작업 메모리 한도 약 17.8GB |

### 모델

| 용도 | 모델 | 비고 |
|---|---|---|
| LLM 기본 | `qwen3:14b` (9.3GB, 실행 시 약 9.8GB) | 전사문에 없는 숫자를 만들지 않았고 결정·담당자·기한이 정확. 담당 미정 업무를 미결 사항으로만 분류하는 경향 |
| LLM 비교 | `exaone3.5:7.8b` (4.8GB) | 가장 빠름(약 46 tok/s). 담당 미정 업무까지 잘 잡지만 요약에 계산한 수치("90%")를 넣고 담당자를 놓친 경우 있음 |
| LLM 비교 | `gemma3:12b` (8.2GB) | 업무 추출은 양호하나 요약에 없는 수치("21건")를 만들고 논의 타임스탬프를 비움 |
| STT | `mlx-community/whisper-large-v3-turbo` | 한국어 샘플 정확 인식, 문장별 타임스탬프 |

비교는 139초 분량의 합성 한국어 회의(3인, 결정·미결·담당자 지정/미지정 업무 포함)로 같은 전사문에 대해 수행했습니다(2026-11-24). 기본 LLM은 설정 화면이나 `.env`의 `LLM_MODEL`로, 회의별로는 상세 화면의 "다시 분석"으로 바꿀 수 있습니다. 24GB 메모리에서 STT와 LLM은 동시에 올리지 않고 순차 실행합니다(Whisper 모델은 STT가 끝나면 메모리에서 내립니다).

## 구조

```
local-ai-work-assistant/
├── frontend/        Next.js 16 (App Router, TypeScript, Tailwind 4) — :3000, LAN 접근 가능
├── backend/         FastAPI + SQLAlchemy + SQLite — 127.0.0.1:8000 (localhost 전용)
│   ├── app/         config, api, services, agents, prompts, models, schemas, db
│   ├── worker/      분석 작업 Worker (main.py: 대기열 폴링, pipeline.py: 처리 단계)
│   └── tests/
├── storage/         음성·전사·회의록·내보내기 파일 (Git 제외)
├── database/        meeting.db (Git 제외)
├── logs/            로그, pid 파일 (Git 제외)
└── scripts/         start.sh / stop.sh / health-check.sh
```

### 프롬프트 구조 대비 변경 사항
- `backend/app/logging_config.py`, `backend/app/api/health.py`, `backend/app/schemas/health.py` 추가 — 로그 설정과 상태 점검 API.
- `scripts/_common.sh` 추가 — 세 스크립트가 공유하는 경로/포트 설정.
- **Frontend → Backend 연결은 Next.js rewrite**(`/api/*` → `http://127.0.0.1:8000/api/*`, `fallback` 단계)로 처리합니다. Backend를 localhost에만 열어 두면서도 LAN의 다른 기기 브라우저가 Frontend를 통해 API를 쓸 수 있게 하기 위함입니다.
- **음성 업로드만은 전용 Route Handler**(`frontend/src/app/api/meetings/[id]/audio/route.ts`)가 Backend로 스트리밍 전달합니다. Next.js rewrite 프록시는 요청 본문을 메모리에 담고 10MB에서 잘라 버려 대용량 녹음 파일이 실패하기 때문입니다. 스트리밍 방식은 300MB 업로드에서도 Next.js 메모리 사용량이 늘지 않음을 확인했습니다.
- DB 테이블에 `documents`(생성된 DOCX 파일 목록)를 추가했습니다. 프롬프트의 7개 테이블에 더해, 회의별로 여러 번 생성되는 문서를 관리하기 위함입니다(PHASE 5에서 사용).
- `backend/app/services/`에 `storage.py`(저장 경로·삭제), `media.py`(ffprobe/ffmpeg, 파일 시그니처), `audio_service.py`(업로드 검증), `job_service.py`(작업 대기열)를 추가했습니다.

## 화면

| 경로 | 화면 | 주요 기능 |
|---|---|---|
| `/` | 대시보드 | 전체·이번 달 회의 수, AI 처리 중, 미완료 후속 업무, 최근 회의, AI 처리 상태, 최근 후속 업무, 최근 문서, 빠른 생성 |
| `/meetings` | 회의록 목록 | 제목·참석자·안건·회의 내용(회의록·전사문) 검색, 날짜 범위, 상태 필터 |
| `/meetings/new` | 새 회의록 생성 | 제목·날짜·참석자·목적·안건(순서 변경)·AI 지시사항(프리셋), 음성 파일 드래그 앤 드롭, 형식·MIME·크기·파일명 검증, 길이 표시 |
| `/meetings/[id]` | 회의 상세 | 처리 단계 진행 표시와 실패 시 재처리, 회의록 8개 섹션 보기·편집, 근거 발언·타임스탬프 → 전사문 이동, 전사문 검색·복사, 이메일 작성·미리보기, 회의 삭제(확인) |
| `/history` | 이력 · 후속 업무 | 회의 전체 후속 업무 조회·상태 변경(담당자 필터), 월별 회의 타임라인, 이메일 발송 이력 |
| `/settings` | 설정 | 실제 시스템 상태(`/api/health`), 설치된 Ollama 모델, 테마(라이트/다크/시스템) |

- 좌측 Sidebar + 상단 Header, 모바일에서는 메뉴 버튼으로 여는 서랍형 Sidebar, 다크/라이트 모드.
- 회의록에서 AI가 확인하지 못한 값은 노란색 **미확인** 표시로 구분합니다.
- **아직 연결되지 않은 버튼**: `DOCX 생성·다운로드`, `발송`은 비활성 상태이며 버튼에 `(PHASE 5)`가 표시됩니다.
- 새 회의록 생성 시 `회의 등록 → 업로드(진행률 표시) → 처리 대기열 등록` 순서로 진행되며, 업로드가 실패하면 등록된 회의를 자동으로 되돌립니다.

### Frontend 코드 구조

```
frontend/src/
├── app/                    페이지 (App Router)
├── components/
│   ├── layout/             AppShell, Sidebar, ThemeToggle
│   ├── common/             ui.tsx(버튼·카드·배지·탭·대화상자 등), Icon, SystemStatus
│   ├── meeting/            MeetingList, AudioDropzone, JobProgress, MinutesView, TranscriptView, EmailPanel, ListInput
│   └── editor/             MinutesEditor
├── services/
│   ├── meetings.ts         모든 페이지가 쓰는 데이터 함수 (Backend API 호출)
│   └── api.ts              fetch/업로드 공통 처리, 오류 메시지 변환
├── hooks/useAsync.ts       데이터 로딩·폴링
├── app/api/meetings/[id]/audio/route.ts   음성 업로드 스트리밍 전달
├── lib/                    형식 변환, 업로드 사전 검증, 이메일 초안, backend 주소 (+ *.test.ts)
└── types/meeting.ts        Backend API와 맞출 도메인 타입
```

## Backend

### API

| Method | 경로 | 설명 |
|---|---|---|
| POST | `/api/meetings` | 회의 등록 |
| GET | `/api/meetings?q=&from=&to=&status=` | 회의 목록 (제목·목적·참석자·안건·전사문·회의록·후속 업무 내용 검색) |
| GET / DELETE | `/api/meetings/{id}` | 회의 조회 / 삭제 (DB 행과 저장된 모든 파일 삭제, 처리 중이면 409) |
| POST | `/api/meetings/{id}/audio` | 음성 업로드 (multipart `file`) |
| POST | `/api/meetings/{id}/analyze` | 분석 작업 등록. 본문(선택) `{"llm_model": "...", "overwrite_edited": false}`. 같은 음성의 전사문이 있으면 재사용하고 AI 분석만 다시 실행. 직접 수정한 회의록이 있으면 `overwrite_edited: true` 없이는 409 |
| GET | `/api/jobs/{id}` | 작업 상태 |
| GET | `/api/meetings/{id}/transcript` | STT 결과 (없으면 `null`) |
| GET / PUT | `/api/meetings/{id}/minutes` | 회의록 조회 / 수정 (후속 업무 포함, 기존 업무 id 유지) |
| PATCH | `/api/meetings/{id}/action-items/{item_id}` | 후속 업무 상태 변경 |
| GET | `/api/action-items?status=OPEN\|PENDING\|IN_PROGRESS\|DONE&assignee=` | 전체 후속 업무 |
| GET | `/api/meetings/{id}/documents`, `/api/meetings/{id}/emails`, `/api/emails` | 문서·발송 이력 |
| POST | `/api/meetings/{id}/export` | 현재 회의록으로 DOCX 생성 |
| GET / DELETE | `/api/documents/{doc_id}/download`, `/api/documents/{doc_id}` | DOCX 다운로드(한글 파일명) / 삭제 |
| GET | `/api/meetings/{id}/email/draft` | 회의록 기반 메일 제목·본문 초안, SMTP 준비 상태 |
| POST | `/api/meetings/{id}/email/preview` | 보낼 내용 그대로의 미리보기 + `content_hash` (발송·파일 생성 없음) |
| POST | `/api/meetings/{id}/email/send` | `confirm: true`와 미리보기의 `content_hash`가 있어야 발송. 내용·회의록이 바뀌었으면 409 |
| POST | `/api/email/test-connection` | SMTP 로그인만 확인 (발송 없음) |
| GET | `/api/dashboard` | 대시보드 집계 |
| GET / PUT | `/api/settings` | 기본 LLM 모델 조회·변경(설치된 모델만 허용), 설치 모델 목록, STT·업로드·SMTP 설정 요약 |
| GET | `/api/health` | DB·Ollama·STT 상태 |

API 문서: <http://127.0.0.1:8000/docs> (이 Mac에서만 접속 가능).

### 데이터베이스 (SQLite, `database/meeting.db`)

`meetings`, `audio_files`, `jobs`, `transcripts`, `meeting_minutes`, `action_items`, `email_history`, `documents`, `app_settings`. WAL 모드로 API와 Worker가 함께 사용합니다. JSON 컬럼은 한글을 그대로 저장해 검색이 가능합니다. 나중에 추가된 nullable 컬럼은 시작 시 자동으로 `ALTER TABLE ADD COLUMN` 됩니다(데이터 삭제 없음).

### 음성 업로드 검증
1. 파일명은 표시용으로만 저장합니다(경로 부분·제어 문자 제거). 실제 저장 파일명은 서버가 만든 ID입니다: `storage/audio/original/<회의ID>/<파일ID>.<확장자>`.
2. 확장자(mp3·wav·m4a·mp4) → 브라우저가 보낸 MIME 형식 → 파일 앞부분 시그니처(RIFF/WAVE, ftyp, ID3/MPEG 프레임) → `ffprobe`로 실제 오디오 트랙 존재 확인.
3. 크기 제한(`MAX_UPLOAD_MB`, 기본 500MB)은 저장하면서 계속 확인하고, 초과하면 즉시 중단하고 임시 파일을 지웁니다.
4. 같은 회의에 다시 올리면 이전 파일을 교체합니다. 처리 중에는 거부합니다.

### 작업 대기열 · Worker
- `POST /analyze`가 `jobs`에 `PENDING` 행을 추가하고, Worker(`python -m worker.main`)가 2초마다 확인해 하나씩 처리합니다. 작업을 가져갈 때 조건부 UPDATE를 써서 같은 작업이 두 번 처리되지 않습니다.
- 처리 단계: `PREPROCESSING`(ffmpeg로 16kHz 모노 WAV 변환) → `TRANSCRIBING`(MLX Whisper) → `ANALYZING`(Ollama 구간 분석) → `GENERATING`(통합·근거 검증·저장) → `COMPLETED`.
- 실패하면 원인을 `jobs.error`에 기록하고 화면에서 "다시 처리"로 재시도할 수 있습니다. Worker가 처리 도중 종료되면 다음 시작 시 해당 작업을 실패로 표시합니다.

## AI 처리 (PHASE 4)

### 음성 인식 — `app/services/stt_service.py`
- `mlx-community/whisper-large-v3-turbo`, 한국어 고정. 실측 속도: 139초 음성을 약 3~4초(실시간 대비 30~40배).
- 긴 음성은 `STT_CHUNK_SECONDS`(기본 600초) 단위로 나누고 `STT_OVERLAP_SECONDS`(기본 10초)씩 겹쳐 인식합니다. 겹친 구간은 경계의 중간 지점을 기준으로 한쪽 결과만 남겨 문장 중복·누락을 막습니다.
- 회의 제목·안건·참석자를 Whisper 초기 프롬프트로 넣어 전문 용어·이름 인식을 돕습니다.
- 장시간 오디오에서 같은 문장이 반복되는 현상을 막기 위해 앞 문장 조건부 디코딩을 끄고, 무음 구간의 대표적인 환각 문구("시청해 주셔서 감사합니다" 등)·반복 출력·무음 판정 구간을 제거합니다.
- 결과는 DB(`transcripts`)와 `storage/transcripts/<회의ID>/transcript.txt`에 저장됩니다.

### 회의 분석 — `app/agents/`
1. **구간 분석**(`meeting_agent.py`): 전사문을 `[시:분:초] 문장` 형태로 만들어 `LLM_CHUNK_CHARS`(기본 6000자) 단위로 문장 경계에서 나눕니다. 짧은 회의는 한 번의 호출로, 긴 회의는 구간별로 분석한 뒤 구조화된 추출 결과만 모아 한 번 더 통합합니다(전체 전사문을 한 번에 보내지 않음). 각 구간 앞에는 이전 구간의 마지막 2문장을 문맥으로 붙입니다.
2. **구조화 출력**(`llm_service.py`): Ollama에 JSON 스키마를 `format`으로 지정하고(thinking 끔) Pydantic으로 검증합니다. 형식 오류 시 1회 재시도합니다. 모든 호출은 `logs/llm_calls.log`에 모델·소요 시간·토큰 수·성공 여부가 JSON 한 줄로 기록됩니다.
3. **근거 검증**(`review_agent.py`): AI 결과를 전사문과 대조합니다.
   - 결정사항·후속 업무의 근거 인용문을 전사문에서 찾아 **타임스탬프를 실제 문장 위치로 교체**합니다. 근거를 못 찾은 결정사항은 결정에서 빼고 미결 사항에 `[검증 필요]`로 옮깁니다.
   - 담당자·기한은 전사문에 실제로 나온 경우에만 남기고, 아니면 `미확인`으로 바꿉니다.
   - 업무 배정("누가 언제까지")이 결정사항에도 들어가면 결정사항에서 제외합니다.
   - 요약·논의·미결 문장에 전사문에 없는 **숫자**가 있으면 표시합니다(한글 수사 "열두", "스물세", "십이월"도 인식).
   - 화자 분리가 없으므로 발언자는 항상 `미확인`. 논의가 없었던 안건은 "논의가 확인되지 않음"으로 명시합니다.
4. **후속 업무 정리**(`task_agent.py`): 중복 업무 병합, 담당자를 등록된 참석자 이름으로 맞춤, STT가 참석자 이름을 한 글자 다르게 인식한 경우(예: 이지은→이지훈) 참석자 이름으로 보정(근거 인용문은 원문 유지).
5. 검증 결과는 회의록의 `review_notes`로 저장되어 화면에 **"검토가 필요한 항목"**으로 표시됩니다.

프롬프트는 `app/prompts/<이름>_v<N>.md` 파일로 관리하며, 사용 버전은 `app/services/prompt_service.py`의 `PROMPT_VERSIONS`에서 정합니다(현재 system v2, 나머지 v1).

### 모델 비교 방법
회의 상세 → **다시 분석** → 모델 선택. 같은 음성이면 전사문을 재사용해 LLM 단계만 실행합니다. 결과 회의록에는 사용한 모델명이 표시됩니다. 직접 수정한 회의록은 덮어쓰기 확인 후에만 바뀝니다.

### 알려진 한계
- 화자 분리(누가 말했는지)는 지원하지 않습니다. 담당자는 발언 내용("박정우 책임님이…")으로만 판단합니다.
- 논의사항 요약 문장 자체는 근거 인용이 없어 자동 검증이 숫자 확인에 한정됩니다. 최종 회의록은 사용자가 검토·수정하는 것을 전제로 합니다.
- 실측 처리 시간(qwen3:14b): 2분 회의 약 35~40초(한 번 호출), 구간 분석 경로는 구간당 20~35초 + 통합 약 40초.

## 문서 · 이메일 (PHASE 5)

### DOCX — `app/services/document_service.py`
- A4, 맑은 고딕(Windows Word 기준, Mac Word는 Apple SD 고딕으로 대체), 8개 섹션: 회의 개요(요약 포함) · 회의 목적 · 참석자 · 주요 논의사항(표, 시각) · 의사결정 사항(근거 인용·시각) · 담당자별 후속 업무(표) · 미결 사항 · 다음 회의 확인사항.
- `미확인`은 주황색으로 표시해 실제 값과 구분합니다. 표는 고정 너비·테두리를 문서에 직접 지정해 뷰어마다 모양이 달라지지 않게 했습니다.
- 파일: `storage/exports/<회의ID>/<문서ID>.docx`, 다운로드 이름 `YYYYMMDD_<제목>_회의록.docx`. 생성할 때마다 새 버전이 쌓이며 화면에서 개별 삭제할 수 있습니다.

### 이메일 — `app/services/email_service.py`
흐름: **작성 → 미리보기(서버가 보낼 내용 그대로 생성) → 발송 버튼 → 확인 창 → 발송**.
- 미리보기는 수신자·제목·본문·첨부 여부·회의록 수정 시각으로 `content_hash`를 만듭니다. 발송 요청은 같은 해시와 `confirm: true`가 있어야 처리되므로, 사용자가 보지 않은 내용은 발송되지 않습니다. 미리보기 후 회의록이 수정되면 발송이 거부되고 다시 미리보기를 요구합니다.
- AI(Worker)는 발송 기능을 호출하지 않습니다. 발송은 화면의 버튼으로만 이루어집니다.
- 수신자 형식·중복·최대 50명, 제목·주소의 줄바꿈(헤더 주입) 차단. 첨부 DOCX는 발송 시점의 회의록으로 생성되어 문서 목록에도 남습니다.
- 결과(성공/실패와 원인)는 `email_history`에 기록되어 회의 상세와 이력 화면에 표시됩니다.

### 이메일 발송 설정
`.env`에 입력한 뒤 `scripts/stop.sh && scripts/start.sh`로 재시작합니다.

```
SMTP_HOST=smtp.gmail.com        # Microsoft 365: smtp.office365.com
SMTP_PORT=587                   # 465면 SSL 자동 사용
SMTP_USE_TLS=true
SMTP_USERNAME=me@example.com
SMTP_FROM=me@example.com
SMTP_FROM_NAME=AI 회의록 비서
```

비밀번호(Gmail은 [앱 비밀번호](https://myaccount.google.com/apppasswords))는 둘 중 하나로 넣습니다.
- `.env`의 `SMTP_PASSWORD=` (파일은 Git에 포함되지 않음)
- 또는 macOS 키체인에 저장하고 `.env`에는 서비스 이름만 지정 (권장):

```bash
security add-generic-password -s local-ai-work-assistant-smtp -a me@example.com -w
```

```
SMTP_KEYCHAIN_SERVICE=local-ai-work-assistant-smtp
```

설정 화면의 **SMTP 연결 테스트**로 로그인만 확인할 수 있습니다(메일은 보내지 않음).

## 처음 설정

```bash
cp .env.example .env            # 이미 있으면 생략. SMTP 값은 PHASE 5에서 입력
cd backend && uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt   # 운영만: requirements.txt
cd ../frontend && npm install
```

## 실행 / 중지 / 점검

```bash
scripts/start.sh          # 개발 모드 (backend --reload, next dev)
scripts/start.sh prod     # 프로덕션 빌드 후 실행
scripts/health-check.sh   # Ollama, Backend, Frontend, 프록시, Worker, DB·LLM·STT 상태
scripts/stop.sh           # Frontend/Worker/Backend 중지 (Ollama는 건드리지 않음)
```

- 웹: <http://localhost:3000> (같은 LAN: `http://<Mac mini IP>:3000`)
- API 상태: `GET /api/health`
- 로그: `logs/backend.log`, `logs/worker.log`, `logs/*.out.log`

## 테스트

```bash
cd backend && .venv/bin/python -m pytest -q     # 임시 DB·저장소, ffmpeg로 만든 실제 음성, 로컬 SMTP 서버(aiosmtpd)로 검증
cd frontend && npm test && npm run typecheck && npm run lint && npm run build
```

## 보안 원칙
- 외부 AI API 미사용, 모든 음성·텍스트는 이 Mac에서만 처리
- Ollama·Backend는 `127.0.0.1` 바인딩, Frontend만 LAN 노출, 포트포워딩 없음
- `.env`, `storage/`, `database/`, `logs/`는 Git에 포함하지 않음
- 이메일은 사용자가 미리보기 후 발송 버튼을 누르고 확인했을 때만 전송, 미리보기 이후 내용이 바뀌면 발송 거부
- SMTP 비밀번호는 `.env` 또는 macOS 키체인에만 저장하며 API·화면·로그에 노출하지 않음
- 회의 삭제 시 음성·전사문·DOCX 파일 모두 삭제, DOCX는 개별 삭제 가능

## 진행 현황

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | 개발환경 분석·설치 | ✅ 완료 |
| 1 | 프로젝트 초기화 | ✅ 완료 |
| 2 | Frontend UI (Mock) | ✅ 완료 |
| 3 | Backend API·DB·Worker | ✅ 완료 (STT·LLM 단계 제외) |
| 4 | Ollama·MLX Whisper 연동 | ✅ 완료 |
| 5 | DOCX·이메일 | ✅ 완료 (실제 발송은 SMTP 계정 입력 필요) |
| 6 | 통합 테스트 | ⏳ 예정 |
| 7 | 로컬 운영(launchd, 백업) | ⏳ 예정 |

## 변경 이력
- **PHASE 5** — DOCX 생성(8개 섹션, 고정 표 레이아웃, 미확인 강조)·다운로드(한글 파일명)·삭제, 이메일 초안·서버 미리보기·해시 기반 승인 발송·발송 이력, SMTP STARTTLS/SSL·키체인 비밀번호·연결 테스트, 화면의 문서·이메일 패널과 발송 확인 창, 설정 화면 SMTP 연결 테스트, 메일 초안 생성을 Backend로 이전, aiosmtpd 개발 의존성(requirements-dev.txt), pytest 89개.
- **PHASE 4** — MLX Whisper 음성 인식(구간 분할·오버랩·환각 필터·초기 프롬프트), Ollama 구조화 출력 클라이언트(호출 로그·재시도·오류 메시지), Meeting Agent(구간 분석→통합), 근거 검증(타임스탬프 교정·담당자/기한/숫자 확인·업무 배정 분리·이름 보정), 검토 항목 화면 표시, 기본 모델 설정 API·화면, 다른 모델로 다시 분석(전사문 재사용·수정본 보호), DB 컬럼 자동 추가, 프롬프트 버전 관리, pytest 73개, 실제 한국어 회의 음성으로 3개 모델 비교.
- **PHASE 3** — SQLAlchemy 모델 8개 테이블, 회의·업로드·분석·작업·전사문·회의록·후속 업무·대시보드 API, 다단계 업로드 검증, SQLite 작업 대기열과 Worker(ffmpeg 전처리), 회의 삭제 시 파일 삭제, Frontend Mock 제거 및 실제 API 연결(업로드 진행률 표시), 대용량 업로드용 스트리밍 Route Handler, rewrite를 `fallback`으로 변경, 스크립트에 Worker 추가, pytest 40개.
- **PHASE 2** — 대시보드·회의 목록·생성·상세(회의록 보기/편집, 전사문, 이메일 미리보기)·이력·설정 화면, 반응형 레이아웃과 다크/라이트 모드, Backend API와 같은 형태의 Mock 데이터 계층(localStorage), 업로드 사전 검증, vitest 단위 테스트 26개. `@types/node`를 실행 환경(Node 22)에 맞춰 v22로 변경.
- **PHASE 1** — 디렉터리 구조, FastAPI 기본 앱(`/api/health`: DB·Ollama·STT 점검), SQLite 엔진(WAL), 설정/로그, Next.js 초기화와 상태 점검 화면, 실행 스크립트, 단위 테스트 3개.
