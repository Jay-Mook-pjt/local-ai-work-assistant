import httpx
from fastapi.testclient import TestClient

from app.api import health as health_module
from app.config import Settings, get_settings
from app.main import app


def test_health_reports_all_components():
    with TestClient(app) as client:
        r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert set(body["components"]) == {"database", "ollama", "stt", "diarization"}
    assert body["components"]["database"]["ok"] is True


def test_health_degraded_when_ollama_unreachable(monkeypatch):
    def broken_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(lambda req: (_ for _ in ()).throw(httpx.ConnectError("down")))
        return real_client(*args, **kwargs)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(health_module.httpx, "AsyncClient", broken_client)
    with TestClient(app) as client:
        body = client.get("/api/health").json()
    assert body["status"] == "degraded"
    assert body["components"]["ollama"]["ok"] is False


def test_settings_resolve_paths_to_project_root():
    s = get_settings()
    assert s.storage_dir.is_absolute()
    assert s.resolved_database_url.startswith("sqlite:////")
    assert Settings(allowed_audio_extensions=" MP3, .wav ").allowed_extension_set == {"mp3", "wav"}
