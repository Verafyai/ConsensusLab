// Lab controls (spec §8.3), local server only. Every action is a two-step: review the
// server's estimate or warning, then an explicit confirm. The server re-checks every cap.
import { h, clear, isNum, f3, signed, pct, usd, humanize, when, badge, card, post, replayLink, fileLink, resultsPath, sortableTable, emptyState } from "./util.js";
import { ciCell } from "./charts.js";
import { knobRange } from "./views.js";

let runForm = null;

export function controlsView(root, d) {
  root.append(h("div", { class: "view-head" }, h("h2", null, "Lab controls"),
    h("p", null, "Controls only add jobs to the orchestrator's queue; it re-checks every cap before running. They can't change budget caps, the holdout, labels, scoring or the clearance policy.")));
  const jobs = card("Jobs and health", "refreshes every 5 seconds");
  jobs.id = "jobs-panel";
  const jobsBody = h("div", { id: "jobs-body" }, h("p", { class: "muted" }, "Loading status…"));
  jobs.append(jobsBody);
  root.append(jobs);
  const g = h("div", { class: "grid two" });
  g.append(runCard(d), compareCard(d), refineCard(d), arenaCard(d));
  root.append(g);
  if (lastStatus) renderStatus(jobsBody, lastStatus);
  startStatus();
}

export function openRun(zone) {
  location.hash = "#controls";
  setTimeout(() => { if (runForm) { runForm.setZone(zone); runForm.el.scrollIntoView({ behavior: "smooth", block: "start" }); } }, 60);
}

// ------------------------------------------------------------------ status polling
let pollTimer = null, lastStatus = null;
export function startStatus() {
  const tick = async () => {
    const el = document.getElementById("jobs-body");
    try {
      const r = await fetch("/api/status", { cache: "no-store" });
      const j = await r.json();
      lastStatus = j;
      if (el) renderStatus(el, j);
      const comps = Object.values(j.health || {});
      const ok = comps.every((c) => c.ok);
      const hd = document.getElementById("health");
      if (hd) hd.replaceChildren(h("span", { class: `dot ${comps.length ? (ok ? "ok" : "bad") : ""}`, "aria-hidden": "true" }),
        comps.length ? (ok ? "lab healthy ✓" : "lab unhealthy ✕") : "no heartbeat");
    } catch (e) {
      if (el) clear(el).append(h("div", { class: "notice bad" }, `Status unavailable: ${e.message}`));
      const hd = document.getElementById("health");
      if (hd) hd.replaceChildren(h("span", { class: "dot bad", "aria-hidden": "true" }), "server unreachable ✕");
    }
  };
  tick();
  clearInterval(pollTimer);
  pollTimer = setInterval(tick, 5000);
  return tick;
}
function renderStatus(el, j) {
  clear(el);
  const comps = Object.entries(j.health || {});
  el.append(h("div", { class: "links", style: { marginTop: 0 } }, comps.length ? comps.map(([name, c]) =>
    h("span", { class: "health", title: c.why || "" }, h("span", { class: `dot ${c.ok ? "ok" : "bad"}`, "aria-hidden": "true" }),
      h("b", null, name), ` ${c.ok ? "✓" : "✕"} ${humanize(c.state)}`, h("span", { class: "muted" }, isNum(c.age_s) ? ` · ${Math.round(c.age_s)} s ago` : ""), c.why ? h("span", { class: "muted" }, ` · ${c.why}`) : null))
    : h("span", { class: "muted" }, "No heartbeat recorded.")));
  const jobs = (j.jobs || []).slice().reverse();
  if (!jobs.length) { el.append(h("p", { class: "muted small" }, "No jobs queued.")); return; }
  const list = h("div", { class: "jobs" });
  for (const jb of jobs) {
    const p = jb.params || {};
    const what = jb.type === "run" ? `${p.protocol?.id || "protocol"} · n=${p.n ?? "?"}` : jb.type === "refine" ? `${p.zone} · ${p.iterations} iterations · ${usd(p.budget)}`
      : jb.type === "arena" ? `${p.experiment}` : JSON.stringify(p).slice(0, 80);
    list.append(h("div", { class: "job" }, badge(jb.state), h("b", null, jb.type), h("span", null, what),
      isNum(jb.estimate_usd) ? h("span", { class: "muted" }, `est. ${usd(jb.estimate_usd)}`) : null,
      jb.progress ? h("span", { class: "muted" }, typeof jb.progress === "object" ? JSON.stringify(jb.progress) : String(jb.progress)) : null,
      jb.error ? h("span", { class: "delta-down" }, jb.error) : null,
      h("span", { class: "muted small", style: { marginLeft: "auto" } }, `${jb.id} · ${when(jb.created)}`)));
  }
  el.append(list);
}

