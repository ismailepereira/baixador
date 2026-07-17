"""Servidor local do Baixador.

Recebe URLs da extensao Chrome e baixa usando yt-dlp/spotdl.
Roda em localhost:5005 e so aceita requisicoes do proprio Chrome.
"""
from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any

try:
    import browser_cookie3
except ImportError:
    browser_cookie3 = None

from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

DOWNLOADS_DIR = Path.home() / "Downloads" / "Baixador"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

FFMPEG_PATH = os.environ.get("BAIXADOR_FFMPEG", "").strip()


FROZEN = getattr(sys, "frozen", False)


def _find_tool(name: str) -> str:
    """Acha o executavel olhando primeiro nos Scripts/ do venv atual, depois no PATH."""
    scripts_dir = Path(sys.executable).parent
    for ext in (".exe", ""):
        candidate = scripts_dir / f"{name}{ext}"
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    return name  # fallback


def _tool_cmd(name: str) -> list[str]:
    """Retorna a lista de prefixo de comando para chamar 'name'.

    Em modo desenvolvimento: ["caminho/para/yt-dlp.exe"]
    Em modo frozen (PyInstaller bundle): [sys.executable, "--tool", "yt-dlp"]
    """
    if FROZEN:
        return [sys.executable, "--tool", name]
    return [_find_tool(name)]


__version__ = "1.1.2"
# Feed publico com {"version": "...", "url": "...", "notes": "..."}.
# E o update.json versionado na raiz do repo, servido pelo raw do GitHub.
# Publicar uma versao nova = editar o update.json, dar push, e anexar o instalador
# na Release correspondente (ver README > Publicar uma atualizacao).
# Defina BAIXADOR_UPDATE_FEED="" pra desligar a checagem.
UPDATE_FEED_URL = os.environ.get(
    "BAIXADOR_UPDATE_FEED",
    "https://raw.githubusercontent.com/ismailepereira/baixador/main/update.json",
)


YTDLP = _tool_cmd("yt-dlp")
SPOTDL = _tool_cmd("spotdl")
GALLERY_DL = _tool_cmd("gallery-dl")
print(f"yt-dlp:     {' '.join(YTDLP)}")
print(f"spotdl:     {' '.join(SPOTDL)}")
print(f"gallery-dl: {' '.join(GALLERY_DL)}")

PHOTOS_DIR = DOWNLOADS_DIR / "Fotos"
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

MOBILE_DIR = DOWNLOADS_DIR / ".mobile-temp"
MOBILE_DIR.mkdir(parents=True, exist_ok=True)


