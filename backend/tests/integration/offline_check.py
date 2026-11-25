"""Closed-network end-to-end check (PHASE 6-1).

Expects the stack to be running inside the no-network sandbox
(scripts/offline/run-offline-test.sh does that) and drives it like a user:

  web app → upload → STT → diarization → merge → Ollama minutes → JSON check
  → DOCX → SQLite read-back → email via the localhost (internal) SMTP relay

and records every remote endpoint the sandboxed processes open.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx

from tests.integration.e2e import API, OLLAMA, REPORT_DIR, Check, fmt, grade, run_meeting, section_for_run, synthesize, write_report
from tests.integration.scenarios import SCENARIOS

DATA = Path(os.environ["OFFLINE_DATA_DIR"])  # isolated DB/storage of the sandboxed run
PIDS = [int(p) for p in os.environ.get("OFFLINE_PIDS", "").split()]
LOCAL = ("127.0.0.1", "[::1]", "localhost", "*:")


class NetWatch(threading.Thread):
    """Polls lsof for the sandboxed processes and keeps every non-loopback endpoint."""

    def __init__(self, pids):
        super().__init__(daemon=True)
        self.pids, self.seen, self.stop = pids, set(), threading.Event()

    def run(self):
        while not self.stop.is_set():
            for pid in self.pids:
                out = subprocess.run(["lsof", "-nP", "-a", "-p", str(pid), "-i"], capture_output=True, text=True).stdout
                for line in out.splitlines()[1:]:
                    ep = line.split()[8] if len(line.split()) > 8 else ""
                    if ep and not all(part.startswith(LOCAL) for part in ep.split("->")):
                        self.seen.add(ep)
            self.stop.wait(0.2)


def main() -> int:
    checks: list[Check] = []
    watch = NetWatch(PIDS)
    watch.start()
    sc = SCENARIOS["short"]()
    work = Path(tempfile.mkdtemp(prefix="lawa-offline-"))
    print("[offline] synthesising meeting audio (outside the sandbox: test input only)", flush=True)
    audio, starts, script, _ = synthesize(sc, work)

    with httpx.Client(base_url=API, timeout=120) as c:
        r = c.get("/")
        checks.append(Check("웹", "Frontend 페이지 응답", r.status_code == 200, f"HTTP {r.status_code}"))
        h = c.get("/api/health").json()
        checks.append(Check("웹", "health (DB·Ollama·STT·화자 분리)", h["status"] == "ok", json.dumps({k: v["ok"] for k, v in h["components"].items()})))
        tags = httpx.get(f"{OLLAMA}/api/tags").json()["models"]
        checks.append(Check("LLM", "로컬 모델 목록 (샌드박스 Ollama)", bool(tags), ", ".join(m["name"] for m in tags)))
        r = httpx.post(f"{OLLAMA}/api/chat", json={"model": "gpt-oss:120b-cloud", "stream": False, "messages": [{"role": "user", "content": "hi"}]}, timeout=30)
        checks.append(Check("LLM", "클라우드 모델 호출 거부 (OLLAMA_NO_CLOUD)", r.status_code >= 400, r.text[:120]))
        r = httpx.post(f"{OLLAMA}/api/pull", json={"model": "gemma3:1b", "stream": False}, timeout=30)
        checks.append(Check("LLM", "모델 다운로드 시도는 실패 (폐쇄망)", r.status_code >= 400 or "error" in r.text, r.text[:120]))

        print("[offline] processing meeting (upload → STT → diarization → LLM)", flush=True)
        run = run_meeting(c, sc, audio, None)
        graded, metrics = grade(sc, run, starts, script)
        checks.append(Check("파이프라인", "처리 완료", run.job["status"] == "COMPLETED", f"{run.job['status']} {run.job.get('error') or ''}"))
        segs = (run.transcript or {}).get("segments", [])
        checks.append(Check("STT", "전사문 생성", len(segs) > 5, f"{len(segs)}개 문장, 유사도 {metrics['stt_similarity']}"))
        speakers = sorted({s["speaker"] for s in segs if s.get("speaker")})
        checks.append(Check("화자 분리", "화자 정보 통합", bool(speakers), ", ".join(speakers) or "없음"))
        mn = run.minutes or {}
        need = {"meeting_summary", "discussion_items", "decisions", "action_items", "open_issues", "next_meeting_checks"}
        checks.append(Check("LLM", "회의록 JSON 스키마", need <= set(mn), f"{len(mn.get('action_items', []))}개 업무, {len(mn.get('decisions', []))}개 결정"))
        passed = sum(g.ok for g in graded)
        checks.append(Check("LLM", "회의록 정확도 채점", passed >= len(graded) - 2, f"{passed}/{len(graded)}"))

        doc = c.post(f"/api/meetings/{run.meeting_id}/export").json()
        dl = c.get(f"/api/documents/{doc['id']}/download")
        checks.append(Check("문서", "DOCX 생성·다운로드", dl.status_code == 200 and dl.content[:2] == b"PK", f"{doc['filename']} {len(dl.content)} bytes"))

        pv = c.post(f"/api/meetings/{run.meeting_id}/email/preview", json={"to": ["team@internal.test"], "cc": [], "attach_docx": True}).json()
        sent = c.post(f"/api/meetings/{run.meeting_id}/email/send", json={"to": pv["to"], "cc": [], "subject": pv["subject"], "body": pv["body"], "attach_docx": True, "content_hash": pv["content_hash"], "confirm": True})
        maildir = DATA / "mailbox" / "new"
        checks.append(Check("이메일", "내부 SMTP 릴레이(localhost)로 발송", sent.status_code == 200 and any(maildir.iterdir()), f"HTTP {sent.status_code}, 수신 {len(list(maildir.iterdir()))}통"))

    con = sqlite3.connect(DATA / "meeting.db")
    rows = {
        "meetings": con.execute("select count(*) from meetings").fetchone()[0],
        "transcripts": con.execute("select count(*) from transcripts").fetchone()[0],
        "minutes": con.execute("select count(*) from meeting_minutes").fetchone()[0],
        "documents": con.execute("select count(*) from documents").fetchone()[0],
        "email_history": con.execute("select count(*) from email_history where status='SENT'").fetchone()[0],
    }
    integrity = con.execute("pragma integrity_check").fetchone()[0]
    con.close()
    checks.append(Check("DB", "SQLite 저장·조회", all(rows.values()) and integrity == "ok", f"{rows}, integrity={integrity}"))

    watch.stop.set()
    watch.join()
    checks.append(Check("네트워크", "샌드박스 프로세스의 외부 연결", not watch.seen, ", ".join(sorted(watch.seen)) or "0건"))
    shutil.rmtree(work, ignore_errors=True)

    stage_rows = ["| 단계 | 시간(초) | Worker RSS MB | MLX MB | PyTorch MPS MB | Ollama MB | 시스템 여유 % |", "|---|---|---|---|---|---|---|"]
    for m in run.job.get("metrics") or []:
        stage_rows.append(f"| {m['stage']} | {m['seconds']} | {m['worker_rss_mb']} | {m['mlx_active_mb']} | {m['torch_mps_mb']} | {m['ollama_loaded_mb']} | {m['system_free_pct']} |")
    table = ["| 영역 | 항목 | 결과 | 상세 |", "|---|---|---|---|", *[f"| {k.area} | {k.name} | {'✅' if k.ok else '❌'} | {k.detail} |" for k in checks]]
    path = write_report(
        "E2E offline",
        [
            "## 폐쇄망 통합 테스트 (sandbox-exec: 외부 네트워크·DNS 차단, localhost만 허용)",
            "\n".join(table),
            "## 단계별 처리 시간·메모리 (job.metrics)",
            "\n".join(stage_rows),
            section_for_run(sc, starts and max(starts.values()) or 0, 0, run, graded, metrics).replace("## 시나리오", "## 채점 상세 · 시나리오"),
        ],
    )
    print(f"[offline] {sum(k.ok for k in checks)}/{len(checks)} passed · report: {path}")
    for k in checks:
        print(f"  {'✅' if k.ok else '❌'} {k.area} · {k.name}: {k.detail}")
    return 0 if all(k.ok for k in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
