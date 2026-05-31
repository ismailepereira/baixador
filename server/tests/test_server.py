"""Smoke tests do servidor Baixador.

Roda com:  .venv/Scripts/pytest server/tests/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# adiciona server/ ao sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402


@pytest.fixture
def client():
    server.app.config["TESTING"] = True
    with server.app.test_client() as c:
        yield c


# === Health / version ===

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["version"] == server.__version__
    assert "qualities" in data and "1080p" in data["qualities"]


# === Spotify URL detection ===

@pytest.mark.parametrize("url,expected", [
    ("https://open.spotify.com/track/abc123", "track"),
    ("https://open.spotify.com/playlist/xyz", "playlist"),
    ("https://open.spotify.com/album/aaa", "album"),
    ("https://open.spotify.com/artist/bbb", "artist"),
    ("https://open.spotify.com/episode/ccc", "episode"),
    ("https://open.spotify.com/show/ddd", "show"),
    ("https://open.spotify.com/", "unknown"),
    ("https://example.com/", "unknown"),
])
def test_spotify_kind(url, expected):
    assert server._spotify_kind(url) == expected


def test_is_spotify_url():
    assert server._is_spotify("https://open.spotify.com/track/abc")
    assert server._is_spotify("spotify:track:abc")
    assert not server._is_spotify("https://youtube.com/watch?v=abc")


# === Version comparison ===

def test_version_tuple():
    assert server._version_tuple("1.2.3") == (1, 2, 3)
    assert server._version_tuple("v0.1.0") == (0, 1, 0)
    assert server._version_tuple("invalid") == (0, 0, 0)
    assert server._version_tuple("2.0.0") > server._version_tuple("1.9.9")


# === Cookies file ===

def test_cookies_file_from_payload_empty():
    assert server._cookies_file_from_payload([]) is None
    assert server._cookies_file_from_payload(None) is None  # type: ignore


def test_cookies_file_from_payload_writes_netscape(tmp_path):
    cookies = [
        {"name": "sessionid", "value": "abc123",
         "domain": ".instagram.com", "path": "/",
         "secure": True, "hostOnly": False, "expirationDate": 9999999999},
    ]
    path = server._cookies_file_from_payload(cookies)
    assert path is not None
    try:
        content = Path(path).read_text(encoding="utf-8")
        assert content.startswith("# Netscape HTTP Cookie File")
        assert "sessionid" in content
        assert "abc123" in content
        assert ".instagram.com" in content
    finally:
        Path(path).unlink(missing_ok=True)


# === Partial cleanup ===

def test_cleanup_partials_removes_part_files(tmp_path):
    (tmp_path / "real.mp4").write_text("video")
    (tmp_path / "incompleto.mp4.part").write_text("partial")
    (tmp_path / "info.ytdl").write_text("info")
    (tmp_path / "temp.tmp").write_text("temp")
    sub = tmp_path / "playlist"
    sub.mkdir()
    (sub / "track.mp3").write_text("audio")
    (sub / "track.mp3.part").write_text("partial")

    n = server._cleanup_partials(str(tmp_path))
    assert n == 4
    assert (tmp_path / "real.mp4").exists()
    assert not (tmp_path / "incompleto.mp4.part").exists()
    assert not (tmp_path / "info.ytdl").exists()
    assert not (tmp_path / "temp.tmp").exists()
    assert (sub / "track.mp3").exists()
    assert not (sub / "track.mp3.part").exists()


def test_cleanup_partials_handles_missing_dir():
    assert server._cleanup_partials(None) == 0
    assert server._cleanup_partials("/caminho/que/nao/existe") == 0


# === Download endpoint validation ===

def test_download_requires_url(client):
    r = client.post("/download", json={})
    assert r.status_code == 400
    assert "url" in r.get_json()["error"]


def test_download_creates_job(client):
    # URL invalida mas o job e criado (vai falhar depois)
    r = client.post("/download", json={
        "url": "https://www.example.com/fake-video",
        "mode": "video",
        "quality": "720p",
    })
    assert r.status_code == 200
    data = r.get_json()
    assert "job_id" in data
    assert len(data["job_id"]) == 12


# === Jobs endpoint ===

def test_jobs_endpoint_returns_list(client):
    r = client.get("/jobs")
    assert r.status_code == 200
    assert "jobs" in r.get_json()


# === Status endpoint ===

def test_status_unknown_job(client):
    r = client.get("/status/jobnaoexiste")
    assert r.status_code == 404


# === Update check (sem feed configurado) ===

def test_check_update_disabled(client, monkeypatch):
    monkeypatch.setattr(server, "UPDATE_FEED_URL", "")
    r = client.get("/check-update")
    data = r.get_json()
    assert data["ok"] is False
    assert "desabilitado" in data["reason"]