def _local_ip() -> str:
    """Detecta o IP da maquina na rede local (pra mostrar URL pro celular)."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _cookies_file_from_payload(cookies: list[dict]) -> str | None:
    """Salva cookies enviados pela extensao Chrome como Netscape cookies.txt."""
    if not cookies:
        return None
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="baixador_cookies_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                domain = c.get("domain") or ""
                # Em Netscape, o "host only" e indicado pelo dominio NAO comecar com "."
                host_only = c.get("hostOnly", False)
                if host_only and domain.startswith("."):
                    domain = domain[1:]
                elif not host_only and not domain.startswith("."):
                    domain = "." + domain
                f.write("\t".join([
                    domain,
                    "FALSE" if host_only else "TRUE",
                    c.get("path") or "/",
                    "TRUE" if c.get("secure") else "FALSE",
                    str(int(c.get("expirationDate") or 0)),
                    c.get("name") or "",
                    c.get("value") or "",
                ]) + "\n")
        print(f"[cookies] {len(cookies)} cookies salvos em {path}")
        return path
    except Exception as e:
        print(f"[cookies] erro ao escrever: {e}")
        return None

QUALITY_FORMATS = {
    "best":  "bestvideo*+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p":  "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "480p":  "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    "360p":  "bestvideo[height<=360]+bestaudio/best[height<=360]/best",
}

AUDIO_QUALITY = {
    "best": "0",  # VBR ~245 kbps
    "high": "2",  # ~190 kbps
    "med":  "5",  # ~130 kbps
}

# Perfis de saida do video.
#
# O YouTube entrega o melhor video em VP9/AV1 e o melhor audio em Opus. Trocar so
# o container pra .mp4 nao muda os codecs, e nenhum editor (Premiere, CapCut,
# Resolve) decodifica VP9/Opus -- daí o "arquivo nao suportado". Os perfis de
# edicao forcam H.264 + AAC, que todo NLE le nativamente.
VIDEO_PROFILES = ("padrao", "premiere", "capcut", "prores")


def _height_limit(quality: str) -> int | None:
    """'720p' -> 720; 'best' -> None (sem limite)."""
    try:
        return int((quality or "").rstrip("p"))
    except ValueError:
        return None


def _editor_format(max_height: int | None) -> str:
    """Cadeia de formatos que prioriza H.264 (avc1) + AAC (mp4a)."""
    h = f"[height<={max_height}]" if max_height else ""
    return (
        f"bestvideo[vcodec^=avc1]{h}+bestaudio[acodec^=mp4a]/"
        f"bestvideo[vcodec^=avc1]{h}+bestaudio/"
        f"best[vcodec^=avc1]{h}/"
        f"bestvideo{h}+bestaudio/best{h}"
    )


def _profile_args(profile: str, quality: str) -> list[str]:
    """Argumentos do yt-dlp para o perfil de saida escolhido."""
    if profile == "prores":
        # Re-encode pesado, mas o unico 100% garantido: ProRes 422 HQ + PCM em .mov.
        return [
            "-f", QUALITY_FORMATS.get(quality, QUALITY_FORMATS["best"]),
            "--recode-video", "mov",
            "--postprocessor-args",
            "VideoConvertor:-c:v prores_ks -profile:v 3 -pix_fmt yuv422p10le -c:a pcm_s16le",
        ]
    if profile in ("premiere", "capcut"):
        h = _height_limit(quality)
        if profile == "capcut":
            # CapCut engasga com 4K no celular; 1080p e o teto pratico.
            h = min(h or 1080, 1080)
        return [
            "-f", _editor_format(h),
            "--merge-output-format", "mp4",
            # Copia o video (ja e avc1) e normaliza o audio pra AAC mesmo que o
            # fallback tenha pego Opus.
            "--postprocessor-args", "Merger:-c:v copy -c:a aac -b:a 192k",
        ]
    return [
        "-f", QUALITY_FORMATS.get(quality, QUALITY_FORMATS["best"]),
        "--merge-output-format", "mp4",
    ]

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["chrome-extension://*"]}})

JOBS: dict[str, dict[str, Any]] = {}
JOB_LOCK = threading.Lock()


def _spawn(cmd: list[str], job_id: str, cleanup_files: list[str] | None, dest_dir: str | None = None) -> None:
    """Roda um comando externo e empurra cada linha de output na fila do job."""
    with JOB_LOCK:
        job = JOBS[job_id]
        job["status"] = "running"
        job["cmd"] = " ".join(cmd)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"   # spotdl/yt-dlp imprimem em tempo real
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(DOWNLOADS_DIR),
            env=env,
            bufsize=1,            # line-buffered
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except FileNotFoundError as e:
        with JOB_LOCK:
            JOBS[job_id]["status"] = "error"
            JOBS[job_id]["queue"].put(f"[erro] ferramenta nao encontrada: {e}\n")
            JOBS[job_id]["queue"].put(None)
        _cleanup(cleanup_files)
        return

    with JOB_LOCK:
        JOBS[job_id]["proc"] = proc

    assert proc.stdout is not None
    for line in proc.stdout:
        JOBS[job_id]["queue"].put(line)
    proc.wait()

    import time
    with JOB_LOCK:
        cur = JOBS[job_id]
        if cur["status"] != "cancelled":
            cur["status"] = "done" if proc.returncode == 0 else "error"
        cur["returncode"] = proc.returncode
        cur["ended_at"] = time.time()
        final_status = cur["status"]
        cur["queue"].put(None)
    _cleanup(cleanup_files)
    # Limpa arquivos parciais se o job foi cancelado ou deu erro
    if final_status in ("cancelled", "error") and dest_dir:
        n = _cleanup_partials(dest_dir)
        if n:
            print(f"[cleanup] {n} arquivos parciais removidos de {dest_dir}")


def _cleanup(files: list[str] | None) -> None:
    if not files:
        return
    for path in files:
        try:
            if path and os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass


PARTIAL_EXTS = (".part", ".ytdl", ".tmp", ".temp", ".part-Frag", ".aria2", ".download")


def _cleanup_partials(dest_dir: str | None) -> int:
    """Remove arquivos parciais (.part, .ytdl, .tmp, etc) recursivamente."""
    if not dest_dir or not os.path.isdir(dest_dir):
        return 0
    removed = 0
    for root, _, files in os.walk(dest_dir):
        for f in files:
            if f.endswith(PARTIAL_EXTS) or ".part-" in f or f.endswith(".part.json"):
                try:
                    os.unlink(os.path.join(root, f))
                    removed += 1
                except Exception:
                    pass
    return removed


def _start_job(
    cmd: list[str],
    cleanup_files: list[str] | None = None,
    dest_dir: str | None = None,
    metadata: dict | None = None,
) -> str:
    import time
    job_id = uuid.uuid4().hex[:12]
    with JOB_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "status": "queued",
            "queue": queue.Queue(),
            "cmd": "",
            "returncode": None,
            "proc": None,
            "started_at": time.time(),
            "ended_at": None,
            **(metadata or {}),
        }
    threading.Thread(
        target=_spawn, args=(cmd, job_id, cleanup_files, dest_dir), daemon=True
    ).start()
    return job_id


@app.route("/cancel/<job_id>", methods=["POST"])
def cancel(job_id: str) -> Response:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "job desconhecido"}), 404
        proc = job.get("proc")
        if not proc or proc.poll() is not None:
            return jsonify({"ok": False, "reason": "ja finalizado"})
        job["status"] = "cancelled"
    try:
        # Em Windows, terminate() chama TerminateProcess (forceful)
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


def _is_spotify(url: str) -> bool:
    return "spotify.com" in url or url.startswith("spotify:")


def _spotify_kind(url: str) -> str:
    """track / playlist / album / artist / episode / show / unknown."""
    import re
    m = re.search(r"/(track|playlist|album|artist|episode|show)/", url)
    return m.group(1) if m else "unknown"


# =========================================================
# UI Mobile (PWA simples acessivel via WiFi pelo celular)
# =========================================================

MOBILE_HTML = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<meta name="theme-color" content="#1f8a3a">
<title>Baixador Mobile</title>
<link rel="manifest" href="/mobile-manifest.json">
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 16px;
    font: 16px/1.4 -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    background: #1c1c1e; color: #f5f5f7;
    min-height: 100vh;
  }
  h1 { font-size: 22px; margin: 8px 0 4px; display: flex; align-items: center; gap: 8px; }
  h1 .icon {
    display: inline-flex; align-items: center; justify-content: center;
    width: 36px; height: 36px; background: #1f8a3a; border-radius: 50%; font-size: 20px;
  }
  .subtitle { color: #888; font-size: 12px; margin: 0 0 20px; }
  textarea {
    width: 100%; min-height: 80px; resize: vertical;
    background: #2c2c2e; color: #f5f5f7;
    border: 2px solid #3a3a3c; border-radius: 10px;
    padding: 12px; font: 14px/1.4 ui-monospace, Consolas, monospace;
  }
  textarea:focus { outline: none; border-color: #1f8a3a; }
  .row { display: flex; gap: 8px; margin: 12px 0; }
  .row > * { flex: 1; }
  #profile, #quality { width: 100%; margin-bottom: 8px; }
  .hint { font-size: 12px; line-height: 1.35; color: #888; margin: 0 0 12px; }
  select, button {
    background: #2c2c2e; color: #f5f5f7;
    border: 2px solid #3a3a3c; border-radius: 10px;
    padding: 12px; font: 600 15px/1 system-ui, sans-serif;
    appearance: none; -webkit-appearance: none;
  }
  button { cursor: pointer; transition: background 0.15s; }
  .modes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0; }
  .modes button {
    background: #2c2c2e; border: 2px solid #3a3a3c;
    padding: 14px 8px; font-size: 13px;
  }
  .modes button.active { background: #1f8a3a; border-color: #1f8a3a; }
  .modes button:active { transform: scale(0.95); }
  .go {
    width: 100%; padding: 18px; font-size: 17px; font-weight: 700;
    background: #1f8a3a; border-color: #1f8a3a;
    margin-top: 8px;
  }
  .go:disabled { background: #555; border-color: #555; }
  .go:active:not(:disabled) { background: #166b2c; }
  #status {
    margin-top: 16px; padding: 14px; background: #000;
    border-radius: 10px; font-size: 13px; min-height: 44px;
    font-family: ui-monospace, Consolas, monospace;
    color: #aaa; word-break: break-word;
  }
  #status.loading { color: #f0c14b; }
  #status.ok { color: #4ade80; }
  #status.err { color: #f87171; }
  .bar-wrap {
    margin-top: 8px; height: 8px; background: #2c2c2e;
    border-radius: 4px; overflow: hidden;
  }
  .bar-fill {
    height: 100%; width: 0%; background: linear-gradient(90deg, #1f8a3a, #4ade80);
    transition: width 0.3s ease;
  }
  .bar-fill.indet {
    width: 30% !important;
    animation: indet 1.2s ease-in-out infinite;
  }
  @keyframes indet {
    0% { margin-left: -30%; }
    100% { margin-left: 100%; }
  }
  details {
    margin-top: 20px; padding: 12px; background: #2c2c2e;
    border-radius: 10px; font-size: 13px;
  }
  summary { cursor: pointer; color: #aaa; }
  details[open] summary { color: #f5f5f7; margin-bottom: 8px; }
</style>
</head>
<body>
  <h1><span class="icon">⬇</span> Baixador</h1>
  <p class="subtitle">Cole o link, escolha o formato, e baixe.</p>

  <textarea id="url" placeholder="https://www.youtube.com/watch?v=...&#10;https://www.instagram.com/p/...&#10;https://open.spotify.com/playlist/..." autocomplete="off" autocapitalize="off" spellcheck="false"></textarea>

  <div class="modes">
    <button data-mode="video" class="active">🎬 Vídeo</button>
    <button data-mode="audio">🎵 Áudio</button>
    <button data-mode="photo">📷 Foto</button>
  </div>

  <select id="profile">
    <option value="padrao" selected>Padrão (só assistir)</option>
    <option value="premiere">Melhor p/ editar no Premiere</option>
    <option value="capcut">Melhor p/ editar no CapCut</option>
    <option value="prores">Premiere ProRes (pesado)</option>
  </select>
  <p class="hint" id="profile-hint"></p>

  <select id="quality">
    <option value="best">Melhor qualidade</option>
    <option value="1080p">1080p</option>
    <option value="720p" selected>720p</option>
    <option value="480p">480p</option>
    <option value="360p">360p</option>
  </select>

  <button class="go" id="go">⬇ Baixar</button>

  <div id="status">Aguardando…</div>
  <div class="bar-wrap" id="bar-wrap" style="display:none">
    <div class="bar-fill" id="bar-fill"></div>
  </div>

  <details>
    <summary>Sobre / Ajuda</summary>
    <p>Esta é a versão mobile do Baixador. Funciona pegando o link do vídeo/áudio/foto, mandando pro PC do servidor, e devolvendo o arquivo pro seu celular.</p>
    <p><b>Precisa estar na mesma rede WiFi do PC</b> onde o Baixador está rodando.</p>
    <p>Suporta YouTube, Instagram, TikTok, Twitter/X, Facebook, Spotify (áudio via YouTube Music), Reddit, Pinterest, e ~1000 outros sites.</p>
  </details>

<script>
let mode = "video";
const goBtn = document.getElementById("go");
const status = document.getElementById("status");
const barWrap = document.getElementById("bar-wrap");
const barFill = document.getElementById("bar-fill");
const profileEl = document.getElementById("profile");
const profileHint = document.getElementById("profile-hint");
const qualityEl = document.getElementById("quality");

const PROFILE_HINTS = {
  padrao:   "Melhor qualidade por MB, mas pode vir VP9/Opus — o Premiere recusa.",
  premiere: "H.264 + AAC em .mp4. Abre direto no Premiere, sem re-encode.",
  capcut:   "H.264 + AAC em .mp4, limitado a 1080p pro CapCut rodar leve.",
  prores:   "ProRes 422 HQ + PCM em .mov. Edição fluida, arquivo bem maior e demora.",
};

function updateHint() {
  profileHint.textContent = PROFILE_HINTS[profileEl.value] || "";
}
profileEl.addEventListener("change", updateHint);
updateHint();

// Perfil e qualidade so fazem sentido em video.
function syncControls() {
  const isVideo = mode === "video";
  profileEl.style.display = isVideo ? "" : "none";
  profileHint.style.display = isVideo ? "" : "none";
  qualityEl.style.display = isVideo ? "" : "none";
}
syncControls();

document.querySelectorAll(".modes button").forEach(b => {
  b.addEventListener("click", () => {
    document.querySelectorAll(".modes button").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    mode = b.dataset.mode;
    syncControls();
  });
});

function setStatus(text, cls) {
  status.className = cls || "";
  status.textContent = text;
}

async function poll(jobId) {
  try {
    const r = await fetch(`/status/${jobId}`);
    const d = await r.json();
    if (d.status === "done") {
      setStatus("✓ Pronto! Iniciando download pro celular...", "ok");
      barFill.style.width = "100%";
      barFill.classList.remove("indet");
      // dispara download do arquivo pro celular
      window.location.href = `/mobile-file/${jobId}`;
      setTimeout(() => {
        setStatus("✓ Arquivo enviado pro celular. Veja em Downloads.", "ok");
        goBtn.disabled = false;
        goBtn.textContent = "⬇ Baixar outro";
      }, 1500);
      return;
    }
    if (d.status === "error" || d.status === "cancelled") {
      setStatus(`✗ ${d.status === "cancelled" ? "Cancelado" : "Erro no download"}`, "err");
      barFill.classList.remove("indet");
      goBtn.disabled = false;
      goBtn.textContent = "⬇ Tentar novamente";
      return;
    }
    setTimeout(() => poll(jobId), 1500);
  } catch (e) {
    setStatus(`✗ Servidor offline: ${e}`, "err");
    goBtn.disabled = false;
  }
}

goBtn.addEventListener("click", async () => {
  const url = document.getElementById("url").value.trim();
  if (!url) { setStatus("Cole um link primeiro.", "err"); return; }

  goBtn.disabled = true;
  goBtn.textContent = "Processando...";
  setStatus("Iniciando...", "loading");
  barWrap.style.display = "block";
  barFill.classList.add("indet");
  barFill.style.width = "0%";

  try {
    const r = await fetch("/mobile-download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url, mode,
        quality: qualityEl.value,
        profile: profileEl.value
      })
    });
    const d = await r.json();
    if (!d.ok) {
      setStatus(`✗ ${d.error || "Falhou"}`, "err");
      goBtn.disabled = false; goBtn.textContent = "⬇ Tentar novamente";
      return;
    }
    setStatus(`Baixando (${mode})... aguarde, isso vai pro PC primeiro.`, "loading");
    poll(d.job_id);
  } catch (e) {
    setStatus(`✗ ${e}`, "err");
    goBtn.disabled = false;
  }
});

// Service worker pra PWA installable (opcional)
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/mobile-sw.js').catch(() => {});
}
</script>
</body>
</html>"""


