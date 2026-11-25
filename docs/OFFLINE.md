# 폐쇄망(오프라인) 운영 검증 보고서 — PHASE 6-1

작성일: 2026-11-24 · 대상: Mac mini (M5 Pro, 통합 메모리 24GB, macOS 27.2.1)

> 표기: ✅ 이 문서 작성 중 실제로 실행해 확인 · ⚠️ 일부만 확인 · ⏳ 미검증(절차만 제시)

## 1. 현재 로컬 AI 구성

| 구성 요소 | 사용 기술 | 실행 위치 | 모델·데이터 위치 |
|---|---|---|---|
| 음성 인식(STT) | MLX Whisper 0.4.3, `whisper-large-v3-turbo` | Worker 프로세스 (Apple GPU) | `models/whisper-large-v3-turbo` (1.5GB) |
| 화자 분리 | pyannote.audio 4.1.1, `speaker-diarization-community-1` | Worker 프로세스 (PyTorch MPS) | `models/speaker-diarization-community-1` (32MB) |
| 회의록 생성 | Ollama 0.40.17, `qwen3:14b` (비교용 `gemma3:12b`, `exaone3.5:7.8b`) | Ollama 서비스 `127.0.0.1:11434` | `~/.ollama/models` (전체 21GB, qwen3:14b 9.3GB) |
| API·작업 대기열 | FastAPI + SQLite | `127.0.0.1:8000` + Worker 1개 | `database/meeting.db`, `storage/` |
| 웹 화면 | Next.js 16.4.6 | `0.0.0.0:3000` (LAN만) | `frontend/.next` |
| 문서·메일 | python-docx, SMTP | Backend | 내부 메일 릴레이 |

모델 로딩 경로는 `backend/app/services/model_store.py` 한 곳에서 정합니다. `models/<이름>` 폴더가 있으면 그 경로를 쓰고, 없을 때만 Hugging Face 저장소 이름을 씁니다. 폐쇄망 모드에서는 저장소 이름으로 받는 동작이 꺼져 있어, 모델 폴더가 없으면 오류가 납니다.

## 2. 외부 네트워크 의존성 점검 결과

### 2-1. 코드 점검에서 발견하고 조치한 항목

| 항목 | 발견 내용 | 조치 | 확인 |
|---|---|---|---|
| MLX Whisper | 실행할 때마다 `huggingface.co`에 모델 최신 버전을 조회함 (PHASE 4부터, 로그상 22회) | 프로세스 시작 시 `HF_HUB_OFFLINE=1` (`app/offline.py`), 로컬 폴더에서 로딩 | ✅ 외부 요청 0건 |
| pyannote.audio 4.x | 사용 통계(모델명·음성 길이·화자 수)를 `otel.pyannote.ai`로 보내는 기능이 **기본으로 켜져 있음** | `PYANNOTE_METRICS_ENABLED=false`를 라이브러리 import 전에 설정 | ✅ |
| pyannote 모델 로딩 | 하위 모델(segmentation, embedding, plda)을 Hub에서 확인하는 HEAD 요청 | 오프라인 환경변수를 import 전에 설정하고, 로컬 폴더 경로로 로딩 | ✅ |
| Hugging Face 토큰 | macOS 키체인(`local-ai-work-assistant-hf`)에 저장 | 모델을 받는 명령(`model_store fetch`)에서만 읽음. 실행 중에는 사용하지 않음 | ✅ 빈 `HF_HOME`, 토큰 없이 로딩 성공 |
| Ollama 클라우드 모델 | `*-cloud` 모델을 고르면 회의 내용이 ollama.com으로 전송될 수 있음 | ① Ollama 서비스에 `OLLAMA_NO_CLOUD=1` 적용, ② 앱에서 클라우드 이름 모델의 호출을 거부(`LLM_ALLOW_CLOUD=false`), ③ 모델 목록에서 클라우드 모델을 숨김 | ✅ 호출 시 거부 응답 |
| Ollama 모델 받기 | `OLLAMA_NO_CLOUD=1`이어도 `/api/pull`은 막히지 않음 (실측) | 폐쇄망에서는 네트워크가 없어 실패함. 앱에는 모델을 받는 기능이 없음 | ✅ 받기 실패 확인 |
| Next.js | 빌드·실행 시 사용 통계 전송 | `NEXT_TELEMETRY_DISABLED=1` (`scripts/_common.sh`) | ✅ 샌드박스 실행 중 외부 연결 0건 |
| `pyannoteai-sdk` | pyannote의 유료 클라우드 API용 SDK가 의존성으로 함께 설치됨 | 앱 코드에서 사용하지 않음 (`pyannote/...` 로컬 파이프라인만 사용) | ✅ 코드 검색 |

