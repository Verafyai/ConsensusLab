// Entry point: load the snapshot (local API, else the static export's data.json), then render
// tabs lazily. In the static export (local:false) no controls or thumbs are rendered at all.
import { h, clear, state, when } from "./util.js";
import * as V from "./views.js";

const TABS = [
  ["overview", "Overview", V.overview],
  ["season0", "Season 0", V.season0],
  ["leaderboard", "Leaderboard", V.leaderboardView],
  ["disagreement", "Disagreement", V.disagreementView],
  ["trends", "Trends", V.trendsView],
  ["experiments", "Experiments", V.experimentsView],
  ["cases", "Cases", V.casesView],
  ["zones", "Zones", (root, d) => V.zonesView(root, d, { onRun: state.local ? (z) => import("./controls.js").then((m) => m.openRun(z)) : null })],
  ["social", "Raters & social", V.socialView],
  ["learnings", "Learnings", V.learningsView],
  ["budget", "Budget", V.budgetView],
  ["controls", "Controls", null, true],
];

async function load() {
  try {
    const r = await fetch("/api/data", { cache: "no-store" });
    if (r.ok && (r.headers.get("content-type") || "").includes("json")) return await r.json();
  } catch { /* static export: fall through */ }
  const r = await fetch("./data.json", { cache: "no-store" });
  if (!r.ok) throw new Error(`data.json: HTTP ${r.status}`);
  return await r.json();
}

const rendered = new Set();
function show(id) {
  const tabs = TABS.filter(([, , , localOnly]) => !localOnly || state.local);
  if (!tabs.some(([t]) => t === id)) id = "overview";
  for (const [t] of tabs) {
    const sec = document.getElementById(`view-${t}`);
    sec.classList.toggle("active", t === id);
    document.querySelector(`nav.tabs a[data-tab="${t}"]`)?.setAttribute("aria-current", t === id ? "page" : "false");
  }
  const sec = document.getElementById(`view-${id}`);
  if (!rendered.has(id)) {
    rendered.add(id);
    const [, , fn] = TABS.find(([t]) => t === id);
    try {
      if (id === "controls") import("./controls.js").then((m) => m.controlsView(sec, state.data));
      else fn(sec, state.data);
    } catch (e) {
      console.error(e);
      sec.append(h("div", { class: "notice bad" }, `This view failed to render: ${e.message}`));
    }
  }
  document.querySelector(`nav.tabs a[data-tab="${id}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
}

async function main() {
  const main = document.getElementById("main");
  let d;
  try {
    d = await load();
  } catch (e) {
    main.append(h("div", { class: "notice bad" }, `Couldn't load the lab data: ${e.message}`));
    return;
  }
  state.data = d;
  state.local = d.local === true;
  document.documentElement.dataset.mode = state.local ? "local" : "static";
  document.getElementById("generated").textContent = `data as of ${when(d.generated)}`;
  document.getElementById("mode").textContent = state.local ? "Local lab" : "Read-only copy";
  if (!state.local) document.getElementById("health").remove();
  else import("./controls.js").then((m) => m.startStatus());
  const nav = document.getElementById("tabs");
  for (const [id, label, , localOnly] of TABS) {
    if (localOnly && !state.local) continue;
    nav.append(h("a", { href: `#${id}`, "data-tab": id, class: localOnly ? "local-only" : null }, label));
    main.append(h("section", { class: "view", id: `view-${id}`, "aria-label": label }));
  }
  const route = () => show((location.hash || "#overview").slice(1));
  window.addEventListener("hashchange", route);
  route();
  document.body.dataset.ready = "1";
}

main();
