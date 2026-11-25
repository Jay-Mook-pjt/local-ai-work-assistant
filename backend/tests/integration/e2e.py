"""End-to-end integration harness for PHASE 6.

Synthesises a Korean meeting with known ground truth (macOS `say` + ffmpeg),
sends it through the real stack via the frontend (http://127.0.0.1:3000),
then grades the transcript and minutes and writes a Markdown report.

Examples (from backend/):
  .venv/bin/python -m tests.integration.e2e run short
  .venv/bin/python -m tests.integration.e2e run long --model qwen3:14b
  .venv/bin/python -m tests.integration.e2e recovery
  .venv/bin/python -m tests.integration.e2e persistence
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import httpx

from tests.integration.scenarios import SCENARIOS, Scenario

import os

ROOT = Path(__file__).resolve().parents[3]
API = os.environ.get("E2E_API", "http://127.0.0.1:3000")
OLLAMA = os.environ.get("E2E_OLLAMA", "http://127.0.0.1:11434")
LOG_DIR = Path(os.environ.get("E2E_LOG_DIR", ROOT / "logs"))
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
REPORT_DIR = ROOT / "docs" / "test-reports"
# Pitch factors to make one TTS voice sound like different speakers.
VOICE = {"A": 1.0, "B": 0.82, "C": 1.12, "D": 0.92}


def norm(t: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t).lower()


def has(text: str, keyword: str) -> bool:
    """keyword may list alternatives: '1월|일월'."""
    return any(norm(k) in norm(text) for k in keyword.split("|"))


def fmt(sec: float) -> str:
    s = int(sec)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_ts(ts: str) -> float | None:
    m = re.match(r"^(\d{2}):(\d{2}):(\d{2})$", ts or "")
    return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) if m else None


# --------------------------------------------------------------------------- synthesis


def _duration(p: Path) -> float:
    return float(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True).stdout)


def _render_line(i: int, speaker: str, text: str, work: Path) -> Path:
    aiff, wav = work / f"l{i:04d}.aiff", work / f"l{i:04d}.wav"
    subprocess.run(["say", "-v", "Yuna", "-r", "175", "-o", str(aiff), text], check=True)
    f = VOICE[speaker]
    pitch = "aresample=44100" if f == 1.0 else f"asetrate=22050*{f},aresample=44100,atempo={1 / f:.4f}"
    subprocess.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y", "-i", str(aiff), "-af", f"{pitch},apad=pad_dur=0.7", "-ar", "44100", "-ac", "1", str(wav)], check=True)
    if _duration(wav) < 1.0:
        raise RuntimeError(f"TTS produced no audio for line {i} (is the Korean 'Yuna' voice installed?)")
    return wav


def synthesize(sc: Scenario, work: Path) -> tuple[Path, dict[str, float], str, float]:
    """Returns (m4a, fact_id → start seconds, script text, seconds spent)."""
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        wavs = list(pool.map(lambda a: _render_line(a[0], a[1][0], a[1][1], work), enumerate(sc.lines)))
    starts, t = {}, 0.0
    for line, wav in zip(sc.lines, wavs, strict=True):
        if len(line) > 2:
            starts[line[2]] = t
        t += _duration(wav)
    (work / "list.txt").write_text("".join(f"file '{w.name}'\n" for w in wavs))
    speech = work / "speech.wav"
    subprocess.run([FFMPEG, "-nostdin", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(work / "list.txt"), "-c:a", "pcm_s16le", str(speech)], check=True)
    out = work / f"{sc.name}.m4a"
    subprocess.run(
        [FFMPEG, "-nostdin", "-loglevel", "error", "-y", "-i", str(speech), "-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=0.015:duration={t:.2f}",
         "-filter_complex", "amix=inputs=2:duration=first:normalize=0", "-c:a", "aac", "-b:a", "96k", str(out)],
        check=True,
    )
    script = " ".join(line[1] for line in sc.lines)
    return out, starts, script, time.perf_counter() - t0


# --------------------------------------------------------------------------- resource sampling


class Sampler(threading.Thread):
    """Samples worker RSS, Ollama's loaded-model size (/api/ps — GPU memory is not
    fully visible in process RSS on Apple Silicon) and free memory every 2 s."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.peak_worker = self.peak_ollama = 0.0
        self.min_free_pct = 100.0

    def _rss_gb(self, pattern: str) -> float:
        pids = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout.split()
        total = 0
        for pid in pids:
            out = subprocess.run(["ps", "-o", "rss=", "-p", pid], capture_output=True, text=True).stdout.strip()
            total += int(out or 0)
        return total / 1024 / 1024

    def run(self):
        while not self.stop.is_set():
            self.peak_worker = max(self.peak_worker, self._rss_gb("worker.main"))
            try:
                models = httpx.get(f"{OLLAMA}/api/ps", timeout=2).json().get("models", [])
                self.peak_ollama = max(self.peak_ollama, sum(m.get("size", 0) for m in models) / 1024**3)
            except httpx.HTTPError:
                pass
            out = subprocess.run(["memory_pressure"], capture_output=True, text=True).stdout
            m = re.search(r"free percentage: (\d+)%", out)
            if m:
                self.min_free_pct = min(self.min_free_pct, float(m[1]))
            self.stop.wait(2)