### 2-2. 남는 외부 연결 (의도된 것)

| 구분 | 대상 | 시점 | 폐쇄망에서 |
|---|---|---|---|
| **내부망** | SMTP 메일 릴레이 | 사용자가 미리보기 후 발송을 확인할 때만 | 내부 릴레이 주소로 설정 (`.env.offline`의 `SMTP_HOST`) |
| **내부망** | LAN 사용자 브라우저 → `:3000` | 상시 | 허용 |
| 외부망 (준비 단계 1회) | huggingface.co (모델 2개), registry.ollama.ai (LLM), PyPI (wheel), npm, Homebrew | 개발 환경에서 준비할 때만 | 발생하지 않음. 준비한 파일을 반입 |

## 3. 폐쇄망 동작 방식과 설정

| 설정 | 적용 위치 | 개발(.env) | 운영·폐쇄망(.env.offline) |
|---|---|---|---|
| `HF_HUB_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`, `PYANNOTE_METRICS_ENABLED=false` | `app/offline.py` (API·Worker 시작 시 가장 먼저) + `scripts/_common.sh` | 항상 켜짐 | 항상 켜짐 |
| `OLLAMA_NO_CLOUD=1`, `OLLAMA_HOST=127.0.0.1:11434` | Ollama 서비스 plist (`scripts/ollama-offline.sh apply`) | 적용됨 | 적용 |
| `MODELS_DIR` | `.env` | `models` | `models` |
| `LLM_ALLOW_CLOUD` | `.env` | `false` | `false` |
| `LLM_UNLOAD_AFTER_JOB` | `.env` | `true` | `true` |
| `APP_ENV` | `.env` | `development` | `production` |
| `SMTP_HOST` | `.env` | 외부 메일 서비스 가능 | 내부 릴레이 |

- 운영 실행: `APP_ENV_FILE=.env.offline scripts/start.sh prod`
- **실제 프로세스에 적용되었는지 확인** ✅: `scripts/health-check.sh`가 실행 중인 Worker·Backend·Ollama 프로세스의 환경변수(`ps eww`)를 직접 읽어 `HF_HUB_OFFLINE=1`, `PYANNOTE_METRICS_ENABLED=false`, `OLLAMA_NO_CLOUD=1`을 확인합니다.
- 주의: `brew services restart ollama`를 실행하면 Homebrew가 plist를 다시 만들어 `OLLAMA_NO_CLOUD`가 빠집니다. 재시작 후 `scripts/ollama-offline.sh status`로 확인하고, 빠졌으면 `apply`를 다시 실행하세요.

## 4. 로컬 모델 경로와 관리 명령

```
models/
├── whisper-large-v3-turbo/            config.json, weights.safetensors      (1.5GB)
└── speaker-diarization-community-1/   config.yaml, segmentation/, embedding/, plda/  (32MB)
~/.ollama/models/
├── manifests/registry.ollama.ai/library/qwen3/14b
└── blobs/sha256-…                     (qwen3:14b: blob 6개, 9.3GB)
```

```bash
cd backend
.venv/bin/python -m app.services.model_store status          # 경로·존재 여부
.venv/bin/python -m app.services.model_store verify --load   # 필수 파일 + 실제 로딩 테스트 (네트워크 불필요)
.venv/bin/python -m app.services.model_store fetch           # [인터넷 필요, 준비 단계만] HF 캐시 → models/, 없으면 다운로드
```

## 5. 폐쇄망 반입 파일 목록

| 반입물 | 원본 위치 | 크기 | 준비 명령 (개발 환경) |
|---|---|---|---|
| 프로젝트 소스 | Git 저장소 | — | `git clone` 또는 압축 |
| STT·화자 분리 모델 | `models/` | 1.5GB | `model_store fetch` → `model_store verify --load` |
| LLM 모델 | `~/.ollama/models` 중 선택 모델 | qwen3:14b 9.3GB | `scripts/offline/ollama-models.sh export <폴더> qwen3:14b` |
| Python 패키지 | `wheelhouse/` (wheel 126개) | 371MB | 아래 6장 |
| Python 버전 고정 목록 | `backend/requirements.lock.txt` | — | `uv pip freeze` (저장소에 포함) |
| Python 3.12 런타임 | `~/.local/share/uv/python/cpython-3.12.16-macos-aarch64-none` | 약 70MB | uv가 설치한 것을 복사 ⏳ |
| Frontend 의존성·빌드 | `frontend/node_modules`, `frontend/.next` | 511MB / 223MB | `npm ci && npm run build` |
| 시스템 도구 | Homebrew: `ollama`, `ffmpeg`, `node@22`, `uv` | — | 아래 6-3 ⏳ |

