// Read-only views (spec §8.2, zones tile view from §8.3).
import {
  h, clear, append, isNum, f3, f2, signed, pct, usd, secs, when, humanize, state, badge, card,
  numLink, fileLink, replayLink, canLinkFile, fileHref, resultsPath, emptyState, sortableTable, post, showTip, hideTip,
} from "./util.js";
import { scatter, lineChart, legend, hbars, ciCell, ciGlyph, seqBlue, seqOrange, scaleLegend } from "./charts.js";

const LABEL_ORDER = ["supported", "refuted", "not_enough_evidence", "conflicting"];
const rowsOf = (d) => d.leaderboard?.rows || [];
const champRow = (d) => rowsOf(d).find((r) => r.protocol === d.leaderboard?.champion);
function bestSingle(d) {
  const s = rowsOf(d).filter((r) => r.protocol.startsWith("single-") && isNum(r.holdout_macro_f1));
  return s.sort((a, b) => b.holdout_macro_f1 - a.holdout_macro_f1)[0] || null;
}
/** Δ vs best single model: prefer the result file's paired comparison, else the point difference. */
function deltaVsBestSingle(d, r) {
  if (r.vs_best_single && isNum(r.vs_best_single.diff)) return { diff: r.vs_best_single.diff, ci: r.vs_best_single.ci, paired: true };
  const b = bestSingle(d);
  if (!b || !isNum(r.holdout_macro_f1)) return null;
  if (b.protocol === r.protocol) return { diff: 0, ci: null, paired: false, self: true };
  return { diff: r.holdout_macro_f1 - b.holdout_macro_f1, ci: null, paired: false };
}
function lastHitRate(d) {
  const hr = d.hit_rate || [];
  return hr.length ? hr[hr.length - 1] : null;
}
function totalSpend(d) { return (d.spend?.series || []).reduce((a, r) => a + (r.usd || 0), 0); }

// =====================================================================  1. headline
export function overview(root, d) {
  const champ = champRow(d), bs = bestSingle(d);
  root.append(h("div", { class: "view-head" }, h("p", { class: "headline", id: "headline" }, d.headline || "No results yet.")));
  const dv = champ ? deltaVsBestSingle(d, champ) : null;
  const hr = lastHitRate(d);
  const tiles = h("div", { class: "tiles" },
    h("div", { class: "tile hero" }, h("div", { class: "label" }, "Champion holdout macro-F1"),
      h("div", { class: "value" }, champ ? numLink(f3(champ.holdout_macro_f1), champ.holdout_source) : "—"),
      h("div", { class: "foot" }, champ ? champ.protocol : "no champion yet")),
    h("div", { class: "tile" }, h("div", { class: "label" }, "Δ vs best single model"),
      h("div", { class: "value " + (dv && dv.diff > 0 ? "delta-up" : dv && dv.diff < 0 ? "delta-down" : "") },
        dv ? numLink(signed(dv.diff), champ.holdout_source) : "—"),
      h("div", { class: "foot" }, bs ? `macro-F1 vs ${bs.protocol}${dv && !dv.paired ? " (point difference)" : ""}` : "no single-model holdout yet")),
    h("div", { class: "tile" }, h("div", { class: "label" }, "Spent to date"),
      h("div", { class: "value" }, usd(totalSpend(d))),
      h("div", { class: "foot" }, `${(d.experiments || []).length} experiments · ledger ${d.spend?.source || ""}`)),
    h("div", { class: "tile" }, h("div", { class: "label" }, "Experiment hit rate"),
      h("div", { class: "value" }, hr ? pct(hr.cumulative ?? hr.rate) : "—"),
      h("div", { class: "foot" }, hr ? `share of experiments whose hypothesis held, through ${hr.experiment}` : "no experiments yet")));
  root.append(tiles);

  const sc = h("div", { class: "card" });
  sc.append(h("div", { class: "card-head" }, h("h3", null, "Accuracy against cost"),
    h("span", { class: "sub" }, "every protocol; the Pareto frontier shows which are worth their price")));
  accuracyVsCost(sc, d);
  root.append(sc);
}

// =====================================================================  4. accuracy vs cost
export function accuracyVsCost(container, d) {
  const pareto = new Set(d.leaderboard?.pareto || []);
  const pts = rowsOf(d).map((r) => {
    const hold = isNum(r.holdout_macro_f1);
    return {
      id: r.protocol, x: r.usd_per_item, y: hold ? r.holdout_macro_f1 : r.dev_macro_f1, holdout: hold,
      champion: r.protocol === d.leaderboard?.champion, pareto: pareto.has(r.protocol),
      rows: [[hold ? "holdout macro-F1" : "dev macro-F1 (no holdout)", f3(hold ? r.holdout_macro_f1 : r.dev_macro_f1)],
        ["$ per item", usd(r.usd_per_item)], ["status", humanize(r.status)], ["zone", r.zone || "—"],
        ...(pareto.has(r.protocol) ? [["Pareto frontier", "yes"]] : [])],
    };
  });
  container.append(legend([
    { kind: "dot", color: "var(--series-1)", label: "holdout macro-F1" },
    { kind: "hollow", color: "var(--series-1)", label: "dev macro-F1 only (not yet on holdout)" },
    { kind: "line", color: "var(--text-secondary)", opacity: 0.55, label: "Pareto frontier" },
    { kind: "ring", color: "var(--text-primary)", label: "★ champion" },
  ]));
  scatter(container, pts);
  const det = h("details", null, h("summary", null, "Show as table"));
  det.append(sortableTable([
    { key: "protocol", label: "Protocol" },
    { key: "y", label: "macro-F1", num: true, value: (r) => (isNum(r.holdout_macro_f1) ? r.holdout_macro_f1 : r.dev_macro_f1),
      render: (r) => isNum(r.holdout_macro_f1) ? numLink(f3(r.holdout_macro_f1), r.holdout_source) : h("span", null, numLink(f3(r.dev_macro_f1), r.dev_source), h("span", { class: "muted" }, " dev")) },
    { key: "usd_per_item", label: "$ / item", num: true, render: (r) => numLink(usd(r.usd_per_item), r.dev_source) },
    { key: "pareto", label: "Pareto", value: (r) => (pareto.has(r.protocol) ? "yes" : ""), render: (r) => (pareto.has(r.protocol) ? "yes" : "") },
  ], rowsOf(d), { sortKey: "usd_per_item", dir: 1 }));
  container.append(det);
}

