# Baixador

Extensão Chrome + servidor local que baixa vídeos/áudios de YouTube, Instagram,
Facebook, TikTok, Twitter, Twitch e centenas de outros sites — e também Spotify
(via YouTube Music, sem quebrar DRM).

## Como funciona

```
[ extensão Chrome ]  ──HTTP──▶  [ servidor Python local (127.0.0.1:5005) ]
                                       │
                                       ├─▶ yt-dlp  (YouTube, IG, FB, etc.)
                                       └─▶ spotdl  (Spotify)
                                              │
                                              ▼
                              ~/Downloads/Baixador/
```

A extensão só manda a URL da aba atual. O servidor local roda `yt-dlp`/`spotdl`
e salva o arquivo. O Chrome em si não baixa nada — assim contornamos o problema
de HLS/DASH/streams fragmentados que extensões puras não conseguem juntar.

## Instalação

### 1. Servidor

Pré-requisito: **Python 3.10+** instalado e no PATH.

Dê duplo clique em `start.bat`. Na primeira vez ele cria um venv e instala
`yt-dlp`, `spotdl` e `flask`. Pode demorar 1-2 min. Depois disso, abre na hora.

Mantenha a janela do `start.bat` aberta enquanto for usar — fechando ela, o
servidor para.

### 2. Extensão Chrome

1. Abra `chrome://extensions`
2. Ligue o **Modo do desenvolvedor** (canto superior direito)
3. Clique em **Carregar sem compactação**
4. Selecione a pasta `F:\Claude\baixador\extension`
5. (Opcional) Fixe a extensão clicando no ícone de peça do Chrome

### 3. Ícones

A extensão referencia `icons/icon16.png`, `icon48.png`, `icon128.png`. Se
quiser, gere/cole 3 PNGs nesses tamanhos em `extension/icons/`. Sem isso, a
extensão funciona, mas mostra o ícone padrão do Chrome.

## Uso

- **Em qualquer página com vídeo** (YouTube, IG, TikTok, Twitter): um botão
  verde "⬇ Baixar" aparece flutuando sobre o vídeo. Um clique = MP4 na pasta
  `~/Downloads/Baixador`.
- **Spotify**: abra a página da música/playlist/álbum, clique no ícone da
  extensão e em "Áudio (MP3)". O `spotdl` pega os metadados do Spotify e baixa
  o áudio do YouTube Music.
- **Qualquer URL**: clique no ícone da extensão e use "Vídeo (MP4)" ou
  "Áudio (MP3)" — o yt-dlp resolve a maioria dos sites suportados
  ([lista completa](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)).

### ✂️ Edição pelo celular (v1.4)

Na página mobile (`http://IP-DO-PC:5005/mobile`), abra **"✂️ Edição
(opcional)"** antes de baixar um vídeo. Dá pra combinar:

- **Cortar** um trecho (início/fim, ex.: `0:30` a `1:20`)
- **Formato**: vertical 9:16 (Stories/Reels/TikTok) ou quadrado 1:1, com
  fundo desfocado
- **Velocidade**: 0.5x, 1.5x ou 2x
- **Texto** sobreposto no vídeo
- **Fade** de entrada/saída, **sem som**, e **≤16 MB** (pronto pro WhatsApp)

O servidor baixa o vídeo, aplica as edições com o ffmpeg e devolve o
arquivo já pronto pro celular. Requer `ffmpeg` (mesmo requisito dos
downloads com áudio). O motor fica em `server/editor.py`.

### 🤖 Automação via Claude (skill /video)

Abrindo uma sessão do Claude Code neste repositório (inclusive pelo
celular), dá pra pedir em português normal — ex.: *"baixa esse vídeo e
fatia em 15 clipes de 15s a 1min"* — e o Claude roda o `cli/videobot.py`
e devolve os arquivos no chat. O modo `clipes` corta nas **pausas da
fala** (detecção de silêncio); há também corte simples, vertical/quadrado,
velocidade, texto, fade, compressão pra WhatsApp, MP3 e GIF.

## Notas legais

- Baixar conteúdo público para uso pessoal viola os ToS de YouTube/IG/FB/etc.
  Pode haver consequências (raro, mas possível). Use por sua conta.
- **DRM (Netflix, Disney+, Spotify Premium streaming):** o `spotdl` aqui NÃO
  quebra DRM — ele pega metadados do Spotify e baixa o equivalente do YouTube
  Music. Isso é legal porque o áudio vem do YouTube, não do Spotify.
- Não use para distribuição comercial ou redistribuição de obras protegidas.

## Solução de problemas

- **"Servidor OFFLINE" no popup** → janela do `start.bat` está fechada.
- **`yt-dlp` falha em vídeo do YouTube específico** → atualize:
  na pasta `server/`, ative o venv (`.venv\Scripts\activate`) e rode
  `pip install -U yt-dlp`. O YouTube muda o player de tempos em tempos.
- **Vídeo sai sem áudio (ou só áudio)** → falta `ffmpeg`. Baixe de
  [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/) (zip "release essentials"),
  extraia, e coloque a pasta `bin/` no PATH do Windows.
- **Spotify dá erro** → `spotdl` precisa de `ffmpeg` também. Mesmo passo.

---

## Autoria

Desenvolvido por **Ismaile Pereira Machado**
🔗 Portfólio: [ismailepereira.github.io](https://ismailepereira.github.io)
🐙 GitHub: [@ismailepereira](https://github.com/ismailepereira)

