import pytest

from app.config import get_settings
from app.services.audio_service import safe_display_name
from app.services.media import sniff_format
from tests.conftest import make_meeting, upload


@pytest.mark.parametrize(
    ("name", "mime"),
    [("tone.wav", "audio/wav"), ("tone.mp3", "audio/mpeg"), ("tone.m4a", "audio/x-m4a"), ("clip.mp4", "video/mp4"), ("tone.wav", "application/octet-stream")],
)
def test_accepts_supported_audio(client, media_dir, name, mime):
    m = make_meeting(client)
    r = upload(client, m["id"], media_dir / name, mime=mime)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "UPLOADED"
    assert body["audio"]["filename"] == name
    assert body["audio"]["duration_seconds"] == pytest.approx(3, abs=0.3)
    stored = list((get_settings().storage_dir / "audio/original" / m["id"]).iterdir())
    assert len(stored) == 1 and stored[0].name != name  # server-generated name


def test_rejects_unsupported_extension(client, tmp_path):
    m = make_meeting(client)
    p = tmp_path / "notes.txt"
    p.write_text("hello")
    r = upload(client, m["id"], p, mime="text/plain")
    assert r.status_code == 415 and "지원하지 않는 형식" in r.json()["detail"]


def test_rejects_content_that_does_not_match_extension(client, media_dir):
    m = make_meeting(client)
    r = upload(client, m["id"], media_dir / "tone.wav", filename="fake.mp3", mime="audio/mpeg")
    assert r.status_code == 415 and ".mp3 형식이 아닙니다" in r.json()["detail"]


def test_rejects_mime_mismatch(client, media_dir):
    m = make_meeting(client)
    r = upload(client, m["id"], media_dir / "tone.mp3", mime="application/x-msdownload")
    assert r.status_code == 415


def test_rejects_video_without_audio(client, media_dir):
    m = make_meeting(client)
    r = upload(client, m["id"], media_dir / "silent_video.mp4", mime="video/mp4")
    assert r.status_code == 415 and "오디오 트랙" in r.json()["detail"]


def test_rejects_corrupt_file_with_valid_header(client, tmp_path):
    m = make_meeting(client)
    p = tmp_path / "broken.wav"
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 100)
    r = upload(client, m["id"], p, mime="audio/wav")
    assert r.status_code == 415


def test_rejects_empty_file(client, tmp_path):
    m = make_meeting(client)
    p = tmp_path / "empty.mp3"
    p.write_bytes(b"")
    assert upload(client, m["id"], p, mime="audio/mpeg").status_code == 400


def test_size_limit(client, media_dir, monkeypatch):
    m = make_meeting(client)
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)  # every byte is over the limit
    r = upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    assert r.status_code == 413
    assert not any((get_settings().storage_dir / "audio/original" / m["id"]).iterdir())  # partial file removed


def test_path_traversal_filename_is_neutralised(client, media_dir):
    m = make_meeting(client)
    r = upload(client, m["id"], media_dir / "tone.wav", filename="../../../etc/evil.wav", mime="audio/wav")
    assert r.status_code == 201
    assert r.json()["audio"]["filename"] == "evil.wav"
    root = get_settings().storage_dir.resolve()
    assert all(root in p.resolve().parents for p in root.rglob("*") if p.is_file())


def test_reupload_replaces_previous_file(client, media_dir):
    m = make_meeting(client)
    upload(client, m["id"], media_dir / "tone.wav", mime="audio/wav")
    r = upload(client, m["id"], media_dir / "tone.mp3", mime="audio/mpeg")
    assert r.json()["audio"]["filename"] == "tone.mp3"
    files = list((get_settings().storage_dir / "audio/original" / m["id"]).iterdir())
    assert [f.suffix for f in files] == [".mp3"]


def test_unknown_meeting(client, media_dir):
    assert upload(client, "f" * 32, media_dir / "tone.wav").status_code == 404


def test_safe_display_name():
    assert safe_display_name("..\\..\\win\\a.wav") == "a.wav"
    assert safe_display_name("/abs/path/회의.m4a") == "회의.m4a"
    assert safe_display_name("bad\x00\nname.mp3") == "badname.mp3"
    assert safe_display_name(None) == ""


def test_sniff_format():
    assert sniff_format(b"RIFF\x00\x00\x00\x00WAVEfmt ") == "wav"
    assert sniff_format(b"\x00\x00\x00\x20ftypM4A ") == "mp4"
    assert sniff_format(b"ID3\x04") == "mp3"
    assert sniff_format(b"\xff\xfb\x90\x00") == "mp3"
    assert sniff_format(b"MZ\x90\x00") is None
