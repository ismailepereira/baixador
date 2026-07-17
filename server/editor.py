# -*- coding: utf-8 -*-
"""Editor de video do Baixador — aplica edicoes "tipo Premiere" via ffmpeg.

Recebe um spec (dict vindo do JSON da UI mobile) e aplica sobre o arquivo
recem-baixado, na ordem: cortes -> velocidade -> formato -> texto -> fade
-> volume/mudo -> compressao para tamanho-alvo.

Spec (todos os campos opcionais):
    {
      "cortes":        [["0:30", "1:20"], ...],   # trechos a manter, emendados
      "velocidade":    1.5,                        # 0.25 a 8
      "formato":       "vertical" | "quadrado",    # 9:16 / 1:1, fundo desfocado
      "texto":         "Titulo",
      "texto_pos":     "topo" | "centro" | "base", # padrao: base
      "fade":          true,                       # fade in/out 0.5s
      "mudo":          true,
      "volume":        2.0,
      "comprimir_mb":  16                          # so recodifica se passar disso
    }
"""
from __future__ import annotations

import glob
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

VIDEO_EXTS = (".mp4", ".m4v", ".webm", ".mkv", ".mov", ".avi")

FORMATOS = {"vertical": (1080, 1920), "quadrado": (1080, 1080)}
POSICOES_TEXTO = {
    "topo": "h*0.08",
    "centro": "(h-text_h)/2",
    "base": "h*0.92-text_h",
}


class EdicaoErro(Exception):
    """Erro de edicao com mensagem apresentavel ao usuario."""


# ------------------------------------------------------------ ffmpeg/ffprobe


def _resolver_bin(nome: str, ffmpeg_path: str) -> str:
    """Resolve o executavel: BAIXADOR_FFMPEG pode ser a pasta bin/ ou o exe."""
    if ffmpeg_path:
        p = Path(ffmpeg_path)
        if p.is_dir():
            for ext in (".exe", ""):
                cand = p / f"{nome}{ext}"
                if cand.exists():
                    return str(cand)
        elif p.exists():
            # veio o caminho do ffmpeg; ffprobe mora do lado
            if nome == "ffmpeg":
                return str(p)
            irmao = p.parent / p.name.replace("ffmpeg", nome)
            if irmao.exists():
                return str(irmao)
    achado = shutil.which(nome)
    if achado:
        return achado
    raise EdicaoErro(
        f"{nome} nao encontrado — instale o ffmpeg e coloque no PATH "
        "(ou defina BAIXADOR_FFMPEG)"
    )


def _rodar(cmd: list[str], log: Callable[[str], None]) -> None:
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if proc.returncode != 0:
        cauda = (proc.stdout or "")[-1500:]
        log(cauda)
        raise EdicaoErro("ffmpeg falhou durante a edicao (veja o log acima)")


def _sondar(arquivo: Path, ffprobe: str) -> tuple[float, bool]:
    """(duracao_s, tem_audio) via ffprobe."""
    proc = subprocess.run(
        [ffprobe, "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(arquivo)],
        stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        info = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        info = {}
    dur = float(info.get("format", {}).get("duration", 0) or 0)
    tem_audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    return dur, tem_audio


# ------------------------------------------------------------------- helpers


def parse_tempo(txt: str) -> float:
    """'1:23' -> 83.0; '01:02:03' -> 3723.0; '45' -> 45.0."""
    partes = str(txt).strip().split(":")
    if not 1 <= len(partes) <= 3 or any(p.strip() == "" for p in partes):
        raise EdicaoErro(f"tempo invalido: '{txt}' (use SS, MM:SS ou HH:MM:SS)")
    try:
        nums = [float(p) for p in partes]
    except ValueError:
        raise EdicaoErro(f"tempo invalido: '{txt}'")
    seg = 0.0
    for n in nums:
        seg = seg * 60 + n
    return seg


def _achar_fonte() -> str | None:
    padroes = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/**/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/**/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/**/*.ttf",
    ]
    for padrao in padroes:
        achados = glob.glob(padrao, recursive=True)
        if achados:
            return achados[0]
    return None


def _escapar_drawtext(txt: str) -> str:
    return (
        txt.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "’")
        .replace("%", "\\%")
    )


def _filtro_atempo(vel: float) -> str:
    """atempo so aceita 0.5-2.0; encadeia quantos precisar."""
    filtros: list[str] = []
    resto = vel
    while resto > 2.0:
        filtros.append("atempo=2.0")
        resto /= 2.0
    while resto < 0.5:
        filtros.append("atempo=0.5")
        resto /= 0.5
    filtros.append(f"atempo={resto:.6f}")
    return ",".join(filtros)


# ---------------------------------------------------------------- validacao