@app.route("/mobile")
def mobile_ui() -> Response:
    return Response(MOBILE_HTML, mimetype="text/html; charset=utf-8")


@app.route("/mobile-manifest.json")
def mobile_manifest() -> Response:
    return jsonify({
        "name": "Baixador",
        "short_name": "Baixador",
        "start_url": "/mobile",
        "display": "standalone",
        "background_color": "#1c1c1e",
        "theme_color": "#1f8a3a",
        "icons": [
            {"src": "/mobile-icon.png", "sizes": "128x128", "type": "image/png"},
        ],
    })


@app.route("/mobile-sw.js")
def mobile_sw() -> Response:
    # Service worker minimalista — so registra (nao faz cache offline ainda)
    return Response("self.addEventListener('install', () => self.skipWaiting());",
                    mimetype="application/javascript")


@app.route("/mobile-icon.png")
def mobile_icon() -> Response:
    # Procura o icone do bundle
    candidates = [
        Path(sys.executable).parent / "_internal" / "icon.png",
        Path(__file__).parent.parent / "extension" / "icons" / "icon128.png",
    ]
    for c in candidates:
        if c.exists():
            return Response(c.read_bytes(), mimetype="image/png")
    return Response("", status=404)


@app.route("/mobile-download", methods=["POST"])
def mobile_download() -> Response:
    """Inicia download que sera servido de volta pro celular via /mobile-file."""
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    mode = data.get("mode", "video")
    quality = data.get("quality", "best")
    profile = data.get("profile", "padrao")

    if not url:
        return jsonify({"ok": False, "error": "URL ausente"})

    job_id = uuid.uuid4().hex[:12]
    # output: pasta temporaria por job, qualquer extensao
    out_dir = MOBILE_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    if _is_spotify(url):
        cmd = [*SPOTDL, "--simple-tui", "download", url,
               "--output", str(out_dir / "{title}.{output-ext}"),
               "--bitrate", "192k"]
        if FFMPEG_PATH:
            cmd += ["--ffmpeg", FFMPEG_PATH]
    elif mode == "photo":
        cmd = [*GALLERY_DL, "--dest", str(out_dir), url]
    elif mode == "audio":
        cmd = [*YTDLP, "-x", "--audio-format", "mp3", "--audio-quality", "0",
               "--newline",
               "--progress-template", "PROG|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
               "-o", str(out_dir / "%(title)s.%(ext)s"), url]
        if FFMPEG_PATH:
            cmd += ["--ffmpeg-location", FFMPEG_PATH]
    else:
        cmd = [*YTDLP, *_profile_args(profile, quality),
               "--newline",
               "--progress-template", "PROG|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
               "-o", str(out_dir / "%(title)s.%(ext)s"), url]
        if FFMPEG_PATH:
            cmd += ["--ffmpeg-location", FFMPEG_PATH]

    with JOB_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "status": "queued",
            "queue": queue.Queue(),
            "cmd": "",
            "returncode": None,
            "proc": None,
            "started_at": __import__("time").time(),
            "ended_at": None,
            "url": url, "mode": mode, "quality": quality, "profile": profile,
            "mobile_dir": str(out_dir),
        }
    threading.Thread(
        target=_spawn, args=(cmd, job_id, None, str(out_dir)), daemon=True
    ).start()
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/mobile-file/<job_id>")
def mobile_file(job_id: str) -> Response:
    """Stream do arquivo baixado de volta pro celular e limpa depois."""
    with JOB_LOCK:
        job = JOBS.get(job_id)
    if not job or job.get("status") != "done":
        return Response("Arquivo nao disponivel (job ainda rodando ou inexistente)", status=404)

    out_dir = Path(job.get("mobile_dir") or MOBILE_DIR / job_id)
    files = sorted(out_dir.rglob("*"), key=lambda p: p.stat().st_size if p.is_file() else 0, reverse=True)
    files = [f for f in files if f.is_file()]
    if not files:
        return Response("Nenhum arquivo encontrado", status=404)
    target = files[0]  # maior arquivo (o video/audio principal)

    mime = "application/octet-stream"
    ext = target.suffix.lower()
    if ext in (".mp4", ".m4v"): mime = "video/mp4"
    elif ext == ".mov": mime = "video/quicktime"
    elif ext == ".webm": mime = "video/webm"
    elif ext == ".mp3": mime = "audio/mpeg"
    elif ext in (".m4a", ".aac"): mime = "audio/mp4"
    elif ext == ".jpg" or ext == ".jpeg": mime = "image/jpeg"
    elif ext == ".png": mime = "image/png"

    def stream_and_cleanup():
        try:
            with open(target, "rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            # Limpa a pasta temporaria depois de servir
            try:
                shutil.rmtree(out_dir, ignore_errors=True)
            except Exception:
                pass

    headers = {
        "Content-Disposition": f'attachment; filename="{target.name}"',
        "Content-Length": str(target.stat().st_size),
        "Cache-Control": "no-store",
    }
    return Response(stream_and_cleanup(), mimetype=mime, headers=headers)


@app.route("/mobile-info")
def mobile_info() -> Response:
    """Mostra como acessar do celular."""
    return jsonify({
        "local_ip": _local_ip(),
        "url": f"http://{_local_ip()}:5005/mobile",
    })


@app.route("/health")
def health() -> Response:
    return jsonify({
        "ok": True,
        "version": __version__,
        "downloads_dir": str(DOWNLOADS_DIR),
        "ffmpeg": FFMPEG_PATH or "(PATH)",
        "ffmpeg_found": bool(FFMPEG_PATH and Path(FFMPEG_PATH).exists()),
        "qualities": list(QUALITY_FORMATS.keys()),
        "profiles": list(VIDEO_PROFILES),
        "update_feed": bool(UPDATE_FEED_URL),
    })


def _version_tuple(v: str):
    """Converte '1.2.3' em (1,2,3) pra comparar."""
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split(".")[:3])
    except Exception:
        return (0, 0, 0)