// =====================================================================  2. replication scorecard
export function season0(root, d) {
  root.append(h("div", { class: "view-head" }, h("h2", null, "Replication scorecard"),
    h("p", null, "Season 0: one row per paper. Each test compares the paper's protocol to its control on the same items; the bar is the paired difference in macro-F1 with its 95% CI (tick = no difference).")));
  const sc = d.season0?.scorecard || [];
  if (!sc.length) { root.append(emptyState("No Season 0 scorecard yet. It appears once experiments/season0/scorecard.json exists.")); return; }
  const max = Math.max(0.05, ...sc.flatMap((p) => (p.tests || []).flatMap((t) => [Math.abs(t.diff || 0), ...(t.ci || []).map(Math.abs)]))) * 1.1;
  const counts = {};
  sc.forEach((p) => (counts[p.verdict] = (counts[p.verdict] || 0) + 1));
  root.append(h("div", { class: "legend" }, Object.entries(counts).map(([k, n]) => h("span", { class: "key" }, badge(k), ` ${n}`))));
  const tb = h("tbody");
  for (const p of sc) {
    const tests = p.tests?.length ? p.tests : [{}];
    tests.forEach((t, i) => {
      const lbRow = rowsOf(d).find((r) => r.paper && (r.paper === p.paper || r.paper.startsWith(p.paper)));
      const proto = t.protocol || lbRow?.protocol;
      const cases = (d.cases || []).filter((c) => c.protocol === proto || (lbRow && c.protocol === lbRow.protocol)).slice(0, 3);
      const tr = h("tr");
      if (i === 0) {
        tr.append(h("td", { rowspan: tests.length, class: "wrap" },
          h("div", { class: "stack" }, h("b", null, p.paper), h("span", { class: "secondary" }, p.claim || ""),
            p.card ? fileLink("paper card", p.card) : null)));
      }
      tr.append(h("td", null, h("div", { class: "stack" }, h("span", null, proto || "—"), h("span", { class: "muted small" }, `vs ${t.control || "—"}`))));
      tr.append(h("td", null, ciCell(t.diff, t.ci, max)));
      tr.append(h("td", null, t.verdict ? badge(t.verdict) : badge(p.verdict)));
      tr.append(h("td", { class: "n" }, t.n ?? "—", h("div", { class: "muted small" }, t.split || "")));
      tr.append(h("td", { class: "n" }, usd(t.cost_usd)));
      tr.append(h("td", null, cases.length ? h("div", { class: "stack" }, cases.map((c) => replayLink(`▶ ${c.item.slice(-6)}`, c.replay))) : h("span", { class: "muted" }, "none on this machine")));
      tb.append(tr);
    });
  }
  const table = h("table", null, h("thead", null, h("tr", null,
    ["Paper and claim", "Protocol vs control", "Δ macro-F1 (95% CI)", "Verdict", "n", "Cost", "Example replays"].map((x, i) => h("th", { class: [4, 5].includes(i) ? "n" : "" }, x)))), tb);
  root.append(h("div", { class: "table-wrap" }, table));
}

// =====================================================================  3. leaderboard + 5. per-label
export function leaderboardView(root, d) {
  root.append(h("div", { class: "view-head" }, h("h2", null, "Protocol leaderboard"),
    h("p", null, "Every protocol, seed and invented. Click a column to sort. Each score links to the results file it came from.")));
  const rows = rowsOf(d);
  if (!rows.length) { root.append(emptyState("No protocols scored yet.")); return; }
  const champ = d.leaderboard?.champion;
  let filter = "all";
  const holder = h("div");
  const maxCi = Math.max(0.05, ...rows.flatMap((r) => [Math.abs(r.vs_champion?.diff || 0), ...(r.vs_champion?.ci || []).map(Math.abs)])) * 1.05;
  const draw = () => {
    clear(holder);
    const sel = rows.filter((r) => filter === "all" || (filter === "seed" ? !!r.paper : !r.paper));
    holder.append(sortableTable([
      { key: "protocol", label: "Protocol", render: (r) => h("div", { class: "stack" }, h("b", null, r.protocol), h("span", { class: "muted small" }, [r.zone, ...(r.experiments || [])].filter(Boolean).join(" · "))) },
      { key: "status", label: "Status", render: (r) => badge(r.status) },
      { key: "holdout_macro_f1", label: "Holdout macro-F1", num: true, render: (r) => numLink(f3(r.holdout_macro_f1), r.holdout_source) },
      { key: "vs_champion", label: "Δ vs previous champion (95% CI)", title: "paired holdout difference against the champion at the time of the run",
        value: (r) => r.vs_champion?.diff, render: (r) => r.vs_champion ? h("span", null, ciCell(r.vs_champion.diff, r.vs_champion.ci, maxCi)) : h("span", { class: "muted" }, r.protocol === champ ? "—" : "no holdout") },
      { key: "post_cutoff_macro_f1", label: "Post-cutoff F1", num: true, render: (r) => numLink(f3(r.post_cutoff_macro_f1), r.holdout_source) },
      { key: "ece", label: "ECE", num: true, title: "expected calibration error; lower is better", value: (r) => r.holdout_ece ?? r.dev_ece,
        render: (r) => isNum(r.holdout_ece) ? numLink(f3(r.holdout_ece), r.holdout_source) : h("span", null, numLink(f3(r.dev_ece), r.dev_source), h("span", { class: "muted small" }, " dev")) },
      { key: "dev_macro_f1", label: "Dev macro-F1", num: true, render: (r) => numLink(f3(r.dev_macro_f1), r.dev_source) },
      { key: "vs_single", label: "Δ vs best single", num: true, value: (r) => deltaVsBestSingle(d, r)?.diff,
        render: (r) => { const x = deltaVsBestSingle(d, r); if (!x) return "—"; if (x.self) return h("span", { class: "muted" }, "best single"); return x.paired ? ciCell(x.diff, x.ci, maxCi) : h("span", { title: "point difference of holdout macro-F1 (no paired CI in the result file)" }, numLink(signed(x.diff), r.holdout_source)); } },
      { key: "usd_per_item", label: "$ / item", num: true, render: (r) => numLink(usd(r.usd_per_item), r.dev_source) },
      { key: "median_latency_s", label: "Median latency", num: true, render: (r) => numLink(secs(r.median_latency_s), r.dev_source) },
      { key: "rounds", label: "Rounds", num: true, render: (r) => numLink(isNum(r.rounds) ? String(r.rounds) : "—", r.dev_source) },
      { key: "paper", label: "Paper", render: (r) => r.paper ? r.paper : h("span", { class: "muted" }, "invented") },
    ], sel, { class: "sticky-first", sortKey: "holdout_macro_f1", rowClass: (r) => (r.protocol === champ ? "is-champion" : null) }));
  };
  const seg = h("div", { class: "seg", role: "group", "aria-label": "Filter protocols" });
  for (const [k, label] of [["all", "All"], ["seed", "Seed (from a paper)"], ["invented", "Invented"]]) {
    seg.append(h("button", { type: "button", "aria-pressed": String(k === filter), onclick: (e) => {
      filter = k; seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
      e.currentTarget.setAttribute("aria-pressed", "true"); draw();
    } }, label));
  }
  root.append(h("div", { class: "filters" }, seg));
  root.append(holder);
  draw();

  // per-label heatmap
  const heat = h("div", { class: "card" });
  heat.append(h("div", { class: "card-head" }, h("h3", null, "Per-label recall"),
    h("span", { class: "sub" }, "protocol × label; holdout where available, otherwise dev (marked)")));
  perLabel(heat, d);
  root.append(heat);
}

