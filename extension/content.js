// Painel fixo no canto da tela — sempre visivel, nao depende de posicao de video.
// Detecta se ha <video> na pagina e indica visualmente.

// i18n.js (carregado antes via manifest) expoe window.__baixador_i18n.
const T = (window.__baixador_i18n?.T) || {};

const QUALITIES = [
  { label: T.quality_best || "Melhor disponível", value: "best" },
  { label: T.quality_1080 || "1080p (Full HD)",   value: "1080p" },
  { label: T.quality_720  || "720p (HD)",         value: "720p" },
  { label: T.quality_480  || "480p",              value: "480p" },
  { label: T.quality_360  || "360p",              value: "360p" },
];

const PROFILES = [
  { value: "padrao",   label: T.profile_padrao   || "Padrão (só assistir)",              hint: T.profile_hint_padrao   || "" },
  { value: "premiere", label: T.profile_premiere || "Melhor p/ editar no Premiere",       hint: T.profile_hint_premiere || "" },
  { value: "capcut",   label: T.profile_capcut   || "Melhor p/ editar no CapCut",         hint: T.profile_hint_capcut   || "" },
  { value: "prores",   label: T.profile_prores   || "Premiere ProRes (pesado)",           hint: T.profile_hint_prores   || "" },
];

let root, fab, panel, statusEl;
let collapsed = true;

