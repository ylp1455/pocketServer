const clientState = {media: []};
const client$ = (selector) => document.querySelector(selector);
const clientEscape = (value) => String(value).replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[char]);
const clientBytes = (value) => {
  const n = Number(value || 0); if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1);
  return `${(n / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
};

function renderClientMedia() {
  const filter = client$("#clientSearch").value.trim().toLowerCase();
  const items = clientState.media.filter((item) => item.name.toLowerCase().includes(filter));
  client$("#clientGrid").innerHTML = items.map((item) => `
    <button class="client-card" data-url="${clientEscape(item.url)}" data-name="${clientEscape(item.name)}">
      <span class="client-poster"></span>
      <h3>${clientEscape(item.name)}</h3>
      <p>${clientBytes(item.size)} · ${clientEscape(item.filename.split(".").pop().toUpperCase())}</p>
    </button>`).join("") || '<div class="client-empty">No matching videos were found.</div>';
}

async function loadClientMedia() {
  try {
    const response = await fetch("/api/media");
    if (!response.ok) throw new Error();
    const body = await response.json();
    clientState.media = body.items || [];
    renderClientMedia();
  } catch (error) {
    client$("#clientGrid").innerHTML = '<div class="client-empty">PocketServer is unavailable. Try refreshing this page.</div>';
  }
}

client$("#clientSearch").addEventListener("input", renderClientMedia);
client$("#clientGrid").addEventListener("click", (event) => {
  const card = event.target.closest("[data-url]"); if (!card) return;
  client$("#clientVideo").src = card.dataset.url;
  client$("#clientPlayerTitle").textContent = card.dataset.name;
  client$("#clientPlayer").showModal();
});
client$("#clientPlayerClose").addEventListener("click", () => {
  client$("#clientVideo").pause(); client$("#clientVideo").removeAttribute("src"); client$("#clientPlayer").close();
});
loadClientMedia();