def validar_spec(spec: dict) -> list[str]:
    """Retorna lista de erros (vazia = spec ok). Nao mexe em arquivo nenhum."""
    erros: list[str] = []
    if not isinstance(spec, dict):
        return ["edicao deve ser um objeto"]

    cortes = spec.get("cortes") or []
    if not isinstance(cortes, list):
        erros.append("'cortes' deve ser uma lista de pares [inicio, fim]")
        cortes = []
    for c in cortes:
        try:
            ini, fim = parse_tempo(c[0]), parse_tempo(c[1])
            if fim <= ini:
                erros.append(f"corte '{c[0]}-{c[1]}': fim antes do inicio")
        except (EdicaoErro, IndexError, TypeError) as e:
            erros.append(str(e) if isinstance(e, EdicaoErro) else f"corte invalido: {c!r}")

    vel = spec.get("velocidade")
    if vel is not None:
        try:
            if not 0.25 <= float(vel) <= 8:
                erros.append("velocidade deve estar entre 0.25 e 8")
        except (TypeError, ValueError):
            erros.append(f"velocidade invalida: {vel!r}")

    formato = spec.get("formato")
    if formato and formato not in FORMATOS:
        erros.append(f"formato invalido: {formato!r} (use vertical ou quadrado)")

    pos = spec.get("texto_pos")
    if pos and pos not in POSICOES_TEXTO:
        erros.append(f"texto_pos invalido: {pos!r} (use topo, centro ou base)")

    vol = spec.get("volume")
    if vol is not None:
        try:
            if not 0 < float(vol) <= 10:
                erros.append("volume deve estar entre 0 e 10")
        except (TypeError, ValueError):
            erros.append(f"volume invalido: {vol!r}")

    mb = spec.get("comprimir_mb")
    if mb is not None:
        try:
            if float(mb) < 1:
                erros.append("comprimir_mb deve ser >= 1")
        except (TypeError, ValueError):
            erros.append(f"comprimir_mb invalido: {mb!r}")

    return erros


def spec_tem_edicao(spec: dict | None) -> bool:
    """True se o spec pede alguma edicao de fato."""
    if not spec or not isinstance(spec, dict):
        return False
    if spec.get("cortes"):
        return True
    for chave in ("formato", "texto", "fade", "mudo"):
        if spec.get(chave):
            return True
    vel = spec.get("velocidade")
    if vel and float(vel) != 1.0:
        return True
    vol = spec.get("volume")
    if vol and float(vol) != 1.0:
        return True
    if spec.get("comprimir_mb"):
        return True
    return False


# ------------------------------------------------------------------ filtros