@app.route("/check-update")
def check_update() -> Response:
    """Consulta o feed remoto e diz se ha versao mais nova."""
    if not UPDATE_FEED_URL:
        return jsonify({"ok": False, "reason": "auto-update desabilitado"})
    try:
        import urllib.request, json as _json
        with urllib.request.urlopen(UPDATE_FEED_URL, timeout=5) as r:
            feed = _json.loads(r.read().decode("utf-8"))
        remote_v = str(feed.get("version", "0.0.0"))
        has_update = _version_tuple(remote_v) > _version_tuple(__version__)
        return jsonify({
            "ok": True,
            "current": __version__,
            "latest": remote_v,
            "has_update": has_update,
            "download_url": feed.get("url", ""),
            "notes": feed.get("notes", ""),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/download", methods=["POST"])
def download() -> Response:
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    mode = data.get("mode", "video")             # "video" ou "audio"
    quality = data.get("quality", "best")        # "best"/"1080p"/"720p"/"480p"/"360p"
    audio_q = data.get("audio_quality", "best")  # "best"/"high"/"med"
    profile = data.get("profile", "padrao")      # "padrao"/"premiere"/"capcut"/"prores"

    if not url:
        return jsonify({"error": "url ausente"}), 400

    cookies_payload = data.get("cookies") or []
    cookies_path = _cookies_file_from_payload(cookies_payload) if cookies_payload else None
    cleanup = [cookies_path] if cookies_path else None

    if mode == "photo":
        cmd = [*GALLERY_DL, "--dest", str(PHOTOS_DIR)]
        if cookies_path:
            cmd += ["--cookies", cookies_path]
        cmd.append(url)
        job_id = _start_job(cmd, cleanup_files=cleanup, dest_dir=str(PHOTOS_DIR),
                            metadata={"url": url, "mode": mode, "quality": quality})
        return jsonify({
            "job_id": job_id,
            "downloads_dir": str(PHOTOS_DIR),
            "mode": mode,
            "cookies_used": bool(cookies_path),
        })

    if _is_spotify(url):
        kind = _spotify_kind(url)
        # Playlist/album/show -> salva em subpasta com o nome
        # NOTA: spotdl trata list-position como string, entao nao use format specs (:02d, etc)
        if kind in ("playlist", "album", "show"):
            out_template = str(DOWNLOADS_DIR / "{list-name}" / "{list-position} - {artist} - {title}.{output-ext}")
        elif kind == "artist":
            out_template = str(DOWNLOADS_DIR / "{artist}" / "{title}.{output-ext}")
        else:
            out_template = str(DOWNLOADS_DIR / "{artist} - {title}.{output-ext}")
        print(f"[spotify] kind={kind} template={out_template}")
        cmd = [
            *SPOTDL,
            "--simple-tui",      # output linha-por-linha, sem barras animadas (melhor pra pipe)
            "--print-errors",    # mostra erros em vez de silenciar
            "download", url,
            "--output", out_template,
            "--bitrate", "320k" if audio_q == "best" else "192k" if audio_q == "high" else "128k",
        ]
        if FFMPEG_PATH:
            cmd += ["--ffmpeg", FFMPEG_PATH]
    elif mode == "audio":
        cmd = [
            *YTDLP,
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", AUDIO_QUALITY.get(audio_q, "0"),
            "--newline",
            "--progress-template", "PROG|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
            "-o", "%(title)s.%(ext)s",
            url,
        ]
        if FFMPEG_PATH:
            cmd += ["--ffmpeg-location", FFMPEG_PATH]
        if cookies_path:
            cmd += ["--cookies", cookies_path]
    else:
        cmd = [
            *YTDLP,
            *_profile_args(profile, quality),
            "--newline",
            "--progress-template", "PROG|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
            "-o", "%(title)s.%(ext)s",
            url,
        ]
        # Legendas: se solicitado, baixa em PT/EN e converte pra SRT
        if data.get("subtitles"):
            cmd += [
                "--write-subs", "--write-auto-subs",
                "--sub-langs", "pt.*,en.*",
                "--convert-subs", "srt",
                "--embed-subs",
            ]
        # Recorte: se start/end fornecidos, baixa so o trecho
        trim_start = (data.get("trim_start") or "").strip()
        trim_end   = (data.get("trim_end") or "").strip()
        if trim_start or trim_end:
            # formato: *HH:MM:SS-HH:MM:SS (asterisco = trecho relativo)
            section = f"*{trim_start or '0'}-{trim_end or 'inf'}"
            cmd += ["--download-sections", section, "--force-keyframes-at-cuts"]
        if FFMPEG_PATH:
            cmd += ["--ffmpeg-location", FFMPEG_PATH]
        if cookies_path:
            cmd += ["--cookies", cookies_path]

    job_id = _start_job(cmd, cleanup_files=cleanup, dest_dir=str(DOWNLOADS_DIR),
                        metadata={"url": url, "mode": mode,
                                  "quality": quality if mode == "video" else audio_q,
                                  "profile": profile if mode == "video" else None})
    return jsonify({
        "job_id": job_id,
        "downloads_dir": str(DOWNLOADS_DIR),
        "mode": mode,
        "quality": quality if mode == "video" else audio_q,
        "profile": profile if mode == "video" else None,
        "cookies_used": bool(cookies_path),
    })


@app.route("/jobs")
def jobs_list() -> Response:
    """Lista os ultimos N jobs (histórico) com metadata."""
    limit = int(request.args.get("limit", 50))
    with JOB_LOCK:
        items = []
        for jid, j in JOBS.items():
            items.append({
                "id": jid,
                "status": j.get("status"),
                "url": j.get("url"),
                "mode": j.get("mode"),
                "quality": j.get("quality"),
                "profile": j.get("profile"),
                "started_at": j.get("started_at"),
                "ended_at": j.get("ended_at"),
                "returncode": j.get("returncode"),
            })
    # ordena por started_at desc
    items.sort(key=lambda x: x.get("started_at") or 0, reverse=True)
    return jsonify({"jobs": items[:limit]})


@app.route("/status/<job_id>")
def status(job_id: str) -> Response:
    with JOB_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "job desconhecido"}), 404
    return jsonify({"status": job["status"], "returncode": job["returncode"]})


