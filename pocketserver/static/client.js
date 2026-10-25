const clientState = {media: [], selected: null, featured: null, filter: "all", myList: new Set()};
const client$ = (selector) => document.querySelector(selector);
const client$$ = (selector) => [...document.querySelectorAll(selector)];
const clientEscape = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
const mediaMetadata = (item) => item?.metadata || {};
const posterBackground = (value) => value ? `url("${String(value).replace(/["\\]/g, "")}")` : "";
const cleanFilename = (value) => {
  let title = String(value || "Untitled").replace(/\.[^.]+$/, "");
  const year = title.match(/\b(?:19|20)\d{2}\b/);
  if (year) title = title.slice(0, year.index);
  title = title.replace(/\b(?:480p|720p|1080p|2160p|4k|uhd|bluray|blu-ray|brrip|webrip|web-dl|hdrip|dvdrip|xvid|x264|x265|h264|h265|hevc|aac|dts|proper|repack|extended|remastered)\b.*$/i, "");
  title = title.replace(/[._\-\[\]()]+/g, " ").replace(/\s+/g, " ").trim();
  return title || "Untitled";
};
const mediaTitle = (item) => mediaMetadata(item).title || item?.lookup_title || cleanFilename(item?.filename || item?.name);
const mediaType = (item) => (mediaMetadata(item).type || "movie").toLowerCase();

try { clientState.myList = new Set(JSON.parse(localStorage.getItem("pocket-my-list") || "[]")); } catch (error) {}

function applyClientTheme(theme) {
  const selected = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.clientTheme = selected;
  client$("#clientThemeToggle").textContent = selected === "dark" ? "☀" : "☾";
  client$("#clientThemeColor").content = selected === "dark" ? "#090b12" : "#f5f6fa";
  try { localStorage.setItem("pocket-client-theme", selected); } catch (error) {}
}

function cardMarkup(item) {
  const metadata = mediaMetadata(item);
  const poster = metadata.poster;
  const subtitle = [metadata.year, ...(metadata.genres || []).slice(0, 2)].filter(Boolean).join(" · ") || item.filename.split(".").pop().toUpperCase();
  const artwork = poster
    ? `<img loading="lazy" src="${clientEscape(poster)}" alt="${clientEscape(mediaTitle(item))} poster" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><span class="poster-fallback" hidden>▶</span>`
    : '<span class="poster-fallback">▶</span>';
  return `<button class="watch-card" data-media-id="${clientEscape(item.url)}"><span class="watch-poster">${artwork}</span><h3>${clientEscape(mediaTitle(item))}</h3><p>${clientEscape(subtitle)}</p></button>`;
}

function renderRow(selector, items, emptyMessage) {
  client$(selector).innerHTML = items.length ? items.map(cardMarkup).join("") : `<div class="watch-empty">${clientEscape(emptyMessage)}</div>`;
}

function visibleMedia() {
  const search = client$("#clientSearch").value.trim().toLowerCase();
  return clientState.media.filter((item) => {
    const text = [mediaTitle(item), item.filename, ...(mediaMetadata(item).actors || []), ...(mediaMetadata(item).genres || [])].join(" ").toLowerCase();
    const matchesSearch = !search || text.includes(search);
    const matchesType = clientState.filter === "all" || (clientState.filter === "list" ? clientState.myList.has(item.url) : mediaType(item) === clientState.filter);
    return matchesSearch && matchesType;
  });
}

function renderLibrary() {
  const items = visibleMedia();
  const movies = items.filter((item) => mediaType(item) !== "series");
  const series = items.filter((item) => mediaType(item) === "series");
  const saved = items.filter((item) => clientState.myList.has(item.url));
  renderRow("#recentRow", items.slice(0, 12), clientState.media.length ? "No titles match your search." : "Your library is empty. Add videos from the admin dashboard.");
  renderRow("#movieRow", movies, "No movies found.");
  renderRow("#seriesRow", series, "No series found.");
  renderRow("#listRow", saved, "Your list is empty.");
  client$("#libraryCount").textContent = `${items.length} title${items.length === 1 ? "" : "s"}`;
  const single = clientState.filter !== "all";
  const recentAlreadyShowsEverything = !single && items.length > 0 && items.length <= 12;
  client$("#recentShelf").hidden = single;
  client$("#movieShelf").hidden = (single && clientState.filter !== "movie") || (!single && (movies.length === 0 || (recentAlreadyShowsEverything && movies.length === items.length)));
  client$("#seriesShelf").hidden = (single && clientState.filter !== "series") || (!single && (series.length === 0 || (recentAlreadyShowsEverything && series.length === items.length)));
  client$("#listShelf").hidden = clientState.filter !== "list";
}