// ------------------------------------------------------------------ run an experiment
function runCard(d) {
  const zones = d.zones || [];
  const c = card("Run an experiment", "zone → sub-technique → knobs → estimate → confirm");
  c.id = "run-card";
  if (!zones.length) { c.append(emptyState("No zones defined.")); return c; }
  const zoneSel = h("select", { name: "zone" }, zones.map((z) => h("option", { value: z.zone }, `${z.zone} · ${z.name}`)));
  const subSel = h("select", { name: "sub" });
  const knobBox = h("div", { class: "form-grid" });
  const maxDev = d.dev_items || Math.max(0, ...(d.experiments || []).map((e) => e.dev_n || 0));
  let nMode = "screen";
  const nCustom = h("input", { type: "number", min: 1, step: 1, value: 100, name: "n", disabled: true, style: { width: "100px" } });
  const nSeg = h("div", { class: "seg", role: "group", "aria-label": "Item set" });
  const nOpts = [["screen", "100-item screen"], ["full", maxDev ? `Full dev (${maxDev})` : "Full dev"], ["custom", "Custom"]];
  for (const [k, label] of nOpts) nSeg.append(h("button", { type: "button", "aria-pressed": String(k === nMode), onclick: (e) => {
    nMode = k; nSeg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false")); e.currentTarget.setAttribute("aria-pressed", "true");
    nCustom.disabled = k !== "custom"; invalidate();
  } }, label));
  const estBox = h("div", { "aria-live": "polite" });
  const estBtn = h("button", { type: "button", class: "primary", id: "run-estimate" }, "Estimate cost");
  const confirmBtn = h("button", { type: "button", class: "danger", id: "run-confirm", disabled: true }, "Confirm and queue");
  let est = null, inputs = [];

  const z = () => zones.find((x) => x.zone === zoneSel.value);
  function fillSubs() {
    clear(subSel).append(...Object.entries(z().subs || {}).map(([k, v]) => h("option", { value: k, title: v }, k)));
  }
  function fillKnobs() {
    clear(knobBox); inputs = [];
    for (const [name, k] of Object.entries(z().knobs || {})) {
      let input, read;
      if (k.path === "agents" || k.count) {
        knobBox.append(h("div", { class: "field" }, h("span", null, name), h("span", { class: "hint" }, `advanced: unchanged (${knobRange(k)})`)));
        continue;
      } else if (k.free_text) {
        input = h("textarea", { name, maxlength: 600, placeholder: "template default" });
        read = () => input.value.trim() || undefined;
        knobBox.append(h("label", { class: "field wide" }, h("span", null, name), input, h("span", { class: "hint" }, "free text, up to 600 characters")));
      } else if (k.values) {
        input = h("select", { name }, h("option", { value: "" }, "template default"), k.values.map((v, i) => h("option", { value: String(i) }, String(v))));
        read = () => (input.value === "" ? undefined : k.values[+input.value]);
        knobBox.append(h("label", { class: "field" }, h("span", null, name), input));
      } else if (k.range) {
        const step = k.int ? 1 : (k.range[1] - k.range[0]) / 20 || 0.05;
        input = h("input", { type: "number", name, min: k.range[0], max: k.range[1], step: +step.toPrecision(2), placeholder: `${k.range[0]}–${k.range[1]}` });
        read = () => (input.value === "" ? undefined : k.int ? parseInt(input.value, 10) : parseFloat(input.value));
        knobBox.append(h("label", { class: "field" }, h("span", null, name), input, h("span", { class: "hint" }, `${k.range[0]} – ${k.range[1]}${k.int ? ", integer" : ""}`)));
      } else continue;
      input.addEventListener("input", invalidate);
      input.addEventListener("change", invalidate);
      inputs.push([name, read, k, input]);
    }
  }
  function invalidate() { est = null; confirmBtn.disabled = true; clear(estBox); }
  function body() {
    const knobs = {};
    const bad = [];
    for (const [name, read, k] of inputs) {
      const v = read();
      if (v === undefined) continue;
      if (k.range && (Number.isNaN(v) || v < k.range[0] || v > k.range[1])) bad.push(`${name} must be between ${k.range[0]} and ${k.range[1]}`);
      knobs[name] = v;
    }
    const n = nMode === "screen" ? 100 : nMode === "full" ? (maxDev || 100) : parseInt(nCustom.value, 10);
    return { body: { zone: zoneSel.value, sub: subSel.value, knobs, n }, bad };
  }
  zoneSel.addEventListener("change", () => { fillSubs(); fillKnobs(); invalidate(); });
  subSel.addEventListener("change", invalidate);
  nCustom.addEventListener("input", invalidate);
  estBtn.addEventListener("click", async () => {
    invalidate();
    const { body: b, bad } = body();
    if (bad.length) { estBox.append(h("div", { class: "notice bad" }, bad.join("; "))); return; }
    estBtn.disabled = true;
    const r = await post("/api/estimate", b);
    estBtn.disabled = false;
    if (!r.ok) { estBox.append(h("div", { class: "notice bad" }, `Estimate failed: ${r.json?.error || r.status}`)); return; }
    const e = r.json;
    est = { ...b, token: e.token };
    estBox.append(h("div", { class: `notice ${e.ok ? "" : "bad"}`, id: "run-estimate-result" },
      h("dl", { class: "kv" },
        h("dt", null, "Protocol"), h("dd", null, e.protocol?.id || "—"),
        h("dt", null, "Items"), h("dd", null, String(e.n)),
        h("dt", null, "Estimated cost"), h("dd", null, h("b", null, usd(e.estimate_usd)), ` (${usd(e.per_item_usd)} per item)`),
        h("dt", null, "Experiment cap"), h("dd", null, usd(e.cap_usd)),
        h("dt", null, "Left today"), h("dd", null, usd(e.day_left_usd))),
      e.ok ? h("p", { style: { marginTop: "8px" } }, "Within caps. Confirm to add it to the queue.")
        : h("div", { style: { marginTop: "8px" } }, h("b", null, "✕ The orchestrator would refuse this run:"), h("ul", null, (e.problems || []).map((p) => h("li", null, p))))));
    confirmBtn.disabled = !e.ok;
  });
  confirmBtn.addEventListener("click", async () => {
    if (!est) return;
    confirmBtn.disabled = true;
    const r = await post("/api/run", { ...est, confirm: true });
    if (r.ok) estBox.append(h("div", { class: "notice good", style: { marginTop: "8px" } }, `✓ Queued ${r.json.job?.id}. Progress appears under Jobs.`));
    else estBox.append(h("div", { class: "notice bad", style: { marginTop: "8px" } }, `✕ Refused: ${r.json?.error || r.status}`));
    est = null;
  });
  fillSubs(); fillKnobs();
  c.append(h("div", { class: "form-grid" },
    h("label", { class: "field" }, h("span", null, "Zone"), zoneSel),
    h("label", { class: "field" }, h("span", null, "Sub-technique"), subSel)),
    h("div", null, h("h4", null, "Knobs"), h("p", { class: "muted small" }, "Only values allowed by the zone's knobs.yaml are offered. Leave blank for the template default."), knobBox),
    h("div", { class: "field" }, h("span", null, "Item set"), h("div", { class: "actions" }, nSeg, nCustom)),
    h("div", { class: "actions" }, estBtn, confirmBtn), estBox);
  runForm = { el: c, setZone: (zid) => { zoneSel.value = zid; fillSubs(); fillKnobs(); invalidate(); } };
  return c;
}

