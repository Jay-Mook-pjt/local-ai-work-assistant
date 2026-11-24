# Personal AI Work Assistant — Local AI Meeting Agent

Mac mini에서 동작하는 개인용 로컬 AI 업무 비서입니다. 회의 음성을 업로드하면 로컬 STT(MLX Whisper)와 로컬 LLM(Ollama)이 회의록을 만들고, 사용자가 검토·승인한 뒤에만 이메일로 발송합니다. 외부 AI API는 사용하지 않습니다.

> 현재 진행 단계: **PHASE 3 — Backend(API·DB·Worker) 완료**. 회의 등록·음성 업로드·작업 대기열·오디오 변환·회의록 편집·후속 업무·삭제가 실제 SQLite와 파일 저장소로 동작합니다. **음성 인식(MLX Whisper)과 AI 분석(Ollama)은 PHASE 4에서 연결**하므로, 지금은 분석을 시작하면 오디오 변환까지 진행된 뒤 "PHASE 4에서 연결됩니다" 오류로 멈춥니다(다시 처리 가능). DOCX·이메일은 PHASE 5.

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
| LLM 기본 | `qwen3:14b` (9.3GB) | 짧은 샘플 비교에서 결정사항·담당자·기한·타임스탬프 추출이 가장 정확 |
| LLM 비교 | `exaone3.5:7.8b` (4.8GB) | 가장 빠름(46 tok/s), 요약에 약간의 덧붙임 경향 |
| LLM 비교 | `gemma3:12b` (8.2GB) | 결정사항 누락 경향 |
| STT | `mlx-community/whisper-large-v3-turbo` | 한국어 샘플 정확 인식, 문장별 타임스탬프 |

모델은 `.env`의 `LLM_MODEL`, `STT_MODEL`로 바꿀 수 있습니다. 24GB 메모리에서 STT와 LLM은 동시에 올리지 않고 순차 실행합니다.

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
| POST | `/api/meetings/{id}/analyze` | 분석 작업 등록 (실패 후 재시도도 동일, 처리 중이면 409) |
| GET | `/api/jobs/{id}` | 작업 상태 |
| GET | `/api/meetings/{id}/transcript` | STT 결과 (없으면 `null`) |
| GET / PUT | `/api/meetings/{id}/minutes` | 회의록 조회 / 수정 (후속 업무 포함, 기존 업무 id 유지) |
| PATCH | `/api/meetings/{id}/action-items/{item_id}` | 후속 업무 상태 변경 |
| GET | `/api/action-items?status=OPEN\|PENDING\|IN_PROGRESS\|DONE&assignee=` | 전체 후속 업무 |
| GET | `/api/meetings/{id}/documents`, `/api/meetings/{id}/emails`, `/api/emails` | 문서·발송 이력 (PHASE 5부터 기록) |
| GET | `/api/dashboard` | 대시보드 집계 |
| GET | `/api/health` | DB·Ollama·STT 상태 |

`POST /export`, `/email/preview`, `/email/send`는 PHASE 5에서 추가합니다. 동작하지 않는 엔드포인트는 미리 만들지 않았습니다. API 문서: <http://127.0.0.1:8000/docs> (이 Mac에서만 접속 가능).

### 데이터베이스 (SQLite, `database/meeting.db`)

`meetings`, `audio_files`, `jobs`, `transcripts`, `meeting_minutes`, `action_items`, `email_history`, `documents`. WAL 모드로 API와 Worker가 함께 사용합니다. JSON 컬럼은 한글을 그대로 저장해 검색이 가능합니다.

### 음성 업로드 검증
1. 파일명은 표시용으로만 저장합니다(경로 부분·제어 문자 제거). 실제 저장 파일명은 서버가 만든 ID입니다: `storage/audio/original/<회의ID>/<파일ID>.<확장자>`.
2. 확장자(mp3·wav·m4a·mp4) → 브라우저가 보낸 MIME 형식 → 파일 앞부분 시그니처(RIFF/WAVE, ftyp, ID3/MPEG 프레임) → `ffprobe`로 실제 오디오 트랙 존재 확인.
3. 크기 제한(`MAX_UPLOAD_MB`, 기본 500MB)은 저장하면서 계속 확인하고, 초과하면 즉시 중단하고 임시 파일을 지웁니다.
4. 같은 회의에 다시 올리면 이전 파일을 교체합니다. 처리 중에는 거부합니다.