function build() {
  if (document.getElementById("baixador-root")) return;

  root = document.createElement("div");
  root.id = "baixador-root";
  root.className = "collapsed";

  // FAB (botao circular minimizado)
  fab = document.createElement("button");
  fab.id = "baixador-fab";
  fab.type = "button";
  fab.title = "Baixador — clique para abrir";
  fab.textContent = "⬇";
  fab.addEventListener("click", () => toggle(false));
  root.appendChild(fab);

  // Painel expandido
  panel = document.createElement("div");
  panel.id = "baixador-panel";

  const header = document.createElement("div");
  header.id = "baixador-header";
  const title = document.createElement("span");
  title.className = "title";
  title.textContent = T.panel_title || "⬇ Baixador";
  const close = document.createElement("button");
  close.className = "close";
  close.textContent = "−";
  close.title = T.minimize || "Minimizar";
  close.addEventListener("click", (e) => { e.stopPropagation(); toggle(true); });
  header.appendChild(title);
  header.appendChild(close);
  panel.appendChild(header);

  // Grupo de video
  const gv = document.createElement("div");
  gv.className = "group";
  gv.textContent = T.group_video || "Vídeo (MP4)";
  panel.appendChild(gv);

  // Seletor de formato (perfil de codec) -- afeta os botoes de qualidade abaixo.
  const profileRow = document.createElement("div");
  profileRow.id = "bx-profile-row";
  const profileSelect = document.createElement("select");
  profileSelect.id = "bx-profile";
  profileSelect.title = T.profile_label || "Formato:";
  for (const p of PROFILES) {
    const opt = document.createElement("option");
    opt.value = p.value;
    opt.textContent = p.label;
    profileSelect.appendChild(opt);
  }
  profileRow.appendChild(profileSelect);
  panel.appendChild(profileRow);

  const profileHint = document.createElement("div");
  profileHint.id = "bx-profile-hint";
  panel.appendChild(profileHint);

  function updateProfileHint() {
    const p = PROFILES.find(x => x.value === profileSelect.value);
    profileHint.textContent = p?.hint || "";
  }
  chrome.storage.local.get(["profile"]).then(({ profile }) => {
    if (profile) profileSelect.value = profile;
    updateProfileHint();
  });
  profileSelect.addEventListener("change", () => {
    chrome.storage.local.set({ profile: profileSelect.value });
    updateProfileHint();
  });
  profileSelect.addEventListener("click", (e) => e.stopPropagation());

  for (const q of QUALITIES) {
    const b = document.createElement("button");
    b.className = "opt";
    b.textContent = q.label;
    b.addEventListener("click", () => download("video", q.value));
    panel.appendChild(b);
  }

  // Checkbox de legendas (afeta o proximo download de video)
  const subsLabel = document.createElement("label");
  subsLabel.className = "checkbox-row";
  subsLabel.innerHTML = `
    <input type="checkbox" id="bx-subs" />
    <span>${T.subtitles_label || "📝 Incluir legendas (PT/EN)"}</span>
  `;
  panel.appendChild(subsLabel);
  chrome.storage.local.get(["subtitles"]).then(({ subtitles }) => {
    subsLabel.querySelector("input").checked = !!subtitles;
  });
  subsLabel.querySelector("input").addEventListener("change", (e) => {
    chrome.storage.local.set({ subtitles: e.target.checked });
  });

  // Toggle de Recortes
  const trimToggle = document.createElement("button");
  trimToggle.id = "bx-trim-toggle";
  trimToggle.type = "button";
  trimToggle.textContent = T.trim_open || "✂ Cortar trecho";
  panel.appendChild(trimToggle);

  const trimBox = document.createElement("div");
  trimBox.id = "bx-trim";
  trimBox.innerHTML = `
    <div class="row">
      <span>${T.trim_start || "Início:"}</span>
      <input type="text" id="bx-trim-start" placeholder="00:00" />
    </div>
    <div class="row">
      <span>${T.trim_end || "Fim:"}</span>
      <input type="text" id="bx-trim-end" placeholder="00:30" />
    </div>
    <div class="hint">${T.trim_hint || "Formato: MM:SS ou HH:MM:SS. Vazio = início/fim do vídeo."}</div>
  `;
  panel.appendChild(trimBox);

  trimToggle.addEventListener("click", () => {
    trimBox.classList.toggle("visible");
    trimToggle.textContent = trimBox.classList.contains("visible")
      ? (T.trim_close || "✂ Recolher recorte")
      : (T.trim_open  || "✂ Cortar trecho");
  });

  // Grupo de audio
  const ga = document.createElement("div");
  ga.className = "group";
  ga.textContent = T.group_audio || "Áudio";
  panel.appendChild(ga);

  const a = document.createElement("button");
  a.className = "opt audio";
  a.textContent = T.audio_mp3 || "♪ MP3 (melhor qualidade)";
  a.addEventListener("click", () => download("audio", "best"));
  panel.appendChild(a);

  // Grupo de foto/carrossel
  const gp = document.createElement("div");
  gp.className = "group";
  gp.textContent = T.group_photo || "Foto / Galeria";
  panel.appendChild(gp);

  const p = document.createElement("button");
  p.className = "opt photo";
  p.textContent = T.photo_btn || "📷 Baixar fotos / carrossel";
  p.title = T.photo_hint || "Funciona com Instagram, Twitter, Pinterest, Reddit, etc.";
  p.addEventListener("click", () => download("photo", "best"));
  panel.appendChild(p);

  // Grupo Spotify (so aparece em open.spotify.com)
  if (/spotify\.com/.test(location.hostname)) {
    const gs = document.createElement("div");
    gs.className = "group";
    gs.id = "bx-spotify-group";
    gs.textContent = T.group_spotify || "Spotify";
    panel.appendChild(gs);

    const sp = document.createElement("button");
    sp.className = "opt spotify";
    sp.id = "bx-spotify-btn";
    sp.textContent = T.spotify_btn_default || "🎵 Baixar do Spotify";
    sp.addEventListener("click", () => download("audio", "best"));
    panel.appendChild(sp);

    updateSpotifyLabel(sp);
  }

  // Container da fila de jobs (cada download e um card aqui dentro)
  statusEl = document.createElement("div");
  statusEl.id = "baixador-status";
  statusEl.innerHTML = `<div class="empty">Nenhum download ativo.</div>`;
  panel.appendChild(statusEl);

  // Toggle Historico
  const histToggle = document.createElement("button");
  histToggle.id = "bx-history-toggle";
  histToggle.type = "button";
  histToggle.textContent = T.history_show || "📜 Mostrar histórico";
  histToggle.addEventListener("click", toggleHistory);
  panel.appendChild(histToggle);

  // Container do historico (escondido por padrao)
  const hist = document.createElement("div");
  hist.id = "bx-history";
  hist.innerHTML = `<div class="bx-history-empty">Carregando...</div>`;
  panel.appendChild(hist);

  root.appendChild(panel);
  document.documentElement.appendChild(root);

  makeDraggable(header, root);
  loadPosition();
}