# --------------------------------------------------------------------------- API flow


@dataclass
class RunResult:
    meeting_id: str
    job: dict
    stages: list[tuple[str, float]]
    transcript: dict | None
    minutes: dict | None
    total_s: float
    peak_worker_gb: float = 0
    peak_ollama_gb: float = 0
    min_free_pct: float = 100
    llm_calls: list[dict] = field(default_factory=list)


def wait_job(c: httpx.Client, job_id: str, timeout: float = 3600) -> tuple[dict, list[tuple[str, float]]]:
    t0, last, stages = time.time(), None, []
    while time.time() - t0 < timeout:
        job = c.get(f"/api/jobs/{job_id}").json()
        if job["status"] != last:
            stages.append((job["status"], time.time() - t0))
            last = job["status"]
            print(f"  +{time.time() - t0:6.1f}s {job['status']:<13} {job.get('message') or job.get('error') or ''}", flush=True)
        if job["status"] in ("COMPLETED", "FAILED"):
            return job, stages
        time.sleep(1)
    raise TimeoutError(job_id)


def run_meeting(c: httpx.Client, sc: Scenario, audio: Path, model: str | None) -> RunResult:
    m = c.post("/api/meetings", json={k: getattr(sc, k) for k in ("title", "meeting_date", "attendees", "purpose", "agenda", "instructions")}).raise_for_status().json()
    with audio.open("rb") as f:
        c.post(f"/api/meetings/{m['id']}/audio", files={"file": (audio.name, f, "audio/mp4")}, timeout=600).raise_for_status()
    sampler = Sampler()
    sampler.start()
    t0 = time.time()
    log_mark = _llm_log_size()
    job = c.post(f"/api/meetings/{m['id']}/analyze", json={"llm_model": model} if model else {}).raise_for_status().json()
    job, stages = wait_job(c, job["id"])
    total = time.time() - t0
    sampler.stop.set()
    sampler.join()
    return RunResult(
        meeting_id=m["id"], job=job, stages=stages, total_s=total,
        transcript=c.get(f"/api/meetings/{m['id']}/transcript").json(),
        minutes=c.get(f"/api/meetings/{m['id']}/minutes").json(),
        peak_worker_gb=sampler.peak_worker, peak_ollama_gb=sampler.peak_ollama, min_free_pct=sampler.min_free_pct,
        llm_calls=_llm_calls_since(log_mark),
    )


def _llm_log_size() -> int:
    p = LOG_DIR / "llm_calls.log"
    return p.stat().st_size if p.exists() else 0


def _llm_calls_since(offset: int) -> list[dict]:
    p = LOG_DIR / "llm_calls.log"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as f:
        f.seek(offset)
        return [json.loads(line) for line in f if line.strip()]


# --------------------------------------------------------------------------- grading


@dataclass
class Check:
    area: str
    name: str
    ok: bool
    detail: str


