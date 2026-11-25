"""Local model store: everything the AI pipeline needs, in one project folder.

    models/
      whisper-large-v3-turbo/              ← STT_MODEL (mlx-community/whisper-large-v3-turbo)
      speaker-diarization-community-1/     ← DIARIZATION_MODEL (pyannote, gated)

At runtime the app loads from these folders (no Hugging Face lookup, no token).
Ollama models live in Ollama's own store (~/.ollama/models), see README.

Commands (run from backend/, on a machine with internet for `fetch`):
    .venv/bin/python -m app.services.model_store status
    .venv/bin/python -m app.services.model_store fetch        # copy from HF cache, else download
    .venv/bin/python -m app.services.model_store verify       # required files present?
    .venv/bin/python -m app.services.model_store verify --load  # also load both models offline
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.config import PROJECT_ROOT, get_settings


@dataclass
class ModelSpec:
    key: str
    repo: str
    folder: str
    gated: bool = False


@dataclass
class Check:
    key: str
    path: Path
    ok: bool
    missing: list[str] = field(default_factory=list)


def models_dir() -> Path:
    d = get_settings().models_dir
    return d if d.is_absolute() else (PROJECT_ROOT / d).resolve()


def specs() -> list[ModelSpec]:
    s = get_settings()
    out = [ModelSpec("stt", s.stt_model, Path(s.stt_model).name)]
    if s.diarization_enabled or s.diarization_model:
        out.append(ModelSpec("diarization", s.diarization_model, Path(s.diarization_model).name, gated=True))
    return out


def local_path(repo_or_path: str) -> Path | None:
    """Folder to load a model from: an explicit existing path, else models/<name>."""
    p = Path(repo_or_path).expanduser()
    if p.is_absolute() and p.exists():
        return p
    candidate = models_dir() / Path(repo_or_path).name
    return candidate if candidate.exists() else None


def resolve(repo_or_path: str) -> str:
    """What to hand to the model library: the local folder if present, else the repo id
    (which then only works from the Hugging Face cache, since runtime is offline)."""
    p = local_path(repo_or_path)
    return str(p) if p else repo_or_path


def _required_files(spec: ModelSpec, root: Path) -> list[str]:
    if spec.key == "stt":
        weights = "weights.safetensors" if (root / "weights.safetensors").exists() else "weights.npz"
        return ["config.json", weights]
    # pyannote pipeline: config.yaml + every "$model/<sub>" component it references
    req = ["config.yaml"]
    cfg = root / "config.yaml"
    if cfg.exists():
        subs = sorted(set(re.findall(r"\$model/([\w./-]+)", cfg.read_text(encoding="utf-8"))))
        for sub in subs:
            sub_dir = root / sub
            files = [f.name for f in sub_dir.iterdir()] if sub_dir.is_dir() else []
            weights = [f for f in files if f.endswith((".bin", ".ckpt", ".safetensors", ".npz"))]
            req += [f"{sub}/{w}" for w in weights] or [f"{sub}/<weights>"]
    return req


def verify() -> list[Check]:
    out = []
    for spec in specs():
        root = local_path(spec.repo)
        if root is None:
            out.append(Check(spec.key, models_dir() / spec.folder, False, ["(폴더 없음)"]))
            continue
        missing = [f for f in _required_files(spec, root) if not (root / f).exists()]
        out.append(Check(spec.key, root, not missing, missing))
    return out


def _hf_token() -> str:
    s = get_settings()
    r = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-s", s.hf_keychain_service, "-a", s.hf_keychain_account, "-w"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if r.returncode != 0:
        raise SystemExit("키체인에 Hugging Face 토큰이 없습니다 (화자 분리 모델은 최초 1회 토큰이 필요합니다).")
    return r.stdout.strip()


def fetch() -> None:
    """Populate models/: copy from the local HF cache when possible (no network),
    otherwise download (needs internet; the gated pyannote model needs the token)."""
    from huggingface_hub import snapshot_download  # noqa: PLC0415

    models_dir().mkdir(parents=True, exist_ok=True)
    for spec in specs():
        target = models_dir() / spec.folder
        try:
            snapshot_download(spec.repo, local_dir=target, local_files_only=True)
            print(f"[{spec.key}] HF 캐시에서 복사: {target}")
        except Exception:  # noqa: BLE001 - not cached → go online
            token = _hf_token() if spec.gated else None
            snapshot_download(spec.repo, local_dir=target, token=token)
            print(f"[{spec.key}] 다운로드: {target}")


def load_test() -> list[str]:
    """Loads each model the way the worker does (must be run with HF_HUB_OFFLINE=1)."""
    import app.offline  # noqa: F401, PLC0415

    msgs = []
    import mlx_whisper.load_models as lm  # noqa: PLC0415

    lm.load_model(resolve(get_settings().stt_model))
    msgs.append("stt: 로딩 성공")
    if get_settings().diarization_enabled:
        from app.services import diarization_service  # noqa: PLC0415

        diarization_service.load_pipeline()
        msgs.append("diarization: 로딩 성공")
    return msgs


def _size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["status", "fetch", "verify"])
    ap.add_argument("--load", action="store_true", help="verify: also load the models (offline)")
    args = ap.parse_args()
    if args.command == "fetch":
        fetch()
    checks = verify()
    report = [{"model": c.key, "path": str(c.path), "ok": c.ok, "missing": c.missing, "size_mb": round(_size(c.path) / 1e6, 1)} for c in checks]
    if args.command == "verify" and args.load and all(c.ok for c in checks):
        report.append({"load": load_test()})
    print(json.dumps(report, ensure_ascii=False, indent=1))
    sys.exit(0 if all(c.ok for c in checks) else 1)


if __name__ == "__main__":
    main()
