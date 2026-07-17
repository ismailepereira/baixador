const SERVER = "http://127.0.0.1:5005";

const urlEl = document.getElementById("url");
const log = document.getElementById("log");
const qualityEl = document.getElementById("quality");
const audioQualityEl = document.getElementById("audioQuality");
const profileEl = document.getElementById("profile");
const profileHint = document.getElementById("profileHint");
let currentUrl = "";

const PROFILE_HINTS = {
  padrao:   "Melhor qualidade por MB, mas pode vir VP9/Opus — o Premiere recusa.",
  premiere: "H.264 + AAC em .mp4. Abre direto no Premiere, sem re-encode.",
  capcut:   "H.264 + AAC em .mp4, limitado a 1080p pro CapCut rodar leve.",
  prores:   "ProRes 422 HQ + PCM em .mov. Edição fluida, arquivo bem maior e demora.",
};

function updateHint() {
  profileHint.textContent = PROFILE_HINTS[profileEl.value] || "";
}

function append(line, cls) {
  const span = document.createElement("div");
  if (cls) span.className = cls;
  span.textContent = line;
  log.appendChild(span);
  log.scrollTop = log.scrollHeight;
}

async function getTabUrl() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.url || "";
}

async function init() {
  currentUrl = await getTabUrl();
  urlEl.textContent = currentUrl || "(sem aba ativa)";
  // restaura ultima escolha
  const saved = await chrome.storage.local.get(["quality", "audioQuality", "profile"]);
  if (saved.quality) qualityEl.value = saved.quality;
  if (saved.audioQuality) audioQualityEl.value = saved.audioQuality;
  if (saved.profile) profileEl.value = saved.profile;
  updateHint();
}

qualityEl.addEventListener("change", () =>
  chrome.storage.local.set({ quality: qualityEl.value })
);
audioQualityEl.addEventListener("change", () =>
  chrome.storage.local.set({ audioQuality: audioQualityEl.value })
);
profileEl.addEventListener("change", () => {
  chrome.storage.local.set({ profile: profileEl.value });
  updateHint();
});

let currentJob = null;
const cancelBtn = document.getElementById("cancelBtn");

async function download(mode) {
  if (!currentUrl) return append("URL nao detectada.", "err");
  log.textContent = "";
  const payload = {
    url: currentUrl,
    mode,
    quality: qualityEl.value,
    audio_quality: audioQualityEl.value,
    profile: profileEl.value,
  };
  append(mode === "video"
    ? `Iniciando video (${payload.quality}, perfil ${payload.profile})...`
    : `Iniciando ${mode} (${payload.audio_quality})...`);
  try {
    const res = await fetch(`${SERVER}/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    currentJob = data.job_id;
    cancelBtn.style.display = "block";
    append(`Job ${data.job_id}. Salvando em: ${data.downloads_dir}`);
    streamLogs(data.job_id);
  } catch (e) {
    append(`Erro: ${e}. O servidor local esta rodando?`, "err");
  }
}

function streamLogs(jobId) {
  const es = new EventSource(`${SERVER}/stream/${jobId}`);
  es.onmessage = (ev) => append(ev.data);
  es.addEventListener("end", (ev) => {
    const final = ev.data;
    if (final === "done")       append("✓ Concluido!", "ok");
    else if (final === "cancelled") append("✕ Cancelado.", "err");
    else                        append("✗ Falhou.", "err");
    cancelBtn.style.display = "none";
    currentJob = null;
    es.close();
  });
  es.onerror = () => { es.close(); };
}

cancelBtn.addEventListener("click", async () => {
  if (!currentJob) return;
  cancelBtn.disabled = true;
  cancelBtn.textContent = "Cancelando...";
  try {
    const r = await fetch(`${SERVER}/cancel/${currentJob}`, { method: "POST" });
    const d = await r.json();
    if (!d.ok) append(`Cancel falhou: ${d.reason || d.error || "?"}`, "err");
  } catch (e) {
    append(`Erro: ${e}`, "err");
  } finally {
    cancelBtn.disabled = false;
    cancelBtn.textContent = "✕ Cancelar download";
  }
});

document.getElementById("video").addEventListener("click", () => download("video"));
document.getElementById("audio").addEventListener("click", () => download("audio"));
document.getElementById("photo").addEventListener("click", () => download("photo"));
document.getElementById("folder").addEventListener("click", async () => {
  try { await fetch(`${SERVER}/open-folder`, { method: "POST" }); }
  catch (e) { append(`Erro: ${e}`, "err"); }
});
document.getElementById("check").addEventListener("click", async () => {
  try {
    const r = await fetch(`${SERVER}/health`);
    const d = await r.json();
    append(`Servidor OK. Pasta: ${d.downloads_dir}`, "ok");
    append(`ffmpeg: ${d.ffmpeg_found ? "✓ " + d.ffmpeg : "✗ NAO encontrado"}`,
           d.ffmpeg_found ? "ok" : "err");
  } catch (e) {
    append(`Servidor OFFLINE. Rode start.bat.`, "err");
  }
});

init();