def grade(sc: Scenario, r: RunResult, starts: dict[str, float], script: str) -> tuple[list[Check], dict]:
    checks: list[Check] = []
    mn = r.minutes or {}
    segs = (r.transcript or {}).get("segments", [])
    transcript_text = " ".join(s["text"] for s in segs)
    metrics: dict = {}

    # STT similarity (character level, punctuation/spacing ignored; Korean numerals vs digits differ).
    sm = SequenceMatcher(None, norm(script), norm(transcript_text), autojunk=False)
    metrics["stt_similarity"] = round(sm.ratio(), 4)
    metrics["segments"] = len(segs)
    checks.append(Check("STT", "전사 유사도 ≥ 0.90", sm.ratio() >= 0.90, f"{sm.ratio():.3f}"))
    for name in [a.split()[0] for a in sc.attendees if a.split()[0] in script]:
        ok = name in transcript_text
        checks.append(Check("STT", f"참석자 이름 '{name}' 인식", ok, "정확" if ok else "오인식 (회의록 단계에서 참석자 명단으로 보정되는지는 업무 담당자 항목에서 확인)"))

    decisions = mn.get("decisions", [])
    actions = mn.get("action_items", [])
    opens = mn.get("open_issues", []) + mn.get("next_meeting_checks", [])

    def ts_error(item_ts: str, fact: str) -> str:
        t = parse_ts(item_ts)
        if t is None or fact not in starts:
            return "시각 없음"
        return f"{item_ts} (정답 {fmt(starts[fact])}, 오차 {abs(t - starts[fact]):.0f}s)"

    for e in sc.expect.decisions:
        hit = next((d for d in decisions if all(has(d["content"] + d.get("evidence", ""), k) for k in e["keywords"])), None)
        checks.append(Check("결정", f"{e['id']} 포함", hit is not None, ts_error(hit["timestamp"], e["id"]) if hit else "누락"))
        if hit and parse_ts(hit["timestamp"]) is not None and e["id"] in starts:
            checks.append(Check("결정", f"{e['id']} 타임스탬프 ±20s", abs(parse_ts(hit["timestamp"]) - starts[e["id"]]) <= 20, hit["timestamp"]))
    for e in sc.expect.not_decisions:
        bad = [d["content"] for d in decisions if all(has(d["content"], k) for k in e["keywords"])]
        checks.append(Check("결정", f"{e['id']}는 결정이 아님", not bad, "; ".join(bad) or "정상"))

    attendee_cores = {norm(a.split()[0]) for a in sc.attendees}
    for e in sc.expect.actions:
        hit = next((a for a in actions if all(has(a["task"] + a.get("evidence", ""), k) for k in e["keywords"])), None)
        checks.append(Check("업무", f"{e['id']} 포함", hit is not None, f"{hit['task']} / {hit['assignee']} / {hit['deadline']}" if hit else "누락"))
        if hit:
            checks.append(Check("업무", f"{e['id']} 담당자={e['assignee']}", has(hit["assignee"], e["assignee"]), hit["assignee"]))
            checks.append(Check("업무", f"{e['id']} 기한~{e['deadline']}", has(hit["deadline"], e["deadline"]), hit["deadline"]))
    for e in sc.expect.unassigned:
        hit = next((a for a in actions if all(has(a["task"], k) for k in e["keywords"])), None)
        in_open = any(all(has(o, k) for k in e["keywords"]) for o in opens)
        if hit:
            checks.append(Check("업무", f"{e['id']} 담당 미정 유지", hit["assignee"] == "미확인", f"후속 업무, 담당={hit['assignee']}"))
        else:
            checks.append(Check("업무", f"{e['id']} 기록됨", in_open, "미결 사항에만 있음" if in_open else "누락"))

    for e in sc.expect.open_items:
        ok = any(all(has(o, k) for k in e["keywords"]) for o in opens)
        checks.append(Check("미결", f"{e['id']} 미결/다음 회의", ok, "있음" if ok else "누락"))

    fabricated = [a["assignee"] for a in actions if a["assignee"] != "미확인" and not any(c in norm(a["assignee"]) for c in attendee_cores)]
    checks.append(Check("환각", "참석자 외 담당자 없음", not fabricated, ", ".join(fabricated) or "없음"))
    topics = " ".join(d["topic"] + d["content"] for d in mn.get("discussion_items", []))
    missing = [a for a in sc.agenda if not has(topics, a.split()[0])]
    checks.append(Check("안건", "모든 안건이 논의사항에 반영", not missing, ", ".join(missing) or "전체 반영"))
    metrics["review_notes"] = mn.get("review_notes", [])
    return checks, metrics


# --------------------------------------------------------------------------- report


def write_report(title: str, sections: list[str]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{datetime.now():%Y%m%d-%H%M}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}.md"
    path.write_text(f"# {title}\n\n생성: {datetime.now():%Y-%m-%d %H:%M}\n\n" + "\n\n".join(sections) + "\n", encoding="utf-8")
    return path


