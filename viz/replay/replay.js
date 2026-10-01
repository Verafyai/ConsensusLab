// Evidence replay (spec §8.1). Replays one protocol run on one claim from a transcript JSON.
// URL params: ?t=<transcript> ?autoplay=1 ?mode=card ?aspect=square|wide ?variant=<name>
// ?captions=1 (burned-in narration for video capture)

import {
  agentName, capWords, domainOf, familyOf, formatDate, isVerdictLabel, labelName, labelTone,
  MAX_EXCERPT_WORDS, MAX_RATIONALE_WORDS, pct, positionText, timing,
} from "./text.js";

const params = new URLSearchParams(location.search);
const opts = {
  src: params.get("t") || "samples/debate-sample.json",
  autoplay: params.get("autoplay") === "1",
  card: params.get("mode") === "card",
  aspect: ["square", "wide"].includes(params.get("aspect")) ? params.get("aspect") : null,
  variant: params.get("variant"),
  captions: params.get("captions") === "1",
};
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const GLYPH = { sup: "✓", ref: "✕", nee: "?", con: "!" };
const STANCE = {
  supports: { tone: "sup", glyph: "✓", text: "Supports" },
  refutes: { tone: "ref", glyph: "✕", text: "Refutes" },
  neutral: { tone: "nee", glyph: "–", text: "Neutral" },
};
const SVG_NS = "http://www.w3.org/2000/svg";

// --- tiny DOM helper (text only; never parses data as HTML) ------------------------------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "style") node.style.cssText = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

// --- loading ------------------------------------------------------------------------------

async function loadTranscript(src) {
  const res = await fetch(src, { cache: "no-store" });
  if (!res.ok) throw new Error(`Could not load ${src} (HTTP ${res.status})`);
  if (/\.gz$/i.test(new URL(src, location.href).pathname) && "DecompressionStream" in window) {
    const stream = res.body.pipeThrough(new DecompressionStream("gzip"));
    return JSON.parse(await new Response(stream).text());
  }
  return res.json();
}

function applyChrome() {
  const b = document.body.classList;
  if (opts.card) b.add("mode-card");
  else b.add("mode-replay");
  if (opts.aspect) b.add(`aspect-${opts.aspect}`, "fixed");
  if (opts.autoplay) b.add("autoplay");
  if (reducedMotion) b.add("reduced");
  if (opts.captions && !opts.card) b.add("captions");
  // Resolved against the page, so it works at /viz/replay/ (serve.py) and /replay/ (dashboard).
  if (opts.variant && /^[a-z0-9-]{1,40}$/.test(opts.variant)) {
    const href = new URL(`../variants/${opts.variant}.css`, location.href).href;
    const link = el("link", { rel: "stylesheet", href });
    link.addEventListener("error", () => link.remove());
    document.head.append(link);
  }
}

function claimOf(t) {
  return t.question || t.claim || `Item ${t.item}`;
}

function reasonsOf(t) {
  const rs = (t.reasons || []).filter(Boolean).slice(0, 2);
  if (rs.length) return rs.map((r) => capWords(r, 25));
  // Fall back to the first sentences of the rationale.
  return String(t.rationale || "").split(/(?<=[.!?])\s+/).filter(Boolean).slice(0, 2)
    .map((s) => capWords(s, 25));
}

function verdictBadge(label, cls = "") {
  const tone = labelTone(label);
  return el("span", { class: `vlabel tone-${tone} ${cls}` },
    el("span", { class: "glyph", "aria-hidden": "true", text: GLYPH[tone] }),
    el("span", { class: "vtext", text: labelName(label) }));
}

function confBar(conf, cls = "") {
  return el("div", {
    class: `bar ${cls}`, role: "meter", "aria-valuemin": "0", "aria-valuemax": "100",
    "aria-valuenow": String(Math.round(conf * 100)), "aria-label": "Confidence",
  }, el("span", { class: "fill", style: `width:${pct(conf)}` }));
}

