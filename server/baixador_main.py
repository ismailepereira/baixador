"""Entrypoint do Baixador empacotado — sem janela, com icone na bandeja."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import traceback


def _setup_logging():
    """Em modo --windowed, sys.stdout/stderr sao None. Redirecionar pra arquivo
    e essencial, senao qualquer print() crasha o processo.

    MAS: quando este exe roda como filho `--tool yt-dlp` (spawnado pelo servidor
    com stdout=PIPE), o stdout e um pipe valido -- e redirecionar aqui manda todo
    o progresso do yt-dlp pro baixador.log em vez do painel da extensao. So
    redireciona quando stdout realmente nao existe."""
    if sys.stdout is not None:
        return
    if getattr(sys, "frozen", False):
        log_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "Baixador",
        )
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "baixador.log")
        try:
            f = open(log_path, "a", encoding="utf-8", buffering=1)
        except Exception:
            return
        sys.stdout = f
        sys.stderr = f
        import datetime
        f.write(f"\n=== Baixador iniciado {datetime.datetime.now().isoformat()} ===\n")


_setup_logging()


def _run_tool(tool: str, args: list[str]) -> int:
    if tool in ("yt-dlp", "ytdlp"):
        from yt_dlp import main as ytdlp_main
        sys.argv = ["yt-dlp", *args]
        ytdlp_main()
        return 0
    if tool == "spotdl":
        from spotdl.__main__ import console_entry_point
        sys.argv = ["spotdl", *args]
        console_entry_point()
        return 0
    if tool in ("gallery-dl", "gallery_dl"):
        import gallery_dl
        sys.argv = ["gallery-dl", *args]
        return gallery_dl.main()
    print(f"[baixador] ferramenta desconhecida: {tool}", file=sys.stderr)
    return 2


def _ensure_ffmpeg_in_path():
    """Quando empacotado, o ffmpeg.exe vem em _internal/. Adiciona ao PATH."""
    if getattr(sys, "frozen", False):
        bundle_dir = os.path.dirname(sys.executable)
        candidates = [
            os.path.join(bundle_dir, "_internal", "ffmpeg.exe"),
            os.path.join(bundle_dir, "ffmpeg.exe"),
        ]
        for c in candidates:
            if os.path.exists(c):
                os.environ["BAIXADOR_FFMPEG"] = c
                os.environ["PATH"] = os.path.dirname(c) + os.pathsep + os.environ.get("PATH", "")
                return


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _find_icon_path() -> str | None:
    """Localiza um icone PNG embarcado pelo PyInstaller."""
    candidates = []
    if getattr(sys, "frozen", False):
        bundle_dir = os.path.dirname(sys.executable)
        candidates += [
            os.path.join(bundle_dir, "_internal", "icon.png"),
            os.path.join(bundle_dir, "icon.png"),
        ]
    # tambem busca no extension folder (dev mode)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates += [
        os.path.normpath(os.path.join(here, "..", "extension", "icons", "icon128.png")),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _make_default_icon():
    """Cria um icone fallback (seta para baixo verde) caso nao ache nenhum."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (31, 138, 58, 255))  # verde
    d = ImageDraw.Draw(img)
    # seta para baixo branca
    d.polygon([(20, 14), (44, 14), (44, 36), (54, 36), (32, 56), (10, 36), (20, 36)],
              fill=(255, 255, 255, 255))
    return img


def _run_server():
    """Sobe o servidor Flask via waitress. 0.0.0.0 = aceita do celular tambem."""
    from server import app
    from waitress import serve
    host = os.environ.get("BAIXADOR_HOST", "0.0.0.0")
    serve(app, host=host, port=5005, threads=8)


def _open_downloads(icon, item):
    from server import DOWNLOADS_DIR
    try:
        os.startfile(str(DOWNLOADS_DIR))
    except Exception:
        pass