function perLabel(container, d) {
  const rows = rowsOf(d).filter((r) => r.holdout_recall || r.dev_recall);
  if (!rows.length) return container.append(emptyState("No per-label recall yet."));
  const labels = [...new Set(rows.flatMap((r) => Object.keys(r.holdout_recall || r.dev_recall)))]
    .sort((a, b) => (LABEL_ORDER.indexOf(a) + 99 * (LABEL_ORDER.indexOf(a) < 0)) - (LABEL_ORDER.indexOf(b) + 99 * (LABEL_ORDER.indexOf(b) < 0)));
  const vals = rows.flatMap((r) => Object.values(r.holdout_recall || r.dev_recall)).filter(isNum);
  const lo = Math.max(0, Math.floor(Math.min(...vals) * 10) / 10), hi = 1;
  const tb = h("tbody");
  for (const r of rows.slice().sort((a, b) => (b.holdout_macro_f1 ?? b.dev_macro_f1 ?? 0) - (a.holdout_macro_f1 ?? a.dev_macro_f1 ?? 0))) {
    const rec = r.holdout_recall || r.dev_recall, split = r.holdout_recall ? "holdout" : "dev";
    const src = r.holdout_recall ? r.holdout_source : r.dev_source;
    const tr = h("tr", null, h("th", { class: "rowh", scope: "row" }, r.protocol, split === "dev" ? h("span", { class: "muted small" }, " · dev") : null));
    for (const l of labels) {
      const v = rec[l];
      if (!isNum(v)) { tr.append(h("td", { class: "diag" }, "—")); continue; }
      const c = seqBlue((v - lo) / (hi - lo || 1));
      const a = h("a", { href: canLinkFile(src) ? fileHref(src) : null, target: "_blank", rel: "noopener",
        style: { color: c.ink, textDecoration: "none", display: "block", padding: "7px 6px" } }, v.toFixed(2));
      const td = h("td", { class: "cell", style: { background: c.bg } }, a);
      td.addEventListener("pointermove", (ev) => showTip(ev.clientX, ev.clientY, r.protocol, [["label", humanize(l)], [`${split} recall`, f3(v)]]));
      td.addEventListener("pointerleave", hideTip);
      tr.append(td);
    }
    tb.append(tr);
  }
  const table = h("table", { class: "heat" }, h("thead", null, h("tr", null, h("th", null, "Protocol"), labels.map((l) => h("th", { class: "n" }, humanize(l))))), tb);
  container.append(h("div", { class: "table-wrap", style: { border: "0" } }, table));
  container.append(scaleLegend(seqBlue, lo, hi, (v) => v.toFixed(1)));
}

