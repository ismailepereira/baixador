# Baixador Android

Versão APK Android nativa do Baixador — funciona **sem o servidor PC**.

Cole o link → escolha vídeo/áudio/foto → baixa direto no celular. Suporta YouTube, Instagram, TikTok, Twitter/X, Facebook, Reddit, e ~1000 outros sites (via yt-dlp embarcado). Spotify funciona via YouTube Music (precisa de credenciais gratuitas).

```
┌─────────────────────────────────┐
│  Baixador (app Android)         │
│                                  │
│  [cole o link aqui]              │
│  [Vídeo] [Áudio] [Foto]          │
│  Qualidade: 720p ▾               │
│  ━━━━━━━━━━━━ Baixar ━━━━━━━━━  │
└─────────────────────────────────┘
            │
            ▼
   yt-dlp (embarcado) + FFmpeg
            │
            ▼
   /Downloads/Baixador/<arquivo>
```

## Como funciona

- **yt-dlp embarcado**: usa a biblioteca [youtubedl-android](https://github.com/junkfood02/youtubedl-android), que empacota o yt-dlp via Python-for-Android + FFmpegKit dentro do APK. Tudo roda no celular.
- **Spotify**: detecta link Spotify, consulta a API oficial pra pegar `artista + título`, e baixa o equivalente do YouTube Music via yt-dlp (sem quebrar DRM).
- **Share Intent**: instalou? Aparece como destino no menu "Compartilhar" do YouTube/IG/etc. Compartilha → app abre com a URL já preenchida.
- **Foreground Service**: download continua mesmo com a tela apagada. Mostra notificação com progresso e botão "Cancelar".
- **Salva em**: `Downloads/Baixador/` (via MediaStore — visível em qualquer galeria/gerenciador de arquivos).

## Setup — primeira vez

### 1. Instale o Android Studio

Baixe [aqui](https://developer.android.com/studio) (gratuito). Durante o setup, deixe ele baixar:
- Android SDK Platform (API 34)
- Android SDK Build-Tools
- Android Emulator (opcional, pra testar sem celular)

### 2. Abra o projeto

No Android Studio: **File → Open** → selecione a pasta `F:\Claude\baixador\android`.

Ele vai sincronizar o Gradle (baixar dependências) — pode demorar 5–10 minutos na primeira vez. Se aparecer "Trust Project", clique em **Trust**.

### 3. (Opcional) Configure credenciais Spotify

Sem isso, links do Spotify dão erro "não configurado". Sites como YouTube/IG continuam funcionando normalmente.

1. Vá em [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) e faça login.
2. Clique em **Create app**:
   - Name: `Baixador` (qualquer nome)
   - Description: `app pessoal`
   - Redirect URI: `http://localhost` (não usaremos, mas é obrigatório)
   - APIs: marque **Web API**
3. Após criar, clique em **Settings**. Copie:
   - **Client ID**
   - **Client Secret** (clique em "View client secret")
4. Crie o arquivo `F:\Claude\baixador\android\keystore.properties` com:

```properties
spotify.clientId=COLE_AQUI_O_CLIENT_ID
spotify.clientSecret=COLE_AQUI_O_CLIENT_SECRET
```

5. Faça **Build → Rebuild Project**.

> ⚠️ Esse arquivo está no `.gitignore` — nunca commite credenciais.

### 4. Gere o APK debug (mais rápido pra testar)

No Android Studio:
- **Build → Build Bundle(s) / APK(s) → Build APK(s)**
- Quando terminar, clique em **locate** no popup. O APK fica em `app/build/outputs/apk/debug/app-debug.apk`.

Copie pro celular (cabo USB, WhatsApp pra si mesmo, Google Drive, etc.) e instale. Antes de instalar você vai precisar **autorizar instalação de fontes desconhecidas** nas configs do Android.

### 5. (Opcional) APK release assinado

Pra um APK menor e mais rápido (com ProGuard ativado):

1. Gere uma keystore (uma única vez):
   ```powershell
   keytool -genkey -v -keystore baixador.keystore -alias baixador -keyalg RSA -keysize 2048 -validity 10000
   ```
   (use `keytool` que vem com a JDK do Android Studio em `Android Studio\jbr\bin\`)

2. Adicione em `keystore.properties`:
   ```properties
   storeFile=baixador.keystore
   storePassword=SUA_SENHA
   keyAlias=baixador
   keyPassword=SUA_SENHA

   spotify.clientId=...
   spotify.clientSecret=...
   ```

3. **Build → Generate Signed Bundle / APK → APK → release**.

## Uso

1. Abra o app (ou compartilhe um link de qualquer outro app pra ele).
2. O campo de URL preenche sozinho via share. Senão, cole o link.
3. Escolha modo: **Vídeo** (MP4), **Áudio** (MP3) ou **Foto** (imagens de IG/Twitter).
4. Escolha qualidade.
5. Toque em **Baixar**. Notificação aparece com o progresso.
6. Arquivo final em `Internal Storage/Download/Baixador/`.

## Limitações conhecidas

- **Pouco RAM/celular antigo**: a primeira inicialização do yt-dlp (Python embedded) leva 5–15 segundos. Depois fica instantâneo.
- **YouTube muda player**: se algum vídeo do YouTube falhar, abra Android Studio → faça `gradle clean` + sync — a biblioteca youtubedl-android atualiza o binário yt-dlp empacotado. Você também pode rodar `YoutubeDL.getInstance().updateYoutubeDL(context)` programaticamente (não está exposto na UI por enquanto).
- **Spotify**: apenas track/album/playlist públicos. Episódios/podcasts não.
- **Tamanho do APK**: ~50 MB (Python embedded + ffmpeg pesam).
- **Sem Play Store**: distribuição manual (APK direto). Pra publicar precisaria ofuscar o uso do yt-dlp (Google não gosta).

## Estrutura do projeto

```
android/
├── app/
│   ├── build.gradle.kts          # deps + config (Compose, youtubedl-android)
│   └── src/main/
│       ├── AndroidManifest.xml   # permissões, share intent
│       ├── java/com/baixador/
│       │   ├── BaixadorApp.kt    # Application — inicializa yt-dlp/FFmpeg
│       │   ├── MainActivity.kt   # ponto de entrada, recebe share intent
│       │   ├── data/
│       │   │   ├── DownloadHub.kt        # StateFlow bridge Service ↔ UI
│       │   │   ├── DownloadJob.kt        # data classes do job/estado
│       │   │   ├── DownloadMode.kt       # enums (Video/Áudio/Foto + qualidade)
│       │   │   ├── Downloader.kt         # wrapper yt-dlp + export pra Downloads
│       │   │   └── SpotifyResolver.kt    # API Spotify → ytsearch1: query
│       │   ├── service/
│       │   │   └── DownloadService.kt    # Foreground Service + notificação
│       │   └── ui/
│       │       ├── HomeScreen.kt         # Compose UI
│       │       ├── HomeViewModel.kt
│       │       └── theme/                # Material 3 dark (verde Baixador)
│       └── res/
│           ├── mipmap-anydpi-v26/        # ícone adaptativo
│           └── values/                   # strings, cores
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties
└── README.md
```

## Tecnologias

| Componente | Versão | Pra quê |
|---|---|---|
| Kotlin | 1.9.22 | linguagem |
| Jetpack Compose | BOM 2024.02 | UI declarativa |
| Material 3 | 1.x | design system |
| youtubedl-android | 0.16.0 | yt-dlp embarcado |
| FFmpegKit | (via youtubedl-android) | merge de streams, conversão MP3 |
| OkHttp | 4.12.0 | chamadas pra API Spotify |
| Coroutines | 1.7.3 | concorrência |
| AGP | 8.2.2 | build |
| Gradle | 8.5 | build tool |

## Diferenças vs. versão desktop

| Feature | Desktop (PC) | Android |
|---|---|---|
| YouTube/IG/TikTok/etc. | yt-dlp | yt-dlp embarcado |
| Spotify | spotdl (Python) | API Spotify + ytsearch |
| Fotos IG/Twitter | gallery-dl | yt-dlp `--write-thumbnail` |
| Recorte de vídeo | sim | não (V1) |
| Legendas | sim | não (V1) |
| Cookies do browser | sim | não (V1) |
| Local dos arquivos | `~/Downloads/Baixador` | `/Download/Baixador/` |

## Roadmap (ideias)

- [ ] Botão "atualizar yt-dlp" na UI (pra quando YouTube muda player)
- [ ] Recorte de vídeo (start/end)
- [ ] Legendas embedded
- [ ] Lista de downloads paralelos
- [ ] Tema claro
- [ ] Histórico persistente (DataStore — dep já incluída)

## Licença

Mesmo espírito do Baixador desktop: uso pessoal. Não usar pra distribuição comercial ou redistribuição de conteúdo protegido.