// ------------------------------------------------------------------ refine
function refineCard(d) {
  const zones = d.zones || [];
  const c = card("Refine a zone", "the refiner proposes and runs variants within the zone");
  const zoneSel = h("select", null, zones.map((z) => h("option", { value: z.zone }, `${z.zone} · ${z.name}`)));
  const it = h("input", { type: "number", min: 1, max: 20, step: 1, value: 3 });
  const budget = h("input", { type: "number", min: 0.5, step: 0.5, value: 5 });
  const steer = h("textarea", { maxlength: 500, placeholder: "Optional steering, e.g. focus on the conflicting label" });
  const out = h("div", { "aria-live": "polite" });
  const review = h("button", { type: "button", class: "primary" }, "Review");
  const reset = () => clear(out);
  [zoneSel, it, budget, steer].forEach((x) => x.addEventListener("input", reset));
  review.addEventListener("click", () => {
    clear(out);
    const n = parseInt(it.value, 10), b = parseFloat(budget.value);
    if (!(n >= 1 && n <= 20)) return out.append(h("div", { class: "notice bad" }, "Iterations must be 1 to 20."));
    if (!(b > 0)) return out.append(h("div", { class: "notice bad" }, "Budget must be above $0."));
    const confirm = h("button", { type: "button", class: "danger" }, "Confirm refine");
    out.append(h("div", { class: "notice warn" }, h("p", null, `Refine ${zoneSel.value} for up to ${n} iterations, spending at most ${usd(b)}${steer.value.trim() ? `, steered: “${steer.value.trim()}”` : ""}. The budget must fit in today's remaining lab budget.`),
      h("div", { class: "actions", style: { marginTop: "8px" } }, confirm, h("button", { type: "button", onclick: reset }, "Cancel"))));
    confirm.addEventListener("click", async () => {
      confirm.disabled = true;
      const r = await post("/api/refine", { zone: zoneSel.value, iterations: n, budget: b, steer: steer.value.trim(), confirm: true });
      clear(out).append(r.ok ? h("div", { class: "notice good" }, `✓ Queued ${r.json.job?.id}.`) : h("div", { class: "notice bad" }, `✕ Refused: ${r.json?.error || r.status}`));
    });
  });
  c.append(h("div", { class: "form-grid" },
    h("label", { class: "field" }, h("span", null, "Zone"), zoneSel),
    h("label", { class: "field" }, h("span", null, "Iterations (1–20)"), it),
    h("label", { class: "field" }, h("span", null, "Budget ($)"), budget),
    h("label", { class: "field wide" }, h("span", null, "Steering"), steer)),
    h("div", { class: "actions" }, review), out);
  return c;
}