function goldBlock(t, cls = "") {
  if (t.gold == null) return null;
  const match = String(t.gold).toLowerCase() === String(t.verdict).toLowerCase();
  return el("div", { class: `gold ${match ? "match" : "mismatch"} ${cls}` },
    el("span", { class: "gold-label", text: "Human fact-checkers" }),
    verdictBadge(t.gold, "small"),
    el("span", { class: "match-badge" },
      el("span", { class: "glyph", "aria-hidden": "true", text: match ? "✓" : "✕" }),
      match ? "Matches the panel's verdict" : "Differs from the panel's verdict"));
}

// --- still evidence card -------------------------------------------------------------------

function renderCard(app, t) {
  const tone = labelTone(t.verdict);
  const n = (t.evidence || []).length;
  const conf = Number(t.confidence) || 0;
  const card = el("article", { class: `still tone-${tone}`, "aria-label": "Fact-check card" },
    el("p", { class: "still-kicker", text: "Claim" }),
    el("h1", { class: "still-claim", text: claimOf(t) }),
    el("div", { class: "still-verdict" }, verdictBadge(t.verdict)),
    el("div", { class: "still-conf" },
      el("p", { class: "still-conf-text" },
        el("strong", { class: "conf-num", text: pct(conf) }), " confident"),
      confBar(conf, "still-bar")),
    el("ol", { class: "still-reasons" }, reasonsOf(t).map((r) => el("li", { text: r }))),
    el("footer", { class: "still-foot" },
      el("span", { class: "sources", text: `Based on ${n} source${n === 1 ? "" : "s"}` }),
      goldBlock(t, "still-gold")));
  app.replaceChildren(card);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.body.dataset.ready = "1";
  }));
}

// --- replay ---------------------------------------------------------------------------------

