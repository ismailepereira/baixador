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
    assert "premiere" in data["profiles"]


# === Perfis de saida de video ===

@pytest.mark.parametrize("quality,expected", [
    ("best", None),
    ("1080p", 1080),
    ("720p", 720),
    ("360p", 360),
    ("", None),
])
def test_height_limit(quality, expected):
    assert server._height_limit(quality) == expected


def test_editor_format_prioriza_h264_e_aac():
    fmt = server._editor_format(720)
    # A primeira alternativa da cadeia e a que o yt-dlp tenta antes de tudo.
    first = fmt.split("/")[0]
    assert "vcodec^=avc1" in first
    assert "acodec^=mp4a" in first
    assert "height<=720" in first


def test_editor_format_sem_limite_de_altura():
    assert "height" not in server._editor_format(None)


def _flag(args: list[str], flag: str) -> str | None:
    return args[args.index(flag) + 1] if flag in args else None


def test_profile_padrao_mantem_comportamento_antigo():
    args = server._profile_args("padrao", "720p")
    assert _flag(args, "-f") == server.QUALITY_FORMATS["720p"]
    assert _flag(args, "--merge-output-format") == "mp4"


def test_profile_premiere_forca_h264_e_normaliza_audio():
    args = server._profile_args("premiere", "best")
    assert "vcodec^=avc1" in _flag(args, "-f")
    assert _flag(args, "--merge-output-format") == "mp4"
    assert "-c:a aac" in _flag(args, "--postprocessor-args")


def test_profile_capcut_limita_em_1080p():
    # Mesmo pedindo "best", o CapCut nao deve receber 4K.
    assert "height<=1080" in _flag(server._profile_args("capcut", "best"), "-f")
    # E uma escolha menor que o teto continua valendo.
    assert "height<=720" in _flag(server._profile_args("capcut", "720p"), "-f")


def test_profile_prores_recoda_pra_mov():
    args = server._profile_args("prores", "best")
    assert _flag(args, "--recode-video") == "mov"
    assert "prores_ks" in _flag(args, "--postprocessor-args")


def test_profile_desconhecido_cai_no_padrao():
    assert server._profile_args("inventado", "720p") == server._profile_args("padrao", "720p")


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