function toggle(toCollapsed) {
  collapsed = toCollapsed;
  root.className = collapsed ? "collapsed" : "";
}

// === Fila de jobs (multi-download) ===
const jobs = new Map();   // jobId -> { card, msg, fill, percent, speed, eta, cancelBtn }

function shortTitle(mode, quality, url) {
  const path = (() => { try { return new URL(url).pathname.replace(/^\//, ""); } catch { return url; } })();
  const trimmed = path.length > 32 ? path.slice(0, 32) + "…" : path;
  const icon = { video: "🎬", audio: "🎵", photo: "📷" }[mode] || "⬇";
  return `${icon} ${quality} · ${trimmed}`;
}

function createJobCard(jobId, mode, quality, url) {
  const empty = statusEl.querySelector(".empty");
  if (empty) empty.remove();

  const card = document.createElement("div");
  card.className = "bx-job";
  card.dataset.state = "loading";
  card.dataset.jobId = jobId;
  card.innerHTML = `
    <div class="bx-job-header">
      <div class="bx-job-title"></div>
      <button class="bx-job-cancel" type="button">✕</button>
    </div>
    <div class="bx-job-msg">Iniciando...</div>
    <div class="bx-bar">
      <div class="bx-bar-fill indeterminate"></div>
      <div class="bx-bar-text">0%</div>
    </div>
    <div class="bx-info">
      <span class="bx-speed">—</span>
      <span class="bx-eta">ETA —</span>
    </div>
  `;
  card.querySelector(".bx-job-title").textContent = shortTitle(mode, quality, url);
  statusEl.appendChild(card);

  const refs = {
    card,
    msg:       card.querySelector(".bx-job-msg"),
    fill:      card.querySelector(".bx-bar-fill"),
    percent:   card.querySelector(".bx-bar-text"),
    speed:     card.querySelector(".bx-speed"),
    eta:       card.querySelector(".bx-eta"),
    cancelBtn: card.querySelector(".bx-job-cancel"),
  };
  refs.cancelBtn.addEventListener("click", () => cancelJob(jobId));
  jobs.set(jobId, refs);
  return refs;
}

function updateJobProgress(jobId, { percent, speed, eta, phase }) {
  const j = jobs.get(jobId);
  if (!j) return;
  if (typeof percent === "number" && !isNaN(percent)) {
    j.fill.classList.remove("indeterminate");
    j.fill.style.width = `${Math.min(100, percent)}%`;
    j.percent.textContent = `${percent.toFixed(1)}%`;
  }
  if (speed && speed !== "N/A") j.speed.textContent = speed;
  if (eta && eta !== "N/A") j.eta.textContent = `ETA ${eta}`;
  const phaseMsg = {
    downloading: "Baixando",
    merging: "Mesclando vídeo + áudio",
    converting: "Convertendo",
  }[phase];
  if (phaseMsg) j.msg.textContent = phaseMsg + "...";
  if (phase === "merging" || phase === "converting") j.fill.classList.add("indeterminate");
}

function finalizeJob(jobId, status, errorTail) {
  const j = jobs.get(jobId);
  if (!j) return;
  j.card.dataset.state = status;
  j.cancelBtn.classList.add("hidden");
  if (status === "done") j.msg.textContent = "✓ Concluído.";
  else if (status === "cancelled") j.msg.textContent = "✕ Cancelado.";
  else j.msg.textContent = errorTail ? `✗ ${errorTail.slice(0, 120)}` : "✗ Erro.";
  setTimeout(() => {
    j.card.remove();
    jobs.delete(jobId);
    if (jobs.size === 0) {
      statusEl.innerHTML = `<div class="empty">${T.empty_jobs || "Nenhum download ativo."}</div>`;
    }
  }, status === "done" ? 4000 : 8000);
}

function cancelJob(jobId) {
  const j = jobs.get(jobId);
  if (j) { j.msg.textContent = "Cancelando..."; j.cancelBtn.disabled = true; }
  chrome.runtime.sendMessage({ type: "cancel", jobId }, () => {});
}

// === Historico ===
async function toggleHistory() {
  const hist = document.getElementById("bx-history");
  const toggle = document.getElementById("bx-history-toggle");
  if (hist.classList.contains("visible")) {
    hist.classList.remove("visible");
    toggle.textContent = "📜 Mostrar histórico";
    return;
  }
  hist.classList.add("visible");
  toggle.textContent = "📜 Ocultar histórico";
  await refreshHistory();
}

async function refreshHistory() {
  const hist = document.getElementById("bx-history");
  hist.innerHTML = `<div class="bx-history-empty">Carregando...</div>`;
  try {
    const resp = await new Promise((r) =>
      chrome.runtime.sendMessage({ type: "list-jobs" }, r)
    );
    if (!resp?.ok) {
      hist.innerHTML = `<div class="bx-history-empty">Servidor offline.</div>`;
      return;
    }
    const items = resp.jobs || [];
    if (items.length === 0) {
      hist.innerHTML = `<div class="bx-history-empty">Sem downloads recentes.</div>`;
      return;
    }
    hist.innerHTML = "";
    for (const job of items) {
      const div = document.createElement("div");
      div.className = "bx-history-item";
      div.dataset.status = job.status;
      const when = job.started_at
        ? new Date(job.started_at * 1000).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
        : "—";
      const urlShort = (() => {
        try { return new URL(job.url || "").hostname.replace("www.", ""); }
        catch { return (job.url || "").slice(0, 30); }
      })();
      const icon = { video: "🎬", audio: "🎵", photo: "📷" }[job.mode] || "⬇";
      const urlEl = document.createElement("span");
      urlEl.className = "url";
      urlEl.title = job.url || "";
      urlEl.textContent = urlShort;
      div.innerHTML = `<span class="when">${when}</span><span>${icon}</span>`;
      div.appendChild(urlEl);
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = job.status;
      div.appendChild(badge);
      hist.appendChild(div);
    }
  } catch (e) {
    hist.innerHTML = `<div class="bx-history-empty">Erro: ${e}</div>`;
  }
}

function updateVideoIndicator() {
  if (!fab) return;
  const hasVideo = !!document.querySelector("video");
  fab.classList.toggle("no-video", !hasVideo);
  fab.title = hasVideo
    ? (T.fab_video    || "Baixador — vídeo detectado")
    : (T.fab_no_video || "Baixador — nenhum vídeo nesta página (vai tentar pela URL mesmo assim)");

  // Atualiza label do botao Spotify conforme tipo de conteudo
  const sp = document.getElementById("bx-spotify-btn");
  if (sp) updateSpotifyLabel(sp);
}

function spotifyKind() {
  // open.spotify.com/{kind}/{id}
  const m = location.pathname.match(/^\/(track|playlist|album|artist|episode|show)\//);
  return m ? m[1] : null;
}

function updateSpotifyLabel(btn) {
  const kind = spotifyKind();
  const labels = {
    track:    T.spotify_track    || "🎵 Baixar música",
    playlist: T.spotify_playlist || "🎵 Baixar playlist completa",
    album:    T.spotify_album    || "🎵 Baixar álbum",
    artist:   T.spotify_artist   || "🎵 Top tracks do artista",
    episode:  T.spotify_episode  || "🎵 Baixar episódio (podcast)",
    show:     T.spotify_show     || "🎵 Baixar episódios do podcast",
  };
  if (kind) {
    btn.textContent = labels[kind];
    btn.disabled = false;
    btn.title = location.href;
  } else {
    btn.textContent = T.spotify_empty      || "🎵 Abra uma música, playlist ou álbum";
    btn.disabled = true;
    btn.title    = T.spotify_empty_hint || "Navegue até uma música/playlist/álbum no Spotify";
  }
}

async function download(mode, quality, url = location.href, onResp = null) {
  const { subtitles = false } = await chrome.storage.local.get(["subtitles"]);
  const trimStart = document.getElementById("bx-trim-start")?.value?.trim() || "";
  const trimEnd   = document.getElementById("bx-trim-end")?.value?.trim()   || "";
  // Perfil so faz sentido em video; audio/foto vao sempre com "padrao" (o servidor ignora).
  const profile = mode === "video"
    ? (document.getElementById("bx-profile")?.value || "padrao")
    : "padrao";
  chrome.runtime.sendMessage(
    { type: "download", url, mode, quality, audio_quality: "best", subtitles,
      trim_start: trimStart, trim_end: trimEnd, profile },
    (resp) => {
      if (resp?.ok) {
        createJobCard(resp.job_id, mode, quality, url);
      } else {
        // sem job — cria um card temporario de erro
        const tempId = "err-" + Date.now();
        const card = createJobCard(tempId, mode, quality, url);
        finalizeJob(tempId, "error", "Servidor offline. Verifique se o Baixador está rodando.");
      }
      onResp?.(resp);
    }
  );
}

chrome.runtime.onMessage.addListener((msg) => {
  // Atalhos vindos do background
  if (msg.type === "panel-toggle") {
    toggle(!collapsed);
    return;
  }
  if (msg.type === "quick-download") {
    // qualidade padrao = ultima salva ou 720p
    chrome.storage.local.get(["last_quality"]).then(({ last_quality }) => {
      download("video", last_quality || "720p");
    });
    return;
  }

  if (!jobs.has(msg.jobId)) return;

  if (msg.type === "download-progress") {
    updateJobProgress(msg.jobId, msg);
  } else if (msg.type === "download-log") {
    const j = jobs.get(msg.jobId);
    if (j && msg.line) j.msg.textContent = msg.line;
  } else if (msg.type === "download-update") {
    finalizeJob(msg.jobId, msg.status, msg.errorTail);
  }
});

// --- Drag ---
function makeDraggable(handle, target) {
  let sx, sy, sr, sb, dragging = false;
  handle.addEventListener("mousedown", (e) => {
    dragging = true;
    sx = e.clientX; sy = e.clientY;
    const r = target.getBoundingClientRect();
    sr = window.innerWidth - r.right;
    sb = window.innerHeight - r.bottom;
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    target.style.right = `${Math.max(4, sr - (e.clientX - sx))}px`;
    target.style.bottom = `${Math.max(4, sb - (e.clientY - sy))}px`;
  });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    chrome.storage.local.set({
      pos: { right: target.style.right, bottom: target.style.bottom }
    });
  });
}

async function loadPosition() {
  const { pos } = await chrome.storage.local.get(["pos"]);
  if (pos?.right) root.style.right = pos.right;
  if (pos?.bottom) root.style.bottom = pos.bottom;
}

const HOST = location.hostname;
const IS_SPOTIFY = /spotify\.com/.test(HOST);
const IS_PHOTO_SITE = /instagram\.com|twitter\.com|x\.com|facebook\.com|pinterest\.com|reddit\.com/.test(HOST);
const IS_POST_SITE = /instagram\.com|x\.com|twitter\.com/.test(HOST);

build();
updateVideoIndicator();

// Em sites pesados (Spotify) NAO observe o DOM inteiro — so a URL
if (IS_SPOTIFY) {
  let lastUrl = location.href;
  setInterval(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      updateVideoIndicator();
    }
  }, 500);
} else {
  new MutationObserver(updateVideoIndicator).observe(
    document.documentElement, { childList: true, subtree: true }
  );
}

// === Overlay de download em imagens grandes ===
const MIN_IMG_SIZE = 250;
let imgBtn = null;
let currentImg = null;
let hideTimer = null;

function ensureImgBtn() {
  if (imgBtn) return imgBtn;
  imgBtn = document.createElement("button");
  imgBtn.className = "bx-img-btn";
  imgBtn.type = "button";
  imgBtn.textContent = "⬇";
  imgBtn.title = "Baixar esta imagem";
  imgBtn.addEventListener("mouseenter", () => clearTimeout(hideTimer));
  imgBtn.addEventListener("mouseleave", scheduleHide);
  imgBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (currentImg) downloadImage(currentImg);
  });
  document.documentElement.appendChild(imgBtn);
  return imgBtn;
}