function buildReplay(app, t) {
  const evidence = t.evidence || [];
  const turns = [...(t.turns || [])].sort((a, b) => (a.n ?? 0) - (b.n ?? 0));
  const evIndex = new Map(evidence.map((e, i) => [e.id, i]));
  const rounds = [...new Set(turns.map((x) => x.round ?? x.n))].sort((a, b) => a - b);
  const agreement = t.agreement || [];
  const believers = [...new Set(turns.filter((x) => x.belief != null).map((x) => x.agent))];

  // Header
  const header = el("header", { class: "claim-bar" },
    el("p", { class: "kicker" }, "Claim being checked",
      el("span", { class: "proto", text: `${t.protocol}` })),
    el("h1", { class: "claim", text: claimOf(t) }));

  // Agreement meter and beliefs
  const meterFill = el("span", { class: "fill" });
  const meterMarks = el("span", { class: "marks", "aria-hidden": "true" });
  const meterVal = el("span", { class: "meter-val", text: "—" });
  const meterNote = el("p", { class: "meter-note", text: "Waiting for round 1" });
  const beliefRows = believers.map((a) => {
    const fill = el("span", { class: "fill" });
    const val = el("span", { class: "belief-val", text: "—" });
    const row = el("div", { class: "belief-row pending-row" },
      el("span", { class: "belief-who", text: agentName(a).replace("Advocate · ", "") }),
      el("span", { class: "bar small" }, fill), val);
    return { agent: a, row, fill, val };
  });
  const meter = el("section", { class: `meter${beliefRows.length ? "" : " no-beliefs"}`,
                                "aria-label": "Agreement" },
    el("div", { class: "meter-row" },
      el("h2", { class: "meter-label", text: "Agreement between agents" }), meterVal),
    el("span", { class: "bar meter-bar" }, meterFill, meterMarks),
    meterNote,
    beliefRows.length ? el("div", { class: "beliefs" },
      el("p", { class: "beliefs-title", text: "Each advocate's belief that the claim is true" }),
      beliefRows.map((b) => b.row)) : null);

  // Evidence
  const evCards = evidence.map((e, i) => el("li", { class: "ev pending", id: `ev-${i}` },
    el("div", { class: "ev-head" },
      el("span", { class: "ev-num", text: String(i + 1) }),
      el("span", { class: "ev-domain", text: domainOf(e.url) }),
      el("time", { class: "ev-date", datetime: e.published || null,
                   text: formatDate(e.published) })),
    el("p", { class: "ev-title", text: e.title || "" }),
    el("blockquote", { class: "ev-excerpt", text: `“${capWords(e.excerpt, MAX_EXCERPT_WORDS)}”` }),
    el("ul", { class: "stances", "aria-label": "How each model read this source" },
      Object.entries(e.stance || {}).map(([model, s]) => {
        const st = STANCE[s] || STANCE.neutral;
        return el("li", { class: `stance tone-${st.tone}` },
          el("span", { class: "glyph", "aria-hidden": "true", text: st.glyph }),
          el("span", { class: "st-text", text: st.text }),
          el("span", { class: "st-model", text: model }));
      }))));
  const evList = el("ol", { class: "ev-list" }, evCards);
  const evSection = el("section", { class: "evidence", "aria-label": "Evidence" },
    el("h2", { class: "col-title", text: `Evidence · ${evidence.length} sources` }), evList);
  if (evidence.length > 5) evSection.classList.add("dense");

  // Turns
  const turnEls = turns.map((x) => {
    const pos = positionText(x.position);
    const posTone = isVerdictLabel(x.position) ? `tone-${labelTone(x.position)}` : "tone-side";
    const cites = (x.cites || []).filter((c) => evIndex.has(c));
    return el("li", { class: "turn pending" },
      el("div", { class: "turn-head" },
        el("span", { class: "agent", text: agentName(x.agent) }),
        el("span", { class: "fam", title: x.model, text: familyOf(x) }),
        el("span", { class: "round", text: `Round ${x.round ?? x.n}` })),
      pos || x.belief != null ? el("div", { class: "turn-pos" },
        pos ? el("span", { class: `pos ${posTone}`, text: pos }) : null,
        x.belief != null ? el("span", { class: "belief-inline",
                                         text: `Belief true: ${pct(x.belief)}` }) : null) : null,
      el("p", { class: "turn-text", text: x.refused ? "(Declined to answer.)" : capWords(x.text, 120) }),
      cites.length ? el("p", { class: "cites" }, "Cites ",
        cites.map((c) => el("span", { class: "cite-chip", text: String(evIndex.get(c) + 1) })))
        : null);
  });
  const turnScroll = el("div", { class: "turn-scroll" }, el("ol", { class: "turn-list" }, turnEls));
  const turnSection = el("section", { class: "turns", "aria-label": "Deliberation" },
    el("h2", { class: "col-title", text: `Deliberation · ${turns.length} turns` }), turnScroll);

  // Verdict
  const conf = Number(t.confidence) || 0;
  const verdict = el("section", { class: `verdict pending tone-${labelTone(t.verdict)}`,
                                  "aria-label": "Verdict" },
    el("p", { class: "kicker", text: "Verdict" }),
    el("div", { class: "v-main" }, verdictBadge(t.verdict, "big")),
    el("div", { class: "v-conf" },
      el("p", { class: "v-conf-text" }, el("strong", { text: pct(conf) }), " confident"),
      confBar(conf)),
    el("p", { class: "rationale", text: capWords(t.rationale, MAX_RATIONALE_WORDS) }),
    el("ol", { class: "reasons" }, reasonsOf(t).map((r) => el("li", { text: r }))),
    goldBlock(t));

  const links = document.createElementNS(SVG_NS, "svg");
  links.setAttribute("class", "links");
  links.setAttribute("aria-hidden", "true");

  const live = el("p", { class: "sr-only", "aria-live": "polite" });

  const controls = el("nav", { class: "controls", "aria-label": "Replay controls" });
  const grid = el("div", { class: "grid" }, header, meter, evSection, turnSection, verdict);
  const caption = el("div", { class: "caption", "aria-hidden": "true" },
    el("span", { class: "caption-text" }));
  app.replaceChildren(grid, links, controls, live, ...(opts.captions ? [caption] : []));

  return { t, evidence, turns, evIndex, rounds, agreement, header, meter, meterFill, meterMarks,
           meterVal, meterNote, beliefRows, evCards, evSection, evList, turnEls, turnScroll, verdict,
           links, live, controls, app, caption };
}

