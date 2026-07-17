const SERVER = "http://127.0.0.1:5005";

// === Auto-update check ===
async function checkForUpdate() {
  try {
    const r = await fetch(`${SERVER}/check-update`);
    const d = await r.json();
    if (!d.ok || !d.has_update) return;
    const lastSeen = (await chrome.storage.local.get(["update_seen"])).update_seen;
    if (lastSeen === d.latest) return;   // ja avisamos sobre essa versao
    chrome.storage.local.set({ update_seen: d.latest, update_url: d.download_url });
    chrome.notifications.create("baixador-update", {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: `Baixador ${d.latest} disponível`,
      message: `Você está na ${d.current}. ${d.notes || "Clique para baixar."}`,
      requireInteraction: true,
    });
  } catch { /* servidor offline ou sem feed configurado */ }
}

chrome.notifications.onClicked.addListener(async (id) => {
  if (id !== "baixador-update") return;
  const { update_url } = await chrome.storage.local.get(["update_url"]);
  if (update_url) chrome.tabs.create({ url: update_url });
  chrome.notifications.clear(id);
});

// Verifica ao abrir a extensao e periodicamente (a cada 6h)
chrome.runtime.onStartup.addListener(checkForUpdate);
chrome.runtime.onInstalled.addListener(checkForUpdate);
chrome.alarms.create("baixador-update-check", { periodInMinutes: 360 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "baixador-update-check") checkForUpdate();
});

// === Atalhos de teclado ===
chrome.commands.onCommand.addListener(async (command) => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  if (command === "toggle-panel") {
    chrome.tabs.sendMessage(tab.id, { type: "panel-toggle" }).catch(() => {});
  } else if (command === "quick-download") {
    chrome.tabs.sendMessage(tab.id, { type: "quick-download" }).catch(() => {});
  }
});

const COOKIE_DOMAINS = {
  "instagram.com": ".instagram.com",
  "facebook.com":  ".facebook.com",
  "x.com":         ".x.com",
  "twitter.com":   ".x.com",
};

function urlDomain(url) {
  try {
    const h = new URL(url).hostname;
    for (const k of Object.keys(COOKIE_DOMAINS)) {
      if (h.endsWith(k)) return COOKIE_DOMAINS[k];
    }
  } catch {}
  return null;
}

async function gatherCookies(url) {
  const domain = urlDomain(url);
  if (!domain) return null;
  // sem o ponto inicial para chrome.cookies.getAll
  const queryDomain = domain.replace(/^\./, "");
  try {
    const cookies = await chrome.cookies.getAll({ domain: queryDomain });
    if (!cookies.length) return null;
    return cookies.map(c => ({
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path || "/",
      secure: !!c.secure,
      expirationDate: c.expirationDate || 0,
      hostOnly: !!c.hostOnly,
    }));
  } catch (e) {
    console.error("Baixador: erro lendo cookies", e);
    return null;
  }
}

async function startDownload(url, mode, quality, audio_quality, opts = {}) {
  const cookies = await gatherCookies(url);
  const res = await fetch(`${SERVER}/download`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, mode, quality, audio_quality, cookies, ...opts })
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function notify(id, title, message) {
  chrome.notifications.create(id, {
    type: "basic",
    iconUrl: "icons/icon128.png",
    title,
    message
  });
}

// Parseia "PROG| 45.2%|  5.42MiB/s|00:12" -> { percent, speed, eta }
function parseProgress(line) {
  const m = line.match(/^PROG\|\s*(\d+(?:\.\d+)?)%\|\s*(\S+)\|\s*(\S+)/);
  if (!m) return null;
  return { percent: parseFloat(m[1]), speed: m[2], eta: m[3] };
}

function detectPhase(line) {
  if (/\[Merger\]|Merging formats/i.test(line)) return "merging";
  if (/\[ExtractAudio\]|Destination:.*\.mp3/i.test(line)) return "converting";
  if (/^\[download\] Destination:/i.test(line)) return "downloading";
  return null;
}

// strip ANSI escape codes
function cleanLine(s) {
  return s.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "").trim();
}