function bestImageUrl(img) {
  if (img.srcset) {
    const candidates = img.srcset.split(",").map(s => {
      const parts = s.trim().split(/\s+/);
      const url = parts[0];
      const w = parts[1] ? parseInt(parts[1]) : 0;
      return { url, w };
    });
    candidates.sort((a, b) => b.w - a.w);
    if (candidates[0]?.url) return candidates[0].url;
  }
  return img.currentSrc || img.src;
}

function filenameFromUrl(url) {
  try {
    const path = new URL(url).pathname;
    const base = path.split("/").pop() || "imagem";
    const cleaned = base.split("?")[0].split("#")[0];
    if (/\.(jpe?g|png|webp|gif|avif)$/i.test(cleaned)) return cleaned;
    return `imagem-${Date.now()}.jpg`;
  } catch {
    return `imagem-${Date.now()}.jpg`;
  }
}

function showImgBtn(img) {
  if (img.naturalWidth < MIN_IMG_SIZE || img.naturalHeight < MIN_IMG_SIZE) return;
  clearTimeout(hideTimer);
  currentImg = img;
  const btn = ensureImgBtn();
  const r = img.getBoundingClientRect();
  btn.style.top  = `${window.scrollY + r.top + 8}px`;
  btn.style.left = `${window.scrollX + r.right - 44}px`;
  btn.dataset.state = "idle";
  btn.textContent = "⬇";
  btn.classList.add("visible");
}