// ------------------------------------------------------------------ compare
function compareCard(d) {
  const rows = (d.leaderboard?.rows || []).filter((r) => r.dev_n);
  const c = card("Compare configurations", "pick 2 to 4; paired on their shared dev items");
  c.id = "compare-card";
  if (rows.length < 2) { c.append(emptyState("Needs at least two protocols with dev runs.")); return c; }
  const checks = h("div", { class: "checks" });
  const btn = h("button", { type: "button", class: "primary", disabled: true }, "Compare");
  const out = h("div", { "aria-live": "polite" });
  const boxes = rows.map((r) => {
    const cb = h("input", { type: "checkbox", value: r.protocol });
    checks.append(h("label", null, cb, r.protocol));
    return cb;
  });
  const upd = () => {
    const n = boxes.filter((b) => b.checked).length;
    boxes.forEach((b) => (b.disabled = !b.checked && n >= 4));
    btn.disabled = n < 2;
  };
  boxes.forEach((b) => b.addEventListener("change", upd));
  btn.addEventListener("click", async () => {
    const ids = boxes.filter((b) => b.checked).map((b) => b.value);
    clear(out).append(h("p", { class: "muted" }, "Comparing… (bootstrap resampling can take a few seconds)"));
    btn.disabled = true;
    const r = await post("/api/compare", { protocols: ids });
    btn.disabled = false;
    clear(out);
    if (!r.ok) return out.append(h("div", { class: "notice bad" }, `✕ ${r.json?.error || r.status}`));
    renderCompare(out, r.json, ids);
  });
  c.append(checks, h("div", { class: "actions" }, btn), out);
  return c;
}
function renderCompare(out, res, ids) {
  const m = res.metrics || {}, exps = res.experiments || {};
  out.append(h("p", { class: "muted small" }, `${res.n_common} shared dev items.`));
  out.append(sortableTable([
    { key: "id", label: "Protocol", render: (id) => h("div", { class: "stack" }, h("b", null, id), fileLink(exps[id], resultsPath(exps[id]))) },
    { key: "f1", label: "Macro-F1", num: true, value: (id) => m[id]?.macro_f1, render: (id) => f3(m[id]?.macro_f1) },
    { key: "acc", label: "Accuracy", num: true, value: (id) => m[id]?.accuracy, render: (id) => f3(m[id]?.accuracy) },
    { key: "ece", label: "ECE", num: true, value: (id) => m[id]?.ece, render: (id) => f3(m[id]?.ece) },
    { key: "usd", label: "$ / item", num: true, value: (id) => m[id]?.cost?.usd_per_item_uncached, render: (id) => usd(m[id]?.cost?.usd_per_item_uncached) },
  ], ids, {}));
  const labels = [...new Set(ids.flatMap((id) => Object.keys(m[id]?.recall || {})))];
  if (labels.length) out.append(h("h4", { style: { marginTop: "12px" } }, "Per-label recall"), sortableTable([
    { key: "id", label: "Protocol", render: (id) => id },
    ...labels.map((l) => ({ key: l, label: humanize(l), num: true, value: (id) => m[id]?.recall?.[l], render: (id) => f3(m[id]?.recall?.[l]) })),
  ], ids, {}));
  const max = Math.max(0.05, ...(res.pairs || []).flatMap((p) => [Math.abs(p.diff || 0), ...(p.ci || []).map(Math.abs)])) * 1.05;
  for (const p of res.pairs || []) {
    const pc = h("div", { class: "item compare-pair", style: { marginTop: "12px" } },
      h("div", { class: "item-head" }, h("b", null, `${p.a} − ${p.b}`), badge(p.verdict)),
      h("div", { class: "metrics" }, h("span", null, "paired Δ macro-F1 ", ciCell(p.diff, p.ci, max)),
        h("span", null, "cost ratio ", h("b", null, isNum(p.cost_ratio) ? `${p.cost_ratio.toFixed(2)}×` : "—")),
        h("span", null, "Δ per extra $ / item ", h("b", null, isNum(p.diff_per_extra_usd) ? signed(p.diff_per_extra_usd, 2) : "— (no extra spend)")),
        h("span", null, "disagree ", h("b", null, pct(p.disagreement)))));
    const split = p.split_items || [];
    if (split.length) {
      const det = h("details", null, h("summary", null, `${split.length} split cases with side-by-side replays`));
      det.append(sortableTable([
        { key: "item", label: "Item", render: (s) => h("code", null, s.item) },
        { key: "a", label: p.a, render: (s) => [humanize(s.a), " ", replayLink("▶", s.replays[0])] },
        { key: "b", label: p.b, render: (s) => [humanize(s.b), " ", replayLink("▶", s.replays[1])] },
      ], split, {}));
      pc.append(det);
    }
    out.append(pc);
  }
}