// =====================================================================  6. disagreement
export function disagreementView(root, d) {
  root.append(h("div", { class: "view-head" }, h("h2", null, "Where protocols disagree"),
    h("p", null, "Share of shared dev items on which each pair reaches different verdicts. Select a cell to list the items where they split; disagreements are where the interesting replays are.")));
  const dis = d.disagreement || {}, names = dis.protocols || [], cells = dis.cells || [];
  if (names.length < 2 || !cells.length) { root.append(emptyState("Needs dev transcripts from at least two protocols on this machine.")); return; }
  const key = (a, b) => (a < b ? `${a}|${b}` : `${b}|${a}`);
  const byKey = new Map(cells.map((c) => [key(c.a, c.b), c]));
  const rates = cells.map((c) => c.rate);
  const hi = Math.max(...rates) || 1;
  const detail = h("div", { class: "card", id: "split-detail" }, h("p", { class: "muted" }, "Select a cell to see the split items."));
  const tb = h("tbody");
  let selTd = null;
  names.forEach((a, i) => {
    const tr = h("tr", null, h("th", { class: "rowh", scope: "row" }, a));
    names.forEach((b, j) => {
      if (i === j) { tr.append(h("td", { class: "diag", title: "same protocol" }, "·")); return; }
      const c = byKey.get(key(a, b));
      if (!c) { tr.append(h("td", { class: "diag" }, "—")); return; }
      const col = seqOrange(c.rate / hi);
      const btn = h("button", { type: "button", style: { color: col.ink }, "aria-label": `${a} vs ${b}: ${pct(c.rate)} disagree` }, pct(c.rate));
      const td = h("td", { class: "cell", style: { background: col.bg } }, btn);
      btn.addEventListener("click", () => { if (selTd) selTd.classList.remove("sel"); td.classList.add("sel"); selTd = td; showSplit(detail, c); });
      td.addEventListener("pointermove", (ev) => showTip(ev.clientX, ev.clientY, `${a} vs ${b}`, [["disagree", pct(c.rate, 1)], ["shared items", c.n], ["split items", Math.round(c.rate * c.n)]]));
      td.addEventListener("pointerleave", hideTip);
      tr.append(td);
    });
    tb.append(tr);
  });
  const table = h("table", { class: "heat" }, h("thead", null, h("tr", null, h("th", null, ""), names.map((n) => h("th", { class: "n small" }, n)))), tb);
  const c = h("div", { class: "card" }, h("div", { class: "table-wrap", style: { border: "0" } }, table), scaleLegend(seqOrange, 0, hi, (v) => pct(v)));
  root.append(c, detail);
}
function showSplit(detail, c) {
  clear(detail);
  detail.append(h("div", { class: "card-head" }, h("h3", null, `${c.a} vs ${c.b}`),
    h("span", { class: "sub" }, `${pct(c.rate, 1)} of ${c.n} shared dev items split · `,
      fileLink(c.experiments[0], resultsPath(c.experiments[0])), " vs ", fileLink(c.experiments[1], resultsPath(c.experiments[1])))));
  const items = c.split_items || [];
  if (!items.length) { detail.append(emptyState("No split items.")); return; }
  const q = new Map((state.data.cases || []).map((x) => [`${x.experiment}/${x.item}`, x]));
  detail.append(sortableTable([
    { key: "item", label: "Item", render: (it) => h("code", null, it) },
    { key: "r", label: "Replays", sortable: false, render: (it) => h("span", { class: "links", style: { marginTop: 0 } },
      replayLink(`▶ ${c.a}`, c.experiments[0], it), replayLink(`▶ ${c.b}`, c.experiments[1], it)) },
    { key: "va", label: c.a, render: (it) => humanize(q.get(`${c.experiments[0]}/${it}`)?.verdict || "") || "—" },
    { key: "vb", label: c.b, render: (it) => humanize(q.get(`${c.experiments[1]}/${it}`)?.verdict || "") || "—" },
    { key: "gold", label: "Gold", render: (it) => humanize((q.get(`${c.experiments[0]}/${it}`) || q.get(`${c.experiments[1]}/${it}`))?.gold || "") || "—" },
    { key: "q", label: "Question", cls: "wrap", value: (it) => q.get(`${c.experiments[0]}/${it}`)?.question || "",
      render: (it) => q.get(`${c.experiments[0]}/${it}`)?.question || q.get(`${c.experiments[1]}/${it}`)?.question || h("span", { class: "muted" }, "—") },
  ], items, {}));
  detail.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// =====================================================================  7. trends
export function trendsView(root, d) {
  root.append(h("div", { class: "view-head" }, h("h2", null, "Trends"),
    h("p", null, "Each score over experiments, in run order. Scores are never blended; every chart has its own axis.")));
  root.append(sixScores(d));
  const rows = d.trends?.rows || [];
  const xs = rows.map((r) => r.experiment);
  const col = (k) => rows.map((r) => (isNum(r[k]) ? r[k] : null));
  const grid = h("div", { class: "grid mult" });
  const mk = (title, sub, fn) => { const c = h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", null, title), sub ? h("span", { class: "sub" }, sub) : null)); fn(c); grid.append(c); };
  if (!rows.length) root.append(emptyState("No experiments yet."));
  else {
    mk("Macro-F1 per experiment", null, (c) => {
      c.append(legend([{ color: "var(--series-1)", label: "dev" }, { color: "var(--series-2)", label: "holdout" }]));
      lineChart(c, xs, [{ name: "dev", color: "var(--series-1)", values: col("dev_macro_f1") }, { name: "holdout", color: "var(--series-2)", values: col("holdout_macro_f1") }]);
    });
    mk("Champion holdout macro-F1", "after each experiment", (c) => lineChart(c, xs, [{ name: "champion", color: "var(--series-1)", values: col("champion_macro_f1") }]));
    mk("Calibration (ECE)", "lower is better", (c) => lineChart(c, xs, [{ name: "ECE", color: "var(--series-1)", values: col("ece") }], { zeroBased: true }));
    mk("Cost per item", "uncached $ per dev item", (c) => lineChart(c, xs, [{ name: "$ / item", color: "var(--series-1)", values: col("usd_per_item") }], { yFmt: usd, zeroBased: true }));
    mk("Experiment hit rate", "cumulative share of hypotheses that held", (c) => {
      const hr = new Map((d.hit_rate || []).map((x) => [x.experiment, x]));
      lineChart(c, xs, [{ name: "hit rate", color: "var(--series-1)", values: xs.map((x) => hr.get(x)?.cumulative ?? hr.get(x)?.rate ?? null) }], { yFmt: (v) => pct(v), yMin: 0, yMax: 1 });
    });
  }
  const sp = d.spend?.series || [];
  mk("Cumulative spend", `from ${d.spend?.source || "the spend ledger"}`, (c) => lineChart(c, sp.map((r) => r.date), [{ name: "cumulative", color: "var(--series-1)", values: sp.map((r) => r.cumulative) }], { yFmt: usd, zeroBased: true }));
  // Track B over time
  const posts = (d.social?.posts || []).filter((p) => p.scores && Object.keys(p.scores).length).sort((a, b) => String(a.ts).localeCompare(String(b.ts)));
  if (posts.length) {
    const px = posts.map((p) => String(p.ts || "").slice(0, 10));
    mk("X poll score", "Wilson lower bound of “Yes, and convincing” (raw, unweighted)", (c) => lineChart(c, px, [{ name: "poll", color: "var(--series-1)", values: posts.map((p) => p.scores.poll?.score ?? null) }], { yMin: 0, yMax: 1 }));
    mk("Weighted rater score", "weighted by rater reliability", (c) => lineChart(c, px, [{ name: "weighted", color: "var(--series-1)", values: posts.map((p) => p.scores.weighted?.score ?? null) }], { yMin: 0, yMax: 1 }));
    mk("Social index", "1.0 = typical engagement for the account", (c) => lineChart(c, px, [{ name: "social index", color: "var(--series-1)", values: posts.map((p) => p.scores.social_index ?? null) }], { yFmt: f2, zeroBased: true }));
  }
  root.append(grid);
}

function sixScores(d) {
  const rows = d.trends?.rows || [];
  const posts = d.social?.posts || [];
  const rat = d.ratings;
  const readability = rows.filter((r) => isNum(r.readability) || isNum(r.glanceability)).length
    + (d.experiments || []).filter((e) => isNum(e.readability) || isNum(e.glanceability)).length;
  const fam = [
    ["1 · Accuracy", "Track A", rows.filter((r) => isNum(r.dev_macro_f1) || isNum(r.holdout_macro_f1)).length, "experiments scored"],
    ["2 · Cost to iterate", "Track A", rows.filter((r) => isNum(r.usd_per_item)).length, "experiments costed"],
    ["3 · Readability and glanceability", "Track B", readability, "scored runs"],
    ["4 · Human dashboard rating", "Track B", rat ? rat.n : null, "thumbs"],
    ["5 · X poll score", "Track B", posts.filter((p) => p.scores?.poll).length, "posts with polls"],
    ["6 · Social score", "Track B", posts.filter((p) => isNum(p.scores?.social_index)).length, "posts measured"],
  ];
  const c = h("div", { class: "card" }, h("div", { class: "card-head" }, h("h3", null, "The six scores"), h("span", { class: "sub" }, "what has data so far")));
  const g = h("div", { class: "tiles six" });
  for (const [name, track, n, unit] of fam) {
    const has = isNum(n) && n > 0;
    g.append(h("div", { class: "tile" }, h("div", { class: "label" }, name),
      h("div", { class: "value", style: { fontSize: "20px" } }, has ? `${n} ${n === 1 ? unit.replace(/^(\w+?)s\b/, "$1") : unit}` : n === null ? "local only" : "no data yet"),
      h("div", { class: "foot" }, track)));
  }
  c.append(g);
  return c;
}

// =====================================================================  8. experiments
export function experimentsView(root, d) {
  root.append(h("div", { class: "view-head" }, h("h2", null, "Experiments"),
    h("p", null, "Each proposal, its hypothesis, the learnings it cited, its result and the reason for its status.")));
  const ex = (d.experiments || []).slice().reverse();
  if (!ex.length) { root.append(emptyState("No experiments yet.")); return; }
  const max = Math.max(0.05, ...ex.flatMap((e) => [Math.abs(e.vs_champion?.diff || 0), ...(e.vs_champion?.ci || []).map(Math.abs)])) * 1.05;
  const list = h("div", { class: "list" });
  for (const e of ex) {
    const it = h("div", { class: "item", id: `exp-${e.experiment}` },
      h("div", { class: "item-head" }, h("span", { class: "id" }, e.experiment), h("span", null, e.protocol), badge(e.status),
        e.zone ? h("span", { class: "tag" }, e.zone) : null, e.paper ? h("span", { class: "tag" }, e.paper) : null,
        h("span", { class: "right muted small" }, when(e.created))),
      e.hypothesis ? h("div", { class: "body" }, h("b", { class: "secondary" }, "Hypothesis: "), e.hypothesis) : null,
      e.reason ? h("div", { class: "body" }, h("b", { class: "secondary" }, "Result: "), e.reason) : null,
      h("div", { class: "metrics" },
        h("span", null, "dev macro-F1 ", h("b", null, numLink(f3(e.dev_macro_f1), e.source)), e.dev_n ? ` (n=${e.dev_n})` : ""),
        h("span", null, "holdout ", h("b", null, numLink(f3(e.holdout_macro_f1), e.source))),
        h("span", null, "ECE ", h("b", null, numLink(f3(e.ece), e.source))),
        h("span", null, "$/item ", h("b", null, numLink(usd(e.usd_per_item), e.source))),
        h("span", null, "total ", h("b", null, numLink(usd(e.usd_total), e.source))),
        e.vs_champion ? h("span", null, "Δ vs champion ", ciCell(e.vs_champion.diff, e.vs_champion.ci, max), " ", badge(e.vs_champion.verdict)) : null),
      h("div", { class: "links" },
        (e.builds_on || []).length ? h("span", { class: "muted" }, "cites ", (e.builds_on || []).map((l, i) => [i ? ", " : "", h("a", { href: `#learnings`, onclick: () => setTimeout(() => document.getElementById(`learn-${l}`)?.scrollIntoView({ block: "center" }), 50) }, l)])) : h("span", { class: "muted" }, "cites no learnings"),
        fileLink("results.json", e.source),
        (e.cases || []).slice(0, 6).map((c) => replayLink(`▶ ${c.item.slice(-6)}${c.why?.length ? ` · ${c.why.join(", ")}` : ""}`, e.experiment, c.item))));
    list.append(it);
  }
  root.append(list);
}

// =====================================================================  9. cases
export function casesView(root, d) {
  root.append(h("div", { class: "view-head" }, h("h2", null, "Cases"),
    h("p", null, state.local ? "Dev-split replays. Rate a replay with thumbs up or down; ratings are stored locally in ratings.jsonl." : "Dev-split replays.")));
  const cases = d.cases || [];
  if (!cases.length) { root.append(emptyState("No dev transcripts on this machine yet.")); return; }
  const ratings = new Map(((d.ratings || {}).cases || []).map((r) => [`${r.experiment}/${r.item}`, r]));
  const uniq = (k) => [...new Set(cases.map((c) => c[k]).filter(Boolean))].sort();
  const whys = [...new Set(cases.flatMap((c) => c.why || []))].sort();
  const f = { protocol: "", gold: "", outcome: "", dis: "", why: "", q: "" };
  const sel = (name, label, opts) => h("label", { class: "field" }, h("span", null, label),
    h("select", { name, onchange: (e) => { f[name] = e.target.value; page = 1; draw(); } }, h("option", { value: "" }, "All"), opts.map(([v, t]) => h("option", { value: v }, t))));
  const filters = h("div", { class: "filters" },
    sel("protocol", "Protocol", uniq("protocol").map((v) => [v, v])),
    sel("gold", "Gold label", uniq("gold").map((v) => [v, humanize(v)])),
    sel("outcome", "Outcome", [["correct", "Correct"], ["wrong", "Wrong"]]),
    sel("dis", "Disagreement", [["yes", "Panel split (agreement < 0.6)"], ["no", "Agreed"]]),
    sel("why", "Why selected", whys.map((v) => [v, v])),
    h("label", { class: "field" }, h("span", null, "Search"), h("input", { type: "search", placeholder: "question text or item id", oninput: (e) => { f.q = e.target.value.toLowerCase(); page = 1; draw(); } })));
  const count = h("p", { class: "muted small" });
  const list = h("div", { class: "list case-grid", id: "case-list" });
  const more = h("button", { type: "button", onclick: () => { page++; draw(); } }, "Show more");
  let page = 1;
  const PER = 30;
  function draw() {
    const sel = cases.filter((c) => (!f.protocol || c.protocol === f.protocol) && (!f.gold || c.gold === f.gold)
      && (!f.outcome || (f.outcome === "correct" ? c.correct === true : c.correct === false))
      && (!f.dis || (f.dis === "yes" ? isNum(c.min_agreement) && c.min_agreement < 0.6 : !(isNum(c.min_agreement) && c.min_agreement < 0.6)))
      && (!f.why || (c.why || []).includes(f.why))
      && (!f.q || c.question.toLowerCase().includes(f.q) || c.item.includes(f.q)));
    clear(list);
    count.textContent = `${sel.length} of ${cases.length} cases`;
    for (const c of sel.slice(0, page * PER)) list.append(caseItem(c, ratings.get(`${c.experiment}/${c.item}`)));
    more.style.display = sel.length > page * PER ? "" : "none";
  }
  root.append(filters, count, list, more);
  draw();
}

function caseItem(c, rating) {
  const outcome = c.correct === true ? h("span", { class: "badge good" }, h("span", { class: "ico", "aria-hidden": "true" }, "✓"), "correct")
    : c.correct === false ? h("span", { class: "badge bad" }, h("span", { class: "ico", "aria-hidden": "true" }, "✕"), "wrong") : null;
  const split = isNum(c.min_agreement) && c.min_agreement < 0.6;
  const it = h("div", { class: "item case", dataset: { exp: c.experiment, item: c.item } },
    h("div", { class: "item-head" }, h("span", { class: "case-q" }, c.question)),
    h("div", { class: "metrics" },
      h("span", null, "verdict ", h("b", null, humanize(c.verdict))),
      h("span", null, "gold ", h("b", null, humanize(c.gold) || "—")), outcome,
      h("span", null, "confidence ", h("b", null, pct(c.confidence))),
      isNum(c.min_agreement) ? h("span", null, "min agreement ", h("b", null, f2(c.min_agreement)), split ? " · split" : "") : null),
    h("div", { class: "links" },
      replayLink("▶ Replay", c.replay),
      h("span", { class: "muted" }, c.protocol), fileLink(c.experiment, resultsPath(c.experiment)),
      h("code", { class: "muted" }, c.item),
      (c.why || []).map((w) => h("span", { class: "tag" }, w))));
  const agg = h("span", { class: "muted small rating-agg" });
  const setAgg = (r) => { agg.textContent = r && r.up + r.down ? `👍 ${r.up} · 👎 ${r.down}${isNum(r.wilson) ? ` · Wilson ${f2(r.wilson)}` : ""}` : ""; };
  setAgg(rating);
  if (state.local) {
    const note = h("input", { type: "text", maxlength: 500, placeholder: "Optional note (what was good or wrong?)", "aria-label": "note" });
    const msg = h("span", { class: "muted small", role: "status" });
    const rate = async (thumb, btn) => {
      btn.disabled = true;
      const r = await post("/api/rate", { experiment: c.experiment, item: c.item, protocol: c.protocol, thumb, note: note.value });
      btn.disabled = false;
      if (r.ok) {
        msg.textContent = "Saved ✓";
        it.querySelectorAll(".thumbs button").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
        const cur = rating || { up: 0, down: 0 };
        rating = { ...cur, [thumb]: (cur[thumb] || 0) + 1, wilson: null };
        setAgg(rating);
        note.value = "";
      } else msg.textContent = `Not saved: ${r.json?.error || r.status}`;
    };
    const up = h("button", { type: "button", class: "thumb-up", "aria-pressed": "false", title: "Thumbs up", "aria-label": "Thumbs up" }, "👍");
    const down = h("button", { type: "button", class: "thumb-down", "aria-pressed": "false", title: "Thumbs down", "aria-label": "Thumbs down" }, "👎");
    up.addEventListener("click", () => rate("up", up));
    down.addEventListener("click", () => rate("down", down));
    it.append(h("div", { class: "rate-note local-only" }, h("span", { class: "thumbs" }, up, down), note), h("div", { class: "actions", style: { marginTop: "4px" } }, agg, msg));
  } else if (rating) it.append(h("div", { class: "actions" }, agg));
  return it;
}

// =====================================================================  10. raters & social
export function socialView(root, d) {
  root.append(h("div", { class: "view-head" }, h("h2", null, "Raters and social"),
    h("p", null, "Posts with their poll totals, weighted rater score and social index. Rater identities are never shown.")));
  const so = d.social || {};
  const posts = so.posts || [];
  if (!posts.length) root.append(emptyState("No posts yet."));
  else root.append(sortableTable([
    { key: "ts", label: "Posted", render: (p) => when(p.ts) },
    { key: "text", label: "Post", cls: "wrap", render: (p) => h("div", { class: "stack" }, p.text || "", h("span", { class: "muted small" }, p.kind || "",
      p.experiment && p.item ? [" · ", replayLink("▶ replay", p.experiment, p.item)] : null)) },
    { key: "poll_n", label: "Poll votes", num: true, value: (p) => p.scores?.poll?.n, render: (p) => numLink(p.scores?.poll?.n ?? "—", p.result_file) },
    { key: "poll", label: "Poll score", num: true, value: (p) => p.scores?.poll?.score, render: (p) => f2(p.scores?.poll?.score) },
    { key: "wrong", label: "“Wrong” share", num: true, value: (p) => p.scores?.poll?.wrong_share, render: (p) => pct(p.scores?.poll?.wrong_share) },
    { key: "w", label: "Weighted rater score", num: true, value: (p) => p.scores?.weighted?.score, render: (p) => f2(p.scores?.weighted?.score) },
    { key: "neff", label: "n_eff", num: true, value: (p) => p.scores?.weighted?.n_eff, render: (p) => isNum(p.scores?.weighted?.n_eff) ? p.scores.weighted.n_eff.toFixed(1) : "—" },
    { key: "si", label: "Social index", num: true, value: (p) => p.scores?.social_index, render: (p) => f2(p.scores?.social_index) },
    { key: "er", label: "Engagement", num: true, value: (p) => p.scores?.engagement_rate, render: (p) => pct(p.scores?.engagement_rate, 1) },
  ], posts, { sortKey: "ts" }));
  const g = h("div", { class: "grid two" });
  const th = Object.entries(so.feedback_themes || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: k, value: v }));
  const fc = card("Feedback themes", `${so.n_feedback || 0} replies classified`);
  hbars(fc, th);
  g.append(fc);
  const rc = card("Rater reliability", "distribution only; no identities");
  const rel = raterDist(so.raters || {});
  if (rel.length) hbars(rc, rel); else rc.append(emptyState("No rater reliability data yet."));
  if (isNum(so.raters?.n)) rc.append(h("p", { class: "muted small" }, `${so.raters.n} raters`));
  g.append(rc);
  if (d.ratings) {
    const hr = card("Dashboard ratings", `${d.ratings.n} thumbs from this machine`);
    const rs = (d.ratings.cases || []).slice().sort((a, b) => (b.wilson ?? 0) - (a.wilson ?? 0));
    if (!rs.length) hr.append(emptyState("No thumbs yet. Rate replays in Cases."));
    else hr.append(sortableTable([
      { key: "item", label: "Case", render: (r) => replayLink(`${r.experiment}/${r.item.slice(-6)}`, r.experiment, r.item) },
      { key: "protocol", label: "Protocol" },
      { key: "up", label: "Up", num: true }, { key: "down", label: "Down", num: true },
      { key: "wilson", label: "Wilson lower", num: true, render: (r) => f2(r.wilson) },
    ], rs, { sortKey: "wilson" }));
    g.append(hr);
  }
  root.append(g);
}
/** Accepts {reliability:[numbers]} | {histogram:[{bin,count}]} | {bins:{label:count}} — aggregate only. */
function raterDist(r) {
  if (Array.isArray(r.histogram)) return r.histogram.map((b) => ({ label: String(b.bin ?? b.label), value: b.count ?? b.n ?? 0 }));
  if (r.bins && typeof r.bins === "object") return Object.entries(r.bins).map(([k, v]) => ({ label: k, value: v }));
  const vals = (r.reliability || r.reliabilities || []).filter(isNum);
  if (!vals.length) return [];
  const bins = [0, 0.2, 0.4, 0.6, 0.8, 1.0001];
  return bins.slice(0, -1).map((lo, i) => ({ label: `${lo.toFixed(1)}–${Math.min(1, bins[i + 1]).toFixed(1)}`, value: vals.filter((v) => v >= lo && v < bins[i + 1]).length }));
}