def montar_filtros(spec: dict, duracao: float, tem_audio: bool):
    """Monta (filtros_video, filtros_audio, duracao_final).

    filtros_audio == None significa "descartar o audio" (-an).
    Funcao pura — facil de testar sem ffmpeg.
    """
    fv: list[str] = []
    fa: list[str] | None = []

    vel = float(spec.get("velocidade") or 1.0)
    if vel != 1.0:
        fv.append(f"setpts=PTS/{vel:.6f}")
        fa.append(_filtro_atempo(vel))
        duracao = duracao / vel

    formato = spec.get("formato")
    if formato in FORMATOS:
        larg, alt = FORMATOS[formato]
        fv.append(
            f"split[fundo][frente];"
            f"[fundo]scale={larg}:{alt}:force_original_aspect_ratio=increase,"
            f"crop={larg}:{alt},boxblur=24:4[f1];"
            f"[frente]scale={larg}:{alt}:force_original_aspect_ratio=decrease"
            f"[f2];[f1][f2]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )

    texto = (spec.get("texto") or "").strip()
    if texto:
        fonte = _achar_fonte()
        opc_fonte = f"fontfile={fonte}:" if fonte else "font='sans':"
        pos_y = POSICOES_TEXTO[spec.get("texto_pos") or "base"]
        fv.append(
            f"drawtext={opc_fonte}text='{_escapar_drawtext(texto)}':"
            f"fontsize=h/16:fontcolor=white:borderw=3:bordercolor=black:"
            f"x=(w-text_w)/2:y={pos_y}"
        )

    if spec.get("fade"):
        d = 0.5
        ini_saida = max(duracao - d, 0)
        fv.append(f"fade=t=in:st=0:d={d},fade=t=out:st={ini_saida:.3f}:d={d}")
        fa.append(f"afade=t=in:st=0:d={d},afade=t=out:st={ini_saida:.3f}:d={d}")

    vol = float(spec.get("volume") or 1.0)
    if vol != 1.0:
        fa.append(f"volume={vol}")

    if not tem_audio or spec.get("mudo"):
        fa = None

    return fv, fa, duracao


# ------------------------------------------------------------------- edicao


def editar_video(entrada: Path, spec: dict, log: Callable[[str], None] = print) -> Path:
    """Aplica o spec sobre `entrada`. Gera '<nome> (editado).mp4' na mesma
    pasta, apaga o original e retorna o caminho novo."""
    ffmpeg_path = os.environ.get("BAIXADOR_FFMPEG", "").strip()
    ffmpeg = _resolver_bin("ffmpeg", ffmpeg_path)
    ffprobe = _resolver_bin("ffprobe", ffmpeg_path)

    erros = validar_spec(spec)
    if erros:
        raise EdicaoErro("; ".join(erros))

    duracao, tem_audio = _sondar(entrada, ffprobe)
    tmp = Path(tempfile.mkdtemp(prefix="baixador-edicao-"))
    try:
        atual = entrada

        # 1) cortes (cada trecho extraido e emendado na ordem)
        cortes = [(parse_tempo(c[0]), parse_tempo(c[1]))
                  for c in (spec.get("cortes") or [])]
        for ini, fim in cortes:
            if ini >= duracao:
                raise EdicaoErro(
                    f"corte comeca em {ini:.0f}s mas o video tem {duracao:.0f}s"
                )
        if cortes:
            log(f"[edicao] cortando {len(cortes)} trecho(s)...")
            pedacos: list[Path] = []
            for i, (ini, fim) in enumerate(cortes):
                pedaco = tmp / f"pedaco{i}.mp4"
                _rodar([ffmpeg, "-y", "-ss", f"{ini:.3f}", "-to", f"{fim:.3f}",
                        "-i", str(atual), "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "18", "-c:a", "aac", "-b:a", "192k",
                        str(pedaco)], log)
                pedacos.append(pedaco)
            if len(pedacos) == 1:
                atual = pedacos[0]
            else:
                lista = tmp / "lista.txt"
                lista.write_text(
                    "".join(f"file '{p.as_posix()}'\n" for p in pedacos),
                    encoding="utf-8",
                )
                emendado = tmp / "emendado.mp4"
                _rodar([ffmpeg, "-y", "-f", "concat", "-safe", "0",
                        "-i", str(lista), "-c", "copy", str(emendado)], log)
                atual = emendado
            duracao, tem_audio = _sondar(atual, ffprobe)

        # 2) encode principal com a cadeia de filtros
        fv, fa, duracao = montar_filtros(spec, duracao, tem_audio)
        destino = entrada.with_name(f"{entrada.stem} (editado).mp4")
        log("[edicao] aplicando filtros e recodificando...")
        cmd = [ffmpeg, "-y", "-i", str(atual)]
        if fv:
            cmd += ["-vf", ",".join(fv)]
        if fa is None:
            cmd += ["-an"]
        elif fa:
            cmd += ["-af", ",".join(fa)]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        if fa is not None:
            cmd += ["-c:a", "aac", "-b:a", "160k"]
        cmd.append(str(destino))
        _rodar(cmd, log)

        # 3) compressao para tamanho-alvo (ex.: 16 MB do WhatsApp)
        alvo_mb = spec.get("comprimir_mb")
        if alvo_mb:
            alvo_mb = float(alvo_mb)
            tamanho_mb = destino.stat().st_size / (1024 * 1024)
            if tamanho_mb > alvo_mb:
                log(f"[edicao] {tamanho_mb:.1f}MB > {alvo_mb:.0f}MB — comprimindo...")
                dur_final, _ = _sondar(destino, ffprobe)
                if dur_final <= 0:
                    dur_final = duracao or 1
                bits_total = alvo_mb * 8 * 1024 * 1024 * 0.93
                kbps_video = math.floor(
                    bits_total / dur_final / 1000 - (0 if fa is None else 96)
                )
                if kbps_video < 100:
                    raise EdicaoErro(
                        f"impossivel comprimir {dur_final:.0f}s para "
                        f"{alvo_mb:.0f}MB com qualidade assistivel — "
                        "corte o video ou aumente o limite"
                    )
                comprimido = tmp / "comprimido.mp4"
                cmd = [ffmpeg, "-y", "-i", str(destino),
                       "-c:v", "libx264", "-preset", "veryfast",
                       "-b:v", f"{kbps_video}k", "-maxrate", f"{kbps_video}k",
                       "-bufsize", f"{kbps_video * 2}k",
                       "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
                cmd += ["-an"] if fa is None else ["-c:a", "aac", "-b:a", "96k"]
                cmd.append(str(comprimido))
                _rodar(cmd, log)
                shutil.move(str(comprimido), str(destino))

        # 4) o editado substitui o original (a UI serve o maior arquivo da pasta)
        if entrada.exists() and entrada != destino:
            entrada.unlink()
        return destino
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def editar_pasta(pasta: Path, spec: dict, log: Callable[[str], None] = print) -> Path:
    """Edita o video principal (maior arquivo de video) da pasta do job."""
    videos = [p for p in pasta.rglob("*")
              if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    if not videos:
        raise EdicaoErro("nenhum video encontrado para editar")
    alvo = max(videos, key=lambda p: p.stat().st_size)
    return editar_video(alvo, spec, log=log)