// ------------------------------------------------------------------ arena
function arenaCard(d) {
  const ex = (d.experiments || []).slice().reverse();
  const c = card("Send to the arena", "a holdout evaluation for one configuration");
  if (!ex.length) { c.append(emptyState("No experiments to send.")); return c; }
  const sel = h("select", null, ex.map((e) => h("option", { value: e.experiment }, `${e.experiment} · ${e.protocol}${e.zone ? ` (${e.zone})` : ""}`)));
  const btn = h("button", { type: "button", class: "primary" }, "Send to arena…");
  const out = h("div", { "aria-live": "polite" });
  sel.addEventListener("change", () => clear(out));
  btn.addEventListener("click", async () => {
    clear(out);
    const e = ex.find((x) => x.experiment === sel.value);
    const r = await post("/api/arena", { experiment: e.experiment, zone: e.zone });
    if (!r.ok) return out.append(h("div", { class: "notice bad" }, `✕ ${r.json?.error || r.status}`));
    if (r.json.needs_confirm) {
      const left = r.json.holdout_evals_left;
      const confirm = h("button", { type: "button", class: "danger", disabled: isNum(left) && left <= 0 }, "Confirm arena run");
      out.append(h("div", { class: "notice warn", id: "arena-warning" }, h("p", null, r.json.message || `This uses 1 of this week's holdout evaluations (${left} left).`),
        h("div", { class: "actions", style: { marginTop: "8px" } }, confirm, h("button", { type: "button", onclick: () => clear(out) }, "Cancel"))));
      confirm.addEventListener("click", async () => {
        confirm.disabled = true;
        const r2 = await post("/api/arena", { experiment: e.experiment, zone: e.zone, confirm: true });
        clear(out).append(r2.ok ? h("div", { class: "notice good" }, `✓ Queued ${r2.json.job?.id}.`) : h("div", { class: "notice bad" }, `✕ Refused: ${r2.json?.error || r2.status}`));
      });
    } else if (r.json.job) out.append(h("div", { class: "notice good" }, `✓ Queued ${r.json.job.id}.`));
  });
  c.append(h("label", { class: "field" }, h("span", null, "Experiment"), sel), h("div", { class: "actions" }, btn), out);
  return c;
}
