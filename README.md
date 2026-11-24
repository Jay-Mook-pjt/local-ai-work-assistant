# Personal AI Work Assistant — Local AI Meeting Agent

Mac mini에서 동작하는 개인용 로컬 AI 업무 비서입니다. 회의 음성을 업로드하면 로컬 STT(MLX Whisper)와 로컬 LLM(Ollama)이 회의록을 만들고, 사용자가 검토·승인한 뒤에만 이메일로 발송합니다. 외부 AI API는 사용하지 않습니다.

> 현재 진행 단계: **PHASE 1 — 프로젝트 초기화 완료**. 회의 업로드/분석/문서/메일 기능은 아직 구현되지 않았습니다.

## 실행 환경 (PHASE 0 점검 결과, 2026-11-23)

| 항목 | 값 |
|---|---|
| 하드웨어 | Mac mini (Mac17,16), Apple M5 Pro (CPU 15코어, GPU 16코어), 24GB 통합 메모리 |
| OS | macOS 27.2.1 |
| Homebrew | 7.0.15 (`/opt/homebrew`) |
| Node.js / npm | 22.23.5 / 10.9.9 (`brew install node@22`, keg-only → `~/.zprofile`에 PATH 추가) |
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
│   ├── worker/      분석 작업 Worker (PHASE 3)
│   └── tests/
├── storage/         음성·전사·회의록·내보내기 파일 (Git 제외)
├── database/        meeting.db (Git 제외)
├── logs/            로그, pid 파일 (Git 제외)
└── scripts/         start.sh / stop.sh / health-check.sh
```

### 프롬프트 구조 대비 변경 사항
- `backend/app/logging_config.py`, `backend/app/api/health.py`, `backend/app/schemas/health.py` 추가 — 로그 설정과 상태 점검 API.
- `scripts/_common.sh` 추가 — 세 스크립트가 공유하는 경로/포트 설정.
- **Frontend → Backend 연결은 Next.js rewrite**(`/api/*` → `http://127.0.0.1:8000/api/*`)로 처리합니다. Backend를 localhost에만 열어 두면서도 LAN의 다른 기기 브라우저가 Frontend를 통해 API를 쓸 수 있게 하기 위함입니다.

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
scripts/health-check.sh   # Ollama, Backend, Frontend, 프록시, DB·LLM·STT 상태
scripts/stop.sh           # Backend/Frontend 중지 (Ollama는 건드리지 않음)
```

- 웹: <http://localhost:3000> (같은 LAN: `http://<Mac mini IP>:3000`)
- API 상태: `GET /api/health`
- 로그: `logs/backend.log`, `logs/backend.out.log`, `logs/frontend.out.log`

## 테스트

```bash
cd backend && .venv/bin/python -m pytest -q
cd frontend && npx tsc --noEmit && npm run lint && npm run build
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
| 2 | Frontend UI (Mock) | ⏳ 예정 |
| 3 | Backend API·DB·Worker | ⏳ 예정 |
| 4 | Ollama·MLX Whisper 연동 | ⏳ 예정 |
| 5 | DOCX·이메일 | ⏳ 예정 |
| 6 | 통합 테스트 | ⏳ 예정 |
| 7 | 로컬 운영(launchd, 백업) | ⏳ 예정 |

## 변경 이력
- **PHASE 1** — 디렉터리 구조, FastAPI 기본 앱(`/api/health`: DB·Ollama·STT 점검), SQLite 엔진(WAL), 설정/로그, Next.js 초기화와 상태 점검 화면, 실행 스크립트, 단위 테스트 3개.