// =====================================================================  11. learnings
export function learningsView(root, d) {
  root.append(h("div", { class: "view-head" }, h("h2", null, "Learnings"),
    h("p", null, "What the lab has learned, grouped by how well it is supported. ", fileLink("LEARNINGS.md", "LEARNINGS.md"))));
  const ls = d.learnings || [];
  if (!ls.length) { root.append(emptyState("No learnings yet.")); return; }
  const max = Math.max(0.05, ...ls.flatMap((l) => (l.ci || []).map(Math.abs))) * 1.05;
  const cols = h("div", { class: "lead-cols" });
  for (const st of ["confirmed", "tentative", "refuted"]) {
    const sel = ls.filter((l) => l.status === st);
    const col = h("div", { class: "list" }, h("div", { class: "item-head" }, badge(st), h("span", { class: "muted" }, `${sel.length}`)));
    if (!sel.length) col.append(emptyState(`No ${st} learnings.`));
    for (const l of sel.slice().reverse()) {
      const eff = typeof l.effect === "string" ? l.effect : isNum(l.effect) ? signed(l.effect) : null;
      const m = eff && eff.match(/[-+−]?\d*\.\d+/);
      col.append(h("div", { class: "item", id: `learn-${l.id}` },
        h("div", { class: "item-head" }, h("span", { class: "id" }, l.id), l.zone ? h("span", { class: "tag" }, l.zone) : null, h("span", { class: "tag" }, `Track ${l.track || "A"}`), h("span", { class: "right muted small" }, l.date || "")),
        h("div", { class: "body" }, l.lesson || l.hypothesis || ""),
        h("div", { class: "metrics" },
          eff ? h("span", null, "effect ", h("b", null, eff)) : null,
          l.ci ? ciCell(m ? parseFloat(m[0].replace("−", "-")) : (l.ci[0] + l.ci[1]) / 2, l.ci, max) : null),
        h("div", { class: "links" }, (l.experiments || []).map((e) => fileLink(e, resultsPath(e))),
          (l.builds_on || []).length ? h("span", { class: "muted" }, `builds on ${l.builds_on.join(", ")}`) : null),
        l.next ? h("div", { class: "body small" }, "Next: ", l.next) : null));
    }
    cols.append(col);
  }
  root.append(cols);
}

