// Hand-written inline-SVG charts. Mark specs: 2px lines, r>=4 markers with a 2px surface ring,
// hairline solid grid, recessive axes, selective direct labels, hover tooltip on every mark.
import { h, s, clear, isNum, f3, showTip, hideTip, signed } from "./util.js";

const BLUE = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5",
  "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"];

export const isDark = () => getComputedStyle(document.documentElement).colorScheme.includes("dark");

function hex2rgb(x) { const n = parseInt(x.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function lum([r, g, b]) {
  const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function rampAt(ramp, t) {
  t = Math.max(0, Math.min(1, t));
  const p = t * (ramp.length - 1), i = Math.floor(p), fr = p - i;
  const a = hex2rgb(ramp[i]), b = hex2rgb(ramp[Math.min(i + 1, ramp.length - 1)]);
  return a.map((v, k) => Math.round(v + (b[k] - v) * fr));
}
/** Sequential blue (magnitude). Light: pale = low. Dark: dark = low (recedes into the surface). */
export function seqBlue(t) {
  const ramp = isDark() ? BLUE.slice(2).reverse() : BLUE;
  const rgb = rampAt(ramp, t);
  return { bg: `rgb(${rgb.join(",")})`, ink: lum(rgb) > 0.32 ? "#0b0b0b" : "#ffffff" };
}
/** Second sequential context (orange), one hue light->dark, built in OKLCH. */
export function seqOrange(t) {
  t = Math.max(0, Math.min(1, t));
  const L = isDark() ? 0.27 + t * 0.5 : 0.95 - t * 0.5;
  const C = 0.03 + t * 0.13;
  return { bg: `oklch(${L.toFixed(3)} ${C.toFixed(3)} 45)`, ink: L > 0.66 ? "#0b0b0b" : "#ffffff" };
}
export function scaleLegend(fn, lo, hi, fmt = f3) {
  const stops = [];
  for (let i = 0; i <= 10; i++) stops.push(`${fn(i / 10).bg} ${i * 10}%`);
  return h("div", { class: "scale" }, h("span", null, fmt(lo)),
    h("span", { class: "bar", style: { background: `linear-gradient(90deg, ${stops.join(",")})` } }),
    h("span", null, fmt(hi)));
}

// ---------- CI glyph: interval around 0 ----------
export function ciGlyph(diff, ci, max = 0.3, w = 116) {
  const H = 18, pad = 5;
  const x = (v) => pad + ((Math.max(-max, Math.min(max, v)) + max) / (2 * max)) * (w - 2 * pad);
  const svg = s("svg", { class: "ci-glyph", width: w, height: H, viewBox: `0 0 ${w} ${H}`, role: "img",
    "aria-label": `difference ${signed(diff)}${ci ? `, 95% CI ${signed(ci[0])} to ${signed(ci[1])}` : ""}` });
  svg.append(s("line", { x1: pad, x2: w - pad, y1: H / 2, y2: H / 2, style: { stroke: "var(--grid)", strokeWidth: 1 } }));
  svg.append(s("line", { x1: x(0), x2: x(0), y1: 1, y2: H - 1, style: { stroke: "var(--axis-muted)", strokeWidth: 1 } }));
  if (ci && isNum(ci[0]) && isNum(ci[1])) {
    const c = ci[0] > 0 ? "var(--good)" : ci[1] < 0 ? "var(--critical)" : "var(--text-secondary)";
    svg.append(s("line", { x1: x(ci[0]), x2: x(ci[1]), y1: H / 2, y2: H / 2, style: { stroke: c, strokeWidth: 2, strokeLinecap: "round" } }));
    for (const v of ci) svg.append(s("line", { x1: x(v), x2: x(v), y1: H / 2 - 4, y2: H / 2 + 4, style: { stroke: c, strokeWidth: 2, strokeLinecap: "round" } }));
  }
  if (isNum(diff)) svg.append(s("circle", { cx: x(diff), cy: H / 2, r: 4, style: { fill: "var(--text-primary)", stroke: "var(--surface-1)", strokeWidth: 2 } }));
  svg.append(s("title", null, `Δ ${signed(diff)}${ci ? ` (95% CI ${signed(ci[0])} to ${signed(ci[1])})` : ""}; tick = 0`));
  return svg;
}
export function ciCell(diff, ci, max) {
  if (!isNum(diff)) return h("span", { class: "muted" }, "—");
  return h("span", { class: "ci-cell" }, ciGlyph(diff, ci, max),
    h("span", { class: "num-col" }, signed(diff), ci ? h("span", { class: "muted small" }, ` [${signed(ci[0])}, ${signed(ci[1])}]`) : null));
}

// ---------- responsive mount ----------
function mount(container, draw) {
  const box = h("div", { class: "chart" });
  container.append(box);
  let last = 0;
  const run = () => {
    const w = Math.max(260, Math.floor(box.clientWidth || container.clientWidth || 600));
    if (w === last) return;
    last = w;
    clear(box);
    draw(box, w);
  };
  const ro = new ResizeObserver(() => run());
  ro.observe(box);
  requestAnimationFrame(run);
  return box;
}

function niceStep(span, target) {
  const raw = span / target, mag = 10 ** Math.floor(Math.log10(raw));
  const n = raw / mag;
  return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag;
}
function linTicks(lo, hi, target = 5) {
  const st = niceStep(hi - lo || 1, target), out = [];
  for (let v = Math.ceil(lo / st) * st; v <= hi + st * 1e-6; v += st) out.push(+v.toFixed(10));
  return out;
}
function logTicks(lo, hi) {
  const out = [];
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++)
    for (const m of [1, 2, 5]) { const v = m * 10 ** e; if (v >= lo * 0.999 && v <= hi * 1.001) out.push(v); }
  return out;
}
const usdTick = (v) => (v >= 1 ? "$" + v.toFixed(v >= 10 ? 0 : 1) : v >= 0.01 ? "$" + v.toFixed(2).replace(/0$/, "") : "$" + +v.toPrecision(1));

// ---------- scatter: accuracy vs cost ----------
/** pts: [{id, x, y, holdout(bool), champion(bool), pareto(bool), rows:[[k,v]]}] */
export function scatter(container, pts, { xLabel = "$ per item (log scale)", yLabel = "macro-F1" } = {}) {
  pts = pts.filter((p) => isNum(p.x) && p.x > 0 && isNum(p.y));
  if (!pts.length) return container.append(h("div", { class: "empty" }, "No protocol has both a cost and a score yet."));
  return mount(container, (box, W) => {
    const narrow = W < 520;
    const H = narrow ? 300 : 380, m = { l: 44, r: narrow ? 14 : 24, t: 26, b: 40 };
    let xlo = Math.min(...pts.map((p) => p.x)), xhi = Math.max(...pts.map((p) => p.x));
    xlo /= 1.35; xhi *= 1.35;
    let ylo = Math.min(...pts.map((p) => p.y)), yhi = Math.max(...pts.map((p) => p.y));
    ylo = Math.max(0, Math.floor((ylo - 0.03) * 20) / 20); yhi = Math.min(1, Math.ceil((yhi + 0.02) * 20) / 20);
    if (yhi - ylo < 0.1) ylo = Math.max(0, yhi - 0.1);
    const X = (v) => m.l + ((Math.log10(v) - Math.log10(xlo)) / (Math.log10(xhi) - Math.log10(xlo))) * (W - m.l - m.r);
    const Y = (v) => m.t + (1 - (v - ylo) / (yhi - ylo)) * (H - m.t - m.b);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
      "aria-label": `Scatter of ${pts.length} protocols, macro-F1 against cost per item` });
    const g = s("g");
    for (const t of linTicks(ylo, yhi, narrow ? 4 : 6)) {
      g.append(s("line", { class: "gridline", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
      g.append(s("text", { x: m.l - 6, y: Y(t) + 4, "text-anchor": "end" }, t.toFixed(2)));
    }
    let xt = logTicks(xlo, xhi);
    if (xt.length > (narrow ? 5 : 9)) xt = xt.filter((v) => /^1|^5/.test(v.toExponential()));
    for (const t of xt) {
      g.append(s("line", { class: "gridline", x1: X(t), x2: X(t), y1: m.t, y2: H - m.b }));
      g.append(s("text", { x: X(t), y: H - m.b + 16, "text-anchor": "middle" }, usdTick(t)));
    }
    g.append(s("line", { class: "axis", x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b }));
    g.append(s("text", { x: W - m.r, y: H - 4, "text-anchor": "end" }, xLabel));
    svg.append(g);
    svg.append(s("text", { x: 4, y: 10, "text-anchor": "start" }, yLabel));

    // Pareto frontier
    const fr = pts.filter((p) => p.pareto).sort((a, b) => a.x - b.x);
    if (fr.length >= 2) {
      svg.append(s("polyline", { points: fr.map((p) => `${X(p.x)},${Y(p.y)}`).join(" "),
        style: { fill: "none", stroke: "var(--text-secondary)", strokeWidth: 2, strokeLinejoin: "round", strokeLinecap: "round", opacity: 0.55 } }));
    }
    // champion halo
    for (const p of pts.filter((p) => p.champion))
      svg.append(s("circle", { cx: X(p.x), cy: Y(p.y), r: 10, style: { fill: "none", stroke: "var(--text-primary)", strokeWidth: 1.5 } }));
    const marks = [];
    for (const p of pts) {
      const c = s("circle", { cx: X(p.x), cy: Y(p.y), r: 5, class: "pt", "data-id": p.id,
        style: p.holdout
          ? { fill: "var(--series-1)", stroke: "var(--surface-1)", strokeWidth: 2, paintOrder: "stroke" }
          : { fill: "var(--surface-1)", stroke: "var(--series-1)", strokeWidth: 2 } });
      marks.push(c);
      svg.append(c);
    }
    // selective direct labels: champion + frontier
    // try right, left, above, below; skip a label that would collide (tooltip + table carry it)
    const boxes = pts.map((p) => ({ x0: X(p.x) - 7, x1: X(p.x) + 7, y0: Y(p.y) - 7, y1: Y(p.y) + 7 }));
    const hitAny = (b) => b.x0 < 0 || b.x1 > W || b.y0 < 0 || b.y1 > H - m.b ||
      boxes.some((o) => b.x0 < o.x1 && b.x1 > o.x0 && b.y0 < o.y1 && b.y1 > o.y0);
    const labelled = pts.filter((p) => p.champion || p.pareto).sort((a, b) => (b.champion ? 1 : 0) - (a.champion ? 1 : 0));
    for (const p of labelled) {
      const px = X(p.x), py = Y(p.y);
      const label = (p.champion ? "★ " : "") + p.id;
      const tw = label.length * (p.champion ? 7 : 6.4);
      const cands = [
        { x: px + 13, y: py + 4, a: "start", b: { x0: px + 12, x1: px + 14 + tw, y0: py - 8, y1: py + 7 } },
        { x: px - 13, y: py + 4, a: "end", b: { x0: px - 14 - tw, x1: px - 12, y0: py - 8, y1: py + 7 } },
        { x: px, y: py - 14, a: "middle", b: { x0: px - tw / 2, x1: px + tw / 2, y0: py - 26, y1: py - 10 } },
        { x: px, y: py + 22, a: "middle", b: { x0: px - tw / 2, x1: px + tw / 2, y0: py + 10, y1: py + 26 } },
      ];
      const c = cands.find((c) => !hitAny(c.b));
      if (!c) continue;
      boxes.push(c.b);
      svg.append(s("text", { x: c.x, y: c.y, "text-anchor": c.a, class: (p.champion ? "lbl-strong" : "lbl") + " halo" }, label));
    }
    // hover layer: nearest point within 36px
    const hl = s("circle", { r: 8, style: { fill: "none", stroke: "var(--text-primary)", strokeWidth: 2, display: "none", pointerEvents: "none" } });
    svg.append(hl);
    const hit = s("rect", { x: 0, y: 0, width: W, height: H, style: { fill: "transparent" } });
    svg.append(hit);
    const near = (ev) => {
      const r = svg.getBoundingClientRect(), sx = W / r.width;
      const mx = (ev.clientX - r.left) * sx, my = (ev.clientY - r.top) * sx;
      let best = null, bd = 36 * 36;
      for (const p of pts) { const d = (X(p.x) - mx) ** 2 + (Y(p.y) - my) ** 2; if (d < bd) { bd = d; best = p; } }
      return best;
    };
    const move = (ev) => {
      const p = near(ev);
      if (!p) { hl.style.display = "none"; return hideTip(); }
      hl.setAttribute("cx", X(p.x)); hl.setAttribute("cy", Y(p.y)); hl.style.display = "";
      showTip(ev.clientX, ev.clientY, p.id, p.rows);
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerdown", move);
    hit.addEventListener("pointerleave", () => { hl.style.display = "none"; hideTip(); });
    box.append(svg);
  });
}

// ---------- line chart (one y-axis; small multiples) ----------
/** xs: labels; series: [{name, color, values:[number|null]}] */
export function lineChart(container, xs, series, { yFmt = f3, height = 170, yMin, yMax, zeroBased = false } = {}) {
  const all = series.flatMap((sr) => sr.values).filter(isNum);
  if (!all.length) return container.append(h("div", { class: "empty" }, "No data yet."));
  return mount(container, (box, W) => {
    const H = height, m = { l: 46, r: 46, t: 10, b: 26 };
    let lo = yMin ?? Math.min(...all), hi = yMax ?? Math.max(...all);
    if (zeroBased) lo = Math.min(0, lo);
    if (hi === lo) { hi = hi + (Math.abs(hi) * 0.1 || 0.1); lo = zeroBased ? lo : lo - (Math.abs(lo) * 0.1 || 0.1); lo = Math.max(lo, zeroBased ? 0 : -Infinity); }
    const ticks = linTicks(lo, hi, 3);
    lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
    const n = xs.length;
    const X = (i) => (n === 1 ? (m.l + W - m.r) / 2 : m.l + (i / (n - 1)) * (W - m.l - m.r));
    const Y = (v) => m.t + (1 - (v - lo) / (hi - lo || 1)) * (H - m.t - m.b);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": series.map((x) => x.name).join(", ") });
    for (const t of ticks) {
      svg.append(s("line", { class: "gridline", x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
      svg.append(s("text", { x: m.l - 6, y: Y(t) + 4, "text-anchor": "end" }, yFmt(t)));
    }
    svg.append(s("line", { class: "axis", x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b }));
    const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor((W - m.l - m.r) / 64))));
    xs.forEach((x, i) => {
      if (i % every === 0 || i === n - 1)
        if (!(i !== n - 1 && n - 1 - i < every))
          svg.append(s("text", { x: X(i), y: H - 8, "text-anchor": n === 1 ? "middle" : i === 0 ? "start" : i === n - 1 ? "end" : "middle" }, x));
    });
    const ends = [];
    for (const sr of series) {
      let d = "", pen = false;
      sr.values.forEach((v, i) => {
        if (!isNum(v)) { pen = false; return; }
        d += `${pen ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`; pen = true;
      });
      if (d) svg.append(s("path", { d, style: { fill: "none", stroke: sr.color, strokeWidth: 2, strokeLinejoin: "round", strokeLinecap: "round" } }));
      // isolated points get a marker so a single run is visible
      sr.values.forEach((v, i) => {
        const iso = isNum(v) && !isNum(sr.values[i - 1]) && !isNum(sr.values[i + 1]);
        if (iso) svg.append(s("circle", { cx: X(i), cy: Y(v), r: 4, style: { fill: sr.color, stroke: "var(--surface-1)", strokeWidth: 2 } }));
      });
      // end dot + value label (labels skipped below if they would collide)
      let li = -1; sr.values.forEach((v, i) => { if (isNum(v)) li = i; });
      if (li >= 0) {
        svg.append(s("circle", { cx: X(li), cy: Y(sr.values[li]), r: 4, style: { fill: sr.color, stroke: "var(--surface-1)", strokeWidth: 2 } }));
        ends.push({ x: X(li), y: Y(sr.values[li]), t: yFmt(sr.values[li]) });
      }
    }
    const clash = ends.some((a, i) => ends.some((b, j) => j > i && Math.abs(a.x - b.x) < 40 && Math.abs(a.y - b.y) < 13));
    if (!clash) for (const e of ends) svg.append(s("text", { x: e.x + 8, y: e.y + 4, class: "lbl halo" }, e.t));
    // crosshair + tooltip
    const cross = s("line", { y1: m.t, y2: H - m.b, style: { stroke: "var(--baseline)", strokeWidth: 1, display: "none" } });
    svg.append(cross);
    const dots = series.map((sr) => { const c = s("circle", { r: 4, style: { fill: sr.color, stroke: "var(--surface-1)", strokeWidth: 2, display: "none" } }); svg.append(c); return c; });
    const hit = s("rect", { x: 0, y: 0, width: W, height: H, style: { fill: "transparent" } });
    svg.append(hit);
    const move = (ev) => {
      const r = svg.getBoundingClientRect(), mx = (ev.clientX - r.left) * (W / r.width);
      const i = n === 1 ? 0 : Math.max(0, Math.min(n - 1, Math.round(((mx - m.l) / (W - m.l - m.r)) * (n - 1))));
      cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.style.display = "";
      series.forEach((sr, k) => {
        const v = sr.values[i];
        if (isNum(v)) { dots[k].setAttribute("cx", X(i)); dots[k].setAttribute("cy", Y(v)); dots[k].style.display = ""; }
        else dots[k].style.display = "none";
      });
      showTip(ev.clientX, ev.clientY, xs[i], series.map((sr) => [sr.name, isNum(sr.values[i]) ? yFmt(sr.values[i]) : "—"]));
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerdown", move);
    hit.addEventListener("pointerleave", () => { cross.style.display = "none"; dots.forEach((d) => (d.style.display = "none")); hideTip(); });
    box.append(svg);
  });
}

export function legend(items) {
  return h("div", { class: "legend" }, items.map((it) => h("span", { class: "key" },
    it.kind === "hollow" ? svgKey((g) => g.append(s("circle", { cx: 6, cy: 6, r: 4, style: { fill: "var(--surface-1)", stroke: it.color, strokeWidth: 2 } })))
      : it.kind === "dot" ? svgKey((g) => g.append(s("circle", { cx: 6, cy: 6, r: 5, style: { fill: it.color } })))
      : it.kind === "ring" ? svgKey((g) => g.append(s("circle", { cx: 6, cy: 6, r: 5, style: { fill: "none", stroke: it.color, strokeWidth: 1.5 } })))
      : svgKey((g) => g.append(s("line", { x1: 0, x2: 14, y1: 6, y2: 6, style: { stroke: it.color, strokeWidth: 2, strokeLinecap: "round", opacity: it.opacity ?? 1 } }))),
    it.label)));
}
function svgKey(fn) { const g = s("svg", { width: 14, height: 12, viewBox: "0 0 14 12", "aria-hidden": "true" }); fn(g); return g; }

// ---------- horizontal bars (one series) ----------
export function hbars(container, rows, { fmt = (v) => String(v) } = {}) {
  if (!rows.length) return container.append(h("div", { class: "empty" }, "No data yet."));
  return mount(container, (box, W) => {
    const lw = Math.min(170, Math.floor(W * 0.38)), bh = 16, gap = 10, H = rows.length * (bh + gap) + 4;
    const max = Math.max(...rows.map((r) => r.value)) || 1;
    const vw = 44, x0 = lw + 8, span = W - x0 - vw;
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": "bar chart" });
    svg.append(s("line", { class: "axis", x1: x0, x2: x0, y1: 0, y2: H }));
    rows.forEach((r, i) => {
      const y = i * (bh + gap) + 2, w = Math.max(2, (r.value / max) * span);
      svg.append(s("text", { x: lw, y: y + bh / 2 + 4, "text-anchor": "end", class: "lbl" }, r.label));
      const rr = Math.min(4, w);
      const p = s("path", { d: `M${x0},${y}h${w - rr}a${rr},${rr} 0 0 1 ${rr},${rr}v${bh - 2 * rr}a${rr},${rr} 0 0 1 -${rr},${rr}h-${w - rr}z`,
        style: { fill: "var(--series-1)" } });
      svg.append(p);
      svg.append(s("text", { x: x0 + w + 6, y: y + bh / 2 + 4, class: "lbl" }, fmt(r.value)));
      const hit = s("rect", { x: 0, y: y - gap / 2, width: W, height: bh + gap, style: { fill: "transparent" } });
      hit.addEventListener("pointermove", (ev) => showTip(ev.clientX, ev.clientY, r.label, [["value", fmt(r.value)]]));
      hit.addEventListener("pointerleave", hideTip);
      svg.append(hit);
    });
    box.append(svg);
  });
}