function renderFeature(item) {
  clientState.featured = item || null;
  if (!item) return;
  const metadata = mediaMetadata(item);
  client$("#featureKicker").textContent = `FEATURED · ${(metadata.type || "MEDIA").toUpperCase()}`;
  client$("#featureTitle").textContent = mediaTitle(item);
  client$("#featurePlot").textContent = metadata.plot || "Ready to stream directly from your PocketServer.";
  const featureBits = [metadata.imdb_rating ? `<span class="rating">${clientEscape(metadata.imdb_rating)}</span>` : "", metadata.year, metadata.runtime, ...(metadata.genres || []).slice(0, 3)].filter(Boolean);
  client$("#featureMeta").innerHTML = featureBits.map((value) => String(value).startsWith("<") ? value : `<span>${clientEscape(value)}</span>`).join("");
  client$("#featureArt").style.backgroundImage = posterBackground(metadata.poster);
  client$("#featureList").textContent = clientState.myList.has(item.url) ? "✓" : "＋";
}

function titleHash(item) {
  const routeType = mediaType(item) === "series" ? "series" : "movie";
  const routeId = mediaMetadata(item).imdb_id || encodeURIComponent(item.url);
  return `#/${routeType}/${routeId}`;
}

function openDetails(item) {
  if (!item) return;
  const target = titleHash(item);
  if (location.hash !== target) location.hash = target;
  else renderTitlePage(item, true);
}

function updateTitleListButton(item) {
  const saved = Boolean(item && clientState.myList.has(item.url));
  client$("#titleList").innerHTML = saved ? "✓ <span>In My List</span>" : "＋ <span>My List</span>";
  client$("#titleList").setAttribute("aria-label", saved ? "Remove from My List" : "Add to My List");
}

function renderTitlePage(item, scrollToTop = false) {
  if (!item) return;
  clientState.selected = item;
  const metadata = mediaMetadata(item);
  const title = mediaTitle(item);
  const plot = metadata.plot || "No description is available yet. Configure OMDb metadata in the admin dashboard to retrieve title information automatically.";
  client$("#homeView").hidden = true;
  client$("#titlePage").hidden = false;
  client$("#titleType").textContent = (metadata.type || "Media").toUpperCase();
  client$("#titleName").textContent = title;
  client$("#titleMeta").innerHTML = [metadata.year, metadata.runtime, metadata.rated, metadata.imdb_rating ? `<span class="rating">${clientEscape(metadata.imdb_rating)}</span>` : ""].filter(Boolean).map((value) => String(value).startsWith("<") ? value : `<span>${clientEscape(value)}</span>`).join("");
  client$("#titleGenres").innerHTML = (metadata.genres || []).map((genre) => `<span>${clientEscape(genre)}</span>`).join("");
  client$("#titleSummary").textContent = plot;
  client$("#titlePlot").textContent = plot;
  client$("#titleActors").textContent = (metadata.actors || []).join(", ") || "Not available";
  client$("#titleDirector").textContent = metadata.director || "Not available";
  client$("#titleFile").textContent = item.filename || item.name;
  client$("#titleAboutHeading").textContent = `About ${title}`;
  client$("#titleBackdrop").style.backgroundImage = posterBackground(metadata.poster);
  client$("#titlePoster").style.backgroundImage = posterBackground(metadata.poster);
  client$("#titlePoster").classList.toggle("has-art", Boolean(metadata.poster));
  updateTitleListButton(item);
  const imdb = client$("#titleImdb");
  imdb.hidden = !metadata.imdb_id;
  if (metadata.imdb_id) imdb.href = `https://www.imdb.com/title/${metadata.imdb_id}/`;
  const sameType = clientState.media.filter((candidate) => candidate.url !== item.url && mediaType(candidate) === mediaType(item));
  const related = (sameType.length ? sameType : clientState.media.filter((candidate) => candidate.url !== item.url)).slice(0, 6);
  renderRow("#titleRelated", related, "Add more media to see related titles here.");
  client$$('[data-library-filter]').forEach((button) => button.classList.remove("active"));
  document.title = `${title} · PocketServer`;
  if (scrollToTop) window.scrollTo({top: 0, behavior: "smooth"});
}