// =====================================================================  12. budget
export function budgetView(root, d) {
  root.append(h("div", { class: "view-head" }, h("h2", null, "Budget"),
    h("p", null, "Spend against the caps in config/budget.yaml. Controls can't change caps. Ledger: ", h("code", null, d.spend?.source || "ops/spend.jsonl"))));
  const t = d.spend?.totals || {}, caps = d.spend?.caps || {};
  const c = card("Spend against caps", null);
  const rows = [
    ["Lab today", t["lab.day"], caps["lab.day"]], ["Lab this week", t["lab.week"], null, "no weekly cap"],
    ["Lab this month", t["lab.month"], caps["lab.month"]], ["Season 0 screening", t["season0"], caps["season0"]],
    ["Social today", t["social.day"], caps["social.day"]], ["Social this month", t["social.month"], caps["social.month"]],
  ];
  for (const [label, spent, cap, nocap] of rows) c.append(meterRow(label, spent || 0, cap, nocap));
  const tiles = h("div", { class: "tiles" },
    h("div", { class: "tile" }, h("div", { class: "label" }, "Holdout evaluations left this week"),
      h("div", { class: "value" }, isNum(d.holdout_evals_left) ? String(d.holdout_evals_left) : "—"),
      h("div", { class: "foot" }, "each arena submission uses one")),
    h("div", { class: "tile" }, h("div", { class: "label" }, "Total spent"), h("div", { class: "value" }, usd(totalSpend(d))),
      h("div", { class: "foot" }, `${(d.spend?.series || []).length} day${(d.spend?.series || []).length === 1 ? "" : "s"} with spend`)));
  root.append(tiles, c);
}
export function meterRow(label, spent, cap, nocap) {
  const has = isNum(cap) && cap > 0;
  const frac = has ? spent / cap : 0;
  const cls = !has ? "unset" : frac >= 0.9 ? "danger" : frac >= 0.7 ? "warn" : "";
  return h("div", { class: "meter-row" },
    h("span", { class: "secondary" }, label),
    h("div", { class: `meter ${cls}`, role: "meter", "aria-valuemin": 0, "aria-valuemax": has ? cap : 0, "aria-valuenow": spent, "aria-label": label },
      has ? h("i", { style: { width: `${Math.min(100, frac * 100)}%` } }) : null),
    h("span", { class: "num-col", style: { textAlign: "left" } }, usd(spent), has ? h("span", { class: "muted" }, ` of ${usd(cap)}${frac >= 0.9 ? " ⚠" : ""}`) : h("span", { class: "muted" }, nocap ? ` · ${nocap}` : " · cap not set")));
}

