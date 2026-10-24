const clientState = {media: [], selected: null, featured: null, filter: "all", myList: new Set()};
const client$ = (selector) => document.querySelector(selector);
const client$$ = (selector) => [...document.querySelectorAll(selector)];
const clientEscape = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
const mediaMetadata = (item) => item?.metadata || {};
const mediaTitle = (item) => mediaMetadata(item).title || item?.lookup_title || item?.name || "Untitled";
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
  return `<button class="watch-card" data-media-id="${clientEscape(item.url)}"><span class="watch-poster"><span class="poster-fallback">▶</span>${poster ? `<img loading="lazy" src="${clientEscape(poster)}" alt="" onerror="this.remove()">` : ""}</span><h3>${clientEscape(mediaTitle(item))}</h3><p>${clientEscape(subtitle)}</p></button>`;
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
  client$("#recentShelf").hidden = single;
  client$("#movieShelf").hidden = single && clientState.filter !== "movie";
  client$("#seriesShelf").hidden = single && clientState.filter !== "series";
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
  client$("#featureArt").style.backgroundImage = metadata.poster ? `url("${String(metadata.poster).replace(/["\\]/g, "")}")` : "";
  client$("#featureList").textContent = clientState.myList.has(item.url) ? "✓" : "＋";
}

function openDetails(item) {
  if (!item) return;
  clientState.selected = item;
  const metadata = mediaMetadata(item);
  client$("#detailsType").textContent = metadata.type || "Media";
  client$("#detailsTitle").textContent = mediaTitle(item);
  client$("#detailsPlot").textContent = metadata.plot || "No description is available yet. Configure OMDb metadata in the admin dashboard to automatically retrieve title information.";
  client$("#detailsActors").textContent = (metadata.actors || []).join(", ") || "Not available";
  client$("#detailsDirector").textContent = metadata.director || "Not available";
  client$("#detailsMeta").innerHTML = [metadata.imdb_rating ? `<span class="rating">${clientEscape(metadata.imdb_rating)}</span>` : "", metadata.year, metadata.rated, metadata.runtime, ...(metadata.genres || [])].filter(Boolean).map((value) => String(value).startsWith("<") ? value : `<span>${clientEscape(value)}</span>`).join("");
  client$("#detailsPoster").style.backgroundImage = metadata.poster ? `url("${String(metadata.poster).replace(/["\\]/g, "")}")` : "linear-gradient(145deg,var(--watch-raised),var(--watch-surface))";
  client$("#detailsList").innerHTML = `${clientState.myList.has(item.url) ? "✓" : "＋"} <span>${clientState.myList.has(item.url) ? "In My List" : "My List"}</span>`;
  const imdb = client$("#detailsImdb");
  imdb.hidden = !metadata.imdb_id;
  if (metadata.imdb_id) imdb.href = `https://www.imdb.com/title/${metadata.imdb_id}/`;
  if (!client$("#detailsDialog").open) client$("#detailsDialog").showModal();
}

function playMedia(item) {
  if (!item) return;
  if (client$("#detailsDialog").open) client$("#detailsDialog").close();
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
  if (client$("#detailsDialog").open) openDetails(item);
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
  } catch (error) {
    client$("#recentRow").innerHTML = '<div class="watch-empty">PocketServer is unavailable. Try refreshing this page.</div>';
  }
}

document.addEventListener("click", (event) => {
  const card = event.target.closest("[data-media-id]");
  if (card) openDetails(clientState.media.find((item) => item.url === card.dataset.mediaId));
  const filter = event.target.closest("[data-library-filter]");
  if (filter) { clientState.filter = filter.dataset.libraryFilter; client$$('[data-library-filter]').forEach((button) => button.classList.toggle("active", button === filter)); renderLibrary(); document.querySelector("#library").scrollIntoView({behavior: "smooth"}); }
  if (event.target.closest("[data-close-details]")) client$("#detailsDialog").close();
});
client$("#clientSearch").addEventListener("input", renderLibrary);
client$("#clientThemeToggle").addEventListener("click", () => applyClientTheme(document.documentElement.dataset.clientTheme === "dark" ? "light" : "dark"));
client$("#featurePlay").addEventListener("click", () => playMedia(clientState.featured));
client$("#featureDetails").addEventListener("click", () => openDetails(clientState.featured));
client$("#featureList").addEventListener("click", () => toggleMyList(clientState.featured));
client$("#detailsPlay").addEventListener("click", () => playMedia(clientState.selected));
client$("#detailsList").addEventListener("click", () => toggleMyList(clientState.selected));
client$("#clientPlayerClose").addEventListener("click", () => { client$("#clientVideo").pause(); client$("#clientVideo").removeAttribute("src"); client$("#clientPlayer").close(); });

applyClientTheme(document.documentElement.dataset.clientTheme);
loadClientMedia();
setInterval(loadClientMedia, 12000);