function makeSteps(v) {
  const steps = [{ kind: "question" }];
  v.evidence.forEach((_, i) => steps.push({ kind: "ev", i }));
  v.turns.forEach((_, j) => steps.push({ kind: "turn", j }));
  steps.push({ kind: "verdict" });
  return steps;
}

function agreementState(v, nTurnsShown) {
  // Round r is complete once all of its turns are shown; agreement[k] belongs to rounds[k].
  const vals = [];
  v.rounds.forEach((r, k) => {
    if (k >= v.agreement.length) return;
    let last = -1;
    v.turns.forEach((x, j) => { if ((x.round ?? x.n) === r) last = j; });
    if (last >= 0 && last < nTurnsShown) vals.push({ round: r, value: v.agreement[k] });
  });
  return vals;
}

function apply(v, idx, steps) {
  const step = steps[idx];
  const nEv = v.evidence.length;
  const shownEv = Math.max(0, Math.min(nEv, idx));
  const shownTurns = Math.max(0, Math.min(v.turns.length, idx - nEv));
  const current = step.kind === "turn" ? step.j : -1;
  const isVerdict = step.kind === "verdict";

  document.body.dataset.step = step.kind;
  v.evCards.forEach((c, i) => {
    c.classList.toggle("pending", i >= shownEv);
    c.classList.toggle("arriving", step.kind === "ev" && step.i === i);
  });
  const citedNow = new Set(current >= 0 ? (v.turns[current].cites || []) : []);
  const citedEver = new Set(v.turns.slice(0, shownTurns).flatMap((x) => x.cites || []));
  v.evidence.forEach((e, i) => {
    v.evCards[i].classList.toggle("cited", citedNow.has(e.id));
    v.evCards[i].classList.toggle("was-cited", !citedNow.has(e.id) && citedEver.has(e.id));
  });
  v.turnEls.forEach((el_, j) => {
    el_.classList.toggle("pending", j >= shownTurns);
    el_.classList.toggle("current", j === current);
    el_.classList.toggle("past", j < shownTurns && j !== current);
  });
  v.verdict.classList.toggle("pending", !isVerdict);
  document.body.classList.toggle("verdict-shown", isVerdict);

  // Agreement meter
  const ag = agreementState(v, shownTurns);
  const lastAg = ag.at(-1);
  v.meterMarks.replaceChildren(...ag.slice(0, -1).map((a) =>
    el("span", { class: "mark", style: `left:${pct(a.value)}` })));
  if (lastAg) {
    v.meterFill.style.width = pct(lastAg.value);
    v.meterVal.textContent = pct(lastAg.value);
    const prev = ag.at(-2);
    let trend = "";
    if (prev) {
      const d = lastAg.value - prev.value;
      trend = d > 0.02 ? " · converging" : d < -0.02 ? " · splitting" : " · holding steady";
    }
    v.meterNote.textContent = `After round ${lastAg.round}${trend}`;
  } else {
    v.meterFill.style.width = "0%";
    v.meterVal.textContent = "—";
    v.meterNote.textContent = v.agreement.length ? `Waiting for round ${v.rounds[0] ?? 1}`
      : "No agreement recorded";
  }
  for (const b of v.beliefRows) {
    const seen = v.turns.slice(0, shownTurns).filter((x) => x.agent === b.agent && x.belief != null);
    const last = seen.at(-1);
    b.row.classList.toggle("pending-row", !last);
    b.fill.style.width = last ? pct(last.belief) : "0%";
    b.val.textContent = last ? pct(last.belief) : "—";
  }

  // Keep the current turn and its cited cards in view inside fixed-size layouts.
  if (current >= 0) {
    ensureVisible(v.turnScroll, v.turnEls[current], "bottom");
    const first = (v.turns[current].cites || []).map((c) => v.evIndex.get(c))
      .filter((i) => i != null).sort((a, b) => a - b)[0];
    if (first != null) ensureVisible(v.evList, v.evCards[first], "nearest");
  } else if (step.kind === "ev") {
    ensureVisible(v.evList, v.evCards[step.i], "nearest");
  }

  v.live.textContent = describe(v, step);
  v.caption.firstChild.textContent = captionFor(v, step);
  trackLinks(v, current);
}