// =====================================================================  13. zones
export function zonesView(root, d, { onRun } = {}) {
  root.append(h("div", { class: "view-head" }, h("h2", null, "Zones"),
    h("p", null, "Each zone is a family of techniques refined against its control and against Z1 (single model). Open a zone for its sub-techniques, knobs, leaderboard and cases.")));
  const zs = d.zones || [];
  if (!zs.length) { root.append(emptyState("No zones defined.")); return; }
  const grid = h("div", { class: "grid three" });
  const detail = h("div", { id: "zone-detail" });
  let open = null;
  for (const z of zs) {
    const b = z.board || {};
    const vc = b.vs_control?.raw, vz = b.vs_z1?.raw;
    const btn = h("button", { type: "button", class: "zone-tile", "aria-expanded": "false", "aria-controls": "zone-detail" },
      h("div", { class: "zid" }, z.zone), h("div", { class: "zname" }, z.name),
      h("div", { class: "best" }, b.best ? [h("b", null, b.best.protocol), ` · dev macro-F1 ${f3(b.best.dev_macro_f1)}`] : "no runs yet"),
      h("div", { class: "zstats" },
        h("div", null, h("span", null, `vs control${vc ? ` (${vc.control})` : ""}`), h("b", { class: deltaCls(vc?.diff) }, vc ? signed(vc.diff) : z.zone === "Z1" ? "is the control" : "—")),
        h("div", null, h("span", null, "vs Z1"), h("b", { class: deltaCls(vz?.diff) }, vz ? signed(vz.diff) : "—")),
        h("div", null, h("span", null, "$ / item"), h("b", null, usd(b.best?.usd_per_item))),
        h("div", null, h("span", null, "iterations · spend"), h("b", null, `${b.iterations ?? 0} · ${usd(b.spend_usd ?? 0)}`))));
    btn.addEventListener("click", () => {
      grid.querySelectorAll(".zone-tile").forEach((x) => x.setAttribute("aria-expanded", "false"));
      if (open === z.zone) { open = null; clear(detail); return; }
      open = z.zone; btn.setAttribute("aria-expanded", "true");
      zoneDetail(detail, z, d, onRun);
      detail.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    grid.append(btn);
  }
  root.append(grid, detail);
}
const deltaCls = (v) => (isNum(v) ? (v > 0 ? "delta-up" : v < 0 ? "delta-down" : "") : "");

function zoneDetail(el, z, d, onRun) {
  clear(el);
  const b = z.board || {};
  const c = h("div", { class: "card" });
  c.append(h("div", { class: "card-head" }, h("h3", null, `${z.zone} · ${z.name}`),
    h("span", { class: "sub" }, controlText(z.control)),
    h("span", { class: "right" }, fileLink("ZONE.md", z.doc), state.local && onRun ? [" ", h("button", { type: "button", onclick: () => onRun(z.zone) }, "Run in this zone…")] : null)));
  const cmp = h("div", { class: "grid two" });
  for (const [title, v] of [["Against its control", b.vs_control], ["Against Z1 (best single model)", b.vs_z1]]) {
    cmp.append(h("div", null, h("h4", null, title), v ? h("dl", { class: "kv" },
      h("dt", null, "reference"), h("dd", null, `${v.raw?.control} (dev macro-F1 ${f3(v.raw?.control_f1)})`),
      h("dt", null, "Δ raw"), h("dd", { class: deltaCls(v.raw?.diff) }, signed(v.raw?.diff)),
      h("dt", null, "cost ratio"), h("dd", null, isNum(v.raw?.cost_ratio) ? `${v.raw.cost_ratio.toFixed(1)}×` : "—"),
      h("dt", null, "Δ at matched cost"), h("dd", { class: deltaCls(v.matched_cost?.diff) }, signed(v.matched_cost?.diff), v.matched_cost?.control && v.matched_cost.control !== v.raw?.control ? ` vs ${v.matched_cost.control}` : ""))
      : h("p", { class: "muted" }, "not available")));
  }
  c.append(cmp);
  c.append(h("div", null, h("h4", null, "Sub-techniques"), h("div", { class: "links" }, Object.entries(z.subs || {}).map(([k, v]) => h("span", { class: "tag", title: v }, k)))));
  const knobs = Object.entries(z.knobs || {});
  c.append(h("div", null, h("h4", null, "Knobs"), sortableTable([
    { key: "name", label: "Knob", value: (r) => r[0], render: (r) => h("b", null, r[0]) },
    { key: "range", label: "Allowed values", sortable: false, cls: "wrap", render: (r) => knobRange(r[1]) },
    { key: "path", label: "Path", sortable: false, render: (r) => h("code", { class: "muted" }, r[1].path) },
  ], knobs, {})));
  c.append(h("div", null, h("h4", null, "Zone leaderboard (dev)"), sortableTable([
    { key: "protocol", label: "Protocol" },
    { key: "dev_macro_f1", label: "Dev macro-F1", num: true, render: (r) => numLink(f3(r.dev_macro_f1), r.source) },
    { key: "usd_per_item", label: "$ / item", num: true, render: (r) => numLink(usd(r.usd_per_item), r.source) },
    { key: "experiment", label: "Experiment", render: (r) => fileLink(r.experiment, r.source) },
    { key: "status", label: "Status", render: (r) => badge(r.status) },
  ], b.rows || [], { sortKey: "dev_macro_f1", empty: "No runs in this zone yet." })));
  const exps = new Set((b.rows || []).map((r) => r.experiment));
  const ls = (d.learnings || []).filter((l) => l.zone === z.zone);
  c.append(h("div", null, h("h4", null, "Learnings"), ls.length ? h("ul", null, ls.map((l) => h("li", null, h("b", null, l.id), " ", badge(l.status), " ", l.lesson))) : h("p", { class: "muted" }, "None yet.")));
  const cs = (d.cases || []).filter((x) => exps.has(x.experiment) && (x.why || []).length).slice(0, 8);
  c.append(h("div", null, h("h4", null, "Interesting cases"), cs.length ? h("div", { class: "links" }, cs.map((x) => replayLink(`▶ ${x.protocol} · ${x.item.slice(-6)} · ${x.why.join(", ")}`, x.replay))) : h("p", { class: "muted" }, "None yet.")));
  el.append(c);
}
function controlText(c) {
  if (!c) return "no control (this zone is the baseline)";
  if (typeof c === "string") return `control: ${c}`;
  const who = c.protocol ? c.protocol : c.zone_best ? `best of ${c.zone_best}` : JSON.stringify(c);
  return `control: ${who}${c.matched_cost ? ", compared at matched cost" : ""}`;
}
export function knobRange(k) {
  if (k.free_text) return "free text";
  if (k.values) return k.values.map(String).join(" · ");
  if (k.range) return `${k.range[0]} – ${k.range[1]}${k.int ? " (integer)" : ""}`;
  if (k.count) return `${k.count[0]}–${k.count[1]} agents${k.models ? ` from ${k.models.join(", ")}` : ""}`;
  return JSON.stringify(k);
}