function scheduleHide() {
  hideTimer = setTimeout(() => {
    if (imgBtn) imgBtn.classList.remove("visible");
    currentImg = null;
  }, 250);
}

function downloadImage(img) {
  const url = bestImageUrl(img);
  if (!url || url.startsWith("data:")) {
    imgBtn.textContent = "✗";
    return;
  }
  imgBtn.dataset.state = "loading";
  imgBtn.textContent = "…";
  chrome.runtime.sendMessage(
    {
      type: "download-image",
      url,
      filename: `Baixador/Fotos/${filenameFromUrl(url)}`,
    },
    (resp) => {
      if (resp?.ok) {
        imgBtn.dataset.state = "done";
        imgBtn.textContent = "✓";
        setTimeout(() => { if (imgBtn) imgBtn.textContent = "⬇"; imgBtn.dataset.state = "idle"; }, 1500);
      } else {
        imgBtn.dataset.state = "idle";
        imgBtn.textContent = "✗";
        console.error("Baixador: erro ao baixar imagem", resp?.error);
      }
    }
  );
}

if (IS_PHOTO_SITE) {
  document.addEventListener("mouseover", (e) => {
    const t = e.target;
    if (t instanceof HTMLImageElement &&
        t.naturalWidth >= MIN_IMG_SIZE &&
        t.naturalHeight >= MIN_IMG_SIZE) {
      showImgBtn(t);
    }
  }, { capture: true });

  document.addEventListener("mouseout", (e) => {
    if (e.target instanceof HTMLImageElement) scheduleHide();
  }, { capture: true });
}

