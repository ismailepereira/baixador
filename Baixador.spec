# -*- mode: python ; coding: utf-8 -*-
"""Build do executavel Windows.

    server/.venv/Scripts/python.exe -m PyInstaller Baixador.spec --noconfirm

Caminhos sao relativos a este arquivo de proposito: a versao anterior deste spec
tinha os caminhos chumbados em F:\\Claude\\baixador e parou de compilar quando o
projeto mudou de pasta.

Pre-requisito: bin/ffmpeg/bin/{ffmpeg,ffprobe}.exe (o start.bat baixa).
"""
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.getcwd())
FFMPEG_DIR = os.path.join(ROOT, "bin", "ffmpeg", "bin")

for _exe in ("ffmpeg.exe", "ffprobe.exe"):
    if not os.path.exists(os.path.join(FFMPEG_DIR, _exe)):
        raise SystemExit(
            f"[spec] {_exe} nao encontrado em {FFMPEG_DIR}.\n"
            f"       Rode start.bat uma vez pra baixar o ffmpeg."
        )

datas = [(os.path.join(ROOT, "server", "icon.png"), ".")]
binaries = [
    (os.path.join(FFMPEG_DIR, "ffmpeg.exe"), "."),
    (os.path.join(FFMPEG_DIR, "ffprobe.exe"), "."),
]
hiddenimports = ["flask_cors", "PIL._tkinter_finder"]
hiddenimports += collect_submodules("curl_cffi")

for _pkg in (
    "yt_dlp", "spotdl", "gallery_dl", "browser_cookie3", "tls_client",
    "SpotipyFree", "spotapi", "spotipy", "syncedlyrics", "ytmusicapi",
    "pykakasi", "jaconv", "pystray",
):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h


a = Analysis(
    [os.path.join(ROOT, "server", "baixador_main.py")],
    pathex=[os.path.join(ROOT, "server")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Baixador",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(ROOT, "extension", "icons", "icon128.png")],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Baixador",
)
