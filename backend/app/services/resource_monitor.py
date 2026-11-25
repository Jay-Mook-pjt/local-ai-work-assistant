"""Memory/time snapshots for each pipeline stage (24 GB unified memory budget).

Recorded per job in jobs.metrics and logged, so it is visible whether STT,
diarization and the LLM really ran one after another.
"""

import ctypes
import ctypes.util
import logging
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field

import httpx

from app.config import get_settings

MB = 1024 * 1024
log = logging.getLogger(__name__)


class _MachTaskBasicInfo(ctypes.Structure):
    _fields_ = [
        ("virtual_size", ctypes.c_uint64),
        ("resident_size", ctypes.c_uint64),
        ("resident_size_max", ctypes.c_uint64),
        ("user_time", ctypes.c_int32 * 2),
        ("system_time", ctypes.c_int32 * 2),
        ("policy", ctypes.c_int32),
        ("suspend_count", ctypes.c_int32),
    ]


def _rss_mb() -> float | None:
    """Current resident size via Mach task_info (no subprocess: `ps` is setuid and may be blocked by a sandbox)."""
    libc = ctypes.CDLL(ctypes.util.find_library("c"))
    libc.mach_task_self.restype = ctypes.c_uint32
    info = _MachTaskBasicInfo()
    count = ctypes.c_uint32(ctypes.sizeof(info) // 4)
    if libc.task_info(libc.mach_task_self(), 20, ctypes.byref(info), ctypes.byref(count)) != 0:  # 20 = MACH_TASK_BASIC_INFO
        return None
    return round(info.resident_size / MB, 1)


def _mlx_mb() -> float | None:
    if "mlx.core" not in sys.modules:
        return None
    import mlx.core as mx  # noqa: PLC0415

    return round(mx.get_active_memory() / MB, 1)


def _mps_mb() -> float | None:
    if "torch" not in sys.modules:
        return None
    import torch  # noqa: PLC0415

    if not torch.backends.mps.is_available():
        return None
    return round(torch.mps.driver_allocated_memory() / MB, 1)


def _ollama_mb() -> float | None:
    try:
        models = httpx.get(f"{get_settings().ollama_base_url}/api/ps", timeout=2).json().get("models", [])
    except (httpx.HTTPError, ValueError):
        return None
    return round(sum(m.get("size", 0) for m in models) / MB, 1)


def _system_free_pct() -> float | None:
    out = subprocess.run(["/usr/bin/memory_pressure", "-Q"], capture_output=True, text=True).stdout
    m = re.search(r"free percentage:\s*(\d+)%", out) or re.search(r"(\d+)%", out)
    return float(m.group(1)) if m else None


def _safe(probe) -> float | None:
    """Measurement must never break a job: any probe failure is recorded as None."""
    try:
        return probe()
    except Exception as exc:  # noqa: BLE001
        log.warning("resource probe %s failed: %s", probe.__name__, exc)
        return None


def snapshot() -> dict:
    return {
        "worker_rss_mb": _safe(_rss_mb),
        "mlx_active_mb": _safe(_mlx_mb),
        "torch_mps_mb": _safe(_mps_mb),
        "ollama_loaded_mb": _safe(_ollama_mb),
        "system_free_pct": _safe(_system_free_pct),
    }


@dataclass
class StageTimer:
    """Collects {stage, seconds, memory-after} records for one job."""

    records: list[dict] = field(default_factory=list)
    _t: float = field(default_factory=time.perf_counter)

    def mark(self, stage: str) -> dict:
        now = time.perf_counter()
        rec = {"stage": stage, "seconds": round(now - self._t, 2), **snapshot()}
        self.records.append(rec)
        self._t = time.perf_counter()  # exclude snapshot cost from the next stage
        return rec
