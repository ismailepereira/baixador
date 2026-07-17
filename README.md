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
4. Selecione a pasta `extension` deste projeto. Se instalou pelo
   `Baixador-Setup-*.exe`, ela fica em `%LOCALAPPDATA%\Baixador\extension`.
5. (Opcional) Fixe a extensão clicando no ícone de peça do Chrome

> Ao atualizar o Baixador, o instalador troca os arquivos da extensão, mas o
> Chrome não recarrega sozinho: volte em `chrome://extensions` e clique em
> **Atualizar** no card do Baixador, senão o popup continua o da versão antiga.

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
- **O Premiere não abre o vídeo** → o perfil "Padrão" pega o melhor formato do
  YouTube, que costuma ser AV1 ou VP9 com áudio Opus — codecs que o Premiere não
  decodifica, mesmo dentro de um `.mp4`. No popup da extensão, escolha
  **"Melhor p/ editar no Premiere"** (H.264 + AAC). Se mesmo assim falhar, use
  **"Premiere ProRes"**, que re-encoda e sempre funciona (arquivo bem maior).

---

## Build do instalador (Windows)

Pré-requisitos: venv do `server/` criado, `bin/ffmpeg/bin/ffmpeg.exe` presente
(o `start.bat` baixa), e [Inno Setup 6](https://jrsoftware.org/isdl.php).

```bash
# 1. Empacota o servidor + ffmpeg num executavel (dist/Baixador/)
server/.venv/Scripts/python.exe -m PyInstaller Baixador.spec --noconfirm

# 2. Gera o Baixador-Setup-v<versao>.exe na raiz
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" Baixador.iss
```

A versão fica em três lugares e precisa bater: `__version__` em
`server/server.py`, `AppVersion` em `Baixador.iss`, e `version` em
`extension/manifest.json` (esse último ficou 3 releases atrasado antes de
alguém notar — é o que aparece em `chrome://extensions`, então é a forma mais
fácil do usuário confirmar que pegou a versão certa).

O instalador leva junto a pasta `extension/` — veja a nota em [Instalação](#2-extensão-chrome)
sobre recarregar a extensão no Chrome depois de atualizar.

> **Não mude o `AppId` do `Baixador.iss`.** Ele é o que faz o instalador atualizar
> por cima em vez de instalar uma segunda cópia. Não é um GUID válido e tem uma
> chave `}` sobrando — foi escrito à mão na v1.0.0 e está reproduzido exatamente
> como ficou no registro. "Consertá-lo" quebraria a atualização de quem já tem o
> Baixador instalado.

## Publicar uma atualização

O Baixador checa atualizações sozinho: o `background.js` da extensão consulta
`/check-update` na inicialização e a cada 6h, e o servidor compara `__version__`
com o `update.json` publicado. Se houver versão nova, o usuário recebe uma
notificação que, clicada, abre o link de download. Ele **não** instala sozinho —
quem baixa e roda o instalador é o usuário.

Para lançar a versão `X.Y.Z`:

1. Suba a versão em `server/server.py` (`__version__`) e em `Baixador.iss` (`AppVersion`).
2. Builde o instalador (seção acima).
3. Crie a Release `vX.Y.Z` no GitHub e anexe o `Baixador-Setup-vX.Y.Z.exe`
   (o `.exe` é grande demais pro repo — por isso fica na Release, e é por isso
   que `*.exe` está no `.gitignore`).
4. Atualize o `update.json` da raiz (`version`, `url`, `notes`) e dê push.

O `update.json` é servido pelo raw do GitHub, e é ele que o
`UPDATE_FEED_URL` em `server/server.py` aponta. A ordem importa: publique a
Release **antes** do `update.json`, senão os usuários recebem a notificação e
clicam num link que ainda não existe.

---

## Autoria

Desenvolvido por **Ismaile Pereira Machado**
🔗 Portfólio: [ismailepereira.github.io](https://ismailepereira.github.io)
🐙 GitHub: [@ismailepereira](https://github.com/ismailepereira)