function describe(v, step) {
  if (step.kind === "question") return `Claim: ${claimOf(v.t)}`;
  if (step.kind === "ev") {
    const e = v.evidence[step.i];
    return `Source ${step.i + 1}: ${domainOf(e.url)}, ${e.title}`;
  }
  if (step.kind === "turn") {
    const x = v.turns[step.j];
    return `${agentName(x.agent)}, round ${x.round ?? x.n}: ${x.text}`;
  }
  return `Verdict: ${labelName(v.t.verdict)}, ${pct(v.t.confidence)} confident.`;
}

function familyName(x) {
  const f = familyOf(x);
  return f.charAt(0).toUpperCase() + f.slice(1);
}

// One short line of plain-words narration per step (?captions=1).
export function captionFor(v, step) {
  const t = v.t;
  if (step.kind === "question") return "The claim";
  if (step.kind === "ev") {
    const n = step.i + 1;
    return `${n} source${n === 1 ? "" : "s"} found`;
  }
  if (step.kind === "turn") {
    const x = v.turns[step.j];
    const who = agentName(x.agent).replace(" · ", " ");
    const fam = familyName(x);
    if (String(x.agent).toLowerCase() === "judge" && step.j === v.turns.length - 1) {
      return `Judge rules (${fam})`;
    }
    const says = isVerdictLabel(x.position) ? `: ${labelName(x.position)}` : "";
    return `Round ${x.round ?? x.n} · ${who} (${fam})${says}`;
  }
  let text = `Verdict: ${labelName(t.verdict)}, ${pct(t.confidence)}`;
  if (t.gold != null) {
    const match = String(t.gold).toLowerCase() === String(t.verdict).toLowerCase();
    text += ` · Human experts: ${labelName(t.gold)} ${match ? "✓" : "✕"}`;
  }
  return text;
}

// Fixed video aspects are laid out at 1080 px tall and scaled to fit the viewport, so the
// same design renders at 720×720 and 1280×720.
const DESIGN = { square: [1080, 1080], wide: [1920, 1080] };
let stageScale = 1;

function fitStage() {
  const app = document.getElementById("app");
  if (!opts.aspect || !app) return;
  const [w, h] = DESIGN[opts.aspect];
  stageScale = Math.min(window.innerWidth / w, window.innerHeight / h) || 1;
  app.style.transformOrigin = "0 0";
  app.style.transform = Math.abs(stageScale - 1) < 0.001 ? "" : `scale(${stageScale})`;
}

function ensureVisible(container, node, align) {
  if (!document.body.classList.contains("fixed")) return;
  if (container.scrollHeight <= container.clientHeight + 1) return;
  const c = container.getBoundingClientRect();
  const r = node.getBoundingClientRect();
  const pad = 8;
  const offTop = (r.top - c.top) / stageScale + container.scrollTop;
  const offBot = offTop + r.height / stageScale;
  let top = container.scrollTop;
  if (align === "bottom" || offBot > top + container.clientHeight) {
    top = offBot - container.clientHeight + pad;
  }
  if (offTop < top) top = offTop - pad;          // a tall node shows its top first
  top = Math.max(0, Math.min(top, container.scrollHeight - container.clientHeight));
  container.scrollTo({ top, behavior: reducedMotion ? "auto" : "smooth" });
}

// --- connectors ------------------------------------------------------------------------------

let linkRaf = 0;
let linkUntil = 0;
let linkTurn = -1;