def _copy_mobile_url(icon, item):
    """Copia URL mobile pro clipboard pra colar no celular."""
    from server import _local_ip
    url = f"http://{_local_ip()}:5005/mobile"
    try:
        # subprocess sem janela usando clip do Windows
        import subprocess
        p = subprocess.Popen(
            ["cmd", "/c", "clip"],
            stdin=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        p.communicate(input=url.encode("utf-8"))
        icon.notify(
            f"URL copiada: {url}\nCole no navegador do celular (mesma WiFi).",
            "Baixador Mobile",
        )
    except Exception as e:
        print(f"[mobile] erro ao copiar URL: {e}")


def _quit_app(icon, item):
    icon.stop()
    os._exit(0)


# === Auto-start no Windows via Registry HKCU\...\Run ===
_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "Baixador"


def _autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_READ) as k:
            value, _ = winreg.QueryValueEx(k, _AUTOSTART_NAME)
            return bool(value)
    except (FileNotFoundError, OSError):
        return False


def _set_autostart(enable: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg
    exe_path = sys.executable
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, _AUTOSTART_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
                print(f"[autostart] habilitado: {exe_path}")
            else:
                try:
                    winreg.DeleteValue(k, _AUTOSTART_NAME)
                    print("[autostart] desabilitado")
                except FileNotFoundError:
                    pass
    except OSError as e:
        print(f"[autostart] erro: {e}")


def _toggle_autostart(icon, item):
    _set_autostart(not _autostart_enabled())
    icon.update_menu()


def _run_with_tray():
    """Modo principal: roda servidor em thread + icone na bandeja."""
    print("[tray] iniciando...")
    try:
        import pystray
        from PIL import Image
    except Exception as e:
        print(f"[tray] erro ao importar pystray/PIL: {e}")
        traceback.print_exc()
        # fallback: roda so o servidor sem tray
        _run_server()
        return

    icon_path = _find_icon_path()
    print(f"[tray] icon_path: {icon_path}")
    try:
        if icon_path:
            img = Image.open(icon_path)
            img.load()  # forca leitura completa
        else:
            img = _make_default_icon()
    except Exception as e:
        print(f"[tray] falha ao carregar icone: {e}, usando default")
        img = _make_default_icon()

    from server import DOWNLOADS_DIR

    icon = pystray.Icon(
        "baixador",
        icon=img,
        title=f"Baixador — rodando\nSalvando em: {DOWNLOADS_DIR}",
        menu=pystray.Menu(
            pystray.MenuItem("Baixador (rodando)", None, enabled=False, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Abrir pasta de downloads", _open_downloads),
            pystray.MenuItem("📱 Copiar URL pro celular", _copy_mobile_url),
            pystray.MenuItem(
                "Iniciar com o Windows",
                _toggle_autostart,
                checked=lambda item: _autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", _quit_app),
        ),
    )

    threading.Thread(target=_run_server, daemon=True).start()
    print("[tray] thread do servidor iniciada, chamando icon.run()...")

    def _on_start(_icon):
        _icon.visible = True
        print("[tray] icon.visible=True; tentando notificar...")
        try:
            _icon.notify("Baixador iniciado. Use a extensao no Chrome.", "Baixador")
        except Exception as e:
            print(f"[tray] notify falhou: {e}")

    try:
        icon.run(setup=_on_start)
    except Exception as e:
        print(f"[tray] icon.run crashou: {e}")
        traceback.print_exc()
        # mantem o servidor vivo mesmo sem tray
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass


def main() -> int:
    _ensure_ffmpeg_in_path()

    # dispatch para ferramenta: --tool <name> <args...>
    if len(sys.argv) >= 3 and sys.argv[1] == "--tool":
        try:
            return _run_tool(sys.argv[2], sys.argv[3:])
        except SystemExit as e:
            return int(e.code or 0)

    # detecta instancia duplicada
    if _port_in_use(5005):
        try:
            # tenta mostrar uma mensagem amigavel via Win32
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "O Baixador ja esta rodando.\n\nVeja o icone na bandeja (perto do relogio).",
                "Baixador",
                0x40,  # MB_ICONINFORMATION
            )
        except Exception:
            print("[baixador] ja esta rodando", file=sys.stderr)
        return 0

    # modo dev (sem frozen): roda sem tray, mostra logs
    if not getattr(sys, "frozen", False):
        from server import DOWNLOADS_DIR
        print(f"Baixador rodando em http://127.0.0.1:5005")
        print(f"Salvando em: {DOWNLOADS_DIR}")
        _run_server()
        return 0

    # modo empacotado: roda com tray, sem janela
    _run_with_tray()
    return 0


if __name__ == "__main__":
    sys.exit(main())
