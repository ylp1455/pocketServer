const state = { status: null, downloads: [], media: [], scheduleDirty: false, authenticated: false, csrfToken: "" };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const bytes = (value) => {
  const n = Number(value || 0);
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1);
  return `${(n / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
};
const duration = (seconds) => {
  if (seconds == null) return "—";
  const s = Number(seconds);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
};
const escapeHtml = (value) => String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);

function applyTheme(theme) {
  const selected = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = selected;
  $("#themeToggle").textContent = selected === "light" ? "☾" : "☀";
  $("#themeToggle").setAttribute("aria-label", `Switch to ${selected === "light" ? "dark" : "light"} mode`);
  $("#themeColor").content = selected === "light" ? "#f4f7fb" : "#111827";
  try { localStorage.setItem("pocket-theme", selected); } catch (e) {}
}

async function api(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  if (method !== "GET" && state.csrfToken && url !== "/api/auth/login") {
    options.headers = {...(options.headers || {}), "X-CSRF-Token": state.csrfToken};
  }
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function showLogin(message = "") {
  state.authenticated = false;
  state.csrfToken = "";
  $("#adminShell").classList.add("hidden");
  $("#loginScreen").classList.remove("hidden");
  $("#loginError").textContent = message;
  $("#loginPassword").focus();
}

function showAdmin(session) {
  state.authenticated = true;
  state.csrfToken = session.csrf_token;
  $("#loginScreen").classList.add("hidden");
  $("#adminShell").classList.remove("hidden");
  $("#passwordWarning").classList.toggle("hidden", !session.must_change_password);
  $("#accountName").textContent = session.username || "admin";
}

function showView(name) {
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === name));
  const titles = {overview: ["YOUR HOME SERVER", "Overview"], media: ["STREAM & WATCH", "Media"], downloads: ["QUEUE & SCHEDULE", "Downloads"], system: ["HEALTH & STORAGE", "System"]};
  $("#pageEyebrow").textContent = titles[name][0];
  $("#pageTitle").textContent = titles[name][1];
  $("#sidebar").classList.remove("open");
}

function renderStatus() {
  const s = state.status;
  if (!s) return;
  $("#welcomeTitle").textContent = `${s.name} is ready`;
  $("#activeCount").textContent = s.active_downloads;
  $("#storageValue").textContent = `${Math.round(s.disk.used / s.disk.total * 100)}%`;
  $("#uptimeValue").textContent = duration(s.uptime_seconds);
  $("#headerDown").textContent = `↓ ${bytes(s.download_speed)}/s`;
  $("#headerUp").textContent = `↑ ${bytes(s.upload_speed)}/s`;
  $("#engineDot").classList.toggle("ok", s.aria2_available);
  $("#engineText").textContent = s.aria2_available ? "aria2 connected" : "aria2 unavailable";
  $("#ariaNotice").classList.toggle("hidden", s.aria2_available);
  const diskPercent = Math.round(s.disk.used / s.disk.total * 100);
  const memoryPercent = s.memory ? Math.round(s.memory.used / s.memory.total * 100) : 0;
  $("#healthRows").innerHTML = `
    <div class="health-row"><span>Storage</span><div class="track"><span style="width:${diskPercent}%"></span></div><strong>${diskPercent}%</strong></div>
    <div class="health-row"><span>Memory</span><div class="track"><span style="width:${memoryPercent}%"></span></div><strong>${s.memory ? memoryPercent + "%" : "N/A"}</strong></div>
    <div class="health-row"><span>Download engine</span><div></div><strong>${s.aria2_available ? "Online" : "Offline"}</strong></div>`;
  const schedule = s.schedule;
  $("#scheduleText").textContent = schedule.enabled ? `Scheduled ${schedule.start}–${schedule.end}` : "Schedule off";
  if (!state.scheduleDirty) {
    $("#scheduleEnabled").checked = schedule.enabled;
    $("#scheduleStart").value = schedule.start;
    $("#scheduleEnd").value = schedule.end;
  }
  const scheduleState = $("#scheduleState");
  scheduleState.classList.toggle("success", schedule.enabled && s.schedule_active_now && s.aria2_available);
  scheduleState.textContent = !schedule.enabled ? "Disabled" : !s.aria2_available ? "Engine offline" : s.schedule_active_now ? "Downloading now" : "Waiting for start";
  const metadata = s.metadata || {};
  $("#metadataEnabled").checked = Boolean(metadata.enabled);
  const metadataStatus = $("#metadataStatus");
  metadataStatus.classList.toggle("success", Boolean(metadata.enabled && metadata.configured));
  metadataStatus.textContent = !metadata.configured ? "API key needed" : metadata.enabled ? `${metadata.cached_titles || 0} titles cached` : "Disabled";
  $("#systemGrid").innerHTML = `
    <article class="system-card"><h3>Device</h3><div class="info-row"><span>Hostname</span><strong>${escapeHtml(s.hostname)}</strong></div><div class="info-row"><span>Platform</span><strong>${escapeHtml(s.platform)}</strong></div><div class="info-row"><span>Python</span><strong>${escapeHtml(s.python)}</strong></div><div class="info-row"><span>Uptime</span><strong>${duration(s.uptime_seconds)}</strong></div></article>
    <article class="system-card"><h3>Storage</h3><div class="info-row"><span>Total</span><strong>${bytes(s.disk.total)}</strong></div><div class="info-row"><span>Used</span><strong>${bytes(s.disk.used)}</strong></div><div class="info-row"><span>Available</span><strong>${bytes(s.disk.free)}</strong></div></article>
    <article class="system-card"><h3>Download engine</h3><div class="info-row"><span>Status</span><strong>${s.aria2_available ? "Connected" : "Unavailable"}</strong></div><div class="info-row"><span>Active</span><strong>${s.active_downloads}</strong></div><div class="info-row"><span>Waiting</span><strong>${s.waiting_downloads}</strong></div></article>
    <article class="system-card"><h3>Night schedule</h3><div class="info-row"><span>Enabled</span><strong>${schedule.enabled ? "Yes" : "No"}</strong></div><div class="info-row"><span>Start</span><strong>${schedule.start}</strong></div><div class="info-row"><span>End</span><strong>${schedule.end}</strong></div></article>`;
}

function renderDownloads() {
  const filter = $("#downloadSearch").value.toLowerCase();
  const items = state.downloads.filter((item) => item.name.toLowerCase().includes(filter));
  const html = items.map((item) => `
    <div class="download-row">
      <div class="download-name"><strong>${escapeHtml(item.name)}</strong><span>${item.torrent ? "BitTorrent" : "Direct download"} · ${bytes(item.total)}</span></div>
      <span class="state ${item.status}">${escapeHtml(item.status)}</span>
      <div class="progress-wrap"><div class="track"><span style="width:${item.progress}%"></span></div><small>${item.progress}%</small></div>
      <span class="speed">↓ ${bytes(item.download_speed)}/s</span>
      <span class="eta">${duration(item.eta_seconds)}</span>
      <div class="row-actions">
        ${item.status === "active" ? `<button data-action="pause" data-gid="${item.gid}" title="Pause">Ⅱ</button>` : item.status !== "complete" ? `<button data-action="resume" data-gid="${item.gid}" title="Resume">▶</button>` : ""}
        <button data-action="${item.status === "complete" ? "remove-result" : "remove"}" data-gid="${item.gid}" title="Remove">×</button>
      </div>
    </div>`).join("");
  $("#downloadList").innerHTML = html || '<div class="empty-state">No downloads in the queue.</div>';
  const recent = state.downloads.slice(0, 4);
  $("#recentDownloads").innerHTML = recent.length ? recent.map((item) => `<div class="download-row" style="grid-template-columns:1fr 85px"><div class="download-name"><strong>${escapeHtml(item.name)}</strong><span>${item.progress}% · ${bytes(item.total)}</span></div><span class="state ${item.status}">${item.status}</span></div>`).join("") : "No downloads yet.";
}

function renderMedia() {
  const filter = $("#mediaSearch").value.toLowerCase();
  const items = state.media.filter((item) => item.name.toLowerCase().includes(filter));
  $("#mediaCount").textContent = state.media.length;
  $("#mediaGrid").innerHTML = items.map((item) => `<button class="media-card" data-media-url="${escapeHtml(item.url)}" data-media-name="${escapeHtml(item.name)}"><div class="poster"></div><h3>${escapeHtml(item.name)}</h3><p>${bytes(item.size)} · ${escapeHtml(item.filename.split(".").pop().toUpperCase())}</p></button>`).join("") || '<div class="empty-state">No videos found. Put video files in the media or downloads folder.</div>';
}

async function refresh() {
  const [status, downloads, media] = await Promise.all([api("/api/status"), api("/api/downloads"), api("/api/media")]);
  state.status = status;
  state.downloads = downloads.items || [];
  state.media = media.items || [];
  renderStatus(); renderDownloads(); renderMedia();
}

function toast(message) {
  $("#toast").textContent = message; $("#toast").classList.add("show");
  setTimeout(() => $("#toast").classList.remove("show"), 2600);
}

async function addDownload() {
  const uri = $("#downloadUri").value.trim();
  const file = $("#torrentFile").files[0];
  const error = $("#addError"); error.textContent = "";
  try {
    if (file) {
      await api("/api/downloads/torrent", {method: "POST", headers: {"Content-Type": "application/x-bittorrent"}, body: await file.arrayBuffer()});
    } else if (uri) {
      await api("/api/downloads/uri", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({uri})});
    } else throw new Error("Enter a link or choose a .torrent file.");
    $("#addDialog").close(); $("#downloadUri").value = ""; $("#torrentFile").value = "";
    toast("Download added to the queue"); await refresh();
  } catch (e) { error.textContent = e.message; }
}

async function saveSchedule(event) {
  event.preventDefault();
  const payload = {
    enabled: $("#scheduleEnabled").checked,
    start: $("#scheduleStart").value,
    end: $("#scheduleEnd").value,
  };
  try {
    await api("/api/settings/schedule", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    state.scheduleDirty = false;
    toast(payload.enabled ? `Downloads scheduled for ${payload.start}–${payload.end}` : "Download schedule disabled");
    await refresh();
  } catch (e) { toast(e.message); }
}

async function login(event) {
  event.preventDefault();
  $("#loginError").textContent = "";
  try {
    const session = await api("/api/auth/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({username: $("#loginUsername").value.trim(), password: $("#loginPassword").value}),
    });
    showAdmin(session);
    $("#loginPassword").value = "";
    await refresh();
  } catch (e) { $("#loginError").textContent = e.message; }
}

async function logout() {
  try { await api("/api/auth/logout", {method: "POST"}); } catch (e) {}
  showLogin();
}

async function changePassword(event) {
  event.preventDefault();
  const current = $("#currentPassword").value;
  const next = $("#newPassword").value;
  const confirmation = $("#confirmPassword").value;
  const error = $("#passwordError");
  error.textContent = "";
  if (next !== confirmation) { error.textContent = "The new passwords do not match."; return; }
  try {
    await api("/api/auth/password", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({current_password: current, new_password: next})});
    $("#passwordForm").reset();
    $("#passwordWarning").classList.add("hidden");
    toast("Admin password updated");
  } catch (e) { error.textContent = e.message; }
}

async function saveMetadata(event) {
  event.preventDefault();
  const error = $("#metadataError"); error.textContent = "";
  try {
    await api("/api/settings/metadata", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({enabled: $("#metadataEnabled").checked, api_key: $("#metadataApiKey").value.trim()}),
    });
    $("#metadataApiKey").value = "";
    toast("Metadata settings saved");
    await refresh();
  } catch (e) { error.textContent = e.message; }
}

async function refreshAllMetadata() {
  try {
    await api("/api/metadata/refresh", {method: "POST"});
    toast("Metadata cache cleared; the library will refresh in the background");
    await refresh();
  } catch (e) { toast(e.message); }
}

async function initialize() {
  try {
    const session = await api("/api/auth/session");
    if (!session.authenticated) { showLogin(); return; }
    showAdmin(session);
    await refresh();
  } catch (e) { showLogin("Could not connect to PocketServer."); }
}

document.addEventListener("click", async (event) => {
  const nav = event.target.closest("[data-view]"); if (nav) showView(nav.dataset.view);
  const go = event.target.closest("[data-go]"); if (go) showView(go.dataset.go);
  const action = event.target.closest("[data-action]");
  if (action) { try { await api(`/api/downloads/${action.dataset.gid}/${action.dataset.action}`, {method: "POST"}); await refresh(); } catch (e) { toast(e.message); } }
  const media = event.target.closest("[data-media-url]");
  if (media) { $("#videoPlayer").src = media.dataset.mediaUrl; $("#playerTitle").textContent = media.dataset.mediaName; $("#playerDialog").showModal(); }
});
$("#menuButton").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
$("#themeToggle").addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light"));
$("#logoutButton").addEventListener("click", logout);
$("#loginForm").addEventListener("submit", login);
$("#passwordForm").addEventListener("submit", changePassword);
$("#metadataForm").addEventListener("submit", saveMetadata);
$("#refreshMetadata").addEventListener("click", refreshAllMetadata);
$("#openAdd").addEventListener("click", () => $("#addDialog").showModal());
$("#submitDownload").addEventListener("click", addDownload);
$("#scheduleForm").addEventListener("submit", saveSchedule);
[$("#scheduleEnabled"), $("#scheduleStart"), $("#scheduleEnd")].forEach((input) => input.addEventListener("input", () => { state.scheduleDirty = true; }));
$("#downloadSearch").addEventListener("input", renderDownloads);
$("#mediaSearch").addEventListener("input", renderMedia);
$("#closePlayer").addEventListener("click", () => { $("#videoPlayer").pause(); $("#videoPlayer").removeAttribute("src"); $("#playerDialog").close(); });

applyTheme(document.documentElement.dataset.theme);
initialize();
setInterval(() => { if (state.authenticated) refresh().catch((error) => { if (error.message.includes("authentication")) showLogin("Your session expired. Sign in again."); }); }, 3000);