function trackLinks(v, current) {
  linkTurn = current;
  linkUntil = performance.now() + 1100;
  if (!linkRaf) {
    const loop = () => {
      drawLinks(v, linkTurn);
      linkRaf = performance.now() < linkUntil ? requestAnimationFrame(loop) : 0;
    };
    linkRaf = requestAnimationFrame(loop);
  }
}

function svgEl(tag, cls) {
  const node = document.createElementNS(SVG_NS, tag);
  node.setAttribute("class", cls);
  return node;
}

// Elements are rebuilt only when the turn changes (so the draw-in animation plays once);
// while layout settles or scrolls, only their coordinates are updated.
let drawnFor = null;

function drawLinks(v, current) {
  const svg = v.links;
  const stage = v.app.getBoundingClientRect();
  svg.setAttribute("width", String(v.app.scrollWidth));
  svg.setAttribute("height", String(v.app.scrollHeight));
  const geo = linkGeometry(v, current, stage);
  if (!geo) {
    svg.replaceChildren();
    drawnFor = null;
    return;
  }
  const key = `${current}:${geo.ends.map((e) => e.i).join(",")}`;
  if (drawnFor !== key) {
    svg.replaceChildren(...geo.ends.flatMap(() => [svgEl("path", "link"),
                                                     svgEl("circle", "link-dot")]),
                        svgEl("circle", "link-dot start"));
    drawnFor = key;
  }
  const nodes = svg.children;
  geo.ends.forEach((e, k) => {
    const dx = Math.max(24, (geo.x1 - e.x2) * 0.5);
    nodes[2 * k].setAttribute("d", `M ${geo.x1} ${geo.y1} C ${geo.x1 - dx} ${geo.y1}, `
                                  + `${e.x2 + dx} ${e.y2}, ${e.x2} ${e.y2}`);
    nodes[2 * k + 1].setAttribute("cx", String(e.x2));
    nodes[2 * k + 1].setAttribute("cy", String(e.y2));
    nodes[2 * k + 1].setAttribute("r", "4.5");
  });
  const start = nodes[nodes.length - 1];
  start.setAttribute("cx", String(geo.x1));
  start.setAttribute("cy", String(geo.y1));
  start.setAttribute("r", "4.5");
}

function linkGeometry(v, current, stage) {
  if (current < 0) return null;
  const evBox = v.evList.getBoundingClientRect();
  const turnBox = v.turnScroll.getBoundingClientRect();
  const tr = v.turnEls[current].getBoundingClientRect();
  // Only draw when evidence sits to the left of the turns (side-by-side layouts).
  if (tr.left < evBox.right - 4) return null;
  const k = stageScale;
  const x1 = (tr.left - stage.left) / k;
  const y1 = (Math.max(tr.top, turnBox.top) - stage.top) / k + 22;
  const ends = [];
  for (const id of v.turns[current].cites || []) {
    const i = v.evIndex.get(id);
    if (i == null) continue;
    const cr = v.evCards[i].getBoundingClientRect();
    const visTop = Math.max(cr.top, evBox.top);
    const visBot = Math.min(cr.bottom, evBox.bottom);
    if (visBot - visTop < 12 * k) continue;            // card scrolled out of view
    ends.push({ i, x2: (cr.right - stage.left) / k, y2: ((visTop + visBot) / 2 - stage.top) / k });
  }
  return ends.length ? { x1, y1, ends } : null;
}

// --- player ----------------------------------------------------------------------------------