@app.route("/stream/<job_id>")
def stream(job_id: str) -> Response:
    with JOB_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "job desconhecido"}), 404

    q: queue.Queue = job["queue"]

    @stream_with_context
    def gen():
        while True:
            line = q.get()
            if line is None:
                with JOB_LOCK:
                    final = JOBS[job_id]["status"]
                yield f"event: end\ndata: {final}\n\n"
                break
            safe = line.rstrip().replace("\r", "")
            yield f"data: {safe}\n\n"

    return Response(gen(), mimetype="text/event-stream")


@app.route("/open-folder", methods=["POST"])
def open_folder() -> Response:
    if sys.platform == "win32":
        os.startfile(str(DOWNLOADS_DIR))  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(DOWNLOADS_DIR)])
    else:
        subprocess.Popen(["xdg-open", str(DOWNLOADS_DIR)])
    return jsonify({"ok": True})


if __name__ == "__main__":
    host = os.environ.get("BAIXADOR_HOST", "0.0.0.0")
    ip = _local_ip()
    print(f"Baixador rodando em http://127.0.0.1:5005")
    print(f"  Mobile (no celular):  http://{ip}:5005/mobile")
    print(f"  Salvando em: {DOWNLOADS_DIR}")
    from waitress import serve
    serve(app, host=host, port=5005, threads=8)