`models/`, `wheelhouse/`는 `.gitignore`에 포함되어 Git에 올라가지 않습니다.

## 6. 오프라인 설치 절차

### 6-1. Python 패키지 ✅
```bash
# [개발 환경, 인터넷 연결]
cd backend
uv pip freeze -p .venv/bin/python --exclude-editable > requirements.lock.txt
uvx --from pip pip download -r requirements.lock.txt -d ../wheelhouse --only-binary=:all:

# [폐쇄망]
cd backend
UV_OFFLINE=1 uv venv -p 3.12 .venv
uv pip install -p .venv/bin/python --offline --no-index --find-links ../wheelhouse -r requirements.lock.txt
```
검증: 네트워크 차단 샌드박스에서 새 venv를 만들고 wheelhouse만으로 설치했습니다. 이후 `model_store verify --load`로 두 모델의 로딩을 확인했고, pytest 114개가 모두 통과했습니다.

### 6-2. Ollama 모델 백업·복원 ✅
```bash
scripts/offline/ollama-models.sh export /Volumes/USB/ollama-backup qwen3:14b   # manifest와 blob만 복사 + sha256 검사
scripts/offline/ollama-models.sh verify /Volumes/USB/ollama-backup             # 반입 후 손상 확인
scripts/offline/ollama-models.sh import /Volumes/USB/ollama-backup             # ~/.ollama/models로 복원 (기존 파일은 삭제·덮어쓰기 안 함)
/opt/homebrew/bin/ollama list
```
검증 결과:
- export(9.3GB)에 20초, import에 17초가 걸렸습니다. import는 네트워크 차단 샌드박스에서 비어 있는 모델 폴더로 진행했습니다.
- 복원한 폴더만으로 띄운 Ollama가 `qwen3:14b` 하나만 표시했고, 응답 생성에 성공했습니다("서울", 2.9초).
- blob의 1바이트를 바꾸면 `verify`가 손상을 감지하고 실패로 끝났습니다.

### 6-3. 시스템 도구 ⏳ (미검증)
Homebrew 패키지(`ollama`, `ffmpeg`, `node@22`, `uv`)의 오프라인 설치는 이번에 검증하지 않았습니다. 다음 둘 중 하나로 진행할 수 있습니다.
- 같은 macOS·아키텍처의 Mac에서 `brew fetch --deps <패키지>`로 bottle을 받아 반입한 뒤 `brew install <bottle 파일>`로 설치
- 공식 설치 파일(Ollama.app, Node.js pkg)과 정적 ffmpeg 바이너리 사용 (`.env`의 `FFMPEG_BIN`·`FFPROBE_BIN`으로 경로 지정)

폐쇄망 장비를 처음 구성할 때 실제로 검증해야 합니다.

### 6-4. Frontend ⚠️
샌드박스 안에서 `next start`로 운영 서버를 실행하는 것은 확인했습니다. `npm ci`는 npm 레지스트리가 필요하므로, 준비한 `node_modules`를 그대로 반입하는 방식을 권장합니다.

## 7. 폐쇄망 통합 테스트 결과 ✅

`scripts/offline/run-offline-test.sh` 방식:
- macOS `sandbox-exec`로 외부 연결과 DNS를 모두 차단하고 localhost만 허용합니다.
- 별도 DB·저장소, 빈 `HF_HOME`을 씁니다.
- Ollama(:11435), 내부 SMTP 릴레이 대역(:2525), Backend, Worker, Frontend를 실행합니다.
- 사용자와 같은 경로(`:3000`)로 처리합니다.
- 테스트 중에는 샌드박스 프로세스의 네트워크 연결을 0.2초 간격으로 감시합니다.

결과 **14/14 통과**. 2회 실행했고 결과는 같습니다 ([1회차](test-reports/20261124-1753-e2e-offline.md), [2회차 — 종료 처리 수정 후](test-reports/20261124-1758-e2e-offline.md)):

| 영역 | 항목 | 결과 |
|---|---|---|
| 웹 | Frontend 응답, health(DB·Ollama·STT·화자 분리) | ✅ |
| LLM | 로컬 모델 목록 / 클라우드 모델 호출 거부 / 모델 받기 실패 | ✅ / ✅ / ✅ |
| 파이프라인 | 업로드 → STT → 화자 분리 → 통합 → 회의록 (COMPLETED) | ✅ |
| STT | 20개 문장, 대본 대비 유사도 0.965 | ✅ |
| 화자 분리 | 화자 1·2·3 배정 | ✅ |
| LLM | JSON 스키마, 정확도 채점 16/17 (실패 1건은 STT 이름 오인식이며 회의록에서는 보정됨) | ✅ |
| 문서 | DOCX 생성·다운로드 | ✅ |
| 이메일 | localhost SMTP 릴레이로 발송·수신 (내부 메일 서버 대역) | ✅ |
| DB | SQLite 저장·조회, `integrity_check=ok` | ✅ |
| 네트워크 | 샌드박스 프로세스의 외부 연결 **0건** | ✅ |

