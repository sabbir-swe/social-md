/* ==========================================================================
   SOCIAL-MD — Front-end controller
   ========================================================================== */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);

  const els = {
    form: $("#searchForm"),
    input: $("#urlInput"),
    searchIcon: $("#searchIcon"),
    clearBtn: $("#clearBtn"),
    pasteBtn: $("#pasteBtn"),
    analyzeBtn: $("#analyzeBtn"),
    platforms: $("#platforms"),
    result: $("#result"),
    skeleton: $("#skeleton"),
    card: $("#card"),
    thumb: $("#thumb"),
    badge: $("#badge"),
    duration: $("#duration"),
    title: $("#title"),
    meta: $("#meta"),
    qualities: $("#qualities"),
    downloadBtn: $("#downloadBtn"),
    progress: $("#progress"),
    stage: $("#stage"),
    percent: $("#percent"),
    fill: $("#fill"),
    speed: $("#speed"),
    eta: $("#eta"),
    notice: $("#notice"),
    healthPill: $("#healthPill"),
    historyBtn: $("#historyBtn"),
    drawer: $("#drawer"),
    scrim: $("#scrim"),
    closeDrawerBtn: $("#closeDrawerBtn"),
    clearHistoryBtn: $("#clearHistoryBtn"),
    historyList: $("#historyList"),
    historyEmpty: $("#historyEmpty"),
    toasts: $("#toasts"),
  };

  const PLATFORMS = {
    youtube:   { label: "YouTube",   color: "#ff3d3d" },
    tiktok:    { label: "TikTok",    color: "#25f4ee" },
    instagram: { label: "Instagram", color: "#e1306c" },
    facebook:  { label: "Facebook",  color: "#1877f2" },
    other:     { label: "Video",     color: "#7c5cff" },
  };
  const PATTERNS = {
    youtube: /(youtube\.com|youtu\.be)/i,
    tiktok: /tiktok\.com/i,
    instagram: /instagram\.com/i,
    facebook: /(facebook\.com|fb\.watch|fb\.com)/i,
  };
  const STAGES = {
    queued: "Waiting for a free slot…",
    starting: "Preparing…",
    downloading: "Downloading…",
    merging: "Merging video & audio…",
    processing: "Finalizing…",
    done: "Complete",
  };
  const HISTORY_KEY = "socialmd.history.v1";
  const HISTORY_LIMIT = 20;

  const state = { url: "", info: null, quality: "best", timer: null, polling: false };

  /* ----------------------------------------------------------------------
     Helpers
     ---------------------------------------------------------------------- */
  const detectPlatform = (url) =>
    Object.keys(PATTERNS).find((key) => PATTERNS[key].test(url)) || "other";

  const isValidUrl = (url) => /^https?:\/\/\S+$/i.test(url);

  const formatDuration = (seconds) => {
    if (!seconds) return "";
    const s = Math.round(seconds);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return (h ? `${h}:` : "") + `${String(m).padStart(h ? 2 : 1, "0")}:${String(sec).padStart(2, "0")}`;
  };

  const formatCount = (n) => {
    if (!n) return "";
    if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
    return String(n);
  };

  const qualityLabel = (q) => {
    if (q === "best") return { main: "Best", sub: "Original" };
    if (q === "audio") return { main: "MP3", sub: "Audio" };
    const sub = q >= 2160 ? "4K" : q >= 1440 ? "2K" : q >= 1080 ? "FHD" : q >= 720 ? "HD" : "SD";
    return { main: `${q}p`, sub };
  };

  const icon = (name) => `<svg class="ic"><use href="#i-${name}"/></svg>`;

  const debounce = (fn, ms) => {
    let id;
    return (...args) => { clearTimeout(id); id = setTimeout(() => fn(...args), ms); };
  };

  async function request(path, options = {}) {
    const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
    let data = null;
    try { data = await response.json(); } catch { /* non-JSON body */ }
    if (!response.ok) throw new Error((data && data.error) || `Request failed (${response.status})`);
    return data;
  }

  /* ----------------------------------------------------------------------
     UI primitives
     ---------------------------------------------------------------------- */
  function toast(message, type = "info", timeout = 4200) {
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.innerHTML = `${icon(type === "ok" ? "check" : type === "err" ? "alert" : "zap")}<span></span>`;
    el.lastElementChild.textContent = message;
    els.toasts.appendChild(el);
    setTimeout(() => { el.classList.add("out"); el.addEventListener("animationend", () => el.remove(), { once: true }); }, timeout);
  }

  function showNotice(message, type) {
    els.notice.className = `notice ${type}`;
    els.notice.innerHTML = `${icon(type === "ok" ? "check" : "alert")}<span></span>`;
    els.notice.lastElementChild.textContent = message;
    els.notice.hidden = false;
  }

  function setBusy(button, busy) {
    button.disabled = busy;
    const spinner = button.querySelector(".btn-spinner");
    const label = button.querySelector(".btn-label");
    if (spinner) spinner.hidden = !busy;
    if (label && button === els.analyzeBtn) label.textContent = busy ? "Analyzing" : "Analyze";
  }

  function highlightPlatform(url) {
    const platform = url ? detectPlatform(url) : null;
    els.platforms.classList.toggle("detecting", Boolean(platform && platform !== "other"));
    els.platforms.querySelectorAll(".chip").forEach((chip) => {
      const active = chip.dataset.platform === platform;
      chip.classList.toggle("active", active);
      chip.style.setProperty("--chip", PLATFORMS[chip.dataset.platform].color);
    });
    const color = platform && platform !== "other" ? PLATFORMS[platform].color : "";
    els.searchIcon.style.color = color;
    els.searchIcon.innerHTML = platform && platform !== "other" ? icon(platform) : icon("link");
  }

  function resetProgress() {
    els.progress.hidden = true;
    els.progress.classList.remove("indeterminate");
    els.fill.style.width = "0%";
    els.percent.textContent = "0%";
    els.stage.textContent = STAGES.starting;
    els.speed.textContent = "";
    els.eta.textContent = "";
  }

  /* ----------------------------------------------------------------------
     Analyze
     ---------------------------------------------------------------------- */
  async function analyze() {
    const url = els.input.value.trim();
    if (!isValidUrl(url)) { toast("Please paste a valid video link.", "err"); els.input.focus(); return; }
    if (els.analyzeBtn.disabled) return;

    stopPolling();
    state.url = url;
    state.info = null;
    setBusy(els.analyzeBtn, true);
    els.result.hidden = false;
    els.card.hidden = true;
    els.skeleton.hidden = false;
    els.notice.hidden = true;
    resetProgress();
    els.result.scrollIntoView({ behavior: "smooth", block: "start" });

    try {
      const info = await request("/api/info", { method: "POST", body: JSON.stringify({ url }) });
      state.info = info;
      renderCard(info);
    } catch (error) {
      els.skeleton.hidden = true;
      els.result.hidden = true;
      toast(error.message, "err", 7000);
    } finally {
      setBusy(els.analyzeBtn, false);
    }
  }

  function renderCard(info) {
    const platform = PLATFORMS[info.platform] || PLATFORMS.other;

    els.thumb.removeAttribute("src");
    if (info.thumbnail) els.thumb.src = `/api/thumb?u=${encodeURIComponent(info.thumbnail)}`;

    els.badge.innerHTML = `${info.platform !== "other" ? icon(info.platform) : icon("film")}<span></span>`;
    els.badge.lastElementChild.textContent = platform.label;
    els.badge.style.setProperty("--badge", platform.color);
    els.duration.textContent = formatDuration(info.duration);
    els.title.textContent = info.title;

    const meta = [];
    if (info.channel) meta.push(info.channel);
    if (info.views) meta.push(`${formatCount(info.views)} views`);
    if (info.items > 1) meta.push(`${info.items} clips — first one will be downloaded`);
    els.meta.textContent = meta.join(" · ");

    const options = ["best", ...info.qualities, "audio"];
    state.quality = "best";
    els.qualities.innerHTML = "";
    options.forEach((q) => {
      const { main, sub } = qualityLabel(q);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `q-btn${q === state.quality ? " active" : ""}`;
      btn.dataset.value = String(q);
      btn.innerHTML = `${q === "audio" ? icon("music") : ""}<span></span><small></small>`;
      btn.querySelector("span").textContent = main;
      btn.querySelector("small").textContent = sub;
      els.qualities.appendChild(btn);
    });

    els.downloadBtn.disabled = false;
    els.skeleton.hidden = true;
    els.card.hidden = false;
  }

  /* ----------------------------------------------------------------------
     Download & progress
     ---------------------------------------------------------------------- */
  async function startDownload() {
    if (!state.info || els.downloadBtn.disabled) return;
    els.downloadBtn.disabled = true;
    els.notice.hidden = true;
    resetProgress();
    els.progress.hidden = false;

    try {
      const { task_id: taskId } = await request("/api/download", {
        method: "POST",
        body: JSON.stringify({ url: state.url, quality: state.quality }),
      });
      poll(taskId);
    } catch (error) {
      showNotice(error.message, "err");
      els.downloadBtn.disabled = false;
    }
  }

  function poll(taskId) {
    stopPolling();
    state.timer = setInterval(async () => {
      if (state.polling) return;
      state.polling = true;
      try {
        const task = await request(`/api/progress/${taskId}`);
        applyProgress(task, taskId);
      } catch (error) {
        stopPolling();
        showNotice(error.message, "err");
        els.downloadBtn.disabled = false;
      } finally {
        state.polling = false;
      }
    }, 600);
  }

  function stopPolling() {
    clearInterval(state.timer);
    state.timer = null;
    state.polling = false;
  }

  function applyProgress(task, taskId) {
    const indeterminate = ["queued", "starting", "merging", "processing"].includes(task.status);
    els.progress.classList.toggle("indeterminate", indeterminate);
    els.stage.textContent = STAGES[task.status] || task.status;
    els.speed.textContent = task.speed || "";
    els.eta.textContent = task.eta || "";

    if (task.status === "downloading") {
      els.fill.style.width = `${task.progress}%`;
      els.percent.textContent = `${task.progress}%`;
    } else if (indeterminate) {
      els.percent.textContent = "";
    }

    if (task.status === "done") {
      stopPolling();
      els.fill.style.width = "100%";
      els.percent.textContent = "100%";
      showNotice(task.cached ? "Delivered instantly from cache. Saving file…" : "Download complete. Saving file…", "ok");
      toast(task.cached ? "Served from cache" : "Download complete", "ok");
      triggerSave(taskId, task.filename);
      addHistory({ url: state.url, title: state.info.title, platform: state.info.platform,
                   quality: state.quality, thumb: state.info.thumbnail, at: Date.now() });
      els.downloadBtn.disabled = false;
    }

    if (task.status === "error") {
      stopPolling();
      els.progress.hidden = true;
      showNotice(task.error || "Download failed.", "err");
      els.downloadBtn.disabled = false;
    }
  }

  function triggerSave(taskId, filename) {
    const link = document.createElement("a");
    link.href = `/api/file/${taskId}`;
    link.download = filename || "";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  /* ----------------------------------------------------------------------
     History (localStorage)
     ---------------------------------------------------------------------- */
  const loadHistory = () => {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; } catch { return []; }
  };
  const saveHistory = (items) => localStorage.setItem(HISTORY_KEY, JSON.stringify(items));

  function addHistory(entry) {
    const items = loadHistory().filter((i) => !(i.url === entry.url && i.quality === entry.quality));
    items.unshift(entry);
    saveHistory(items.slice(0, HISTORY_LIMIT));
    renderHistory();
  }

  function renderHistory() {
    const items = loadHistory();
    els.historyList.innerHTML = "";
    els.historyEmpty.hidden = items.length > 0;
    items.forEach((item) => {
      const li = document.createElement("li");
      li.title = "Analyze this link again";
      const img = document.createElement("img");
      img.alt = "";
      img.loading = "lazy";
      if (item.thumb) img.src = `/api/thumb?u=${encodeURIComponent(item.thumb)}`;
      const body = document.createElement("div");
      const title = document.createElement("div");
      title.className = "h-title";
      title.textContent = item.title || item.url;
      const meta = document.createElement("div");
      meta.className = "h-meta";
      const { main } = qualityLabel(item.quality === "best" || item.quality === "audio" ? item.quality : Number(item.quality));
      meta.textContent = `${(PLATFORMS[item.platform] || PLATFORMS.other).label} · ${main} · ${new Date(item.at).toLocaleString()}`;
      body.append(title, meta);
      li.append(img, body);
      li.addEventListener("click", () => {
        els.input.value = item.url;
        highlightPlatform(item.url);
        els.clearBtn.hidden = false;
        toggleDrawer(false);
        analyze();
      });
      els.historyList.appendChild(li);
    });
  }

  function toggleDrawer(open) {
    els.drawer.classList.toggle("open", open);
    els.scrim.classList.toggle("show", open);
  }

  /* ----------------------------------------------------------------------
     Health
     ---------------------------------------------------------------------- */
  async function checkHealth() {
    try {
      const h = await request("/api/health");
      const label = els.healthPill.querySelector("span");
      if (h.ffmpeg) {
        els.healthPill.className = "pill ok";
        label.textContent = "Ready";
      } else {
        els.healthPill.className = "pill bad";
        label.textContent = "FFmpeg missing";
      }
      els.healthPill.title = `yt-dlp ${h.ytdlp} · FFmpeg ${h.ffmpeg ? "OK" : "missing"} · cookies ${h.cookies ? "found" : "none"}`;
      if (!h.ffmpeg) toast("FFmpeg not found — HD downloads and MP3 will fail.", "err", 8000);
    } catch {
      els.healthPill.className = "pill bad";
      els.healthPill.querySelector("span").textContent = "Offline";
    }
  }

  /* ----------------------------------------------------------------------
     Events
     ---------------------------------------------------------------------- */
  els.form.addEventListener("submit", (e) => { e.preventDefault(); analyze(); });

  els.input.addEventListener("input", debounce(() => {
    const value = els.input.value.trim();
    els.clearBtn.hidden = !value;
    highlightPlatform(value);
  }, 80));

  els.input.addEventListener("paste", () => setTimeout(() => {
    const value = els.input.value.trim();
    els.clearBtn.hidden = !value;
    highlightPlatform(value);
    if (isValidUrl(value)) analyze();
  }, 50));

  els.clearBtn.addEventListener("click", () => {
    els.input.value = "";
    els.clearBtn.hidden = true;
    highlightPlatform("");
    els.input.focus();
  });

  els.pasteBtn.addEventListener("click", async () => {
    try {
      const text = (await navigator.clipboard.readText()).trim();
      if (!text) { toast("Clipboard is empty.", "info"); return; }
      els.input.value = text;
      els.clearBtn.hidden = false;
      highlightPlatform(text);
      if (isValidUrl(text)) analyze(); else toast("Clipboard does not contain a link.", "err");
    } catch {
      toast("Clipboard access was denied. Paste manually with Ctrl+V.", "err");
      els.input.focus();
    }
  });

  els.qualities.addEventListener("click", (e) => {
    const btn = e.target.closest(".q-btn");
    if (!btn) return;
    els.qualities.querySelectorAll(".q-btn").forEach((b) => b.classList.toggle("active", b === btn));
    const value = btn.dataset.value;
    state.quality = value === "best" || value === "audio" ? value : Number(value);
  });

  els.downloadBtn.addEventListener("click", startDownload);
  els.historyBtn.addEventListener("click", () => toggleDrawer(true));
  els.closeDrawerBtn.addEventListener("click", () => toggleDrawer(false));
  els.scrim.addEventListener("click", () => toggleDrawer(false));
  els.clearHistoryBtn.addEventListener("click", () => { saveHistory([]); renderHistory(); toast("History cleared.", "info"); });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") toggleDrawer(false);
    if (e.key === "/" && document.activeElement !== els.input) { e.preventDefault(); els.input.focus(); }
  });

  /* ----------------------------------------------------------------------
     Init
     ---------------------------------------------------------------------- */
  renderHistory();
  checkHealth();
  els.input.focus();
})();