def section_for_run(sc: Scenario, audio_s: float, synth_s: float, r: RunResult, checks: list[Check], metrics: dict) -> str:
    stage_times = []
    for (st, t), nxt in zip(r.stages, [*r.stages[1:], (None, r.total_s)], strict=True):
        stage_times.append(f"{st} {nxt[1] - t:.0f}s")
    calls = r.llm_calls
    ok = sum(c.ok for c in checks)
    lines = [
        f"## 시나리오: {sc.name} — {sc.title}",
        f"- 음성 길이: **{fmt(audio_s)}** ({len(sc.lines)}문장, 합성 {synth_s:.0f}s)",
        f"- 결과: **{r.job['status']}** · 전체 처리 {r.total_s:.0f}s (실시간 대비 x{audio_s / r.total_s:.1f})",
        f"- 단계별: {' → '.join(stage_times)}",
        f"- LLM: {len(calls)}회 호출, 합계 {sum(c.get('seconds', 0) for c in calls):.0f}s, 모델 {', '.join(sorted({c['model'] for c in calls})) or '-'}"
        + (f", 실패 {sum(not c['ok'] for c in calls)}회" if any(not c["ok"] for c in calls) else ""),
        f"- 메모리 최대: Worker {r.peak_worker_gb:.1f}GB · Ollama {r.peak_ollama_gb:.1f}GB · 시스템 여유 최저 {r.min_free_pct:.0f}%",
        f"- STT: {metrics['segments']}개 구간, 대본 대비 유사도 {metrics['stt_similarity']:.3f}",
        f"- 채점: **{ok}/{len(checks)} 통과**",
        "",
        "| 영역 | 항목 | 결과 | 상세 |",
        "|---|---|---|---|",
        *[f"| {c.area} | {c.name} | {'✅' if c.ok else '❌'} | {c.detail} |" for c in checks],
    ]
    if r.job.get("error"):
        lines.append(f"\n오류: {r.job['error']}")
    if metrics["review_notes"]:
        lines += ["", "검토 항목(review_notes):", *[f"- {n}" for n in metrics["review_notes"]]]
    mn = r.minutes or {}
    lines += ["", "<details><summary>생성된 회의록 요약·결정·업무</summary>", "", f"요약: {mn.get('meeting_summary', '')}", ""]
    lines += [f"- 결정 [{d['timestamp']}] {d['content']}" for d in mn.get("decisions", [])]
    lines += [f"- 업무 [{a['timestamp']}] {a['task']} — {a['assignee']} / {a['deadline']}" for a in mn.get("action_items", [])]
    lines += [f"- 미결: {x}" for x in mn.get("open_issues", [])]
    lines += [f"- 다음 회의: {x}" for x in mn.get("next_meeting_checks", [])]
    lines += ["", "</details>"]
    return "\n".join(lines)


# --------------------------------------------------------------------------- commands


def cmd_run(args) -> int:
    sc = SCENARIOS[args.scenario]()
    work = Path(tempfile.mkdtemp(prefix=f"lawa-e2e-{sc.name}-"))
    print(f"[{sc.name}] synthesising {len(sc.lines)} lines …", flush=True)
    audio, starts, script, synth_s = synthesize(sc, work)
    audio_s = _duration(audio)
    print(f"[{sc.name}] audio {fmt(audio_s)} ({audio.stat().st_size / 1e6:.1f} MB); running pipeline …", flush=True)
    with httpx.Client(base_url=API, timeout=120) as c:
        r = run_meeting(c, sc, audio, args.model)
        checks, metrics = grade(sc, r, starts, script)
        if not args.keep:
            c.delete(f"/api/meetings/{r.meeting_id}")
    shutil.rmtree(work, ignore_errors=True)
    path = write_report(f"E2E {sc.name}", [section_for_run(sc, audio_s, synth_s, r, checks, metrics)])
    ok = sum(c.ok for c in checks)
    print(f"[{sc.name}] {r.job['status']} · {ok}/{len(checks)} checks passed · report: {path}")
    for c in checks:
        if not c.ok:
            print(f"   ❌ {c.area} {c.name}: {c.detail}")
    return 0 if r.job["status"] == "COMPLETED" else 1


def _stt_runs() -> int:
    """Number of real Whisper runs logged by the worker so far."""
    log = ROOT / "logs" / "worker.log"
    return sum(" STT " in line for line in log.open(encoding="utf-8")) if log.exists() else 0


def _worker_pid() -> int:
    return int((ROOT / "logs" / "run" / "worker.pid").read_text())


