"""A schema-aware fake model for offline tests and dry runs.

It answers whatever JSON schema the request asks for, deterministically, from a hash of
the request. Quotes are copied from the evidence passages in the prompt, so they verify.
`bias` makes one model alias right more often than another, for orchestrator tests.
"""

from __future__ import annotations

import hashlib
import re

from lab.clients.base import Request

EV_RE = re.compile(r"\[(ev\d+)\][^\n]*\n([^\n]+)")
CLAIM_RE = re.compile(r"^Claim: (.+)$", re.M)


def _h(*parts: object) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


class SchemaResponder:
    def __init__(self, accuracy: dict[str, float] | None = None,
                 gold: dict[str, str] | None = None):
        self.accuracy = accuracy or {}     # model_id -> P(correct) when gold is known
        self.gold = gold or {}             # claim text -> gold label

    def __call__(self, req: Request, model_id: str) -> dict:
        text = req.messages[-1]["content"]
        text = text if isinstance(text, str) else str(text)
        props = (req.json_schema or {}).get("properties", {})
        seed = _h(model_id, req.sample, text)
        evs = EV_RE.findall(text)
        ids = [e for e, _ in evs]
        if "verdict" in props:
            labels = props["verdict"]["enum"]
            m = CLAIM_RE.search(text)
            gold = self.gold.get(m.group(1).strip()) if m else None
            p = self.accuracy.get(model_id, 0.5)
            if gold in labels and (seed % 1000) / 1000 < p:
                v = gold
            else:
                v = labels[seed % len(labels)]
            out = {"verdict": v, "confidence": 0.55 + (seed % 40) / 100,
                   "rationale": f"The evidence points to {v.replace('_', ' ')}.",
                   "reasons": ["Main source says so", "Dates line up"],
                   "cites": ids[:2],
                   "stances": [{"ev": e, "stance": ["supports", "refutes", "neutral"][
                       _h(seed, e) % 3]} for e in ids]}
            if "end_debate" in props:
                out["end_debate"] = False
            return out
        if "argument" in props:
            quotes = []
            if evs:
                ev, passage = evs[seed % len(evs)]
                words = passage.split()
                if len(words) >= 8:
                    quotes.append({"ev": ev, "text": " ".join(words[:8])})
            return {"argument": f"Argument {seed % 97} grounded in the sources.",
                    "cites": ids[:1], "quotes": quotes, "belief": (seed % 100) / 100,
                    "stances": [{"ev": e, "stance": "neutral"} for e in ids]}
        if "choice" in props:
            return {"choice": 1}
        if "summary" in props:
            return {"summary": "Panelists split; the strongest reason cites the main source."}
        if "grades" in props:
            return {"grades": [{"ev": e, "stance": ["supports", "refutes", "neutral"][
                _h(seed, e) % 3], "strength": 0.4 + (_h(e, seed) % 60) / 100} for e in ids]}
        return {}
