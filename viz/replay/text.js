// Pure text helpers for the evidence replay. No DOM access, so they can be unit-tested in node.

export const MAX_EXCERPT_WORDS = 40;
export const MAX_RATIONALE_WORDS = 60;

const LABELS = {
  supported: "Supported",
  refuted: "Refuted",
  not_enough_evidence: "Not enough evidence",
  conflicting: "Conflicting / misleading",
  abstain: "Abstained",
};

// Hard cap on words. Anything over the cap is cut and ends with an ellipsis. A trailing
// ellipsis already in the data does not count as a word.
export function capWords(text, max = MAX_EXCERPT_WORDS) {
  const words = String(text ?? "").replace(/…+\s*$/, "").trim().split(/\s+/).filter(Boolean);
  if (words.length <= max) return words.join(" ");
  return words.slice(0, max).join(" ").replace(/[\s,;:.\-–—]+$/, "") + "…";
}

export function wordCount(text) {
  return String(text ?? "").replace(/…+\s*$/, "").trim().split(/\s+/).filter(Boolean).length;
}

export function labelName(label) {
  if (label == null) return "";
  const key = String(label).toLowerCase();
  if (LABELS[key]) return LABELS[key];
  const s = key.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// CSS class suffix for a verdict label's accent color.
export function labelTone(label) {
  const key = String(label ?? "").toLowerCase();
  if (key === "supported") return "sup";
  if (key === "refuted") return "ref";
  if (key === "conflicting") return "con";
  return "nee";
}

export function isVerdictLabel(position) {
  return position != null && String(position).toLowerCase() in LABELS;
}

export function domainOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return String(url ?? "").replace(/^[a-z]+:\/\//i, "").split("/")[0] || "source";
  }
}

const KNOWN_FAMILIES = ["claude", "grok", "gpt", "gemini", "llama", "mistral", "qwen", "deepseek"];

export function familyOf(turnOrModel) {
  if (turnOrModel && typeof turnOrModel === "object") {
    if (turnOrModel.family) return String(turnOrModel.family).toLowerCase();
    return familyOf(turnOrModel.model);
  }
  const m = String(turnOrModel ?? "").toLowerCase();
  return KNOWN_FAMILIES.find((f) => m.startsWith(f)) ?? (m.split(/[-_]/)[0] || "model");
}

// "advocate-affirm" -> "Advocate for", "panelist-2" -> "Panelist 2", "grader-1" -> "Grader 1".
export function agentName(agent) {
  const a = String(agent ?? "").trim();
  const low = a.toLowerCase();
  if (low === "advocate-affirm") return "Advocate · for the claim";
  if (low === "advocate-deny") return "Advocate · against the claim";
  const m = a.match(/^([a-z]+)[-_ ]?(\d+)$/i);
  if (m) return `${m[1].charAt(0).toUpperCase()}${m[1].slice(1)} ${m[2]}`;
  return a.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Agent";
}

export function positionText(position) {
  if (position == null) return null;
  const p = String(position).toLowerCase();
  if (p === "affirm") return "Argues true";
  if (p === "deny") return "Argues false";
  return labelName(p);
}

export function formatDate(iso) {
  if (!iso) return "Undated";
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric",
                                         timeZone: "UTC" });
}

export function pct(x) {
  return `${Math.round(Math.max(0, Math.min(1, Number(x) || 0)) * 100)}%`;
}

// Per-step durations (ms) for autoplay. A 5-turn debate with 4 sources lands near 28 s; long
// transcripts compress so the whole replay stays under ~40 s.
export function timing(nEvidence, nTurns) {
  const question = 2200;
  const evidence = Math.min(800, nEvidence ? 4200 / nEvidence : 800);
  const turn = Math.min(3600, Math.max(1300, nTurns ? 19000 / nTurns : 3600));
  const verdict = 5000;
  const total = question + evidence * nEvidence + turn * nTurns + verdict;
  return { question, evidence, turn, verdict, total };
}