def _start_worker(env_extra: dict[str, str] | None = None) -> None:
    import os  # noqa: PLC0415

    env = {**os.environ, **(env_extra or {})}
    log = (ROOT / "logs" / "worker.out.log").open("a")
    p = subprocess.Popen([str(ROOT / "backend/.venv/bin/python"), "-m", "worker.main"], cwd=ROOT / "backend", env=env, stdout=log, stderr=log)
    (ROOT / "logs" / "run" / "worker.pid").write_text(str(p.pid))
    time.sleep(3)


def _stop_worker(sig: str = "-TERM") -> None:
    subprocess.run(["kill", sig, str(_worker_pid())], check=False)
    time.sleep(3)


def cmd_recovery(args) -> int:
    """1) worker killed mid-transcription → FAILED → retry succeeds
    2) Ollama unreachable → FAILED with clear message, transcript kept → retry reuses it
    3) invalid upload rejected, nothing stored"""
    sc = SCENARIOS["short"]()
    work = Path(tempfile.mkdtemp(prefix="lawa-e2e-recovery-"))
    audio, *_ = synthesize(sc, work)
    out: list[str] = ["## 오류 복구 시나리오"]
    checks: list[Check] = []
    with httpx.Client(base_url=API, timeout=120) as c:
        def new_meeting():
            m = c.post("/api/meetings", json={k: getattr(sc, k) for k in ("title", "meeting_date", "attendees", "purpose", "agenda", "instructions")}).json()
            with audio.open("rb") as f:
                c.post(f"/api/meetings/{m['id']}/audio", files={"file": (audio.name, f, "audio/mp4")}).raise_for_status()
            return m

        # 1. kill -9 the worker while it is busy
        print("[recovery] 1/3 worker crash during processing", flush=True)
        m = new_meeting()
        job = c.post(f"/api/meetings/{m['id']}/analyze").json()
        for _ in range(120):
            st = c.get(f"/api/jobs/{job['id']}").json()["status"]
            if st in ("TRANSCRIBING", "ANALYZING"):
                break
            time.sleep(0.5)
        _stop_worker("-KILL")
        stuck = c.get(f"/api/jobs/{job['id']}").json()
        _start_worker()
        after = c.get(f"/api/jobs/{job['id']}").json()
        checks.append(Check("복구", "강제 종료 시점 작업 상태", stuck["status"] in ("TRANSCRIBING", "ANALYZING"), stuck["status"]))
        checks.append(Check("복구", "재시작 시 중단 작업을 실패로 표시", after["status"] == "FAILED" and "중단" in (after["error"] or ""), f"{after['status']}: {after['error']}"))
        retry = c.post(f"/api/meetings/{m['id']}/analyze").json()
        done, _ = wait_job(c, retry["id"])
        checks.append(Check("복구", "다시 처리하면 완료", done["status"] == "COMPLETED", done["status"]))
        c.delete(f"/api/meetings/{m['id']}")

        # 2. LLM down: restart the worker pointed at a closed port
        print("[recovery] 2/3 Ollama unreachable", flush=True)
        _stop_worker()
        _start_worker({"OLLAMA_BASE_URL": "http://127.0.0.1:9"})
        m = new_meeting()
        job = c.post(f"/api/meetings/{m['id']}/analyze").json()
        failed, _ = wait_job(c, job["id"])
        transcript = c.get(f"/api/meetings/{m['id']}/transcript").json()
        checks.append(Check("복구", "LLM 연결 실패 시 명확한 오류", failed["status"] == "FAILED" and "Ollama" in (failed["error"] or ""), failed.get("error") or ""))
        checks.append(Check("복구", "실패해도 전사문은 보존", bool(transcript and transcript["segments"]), f"{len(transcript['segments']) if transcript else 0}개 구간"))
        _stop_worker()
        _start_worker()
        t0 = time.time()
        stt_runs_before = _stt_runs()
        retry = c.post(f"/api/meetings/{m['id']}/analyze").json()
        done, stages = wait_job(c, retry["id"])
        reused = _stt_runs() == stt_runs_before
        checks.append(Check("복구", "Ollama 복구 후 재처리 완료", done["status"] == "COMPLETED", f"{done['status']} ({time.time() - t0:.0f}s)"))
        checks.append(Check("복구", "재처리 시 전사문 재사용(STT 생략)", reused, " → ".join(s for s, _ in stages)))
        c.delete(f"/api/meetings/{m['id']}")

        # 3. invalid upload
        print("[recovery] 3/3 invalid upload", flush=True)
        m = c.post("/api/meetings", json={"title": "잘못된 파일 테스트", "meeting_date": "2026-11-25"}).json()
        fake = work / "fake.m4a"
        fake.write_text("this is not audio")
        r = c.post(f"/api/meetings/{m['id']}/audio", files={"file": ("fake.m4a", fake.open("rb"), "audio/mp4")})
        stored = list((ROOT / "storage/audio/original" / m["id"]).glob("*")) if (ROOT / "storage/audio/original" / m["id"]).exists() else []
        checks.append(Check("복구", "음성이 아닌 파일 거부", r.status_code == 415, f"HTTP {r.status_code} {r.json().get('detail')}"))
        checks.append(Check("복구", "거부된 파일은 저장되지 않음", not stored, f"{len(stored)}개"))
        c.delete(f"/api/meetings/{m['id']}")
    shutil.rmtree(work, ignore_errors=True)
    out += ["", "| 영역 | 항목 | 결과 | 상세 |", "|---|---|---|---|", *[f"| {k.area} | {k.name} | {'✅' if k.ok else '❌'} | {k.detail} |" for k in checks]]
    path = write_report("E2E recovery", ["\n".join(out)])
    print(f"[recovery] {sum(k.ok for k in checks)}/{len(checks)} passed · report: {path}")
    for k in checks:
        if not k.ok:
            print(f"   ❌ {k.name}: {k.detail}")
    return 0 if all(k.ok for k in checks) else 1