// Reposiciona o botao quando rola
window.addEventListener("scroll", () => {
  if (currentImg && imgBtn?.classList.contains("visible")) {
    const r = currentImg.getBoundingClientRect();
    imgBtn.style.top  = `${window.scrollY + r.top + 8}px`;
    imgBtn.style.left = `${window.scrollX + r.right - 44}px`;
  }
}, { passive: true });

// === Botao em cada post do Instagram (e Twitter) ===
const POST_BTN = new WeakSet();

function postUrlFromArticle(article) {
  // Filtro estrito: precisa de <time> dentro de um link de POST (/p/, /reel/, /tv/, /status/)
  const timeEl = article.querySelector("time");
  if (!timeEl) return null;
  const link = timeEl.closest("a[href]");
  if (!link) return null;
  const href = link.getAttribute("href") || "";
  if (!/\/(p|reel|reels|tv|status)\//.test(href)) return null;
  try {
    return new URL(href, location.origin).href;
  } catch {
    return null;
  }
}

function addPostButton(article) {
  if (POST_BTN.has(article)) return;
  // ja tem um botao dentro?
  if (article.querySelector(":scope > .bx-post-btn")) { POST_BTN.add(article); return; }

  // Tamanho minimo (evita cards pequenos da sidebar)
  const r = article.getBoundingClientRect();
  if (r.width < 280) return;

  // Precisa ter imagem ou video real
  if (!article.querySelector("img, video")) return;

  const url = postUrlFromArticle(article);
  if (!url) return;

  // garante referencia posicional
  const cs = getComputedStyle(article);
  if (cs.position === "static") article.style.position = "relative";

  const btn = document.createElement("button");
  btn.className = "bx-post-btn";
  btn.type = "button";
  btn.dataset.state = "idle";
  btn.dataset.url = url;
  btn.textContent = "⬇ Baixar post";
  btn.title = url;

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (btn.dataset.state !== "idle") return;
    btn.dataset.state = "loading";
    btn.textContent = "Baixando…";
    const mode = isVideoUrl(url) ? "video" : "photo";
    download(mode, "best", url, (resp) => {
      if (!resp?.ok) {
        btn.dataset.state = "err"; btn.textContent = "✗ Erro";
        setTimeout(() => { btn.dataset.state = "idle"; btn.textContent = "⬇ Baixar post"; }, 4000);
        return;
      }
      const myJob = resp.job_id;
      const finalize = (msg) => {
        if (msg.type !== "download-update" || msg.jobId !== myJob) return;
        if (msg.status === "done") { btn.dataset.state = "done"; btn.textContent = "✓ Baixado"; }
        else                       { btn.dataset.state = "err";  btn.textContent = "✗ Erro"; }
        chrome.runtime.onMessage.removeListener(finalize);
        setTimeout(() => { btn.dataset.state = "idle"; btn.textContent = "⬇ Baixar post"; }, 4000);
      };
      chrome.runtime.onMessage.addListener(finalize);
    });
  });

  article.appendChild(btn);
  POST_BTN.add(article);
}

function isVideoUrl(url) {
  return /\/(reel|reels|tv|status)\//.test(url);
}

function scanPosts() {
  if (!/instagram\.com|x\.com|twitter\.com/.test(location.hostname)) return;
  document.querySelectorAll("article").forEach(addPostButton);
}

let scanTimer = null;
function scheduleScan() {
  if (scanTimer) return;
  scanTimer = setTimeout(() => { scanTimer = null; scanPosts(); }, 300);
}
if (IS_POST_SITE) {
  scanPosts();
  new MutationObserver(scheduleScan).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
}