### 작업 대기열 · Worker
- `POST /analyze`가 `jobs`에 `PENDING` 행을 추가하고, Worker(`python -m worker.main`)가 2초마다 확인해 하나씩 처리합니다. 작업을 가져갈 때 조건부 UPDATE를 써서 같은 작업이 두 번 처리되지 않습니다.
- 처리 단계: `PREPROCESSING`(ffmpeg로 16kHz 모노 WAV 변환, `storage/audio/processed/`) → `TRANSCRIBING` → `ANALYZING` → `GENERATING` → `COMPLETED`. **PHASE 3에서는 PREPROCESSING까지 구현**되어 있습니다.
- 실패하면 원인을 `jobs.error`에 기록하고 화면에서 "다시 처리"로 재시도할 수 있습니다. Worker가 처리 도중 종료되면 다음 시작 시 해당 작업을 실패로 표시합니다.

## 처음 설정

```bash
cp .env.example .env            # 이미 있으면 생략. SMTP 값은 PHASE 5에서 입력
cd backend && uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt
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
cd backend && .venv/bin/python -m pytest -q     # 임시 DB·저장소 사용, ffmpeg로 실제 MP3/WAV/M4A/MP4 생성해 검증
cd frontend && npm test && npm run typecheck && npm run lint && npm run build
```

## 보안 원칙
- 외부 AI API 미사용, 모든 음성·텍스트는 이 Mac에서만 처리
- Ollama·Backend는 `127.0.0.1` 바인딩, Frontend만 LAN 노출, 포트포워딩 없음
- `.env`, `storage/`, `database/`, `logs/`는 Git에 포함하지 않음
- 이메일은 사용자가 미리보기 후 발송 버튼을 눌렀을 때만 전송

## 진행 현황

| Phase | 내용 | 상태 |
|---|---|---|
| 0 | 개발환경 분석·설치 | ✅ 완료 |
| 1 | 프로젝트 초기화 | ✅ 완료 |
| 2 | Frontend UI (Mock) | ✅ 완료 |
| 3 | Backend API·DB·Worker | ✅ 완료 (STT·LLM 단계 제외) |
| 4 | Ollama·MLX Whisper 연동 | ⏳ 예정 |
| 5 | DOCX·이메일 | ⏳ 예정 |
| 6 | 통합 테스트 | ⏳ 예정 |
| 7 | 로컬 운영(launchd, 백업) | ⏳ 예정 |

## 변경 이력
- **PHASE 3** — SQLAlchemy 모델 8개 테이블, 회의·업로드·분석·작업·전사문·회의록·후속 업무·대시보드 API, 다단계 업로드 검증, SQLite 작업 대기열과 Worker(ffmpeg 전처리), 회의 삭제 시 파일 삭제, Frontend Mock 제거 및 실제 API 연결(업로드 진행률 표시), 대용량 업로드용 스트리밍 Route Handler, rewrite를 `fallback`으로 변경, 스크립트에 Worker 추가, pytest 40개.
- **PHASE 2** — 대시보드·회의 목록·생성·상세(회의록 보기/편집, 전사문, 이메일 미리보기)·이력·설정 화면, 반응형 레이아웃과 다크/라이트 모드, Backend API와 같은 형태의 Mock 데이터 계층(localStorage), 업로드 사전 검증, vitest 단위 테스트 26개. `@types/node`를 실행 환경(Node 22)에 맞춰 v22로 변경.
- **PHASE 1** — 디렉터리 구조, FastAPI 기본 앱(`/api/health`: DB·Ollama·STT 점검), SQLite 엔진(WAL), 설정/로그, Next.js 초기화와 상태 점검 화면, 실행 스크립트, 단위 테스트 3개.
