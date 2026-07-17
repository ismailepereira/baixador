#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
videobot.py — baixador + editor de vídeo por linha de comando.

Pensado para ser operado pelo Claude (skill /video): o usuário pede em
linguagem natural ("baixa esse vídeo, corta do 0:30 ao 1:20 e deixa
vertical") e o Claude traduz para as flags abaixo.

Dependências: yt-dlp (pip) e ffmpeg/ffprobe no PATH.

Comandos:
  baixar URL  [--qualidade 1080] [--saida DIR] [--nome NOME]
  editar ARQ  [edições…]
  auto URL    [edições…]          # baixa e edita em sequência

Edições (combináveis; aplicadas nesta ordem: cortes → velocidade →
formato → texto → fade → volume):
  --cortar INI-FIM      trecho a manter (ex.: 0:30-1:20). Repetível:
                        vários --cortar são emendados na ordem dada.
  --velocidade X        1.5, 2, 0.5…
  --vertical            9:16 com fundo desfocado (Reels/Stories/TikTok)
  --quadrado            1:1 com fundo desfocado (feed)
  --resolucao N         limita a altura (ex.: 720)
  --texto "..."         título sobreposto  [--texto-pos topo|centro|base]
  --fade                fade in/out de 0.5s no vídeo e no áudio
  --mudo                remove o áudio
  --volume X            multiplica o volume (2 = dobro)
  --comprimir-mb N      recodifica se passar de N MB (WhatsApp: 16)
  --mp3                 em vez de vídeo, extrai só o áudio em MP3
  --gif                 em vez de vídeo, gera GIF [--gif-fps 12]
                        [--gif-largura 480]
  --nome NOME           nome-base do arquivo final
  --saida DIR           pasta de saída (padrão: ./saida)
"""

import argparse
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------- utilidades


def erro(msg):
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(1)


def rodar(cmd, silencioso=True):
    """Roda um comando; em caso de falha mostra o stderr e aborta."""
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if proc.returncode != 0:
        print(proc.stderr[-3000:], file=sys.stderr)
        erro(f"comando falhou: {' '.join(cmd[:3])}…")
    if not silencioso and proc.stdout:
        print(proc.stdout)
    return proc.stdout


def checar_dependencias(precisa_ytdlp):
    faltando = [p for p in ("ffmpeg", "ffprobe") if not shutil.which(p)]
    if precisa_ytdlp and not shutil.which("yt-dlp"):
        faltando.append("yt-dlp")
    if faltando:
        erro(
            "dependências ausentes: "
            + ", ".join(faltando)
            + "\n  instale com: pip install yt-dlp"
            + "  e: apt-get update && apt-get install -y ffmpeg"
        )


def parse_tempo(txt):
    """'1:23' → 83.0; '01:02:03' → 3723.0; '45' ou '45.5' → segundos."""
    partes = txt.strip().split(":")
    if not 1 <= len(partes) <= 3 or any(p == "" for p in partes):
        erro(f"tempo inválido: '{txt}' (use SS, MM:SS ou HH:MM:SS)")
    try:
        nums = [float(p) for p in partes]
    except ValueError:
        erro(f"tempo inválido: '{txt}'")
    seg = 0.0
    for n in nums:
        seg = seg * 60 + n
    return seg


def parse_corte(txt):
    if "-" not in txt:
        erro(f"corte inválido: '{txt}' (use INI-FIM, ex.: 0:30-1:20)")
    ini, fim = txt.split("-", 1)
    a, b = parse_tempo(ini), parse_tempo(fim)
    if b <= a:
        erro(f"corte inválido: '{txt}' (fim antes do início)")
    return a, b


def sondar(arquivo):
    """Retorna (duração_s, tem_audio) via ffprobe."""
    saida = rodar(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", arquivo,
        ]
    )
    info = json.loads(saida)
    dur = float(info.get("format", {}).get("duration", 0) or 0)
    tem_audio = any(
        s.get("codec_type") == "audio" for s in info.get("streams", [])
    )
    return dur, tem_audio


def achar_fonte():
    """Localiza uma fonte TTF para o drawtext (ou None)."""
    padroes = [
        "/usr/share/fonts/**/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/**/DejaVuSans.ttf",
        "/usr/share/fonts/**/*.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for padrao in padroes:
        achados = glob.glob(padrao, recursive=True)
        if achados:
            return achados[0]
    return None


def escapar_drawtext(txt):
    return (
        txt.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "’")
        .replace("%", "\\%")
    )


def nome_livre(pasta, base, ext):
    """base.ext, base-2.ext, … — nunca sobrescreve nada."""
    caminho = os.path.join(pasta, f"{base}{ext}")
    n = 2
    while os.path.exists(caminho):
        caminho = os.path.join(pasta, f"{base}-{n}{ext}")
        n += 1
    return caminho


# ------------------------------------------------------------------- baixar


def baixar(args):
    checar_dependencias(precisa_ytdlp=True)
    os.makedirs(args.saida, exist_ok=True)
    modelo = (args.nome or "%(title).80s") + ".%(ext)s"
    destino = os.path.join(args.saida, modelo)
    alt = args.qualidade
    formato = (
        f"bv*[height<={alt}][ext=mp4]+ba[ext=m4a]/"
        f"bv*[height<={alt}]+ba/b[height<={alt}]/b"
    )
    cmd = [
        "yt-dlp", "--no-playlist", "-f", formato,
        "--merge-output-format", "mp4",
        "-o", destino, "--print", "after_move:filepath",
        "--no-simulate", args.url,
    ]
    saida = rodar(cmd).strip().splitlines()
    if not saida:
        erro("yt-dlp terminou sem informar o arquivo baixado")
    arquivo = saida[-1].strip()
    print(arquivo)
    return arquivo


# ------------------------------------------------------------------- editar


def _cortar_e_emendar(entrada, cortes, tmp):
    """Extrai cada trecho e emenda tudo num arquivo só (re-encode leve)."""
    pedacos = []
    for i, (ini, fim) in enumerate(cortes):
        pedaco = os.path.join(tmp, f"pedaco{i}.mp4")
        rodar(
            [
                "ffmpeg", "-y", "-ss", f"{ini:.3f}", "-to", f"{fim:.3f}",
                "-i", entrada, "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "18", "-c:a", "aac", "-b:a", "192k", pedaco,
            ]
        )
        pedacos.append(pedaco)
    if len(pedacos) == 1:
        return pedacos[0]
    lista = os.path.join(tmp, "lista.txt")
    with open(lista, "w", encoding="utf-8") as f:
        for p in pedacos:
            f.write(f"file '{p}'\n")
    emendado = os.path.join(tmp, "emendado.mp4")
    rodar(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista,
            "-c", "copy", emendado,
        ]
    )
    return emendado


def _filtro_atempo(vel):
    """atempo só aceita 0.5–2.0; encadeia quantos precisar."""
    filtros = []
    resto = vel
    while resto > 2.0:
        filtros.append("atempo=2.0")
        resto /= 2.0
    while resto < 0.5:
        filtros.append("atempo=0.5")
        resto /= 0.5
    filtros.append(f"atempo={resto:.6f}")
    return ",".join(filtros)


def montar_filtros(args, duracao, tem_audio):
    """Monta os filtergraphs de vídeo e áudio na ordem documentada."""
    fv, fa = [], []

    if args.velocidade and args.velocidade != 1.0:
        if not 0.25 <= args.velocidade <= 8:
            erro("--velocidade deve estar entre 0.25 e 8")
        fv.append(f"setpts=PTS/{args.velocidade:.6f}")
        fa.append(_filtro_atempo(args.velocidade))
        duracao = duracao / args.velocidade

    if args.vertical or args.quadrado:
        larg, alt = (1080, 1920) if args.vertical else (1080, 1080)
        fv.append(
            f"split[fundo][frente];"
            f"[fundo]scale={larg}:{alt}:force_original_aspect_ratio=increase,"
            f"crop={larg}:{alt},boxblur=24:4[f1];"
            f"[frente]scale={larg}:{alt}:force_original_aspect_ratio=decrease"
            f"[f2];[f1][f2]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    elif args.resolucao:
        fv.append(f"scale=-2:'min({args.resolucao},ih)'")

    if args.texto:
        fonte = achar_fonte()
        opc_fonte = f"fontfile={fonte}:" if fonte else "font='DejaVu Sans':"
        pos_y = {
            "topo": "h*0.08",
            "centro": "(h-text_h)/2",
            "base": "h*0.92-text_h",
        }[args.texto_pos]
        fv.append(
            f"drawtext={opc_fonte}text='{escapar_drawtext(args.texto)}':"
            f"fontsize=h/16:fontcolor=white:borderw=3:bordercolor=black:"
            f"x=(w-text_w)/2:y={pos_y}"
        )

    if args.fade:
        d = 0.5
        ini_saida = max(duracao - d, 0)
        fv.append(f"fade=t=in:st=0:d={d},fade=t=out:st={ini_saida:.3f}:d={d}")
        fa.append(f"afade=t=in:st=0:d={d},afade=t=out:st={ini_saida:.3f}:d={d}")

    if args.volume and args.volume != 1.0:
        fa.append(f"volume={args.volume}")

    if not tem_audio or args.mudo:
        fa = None  # áudio será descartado

    return fv, fa, duracao


def editar_arquivo(entrada, args):
    checar_dependencias(precisa_ytdlp=False)
    if not os.path.exists(entrada):
        erro(f"arquivo não encontrado: {entrada}")
    os.makedirs(args.saida, exist_ok=True)
    duracao, tem_audio = sondar(entrada)
    base = args.nome or os.path.splitext(os.path.basename(entrada))[0]

    tmp = tempfile.mkdtemp(prefix="videobot-")
    try:
        atual = entrada
        if args.cortar:
            cortes = [parse_corte(c) for c in args.cortar]
            for ini, fim in cortes:
                if fim > duracao + 1:
                    erro(
                        f"corte {ini:.0f}-{fim:.0f}s passa do fim do vídeo "
                        f"({duracao:.0f}s)"
                    )
            atual = _cortar_e_emendar(atual, cortes, tmp)
            duracao, tem_audio = sondar(atual)

        # saídas alternativas -------------------------------------------------
        if args.mp3:
            destino = nome_livre(args.saida, base, ".mp3")
            rodar(
                [
                    "ffmpeg", "-y", "-i", atual, "-vn",
                    "-c:a", "libmp3lame", "-q:a", "2", destino,
                ]
            )
            print(destino)
            return destino

        if args.gif:
            destino = nome_livre(args.saida, base, ".gif")
            paleta = os.path.join(tmp, "paleta.png")
            escala = f"fps={args.gif_fps},scale={args.gif_largura}:-1:flags=lanczos"
            rodar(["ffmpeg", "-y", "-i", atual, "-vf",
                   f"{escala},palettegen", paleta])
            rodar(
                [
                    "ffmpeg", "-y", "-i", atual, "-i", paleta,
                    "-lavfi", f"{escala}[x];[x][1:v]paletteuse", destino,
                ]
            )
            print(destino)
            return destino

        # encode principal ----------------------------------------------------
        fv, fa, duracao = montar_filtros(args, duracao, tem_audio)
        destino = nome_livre(args.saida, base, ".mp4")
        cmd = ["ffmpeg", "-y", "-i", atual]
        if fv:
            # os filtros formam uma cadeia única; o bloco vertical/quadrado
            # traz sub-cadeias rotuladas ([f1][f2]…) já ligadas por ';'
            cmd += ["-vf", ",".join(fv)]
        if fa is None:
            cmd += ["-an"]
        elif fa:
            cmd += ["-af", ",".join(fa)]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        ]
        if fa is not None:
            cmd += ["-c:a", "aac", "-b:a", "160k"]
        cmd.append(destino)
        rodar(cmd)

        # compressão para tamanho alvo ---------------------------------------
        if args.comprimir_mb:
            tamanho_mb = os.path.getsize(destino) / (1024 * 1024)
            if tamanho_mb > args.comprimir_mb:
                dur_final, _ = sondar(destino)
                if dur_final <= 0:
                    dur_final = duracao or 1
                bits_total = args.comprimir_mb * 8 * 1024 * 1024 * 0.93
                kbps_video = math.floor(
                    bits_total / dur_final / 1000 - (0 if fa is None else 96)
                )
                if kbps_video < 100:
                    erro(
                        f"impossível comprimir {dur_final:.0f}s para "
                        f"{args.comprimir_mb}MB com qualidade assistível — "
                        "corte o vídeo ou aumente o limite"
                    )
                comprimido = nome_livre(args.saida, base + "-comprimido", ".mp4")
                cmd = [
                    "ffmpeg", "-y", "-i", destino,
                    "-c:v", "libx264", "-preset", "veryfast",
                    "-b:v", f"{kbps_video}k",
                    "-maxrate", f"{kbps_video}k",
                    "-bufsize", f"{kbps_video * 2}k",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                ]
                cmd += ["-an"] if fa is None else ["-c:a", "aac", "-b:a", "96k"]
                cmd.append(comprimido)
                rodar(cmd)
                os.remove(destino)
                destino = comprimido

        print(destino)
        return destino
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------- clipes


def detectar_silencios(arquivo):
    """Pontos médios dos silêncios do áudio — candidatos naturais de corte."""
    proc = subprocess.run(
        [
            "ffmpeg", "-i", arquivo, "-af",
            "silencedetect=noise=-30dB:d=0.4", "-f", "null", "-",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    pontos, inicio = [], None
    for linha in proc.stderr.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", linha)
        if m:
            inicio = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+)", linha)
        if m and inicio is not None:
            pontos.append((inicio + float(m.group(1))) / 2)
            inicio = None
    return pontos


def planejar_clipes(duracao, pontos, quantidade, min_s, max_s):
    """Divide [0, duracao] em trechos de min_s–max_s, cortando de
    preferência num silêncio. Ajusta a janela para render >= quantidade
    clipes quando a duração permite."""
    if duracao < min_s:
        erro(f"vídeo tem só {duracao:.0f}s — menor que o clipe mínimo ({min_s:.0f}s)")
    # janela efetiva: encolhe o teto para alcançar a quantidade pedida
    max_ef = max(min_s, min(max_s, duracao / quantidade))
    cortes, t = [], 0.0
    while t < duracao - 0.5:
        restante = duracao - t
        if restante <= max_s:
            fim = duracao
        else:
            janela = [p for p in pontos if t + min_s <= p <= t + max_ef]
            fim = max(janela) if janela else t + max_ef
        if fim - t < min_s and cortes and (fim - cortes[-1][0]) <= max_s * 1.2:
            # rabinho curto no final: estica o clipe anterior até o fim
            cortes[-1] = (cortes[-1][0], fim)
        else:
            cortes.append((t, fim))
        t = fim
    return cortes


def gerar_clipes(entrada, args):
    checar_dependencias(precisa_ytdlp=False)
    if not os.path.exists(entrada):
        erro(f"arquivo não encontrado: {entrada}")
    os.makedirs(args.saida, exist_ok=True)
    duracao, tem_audio = sondar(entrada)
    base = args.nome or os.path.splitext(os.path.basename(entrada))[0]

    pontos = detectar_silencios(entrada) if tem_audio else []
    cortes = planejar_clipes(
        duracao, pontos, args.quantidade, args.min_s, args.max_s
    )
    if len(cortes) < args.quantidade:
        print(
            f"AVISO: vídeo de {duracao:.0f}s rende só {len(cortes)} clipes "
            f"de >= {args.min_s:.0f}s (pedido: {args.quantidade})",
            file=sys.stderr,
        )

    fv = []
    if args.vertical:
        fv.append(
            "split[fundo][frente];"
            "[fundo]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=24:4[f1];"
            "[frente]scale=1080:1920:force_original_aspect_ratio=decrease"
            "[f2];[f1][f2]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    elif args.resolucao:
        fv.append(f"scale=-2:'min({args.resolucao},ih)'")

    gerados = []
    for i, (ini, fim) in enumerate(cortes, 1):
        destino = nome_livre(args.saida, f"{base}-{i:02d}", ".mp4")
        cmd = ["ffmpeg", "-y", "-ss", f"{ini:.3f}", "-to", f"{fim:.3f}",
               "-i", entrada]
        if fv:
            cmd += ["-vf", ",".join(fv)]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                "-c:a", "aac", "-b:a", "160k", destino]
        rodar(cmd)
        gerados.append(destino)
        print(destino)
    return gerados


# ---------------------------------------------------------------------- CLI


def montar_parser():
    p = argparse.ArgumentParser(
        prog="videobot",
        description="Baixa e edita vídeos (yt-dlp + ffmpeg).",
    )
    sub = p.add_subparsers(dest="comando", required=True)

    def opcoes_comuns(sp):
        sp.add_argument("--saida", default="saida")
        sp.add_argument("--nome")

    def opcoes_edicao(sp):
        sp.add_argument("--cortar", action="append")
        sp.add_argument("--velocidade", type=float)
        sp.add_argument("--vertical", action="store_true")
        sp.add_argument("--quadrado", action="store_true")
        sp.add_argument("--resolucao", type=int)
        sp.add_argument("--texto")
        sp.add_argument(
            "--texto-pos", choices=["topo", "centro", "base"], default="base"
        )
        sp.add_argument("--fade", action="store_true")
        sp.add_argument("--mudo", action="store_true")
        sp.add_argument("--volume", type=float)
        sp.add_argument("--comprimir-mb", type=float)
        sp.add_argument("--mp3", action="store_true")
        sp.add_argument("--gif", action="store_true")
        sp.add_argument("--gif-fps", type=int, default=12)
        sp.add_argument("--gif-largura", type=int, default=480)

    b = sub.add_parser("baixar", help="só baixa")
    b.add_argument("url")
    b.add_argument("--qualidade", type=int, default=1080)
    opcoes_comuns(b)

    e = sub.add_parser("editar", help="edita um arquivo local")
    e.add_argument("arquivo")
    opcoes_comuns(e)
    opcoes_edicao(e)

    a = sub.add_parser("auto", help="baixa e edita em sequência")
    a.add_argument("url")
    a.add_argument("--qualidade", type=int, default=1080)
    opcoes_comuns(a)
    opcoes_edicao(a)

    c = sub.add_parser(
        "clipes", help="fatia em vários clipes curtos, cortando nas pausas"
    )
    c.add_argument("origem", help="URL ou arquivo local")
    c.add_argument("--quantidade", type=int, default=15)
    c.add_argument("--min-s", type=float, default=15)
    c.add_argument("--max-s", type=float, default=60)
    c.add_argument("--vertical", action="store_true")
    c.add_argument("--resolucao", type=int)
    c.add_argument("--qualidade", type=int, default=1080)
    opcoes_comuns(c)

    return p


def main():
    args = montar_parser().parse_args()
    if getattr(args, "vertical", False) and getattr(args, "quadrado", False):
        erro("use --vertical OU --quadrado, não os dois")
    if args.comando == "baixar":
        baixar(args)
    elif args.comando == "editar":
        editar_arquivo(args.arquivo, args)
    elif args.comando == "clipes":
        origem = args.origem
        if origem.startswith(("http://", "https://")):
            args.url = origem
            nome_final = args.nome
            args.nome = None
            origem = baixar(args)
            args.nome = nome_final
        gerar_clipes(origem, args)
    else:  # auto
        nome_final = args.nome
        args.nome = None
        baixado = baixar(args)
        args.nome = nome_final
        editar_arquivo(baixado, args)


if __name__ == "__main__":
    main()