function player(v) {
  const steps = makeSteps(v);
  const tm = timing(v.evidence.length, v.turns.length);
  const dur = (s) => ({ question: tm.question, ev: tm.evidence, turn: tm.turn,
                        verdict: tm.verdict })[s.kind];
  let idx = 0;
  let playing = false;
  let timer = 0;

  const btn = (label, icon, onClick, extra = {}) => {
    const b = el("button", { type: "button", class: "ctl", "aria-label": label, title: label,
                             ...extra },
      el("span", { "aria-hidden": "true", text: icon }), el("span", { class: "ctl-text",
                                                                        text: label }));
    b.addEventListener("click", onClick);
    return b;
  };
  const counter = el("span", { class: "counter" });
  const progress = el("span", { class: "progress" }, el("span", { class: "fill" }));
  // window.__captions: [{start_ms, end_ms, text}] for each step shown, in ms since the
  // replay (re)started; end_ms stays null for the step on screen until the next one.
  window.__captions = [];
  let t0 = performance.now();
  const closeCaption = () => {
    const last = window.__captions.at(-1);
    if (last && last.end_ms == null) last.end_ms = Math.round(performance.now() - t0);
  };
  const go = (i) => {
    idx = Math.max(0, Math.min(steps.length - 1, i));
    if (idx === 0) {
      window.__captions = [];
      t0 = performance.now();
    }
    closeCaption();
    window.__captions.push({ start_ms: Math.round(performance.now() - t0), end_ms: null,
                             text: captionFor(v, steps[idx]) });
    apply(v, idx, steps);
    counter.textContent = `Step ${idx + 1} of ${steps.length}`;
    progress.firstChild.style.width = `${(idx / (steps.length - 1)) * 100}%`;
  };
  const schedule = () => {
    clearTimeout(timer);
    if (!playing) return;
    timer = setTimeout(() => {
      if (idx >= steps.length - 1) {
        setPlaying(false);
        closeCaption();
        if (opts.autoplay) document.body.dataset.done = "1";
        return;
      }
      go(idx + 1);
      schedule();
    }, dur(steps[idx]));
  };
  const playBtn = btn("Play", "▶", () => setPlaying(!playing), { class: "ctl primary" });
  function setPlaying(p) {
    playing = p;
    if (p && idx >= steps.length - 1) go(0);
    playBtn.querySelector("[aria-hidden]").textContent = p ? "❚❚" : "▶";
    playBtn.querySelector(".ctl-text").textContent = p ? "Pause" : "Play";
    playBtn.setAttribute("aria-label", p ? "Pause" : "Play");
    schedule();
  }
  const step = (d) => { setPlaying(false); go(idx + d); };
  v.controls.replaceChildren(
    btn("Restart", "⟲", () => { setPlaying(false); go(0); }),
    btn("Back", "◀", () => step(-1)),
    playBtn,
    btn("Forward", "▶▶", () => step(1)),
    counter, progress);

  document.addEventListener("keydown", (e) => {
    if (e.target.closest && e.target.closest("button") && (e.key === " " || e.key === "Enter")) {
      return;   // let the focused button handle it
    }
    if (e.key === " ") { e.preventDefault(); setPlaying(!playing); }
    else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    else if (e.key === "Home" || e.key === "r") { setPlaying(false); go(0); }
    else if (e.key === "End") { setPlaying(false); go(steps.length - 1); }
  });
  window.addEventListener("resize", () => trackLinks(v, linkTurn));
  v.turnScroll.addEventListener("scroll", () => trackLinks(v, linkTurn), { passive: true });
  v.evList.addEventListener("scroll", () => trackLinks(v, linkTurn), { passive: true });

  if (reducedMotion) {
    go(steps.length - 1);
    if (opts.autoplay) {
      setTimeout(() => { closeCaption(); document.body.dataset.done = "1"; }, 300);
    }
    return;
  }
  go(0);
  if (opts.autoplay) setPlaying(true);
}

// --- main ------------------------------------------------------------------------------------

async function main() {
  applyChrome();
  fitStage();
  window.addEventListener("resize", fitStage);
  const app = document.getElementById("app");
  let t;
  try {
    t = await loadTranscript(opts.src);
  } catch (err) {
    app.replaceChildren(el("p", { class: "msg error", role: "alert",
                                  text: `Could not load the transcript. ${err.message}` }));
    document.body.dataset.error = "1";
    if (opts.card) document.body.dataset.ready = "1";
    if (opts.autoplay) document.body.dataset.done = "1";
    return;
  }
  document.title = `${labelName(t.verdict)}: ${claimOf(t)} · Evidence Replay`;
  if (opts.card) {
    renderCard(app, t);
    return;
  }
  player(buildReplay(app, t));
}

main();