이 테스트에서 발견해 수정한 문제:
1. **메모리 측정이 작업을 멈춤** — 측정에 쓰던 `ps`는 setuid 프로그램이라 샌드박스에서 실행이 거부됩니다. 그 오류가 파이프라인의 오류 처리 바깥에서 발생해 작업이 '처리 중'으로 멈췄습니다.
   - 조치: RSS를 Mach `task_info`로 직접 읽도록 바꿨습니다(하위 프로세스 없음). 모든 측정 항목은 실패해도 `None`만 기록하고, 첫 측정도 오류 처리 안으로 옮겼습니다.
   - 회귀 테스트: `test_job_completes_when_resource_probes_fail`
2. **테스트 종료 후 정상 서비스가 테스트 DB를 바라봄** — 테스트용 환경변수(`DATABASE_URL`, `OLLAMA_BASE_URL` 등)가 남은 채로 정상 서비스가 재시작되었습니다. 실제 DB·파일은 변경되지 않았습니다.
   - 조치: 재시작 전에 테스트 변수를 모두 해제합니다.

## 8. 메모리 사용량 (24GB, 순차 처리) ✅

각 단계가 끝난 직후의 값입니다. 2분 회의, 폐쇄망 테스트 1회차에서 측정했습니다. 2회차도 오차 범위 안에서 같았습니다(화자 분리 6.8초, LLM 33.5초, MPS 최대 4.9GB, Ollama 10.3GB).

| 단계 | 시간(초) | Worker RSS | MLX | PyTorch MPS | Ollama | 시스템 여유 |
|---|---|---|---|---|---|---|
| 시작 (상주 LLM 해제 후) | 0.03 | 94MB | — | — | 0 | 86% |
| STT | 4.4 | 1.9GB | 1.5GB | — | 0 | 74% |
| STT 해제 | 0.05 | 1.6GB | 0.1MB | — | 0 | 77% |
| 화자 분리 | 7.3 | 1.1GB | — | 4.9GB | 0 | 70% |
| 화자 분리 해제 | 0.17 | 0.97GB | — | 1.0GB | 0 | 83% |
| 화자 통합 | 0.0 | — | — | — | 0 | 83% |
| LLM (qwen3:14b) | 33.6 | 0.77GB | — | 51MB | 10.3GB | 32% |
| 완료·LLM 해제 | 0.01 | 0.77GB | — | 51MB | 0 | 57% |

- STT, 화자 분리, LLM이 동시에 메모리에 올라가지 않습니다. 가장 큰 구간은 LLM 단계로, Ollama 10.3GB에 Worker 0.8GB가 더해집니다.
- 작업을 시작하기 전과 끝난 뒤에는 Ollama 모델을 내립니다(`LLM_UNLOAD_AFTER_JOB=true`).
- 참고로, 36분 회의 측정(PHASE 6, 화자 분리 도입 전)에서는 Worker 최대 약 2GB, Ollama 10.3GB였습니다.

## 9. 개선 필요 사항

1. **PyTorch MPS 메모리 잔류** — 화자 분리 후 `empty_cache()`를 호출해도 드라이버 할당량이 약 1GB 남고, LLM 단계에서야 51MB로 줄어듭니다.
   - 24GB에서는 문제가 없습니다.
   - 긴 회의(1시간 이상)에서 화자 분리 단계의 최대 사용량(이번에 4.9GB)이 얼마나 늘어나는지는 측정하지 않았습니다.
2. **Homebrew 도구의 오프라인 설치는 미검증 (6-3)** — 폐쇄망 장비를 처음 구성할 때 확인해야 합니다.
3. **Ollama `brew services restart` 시 `OLLAMA_NO_CLOUD` 소실** — PHASE 7(launchd)에서 별도 LaunchAgent로 고정하는 것을 권장합니다.
4. **pyannoteai-sdk 설치됨** — 사용하지 않지만 pyannote.audio의 의존성이라 제거하지 않았습니다. 앱이 클라우드 파이프라인(`pyannoteAI/...`)을 부르지 않는다는 점은 코드 검색으로만 확인했습니다.
5. **wheelhouse는 이 Mac(arm64, Python 3.12) 전용입니다.** 다른 아키텍처나 Python 버전에서는 다시 만들어야 합니다.
6. **폐쇄망 테스트 범위** — 2분 합성 회의만 진행했습니다. 긴 회의는 일반 환경에서만 검증했습니다(PHASE 6, 36분, 26/27).