def cmd_persistence(args) -> int:
    """Data survives a full stop/start of all services; SQLite integrity check."""
    import sqlite3  # noqa: PLC0415

    with httpx.Client(base_url=API, timeout=60) as c:
        before = {m["id"]: m for m in c.get("/api/meetings").json()}
        detail_before = {mid: (c.get(f"/api/meetings/{mid}/minutes").json(), c.get(f"/api/meetings/{mid}/documents").json()) for mid in before}
    files_before = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "storage").rglob("*") if p.is_file())
    subprocess.run([str(ROOT / "scripts/stop.sh")], check=True, capture_output=True)
    subprocess.run([str(ROOT / "scripts/start.sh")], check=True, capture_output=True)
    for _ in range(60):
        try:
            if httpx.get(f"{API}/api/health", timeout=3).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    with httpx.Client(base_url=API, timeout=60) as c:
        after = {m["id"]: m for m in c.get("/api/meetings").json()}
        detail_after = {mid: (c.get(f"/api/meetings/{mid}/minutes").json(), c.get(f"/api/meetings/{mid}/documents").json()) for mid in after}
    files_after = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "storage").rglob("*") if p.is_file())
    con = sqlite3.connect(ROOT / "database/meeting.db")
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    con.close()
    checks = [
        Check("보존", "재시작 후 회의 목록 동일", before == after, f"{len(before)}건 → {len(after)}건"),
        Check("보존", "회의록·문서 목록 동일", detail_before == detail_after, f"{len(detail_after)}개 회의 비교"),
        Check("보존", "저장 파일 동일", files_before == files_after, f"{len(files_after)}개 파일"),
        Check("보존", "SQLite 무결성 검사", integrity == "ok", integrity),
    ]
    path = write_report("E2E persistence", ["## 데이터 보존(전체 서비스 재시작)\n\n| 영역 | 항목 | 결과 | 상세 |\n|---|---|---|---|\n" + "\n".join(f"| {k.area} | {k.name} | {'✅' if k.ok else '❌'} | {k.detail} |" for k in checks)])
    print(f"[persistence] {sum(k.ok for k in checks)}/{len(checks)} passed · report: {path}")
    return 0 if all(k.ok for k in checks) else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="synthesise a meeting and grade the full pipeline")
    r.add_argument("scenario", choices=sorted(SCENARIOS))
    r.add_argument("--model", help="LLM model (default: the app setting)")
    r.add_argument("--keep", action="store_true", help="keep the meeting in the app afterwards")
    sub.add_parser("recovery", help="worker crash / LLM outage / bad upload")
    sub.add_parser("persistence", help="restart all services and compare data")
    args = ap.parse_args()
    sys.exit({"run": cmd_run, "recovery": cmd_recovery, "persistence": cmd_persistence}[args.cmd](args))


if __name__ == "__main__":
    main()
