// Shared helpers: DOM builders, formatting, link rewriting (local vs static export), tooltip.

export const state = { data: null, local: false };

// Files the local server will serve under /files/ (mirrors server.FILE_PREFIXES).
const FILE_PREFIXES = ["experiments/", "library/cards/", "zones/", "LEARNINGS.md", "STEERING.md",
  "docs/", "data/SOURCES.md", "data/SPLITS.md", "ops/reports/"];

export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  setAttrs(el, attrs);
  append(el, kids);
  return el;
}

const SVGNS = "http://www.w3.org/2000/svg";
export function s(tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  setAttrs(el, attrs);
  append(el, kids);
  return el;
}

function setAttrs(el, attrs) {
  if (!attrs) return;
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.setAttribute("class", v);
    else if (k === "text") el.textContent = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
}

export function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
}

export function clear(el) { while (el.firstChild) el.firstChild.remove(); return el; }

// ---------- formatting ----------
export const isNum = (v) => typeof v === "number" && Number.isFinite(v);
export const f3 = (v) => (isNum(v) ? v.toFixed(3) : "—");
export const f2 = (v) => (isNum(v) ? v.toFixed(2) : "—");
export const signed = (v, d = 3) => (isNum(v) ? (v > 0 ? "+" : v < 0 ? "−" : "±") + Math.abs(v).toFixed(d) : "—");
export const pct = (v, d = 0) => (isNum(v) ? (v * 100).toFixed(d) + "%" : "—");
export function usd(v) {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e6) return "$" + (v / 1e6).toFixed(1) + "M";
  if (a >= 1e4) return "$" + (v / 1e3).toFixed(1) + "K";
  if (a >= 100) return "$" + v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (a >= 1) return "$" + v.toFixed(2);
  if (a >= 0.01) return "$" + v.toFixed(3);
  if (a === 0) return "$0";
  return "$" + v.toFixed(4);
}
export function secs(v) {
  if (!isNum(v)) return "—";
  return v < 1 ? (v * 1000).toFixed(0) + " ms" : v.toFixed(1) + " s";
}
export function when(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (isNaN(d)) return String(ts);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
export const humanize = (s) => String(s ?? "").replace(/_/g, " ");

// ---------- links ----------
export function canLinkFile(path) {
  if (!path || path.includes("..")) return false;
  return FILE_PREFIXES.some((p) => path === p.replace(/\/$/, "") || path.startsWith(p));
}
export function fileHref(path) {
  const rel = String(path).replace(/^\/+/, "");
  return state.local ? `/files/${rel}` : `./files/${rel}`;
}
/** "/t/E-0001/q-x" or (exp, item) -> [exp, item] */
function tParts(a, b) {
  if (b) return [a, b];
  const m = String(a).match(/\/t\/([^/]+)\/([^/?#]+?)(?:\.json)?$/);
  return m ? [m[1], m[2]] : [null, null];
}
export function transcriptHref(a, b) {
  const [exp, item] = tParts(a, b);
  if (!exp) return "#";
  return state.local ? `/t/${exp}/${item}` : `./t/${exp}/${item}.json`;
}
export function replayHref(a, b) {
  const [exp, item] = tParts(a, b);
  if (!exp) return "#";
  const t = state.local ? `/t/${exp}/${item}` : `../t/${exp}/${item}.json`;
  const base = state.local ? "/replay/index.html" : "./replay/index.html";
  return `${base}?t=${t}`;  // ids are [A-Za-z0-9._-], no escaping needed
}

/** A number (or text) that links to the result file it came from. */
export function numLink(text, path, title) {
  if (!path || !canLinkFile(path) || text === "—") return h("span", { title: path ? `from ${path}` : null }, text);
  return h("a", { class: "num", href: fileHref(path), title: title || `from ${path}`, target: "_blank", rel: "noopener" }, text);
}
export function fileLink(text, path) {
  if (!canLinkFile(path)) return h("span", { class: "muted", title: path }, text);
  return h("a", { href: fileHref(path), target: "_blank", rel: "noopener" }, text);
}
export function replayLink(text, a, b) {
  return h("a", { href: replayHref(a, b), target: "_blank", rel: "noopener", class: "replay-link" }, text);
}
export const resultsPath = (exp) => `experiments/${exp}/results.json`;

// ---------- badges ----------
const STATUS = {
  champion: ["accent", "★", "champion"],
  promoted: ["good", "✓", "promoted"],
  not_promoted: ["", "–", "not promoted"],
  stopped_at_dev: ["", "■", "stopped at dev"],
  screened_out: ["", "■", "screened out"],
  finalist: ["accent", "◆", "finalist"],
  replicated: ["good", "✓", "replicated"],
  "not replicated": ["bad", "✕", "not replicated"],
  unclear: ["warn", "?", "unclear"],
  confirmed: ["good", "✓", "confirmed"],
  tentative: ["warn", "?", "tentative"],
  refuted: ["bad", "✕", "refuted"],
  better: ["good", "▲", "better"],
  worse: ["bad", "▼", "worse"],
  queued: ["", "…", "queued"],
  running: ["accent", "▶", "running"],
  done: ["good", "✓", "done"],
  failed: ["bad", "✕", "failed"],
  refused: ["bad", "✕", "refused"],
};
export function badge(key) {
  const k = String(key ?? "").trim();
  const [cls, ico, label] = STATUS[k] || STATUS[k.toLowerCase()] || ["", "•", humanize(k) || "unknown"];
  return h("span", { class: `badge ${cls}` }, h("span", { class: "ico", "aria-hidden": "true" }, ico), label);
}

// ---------- tooltip ----------
let tipEl;
export function tip() {
  if (!tipEl) {
    tipEl = h("div", { class: "tip", role: "tooltip" });
    document.body.append(tipEl);
  }
  return tipEl;
}
/** rows: [[label, value], ...] */
export function showTip(x, y, title, rows) {
  const t = tip();
  clear(t);
  if (title) t.append(h("div", { class: "t-title" }, title));
  for (const r of rows || []) t.append(h("div", { class: "t-row" }, h("span", null, r[0]), h("span", null, r[1])));
  t.style.display = "block";
  const w = t.offsetWidth, ht = t.offsetHeight;
  let left = x + 14, top = y + 14;
  if (left + w > window.innerWidth - 8) left = Math.max(8, x - w - 14);
  if (top + ht > window.innerHeight - 8) top = Math.max(8, y - ht - 14);
  t.style.left = left + "px";
  t.style.top = top + "px";
}
export function hideTip() { if (tipEl) tipEl.style.display = "none"; }

// ---------- api ----------
export async function post(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Lab": "1" },
    body: JSON.stringify(body),
  });
  let json = null;
  try { json = await r.json(); } catch { json = { error: `HTTP ${r.status}` }; }
  return { ok: r.ok, status: r.status, json };
}

export function emptyState(text) { return h("div", { class: "empty" }, text); }

export function card(title, sub, ...body) {
  return h("div", { class: "card" },
    h("div", { class: "card-head" }, h("h3", null, title), sub ? h("span", { class: "sub" }, sub) : null),
    ...body);
}

/** Sortable table. cols: [{key, label, num, value(row), render(row), title}] */
export function sortableTable(cols, rows, opts = {}) {
  let sortKey = opts.sortKey || null, dir = opts.dir || -1;
  const wrap = h("div", { class: "table-wrap" });
  const table = h("table", { class: opts.class || "" });
  wrap.append(table);
  function draw() {
    clear(table);
    const tr = h("tr");
    for (const c of cols) {
      const th = h("th", { class: c.num ? "n" : "", scope: "col", title: c.title || null });
      if (c.sortable === false) th.append(c.label);
      else {
        const arr = sortKey === c.key ? (dir > 0 ? "▲" : "▼") : "↕";
        th.append(h("button", { class: "sort", type: "button", onclick: () => {
          if (sortKey === c.key) dir = -dir; else { sortKey = c.key; dir = c.num ? -1 : 1; }
          draw();
        } }, c.label, h("span", { class: "arr", "aria-hidden": "true" }, arr)));
        if (sortKey === c.key) th.setAttribute("aria-sort", dir > 0 ? "ascending" : "descending");
      }
      tr.append(th);
    }
    table.append(h("thead", null, tr));
    let data = rows.slice();
    if (sortKey) {
      const col = cols.find((c) => c.key === sortKey);
      const val = col.value || ((r) => r[col.key]);
      data.sort((a, b) => {
        const va = val(a), vb = val(b);
        const na = va === null || va === undefined || (typeof va === "number" && !isFinite(va));
        const nb = vb === null || vb === undefined || (typeof vb === "number" && !isFinite(vb));
        if (na && nb) return 0;
        if (na) return 1;
        if (nb) return -1;
        if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
        return String(va).localeCompare(String(vb)) * dir;
      });
    }
    const tb = h("tbody");
    for (const r of data) {
      const row = h("tr", { class: opts.rowClass ? opts.rowClass(r) : null });
      for (const c of cols) {
        const td = h("td", { class: (c.num ? "n " : "") + (c.cls || "") });
        const v = c.render ? c.render(r) : (c.value ? c.value(r) : r[c.key]);
        append(td, [v ?? "—"]);
        row.append(td);
      }
      tb.append(row);
    }
    if (!data.length) tb.append(h("tr", null, h("td", { colspan: cols.length, class: "muted" }, opts.empty || "No rows.")));
    table.append(tb);
  }
  draw();
  return wrap;
}