function isInterestingLog(line) {
  const t = cleanLine(line);
  if (!t) return false;
  // spotdl
  if (/Found \d+ song|Downloading "|Skipping|Converted|Embedding|Searching|"|^Track:/i.test(t)) return true;
  // gallery-dl
  if (/^\[(instagram|twitter|facebook|tiktok|reddit|pinterest|tumblr)\]/i.test(t)) return true;
  // yt-dlp
  if (/^\[info\] |Processing|Downloading webpage|Downloading playlist/i.test(t)) return true;
  return false;
}

function watchJob(jobId, tabId) {
  const es = new EventSource(`${SERVER}/stream/${jobId}`);
  let lastPercent = 0;
  let phase = "starting";
  const lastLines = [];

  es.onmessage = (ev) => {
    const line = ev.data;

    // guarda as ultimas linhas pra debug em caso de erro
    lastLines.push(line);
    if (lastLines.length > 8) lastLines.shift();

    const prog = parseProgress(line);
    if (prog && tabId != null) {
      lastPercent = prog.percent;
      chrome.tabs.sendMessage(tabId, {
        type: "download-progress",
        jobId,
        percent: prog.percent,
        speed: prog.speed,
        eta: prog.eta,
        phase: "downloading",
      }).catch(() => {});
      return;
    }

    const newPhase = detectPhase(line);
    if (newPhase && newPhase !== phase && tabId != null) {
      phase = newPhase;
      chrome.tabs.sendMessage(tabId, {
        type: "download-progress",
        jobId,
        percent: lastPercent,
        phase,
      }).catch(() => {});
    }

    // Encaminha linhas "interessantes" pro painel (essencial pra spotdl/gallery-dl
    // que nao tem progresso percentual)
    if (tabId != null && isInterestingLog(line)) {
      chrome.tabs.sendMessage(tabId, {
        type: "download-log",
        jobId,
        line: cleanLine(line).slice(0, 90),
      }).catch(() => {});
    }
  };

  es.addEventListener("end", (ev) => {
    const final = ev.data; // "done" | "error" | "cancelled"
    const errorTail = lastLines.filter(l => l.trim()).slice(-3).join(" | ");
    const titles = {
      done:      "✓ Download concluído!",
      cancelled: "✕ Download cancelado",
      error:     `✗ ${errorTail.slice(0, 120) || "Erro no download"}`,
    };
    notify(jobId + "-end", "Baixador", titles[final] || titles.error);
    if (tabId != null) {
      chrome.tabs.sendMessage(tabId, {
        type: "download-update",
        jobId,
        status: final,
        errorTail,
      }).catch(() => {});
    }
    es.close();
  });
  es.onerror = () => es.close();
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "download") {
    (async () => {
      try {
        const data = await startDownload(msg.url, msg.mode, msg.quality, msg.audio_quality, {
          subtitles: msg.subtitles,
          trim_start: msg.trim_start,
          trim_end: msg.trim_end,
          profile: msg.profile,
        });
        notify(data.job_id, "Baixador", `Baixando: ${msg.url.slice(0, 60)}`);
        sendResponse({ ok: true, job_id: data.job_id });
        watchJob(data.job_id, sender.tab?.id);
      } catch (e) {
        sendResponse({ ok: false, error: String(e) });
      }
    })();
    return true;
  }

  if (msg.type === "list-jobs") {
    fetch(`${SERVER}/jobs?limit=30`)
      .then(r => r.json())
      .then(d => sendResponse({ ok: true, jobs: d.jobs || [] }))
      .catch(e => sendResponse({ ok: false, error: String(e) }));
    return true;
  }

  if (msg.type === "cancel") {
    fetch(`${SERVER}/cancel/${msg.jobId}`, { method: "POST" })
      .then(r => r.json())
      .then(d => sendResponse(d))
      .catch(e => sendResponse({ ok: false, error: String(e) }));
    return true;
  }

  if (msg.type === "download-image") {
    chrome.downloads.download({
      url: msg.url,
      filename: msg.filename || `Baixador/Fotos/imagem-${Date.now()}.jpg`,
      conflictAction: "uniquify",
      saveAs: false,
    }, (id) => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
      } else {
        sendResponse({ ok: true, id });
      }
    });
    return true;
  }

  if (msg.type === "ping") {
    fetch(`${SERVER}/health`)
      .then(r => r.json())
      .then(d => sendResponse({ ok: true, data: d }))
      .catch(e => sendResponse({ ok: false, error: String(e) }));
    return true;
  }
});
