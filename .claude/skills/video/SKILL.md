---
name: video
description: Baixa um vídeo (YouTube etc.) e edita conforme o pedido do usuário — cortes, fatiamento em clipes curtos para redes sociais, formato vertical/quadrado, velocidade, texto, fade, compressão para WhatsApp, GIF ou MP3 — e devolve os arquivos prontos no chat (funciona pelo celular). Use quando o usuário pedir para baixar, cortar, fatiar ou editar um vídeo.
---

# /video — baixar e editar vídeo

O usuário pede em linguagem natural (ex.: "baixa esse vídeo, corta do 0:30
ao 1:20, deixa vertical" ou "fatia essa live em 15 clipes de até 1min").
Você traduz o pedido para o CLI `cli/videobot.py` e devolve os arquivos
finais com **SendUserFile** (display: attach) — é assim que chegam no
celular.

## 1. Preparar o ambiente (uma vez por sessão)

```bash
pip install -q yt-dlp
which ffmpeg || (apt-get update -qq; apt-get install -y -qq ffmpeg)
```

Trabalhe no scratchpad da sessão (NUNCA salve vídeos dentro do repositório
nem os commite).

## 2. Traduzir o pedido para o CLI

Comandos: `baixar URL` | `editar ARQUIVO` | `auto URL` (baixa + edita) |
`clipes URL_OU_ARQUIVO` (fatia em vários clipes curtos).

| Pedido do usuário                          | Flags                          |
| ------------------------------------------ | ------------------------------ |
| "corta do 0:30 ao 1:20"                    | `--cortar 0:30-1:20`           |
| "só as partes X e Y" (emenda na ordem)     | `--cortar A-B --cortar C-D`    |
| "vertical / pra Reels / Stories / TikTok"  | `--vertical`                   |
| "quadrado / pro feed"                      | `--quadrado`                   |
| "acelera 2x" / "câmera lenta"              | `--velocidade 2` / `0.5`       |
| "coloca o título X"                        | `--texto "X"` (`--texto-pos topo\|centro\|base`) |
| "com fade / entrada e saída suaves"        | `--fade`                       |
| "sem som"                                  | `--mudo`                       |
| "aumenta o volume"                         | `--volume 2`                   |
| "pra mandar no WhatsApp"                   | `--comprimir-mb 16`            |
| "só o áudio / em MP3"                      | `--mp3`                        |
| "vira um GIF"                              | `--gif`                        |
| "em 720p / mais leve"                      | `--resolucao 720`              |
| "fatia em 15 clipes de 15s a 1min"         | comando `clipes` (abaixo)      |

### Modo clipes (cortes para redes sociais)

`clipes URL_OU_ARQUIVO --quantidade 15 --min-s 15 --max-s 60 [--vertical]`
fatia o vídeo em vários clipes curtos, escolhendo os pontos de corte nas
**pausas da fala** (detecção de silêncio) — a janela encolhe sozinha para
render a quantidade pedida. Imprime um arquivo numerado por linha
(`base-01.mp4`, `base-02.mp4`, …). Envie todos com um único SendUserFile.

Exemplo completo:

```bash
python cli/videobot.py clipes "URL" \
  --quantidade 15 --min-s 15 --max-s 60 \
  --nome clipe --saida "$SCRATCHPAD/saida"
```

O script imprime o caminho de cada arquivo final no stdout.

## 3. Devolver o resultado

- Envie os arquivos finais com `SendUserFile` (files: [caminhos], display:
  "attach") e uma legenda curta com duração/resolução/tamanho.
- Se o total passar de ~30 MB por arquivo, avise e ofereça
  `--comprimir-mb` ou `--resolucao 720`.
- Se o usuário pedir WeTransfer ou outro serviço externo: tente somente se
  a rede permitir; se falhar (bloqueio, captcha, sem API), entregue pelo
  chat e explique.

## Avisos e limites

- **Rede bloqueada**: se o yt-dlp falhar com `403 Forbidden` no proxy, a
  política de rede do ambiente remoto está bloqueando o site do vídeo.
  Explique que é preciso liberar em claude.ai/code → ambiente → política
  de rede (YouTube: `youtube.com`, `*.googlevideo.com`, `*.ytimg.com`) ou
  usar acesso total. Não tente burlar o proxy.
- Se o pedido de corte passar do fim do vídeo, o script aborta com erro
  claro — confira a duração com o usuário.
- Ambiguidade real (ex.: não deu URL, ou não disse os tempos do corte):
  pergunte antes de rodar.
- Direitos autorais: a ferramenta é para uso pessoal do usuário (vídeos
  próprios ou uso privado). Não ajude a republicar conteúdo de terceiros
  como se fosse dele.