function renderRoute(scrollToTop = false) {
  const match = location.hash.match(/^#\/(?:movie|series)\/(.+)$/);
  if (match) {
    let id = match[1];
    try { id = decodeURIComponent(id); } catch (error) {}
    const item = clientState.media.find((candidate) => mediaMetadata(candidate).imdb_id === id || candidate.url === id);
    if (item) { renderTitlePage(item, scrollToTop); return; }
  }
  clientState.selected = null;
  client$("#titlePage").hidden = true;
  client$("#homeView").hidden = false;
  client$$('[data-library-filter]').forEach((button) => button.classList.toggle("active", button.dataset.libraryFilter === clientState.filter));
  document.title = "PocketServer · Watch";
  if (scrollToTop) window.scrollTo({top: 0, behavior: "smooth"});
}

function playMedia(item) {
  if (!item) return;
  client$("#clientVideo").src = item.url;
  client$("#clientPlayerTitle").textContent = mediaTitle(item);
  client$("#clientPlayer").showModal();
  client$("#clientVideo").play().catch(() => {});
}

function toggleMyList(item) {
  if (!item) return;
  if (clientState.myList.has(item.url)) clientState.myList.delete(item.url); else clientState.myList.add(item.url);
  try { localStorage.setItem("pocket-my-list", JSON.stringify([...clientState.myList])); } catch (error) {}
  renderLibrary(); renderFeature(clientState.featured);
  if (!client$("#titlePage").hidden && clientState.selected?.url === item.url) updateTitleListButton(item);
}

async function submitMediaRequest(event) {
  event.preventDefault();
  const message = client$("#requestMessage");
  message.className = "request-message";
  message.textContent = "Sending…";
  try {
    const response = await fetch("/api/requests", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        title: client$("#requestTitle").value.trim(),
        type: client$("#requestType").value,
        year: client$("#requestYear").value.trim(),
        requested_by: client$("#requestName").value.trim(),
        notes: client$("#requestNotes").value.trim(),
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
    client$("#requestForm").reset();
    message.classList.add("success");
    message.textContent = `“${body.request.title}” was sent to the administrator.`;
  } catch (error) {
    message.classList.add("error");
    message.textContent = error.message;
  }
}

async function loadClientMedia() {
  try {
    const response = await fetch("/api/media", {cache: "no-store"});
    if (!response.ok) throw new Error();
    const body = await response.json();
    clientState.media = body.items || [];
    renderLibrary();
    const featured = clientState.featured ? clientState.media.find((item) => item.url === clientState.featured.url) : clientState.media.find((item) => item.metadata) || clientState.media[0];
    if (featured) renderFeature(featured);
    renderRoute(false);
  } catch (error) {
    client$("#recentRow").innerHTML = '<div class="watch-empty">PocketServer is unavailable. Try refreshing this page.</div>';
  }
}

document.addEventListener("click", (event) => {
  const card = event.target.closest("[data-media-id]");
  if (card) openDetails(clientState.media.find((item) => item.url === card.dataset.mediaId));
  const filter = event.target.closest("[data-library-filter]");
  if (filter) { clientState.filter = filter.dataset.libraryFilter; if (location.hash !== "#/") location.hash = "#/"; else renderRoute(false); client$$('[data-library-filter]').forEach((button) => button.classList.toggle("active", button === filter)); renderLibrary(); setTimeout(() => document.querySelector("#library").scrollIntoView({behavior: "smooth"}), 0); }
  if (event.target.closest("[data-close-request]")) client$("#requestDialog").close();
});
client$("#clientSearch").addEventListener("input", renderLibrary);
client$("#clientThemeToggle").addEventListener("click", () => applyClientTheme(document.documentElement.dataset.clientTheme === "dark" ? "light" : "dark"));
client$("#openRequest").addEventListener("click", () => { client$("#requestMessage").textContent = ""; client$("#requestDialog").showModal(); client$("#requestTitle").focus(); });
client$("#requestForm").addEventListener("submit", submitMediaRequest);
client$("#featurePlay").addEventListener("click", () => playMedia(clientState.featured));
client$("#featureDetails").addEventListener("click", () => openDetails(clientState.featured));
client$("#featureList").addEventListener("click", () => toggleMyList(clientState.featured));
client$("#titleBack").addEventListener("click", () => { location.hash = "#/"; });
client$("#titlePlay").addEventListener("click", () => playMedia(clientState.selected));
client$("#titleList").addEventListener("click", () => toggleMyList(clientState.selected));
client$("#clientPlayerClose").addEventListener("click", () => { client$("#clientVideo").pause(); client$("#clientVideo").removeAttribute("src"); client$("#clientPlayer").close(); });
window.addEventListener("hashchange", () => renderRoute(true));

applyClientTheme(document.documentElement.dataset.clientTheme);
loadClientMedia();
setInterval(loadClientMedia, 12000);
