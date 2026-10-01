"""Promotion rule (spec §6.2). Plain code; the experimenter never sees or runs this."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Decision:
    promoted: bool
    status: str                       # promoted | not_promoted
    label: str                        # better | worse | no detectable difference | initial
    reasons: list[str] = field(default_factory=list)


def decide(cand: dict, champ: dict | None, vs_champ: dict | None, cfg) -> Decision:
    """cand/champ: holdout score blocks {"full": score, "post_cutoff": score|None}.
    vs_champ: paired bootstrap of candidate minus champion on the full holdout."""
    pr = cfg.scoring["promotion"]
    cost_cap = cfg.cap("max_usd_per_item_champion")
    usd = cand["full"]["cost"]["usd_per_item_uncached"]
    reasons: list[str] = []
    cost_ok = usd <= cost_cap
    if not cost_ok:
        reasons.append(f"cost ${usd:.4f}/item exceeds champion cap ${cost_cap:.4f}")
    if champ is None:
        if cost_ok:
            return Decision(True, "promoted", "initial", ["first protocol evaluated on holdout"])
        return Decision(False, "not_promoted", "initial", reasons)
    assert vs_champ is not None
    lo, hi = vs_champ["ci"]
    label = "better" if lo > 0 else "worse" if hi < 0 else "no detectable difference"
    if lo <= 0:
        reasons.append(f"macro-F1 difference {vs_champ['diff']:+.3f}, 95% CI "
                       f"[{lo:+.3f}, {hi:+.3f}] does not exclude zero" if label != "worse" else
                       f"macro-F1 worse than champion ({vs_champ['diff']:+.3f})")
    pc_c, pc_h = cand.get("post_cutoff"), champ.get("post_cutoff")
    if pc_c and pc_h and pc_c.get("n") and pc_h.get("n"):
        drop = pc_h["macro_f1"] - pc_c["macro_f1"]
        if drop > pr["post_cutoff_tolerance"]:
            tol = pr["post_cutoff_tolerance"]
            reasons.append(f"post-cutoff macro-F1 drops {drop:.3f} (> {tol})")
    rise = cand["full"]["ece"] - champ["full"]["ece"]
    if rise > pr["ece_tolerance"]:
        reasons.append(f"ECE worsens by {rise:.3f} (> {pr['ece_tolerance']})")
    if reasons:
        return Decision(False, "not_promoted", label, reasons)
    return Decision(True, "promoted", label, ["all four promotion conditions hold"])
