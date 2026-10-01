"""Protocol engine: runs one protocol on one item and produces a transcript (spec §5).

    engine = Engine(gateway, retriever)
    transcript = engine.run_item(protocol, item, scope)

Each pattern in lab.protocols.schema.PATTERNS has a runner below. Every model call goes
through the Gateway, so it is cached, estimated, cap-checked and metered.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from lab.clients.base import Request, Response
from lab.clients.gateway import Gateway
from lab.clients.meter import BudgetExceeded, Scope
from lab.evidence import quotes as quote_check
from lab.protocols import prompts as P
from lab.protocols.schema import validate_transcript

AFFIRM_LABEL, DENY_LABEL = "supported", "refuted"
DEFAULT_MAX_TOKENS = 2000       # room for adaptive thinking at low effort
ARG_WORDS = 120


class ProtocolError(RuntimeError):
    pass


@dataclass
class Vote:
    agent: str
    model: str
    verdict: str | None
    confidence: float
    weight: float = 1.0
    data: dict = field(default_factory=dict)


@dataclass
class Run:
    """Mutable state for one protocol run on one item."""
    protocol: dict
    item: dict
    scope: Scope
    evidence: list[dict]
    turns: list[dict] = field(default_factory=list)
    agreement: list[float] = field(default_factory=list)
    stance: dict[str, dict[str, str]] = field(default_factory=lambda: defaultdict(dict))
    usd: float = 0.0

    @property
    def label_set(self) -> list[str]:
        return self.item["label_set"]

    @property
    def rationale_words(self) -> int:
        return self.protocol.get("output", {}).get("rationale_words", 60)


def _clamp01(x: Any, default: float = 0.5) -> float:
    try:
        return min(1.0, max(0.0, float(x)))
    except (TypeError, ValueError):
        return default


def _words(s: str, n: int) -> str:
    w = (s or "").split()
    return " ".join(w[:n])


def _family(cfg, alias: str) -> str:
    try:
        return cfg.model(alias).get("family", alias)
    except Exception:
        return alias


def _seed_int(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)


class Engine:
    def __init__(self, gateway: Gateway, retriever=None):
        self.gw = gateway
        self.retriever = retriever

    # ------------------------------------------------------------------ public API
    def run_item(self, protocol: dict, item: dict, scope: Scope,
                 experiment: str = "adhoc") -> dict:
        cap = self.item_cap(protocol)
        iscope = scope.child(item["id"], cap)
        t0 = time.monotonic()
        error = None
        run = Run(protocol, item, iscope, evidence=[])
        try:
            run.evidence = self._evidence(protocol, item, iscope)
            verdict, conf, rationale, reasons = getattr(self, f"_p_{protocol['pattern']}")(run)
        except BudgetExceeded as e:
            if not e.cap.startswith("item:"):
                raise                      # day/month/experiment caps halt the whole run
            verdict, conf, rationale, reasons = "abstain", 0.0, "", []
            error = f"item budget exceeded: {e}"
        t = {
            "experiment": experiment, "protocol": protocol["id"], "item": item["id"],
            "split": item.get("split") if item.get("split") in ("dev", "holdout") else None,
            "question": item["text"], "label_set": run.label_set, "gold": item.get("gold"),
            "evidence": [self._public_ev(ev, run) for ev in run.evidence],
            "turns": run.turns, "agreement": [round(a, 3) for a in run.agreement],
            "verdict": verdict, "confidence": round(_clamp01(conf, 0.0), 4),
            "rationale": _words(rationale, run.rationale_words),
            "reasons": [_words(r, 14) for r in reasons[:2]],
            "usd": round(iscope.spent.get(f"item:{item['id']}", 0.0), 6),
            "latency_s": round(time.monotonic() - t0, 3), "error": error,
        }
        if t["split"] is None:
            t.pop("split")
        return validate_transcript(t)

    def item_cap(self, protocol: dict) -> float:
        cap = self.gw.cfg.cap("max_usd_per_item")
        p = protocol.get("budget", {}).get("max_usd_per_item")
        return min(cap, p) if p else cap

    # ------------------------------------------------------------------ evidence
    def _evidence(self, protocol: dict, item: dict, scope: Scope) -> list[dict]:
        ev = protocol.get("evidence", {})
        if not ev.get("retrieve"):
            return []
        if self.retriever is None:
            raise ProtocolError(f"{protocol['id']} needs evidence but no retriever configured")
        return self.retriever.retrieve(item, ev.get("max_sources", 6), scope)

    @staticmethod
    def _public_ev(ev: dict, run: Run) -> dict:
        return {"id": ev["id"], "url": ev["url"], "title": ev.get("title", ""),
                "published": ev.get("published"), "excerpt": ev["excerpt"],
                "stance": dict(run.stance.get(ev["id"], {}))}

    # ------------------------------------------------------------------ prompt pieces
    @staticmethod
    def claim_block(item: dict) -> str:
        parts = [f"Claim: {item['text']}"]
        if item.get("context"):
            parts.append(f"Context: {item['context']}")
        if item.get("date"):
            parts.append(f"Claim date: {item['date']}")
        return "\n".join(parts)

    @staticmethod
    def evidence_block(evidence: list[dict]) -> str:
        if not evidence:
            return "No retrieved evidence is available; rely on well-established knowledge."
        lines = ["Evidence:"]
        for e in evidence:
            src = e.get("domain") or e["url"]
            date = f", {e['published']}" if e.get("published") else ""
            lines.append(f"[{e['id']}] {e.get('title', '')} ({src}{date})\n"
                         f"{e.get('passage') or e['excerpt']}")
        return "\n".join(lines) + "\n"

    def prompt(self, run: Run, key: str, **kw: Any) -> str:
        tmpl = run.protocol.get("prompts", {}).get(key, P.DEFAULTS[key])
        base = {"claim_block": self.claim_block(run.item),
                "evidence_block": self.evidence_block(run.evidence),
                "labels": P.labels_text(run.label_set),
                "rationale_words": run.rationale_words, "arg_words": ARG_WORDS,
                "quote_words": run.protocol.get("quotes", {}).get("max_words", 30)}
        base.update(kw)
        return tmpl.format(**base)

    # ------------------------------------------------------------------ calls
    def call(self, run: Run, agent: dict, name: str, text: str, schema: dict,
             sample: int = 0, rnd: int = 0, record: bool = True) -> Response:
        req = Request(model=agent["model"], system=P.SYSTEM, sample=sample,
                      messages=[{"role": "user", "content": text}], json_schema=schema,
                      max_tokens=run.protocol.get("max_tokens", DEFAULT_MAX_TOKENS),
                      effort=agent.get("effort"))
        resp = self.gw.call(req, run.scope)
        run.usd += resp.usd
        if record:
            d = resp.data if isinstance(resp.data, dict) else {}
            body = d.get("argument") or d.get("rationale") or d.get("summary") or ""
            if not body and d.get("grades"):
                body = "; ".join(f"{g['ev']} {g['stance']}" for g in d["grades"])
            run.turns.append({
                "n": len(run.turns) + 1, "round": rnd, "agent": name, "model": agent["model"],
                "family": _family(self.gw.cfg, agent["model"]), "text": body,
                "position": d.get("verdict") or agent.get("side"),
                "belief": _clamp01(d["belief"]) if "belief" in d else None,
                "cites": [c for c in d.get("cites", []) if isinstance(c, str)],
                "quotes": d.get("quotes", []), "tokens": resp.tokens,
                "usd": round(resp.usd, 6), "cached": resp.cached, "refused": resp.refused,
            })
        self._stances(run, agent["model"], resp.data)
        return resp

    @staticmethod
    def _stances(run: Run, model: str, data: Any) -> None:
        if not isinstance(data, dict):
            return
        ids = {e["id"] for e in run.evidence}
        for s in data.get("stances", []) + data.get("grades", []):
            if isinstance(s, dict) and s.get("ev") in ids and s.get("stance") in P.STANCE_ITEM[
                    "properties"]["stance"]["enum"]:
                run.stance[s["ev"]][model] = s["stance"]

    def answer(self, run: Run, agent: dict, name: str, text: str, sample: int = 0,
               rnd: int = 0, end_option: bool = False) -> Vote:
        resp = self.call(run, agent, name, text, P.answer_schema(run.label_set, end_option),
                         sample=sample, rnd=rnd)
        d = resp.data if isinstance(resp.data, dict) else {}
        v = d.get("verdict") if d.get("verdict") in run.label_set else None
        return Vote(name, agent["model"], v, _clamp01(d.get("confidence")),
                    float(agent.get("weight", 1.0)), d)

    # ------------------------------------------------------------------ aggregation
    def aggregate(self, run: Run, votes: list[Vote], rule: str) -> tuple[str, float]:
        valid = [v for v in votes if v.verdict]
        if not valid:
            return "abstain", 0.0
        labels = run.label_set
        if rule in ("majority", "judge"):
            c = Counter(v.verdict for v in valid)
            top = max(c.values())
            tied = [lab for lab, n in c.items() if n == top]
            if len(tied) > 1:   # break ties by summed confidence
                tied.sort(key=lambda lab: -sum(v.confidence for v in valid if v.verdict == lab))
            winner = tied[0]
            return winner, top / len(valid)
        if rule in ("weighted", "mean_prob"):
            k = len(labels)
            dist = dict.fromkeys(labels, 0.0)
            total = 0.0
            for v in valid:
                w = v.weight * (v.confidence if rule == "weighted" else 1.0)
                for lab in labels:
                    p = v.confidence if lab == v.verdict else (1 - v.confidence) / (k - 1)
                    dist[lab] += w * p
                total += w
            if total == 0:
                return self.aggregate(run, votes, "majority")
            winner = max(labels, key=lambda lab: dist[lab])
            return winner, dist[winner] / total
        raise ProtocolError(f"aggregation {rule!r} not supported for this pattern")

    @staticmethod
    def plurality_share(votes: list[Vote]) -> float:
        vs = [v.verdict for v in votes if v.verdict]
        return Counter(vs).most_common(1)[0][1] / len(vs) if vs else 0.0

    @staticmethod
    def best_rationale(votes: list[Vote], verdict: str) -> tuple[str, list[str]]:
        side = [v for v in votes if v.verdict == verdict] or votes
        best = max(side, key=lambda v: v.confidence)
        return best.data.get("rationale", ""), best.data.get("reasons", [])

    # ================================================================== patterns
    def _p_single(self, run: Run):
        a = run.protocol["agents"][0]
        v = self.answer(run, a, a.get("name", "answerer"), self.prompt(run, "answer"))
        run.agreement.append(1.0 if v.verdict else 0.0)
        return v.verdict or "abstain", v.confidence, v.data.get("rationale", ""), \
            v.data.get("reasons", [])

    def _p_sample_vote(self, run: Run):
        a = run.protocol["agents"][0]
        n = a.get("samples", 5)
        votes = [self.answer(run, a, f"{a.get('name', 'sample')}-{i + 1}",
                             self.prompt(run, "answer"), sample=i) for i in range(n)]
        verdict, share = self.aggregate(run, votes, "majority")
        run.agreement.append(self.plurality_share(votes))
        rat, reasons = self.best_rationale(votes, verdict)
        return verdict, share, rat, reasons

    def _p_panel(self, run: Run):
        agents = run.protocol["agents"]
        votes = [self.answer(run, a, a.get("name", f"panelist-{i + 1}"),
                             self.prompt(run, "answer"), sample=i)
                 for i, a in enumerate(agents)]
        verdict, conf = self.aggregate(run, votes, run.protocol["aggregation"])
        run.agreement.append(self.plurality_share(votes))
        rat, reasons = self.best_rationale(votes, verdict)
        return verdict, conf, rat, reasons

    def _p_society(self, run: Run):
        p = run.protocol
        agents = p["agents"]
        names = [a.get("name", f"agent-{i + 1}") for i, a in enumerate(agents)]
        votes = [self.answer(run, a, names[i], self.prompt(run, "answer"), sample=i, rnd=0)
                 for i, a in enumerate(agents)]
        run.agreement.append(self.plurality_share(votes))
        es = p.get("early_stop", {})
        for r in range(1, p.get("rounds", 2) + 1):
            if es.get("agree") and r > es.get("min_rounds", 1) - 1 and \
                    self.plurality_share(votes) == 1.0:
                break
            summary = None
            if p.get("communication") == "simultaneous_summarizer":
                summary = self._summarize(run, agents[0], votes, r)
            new = []
            for i, a in enumerate(agents):
                peers = summary or "\n".join(
                    f"- {names[j]}: {v.verdict} ({v.confidence:.2f}). {v.data.get('rationale', '')}"
                    for j, v in enumerate(votes) if j != i)
                own = f"{votes[i].verdict} ({votes[i].confidence:.2f}). " \
                      f"{votes[i].data.get('rationale', '')}"
                text = self.prompt(run, "revise", own=own, peers=peers,
                                   intensity=P.intensity_text(p.get("agreement_intensity")))
                new.append(self.answer(run, a, names[i], text, sample=i, rnd=r))
            votes = new
            run.agreement.append(self.plurality_share(votes))
        rule = p["aggregation"] if p["aggregation"] != "judge" else "majority"
        verdict, conf = self.aggregate(run, votes, rule)
        rat, reasons = self.best_rationale(votes, verdict)
        return verdict, conf, rat, reasons

    def _summarize(self, run: Run, agent: dict, votes: list[Vote], rnd: int) -> str:
        summ = next((a for a in run.protocol["agents"] if a["role"] == "summarizer"), agent)
        disc = "\n".join(f"- {v.agent}: {v.verdict} ({v.confidence:.2f}). "
                         f"{v.data.get('rationale', '')}" for v in votes)
        resp = self.call(run, summ, "summarizer", self.prompt(run, "summarize", discussion=disc),
                         P.SUMMARY_SCHEMA, rnd=rnd)
        return (resp.data or {}).get("summary", disc) if isinstance(resp.data, dict) else disc

    # ---- debate and consultancy ------------------------------------------------------
    def _judge_view(self, run: Run) -> tuple[str, str, str]:
        """(judge_evidence, judge_view, sees) per evidence.judge_sees."""
        sees = run.protocol.get("evidence", {}).get("judge_sees", "full")
        if sees == "full" or not run.evidence:
            return self.evidence_block(run.evidence), \
                "You can see the evidence and the debate.", "full"
        if sees == "quotes":
            return "", ("You cannot see the evidence. You see only the debate, plus quotes the "
                        "debaters cite. Quotes marked VERIFIED were checked word for word "
                        "against the source; UNVERIFIED quotes may be fabricated."), "quotes"
        return "", "You cannot see any evidence. You see only the debate.", "none"

    def _verify_quotes(self, run: Run, turn: dict) -> None:
        maxw = run.protocol.get("quotes", {}).get("max_words", 30)
        by_id = {e["id"]: e for e in run.evidence}
        checked = []
        for q in turn.get("quotes", []):
            if not isinstance(q, dict):
                continue
            ev = by_id.get(q.get("ev"))
            text = None
            if ev is not None:
                text = self.retriever.page_text(ev["url"]) if self.retriever else None
                text = text or ev.get("passage")
            ok, why = quote_check.verify(q.get("text", ""), text, maxw)
            checked.append({"ev": q.get("ev"), "text": _words(q.get("text", ""), maxw),
                            "verified": ok, "why": why})
        turn["quotes"] = checked

    def _debate_text(self, run: Run, sees: str) -> str:
        lines = []
        for t in run.turns:
            if t["agent"].startswith(("advocate", "consultant")):
                lines.append(f"[round {t['round']}] {t['agent']}: {t['text']}")
                if sees == "quotes":
                    for q in t.get("quotes", []):
                        tag = "VERIFIED" if q.get("verified") else "UNVERIFIED"
                        lines.append(f'    {tag} quote [{q["ev"]}]: "{q["text"]}"')
        return "\n".join(lines) or "(no arguments yet)"

    def _argue(self, run: Run, agent: dict, name: str, key: str, position: str,
               side_name: str, rnd: int, judge: dict) -> dict:
        sees = run.protocol.get("evidence", {}).get("judge_sees", "full")
        text = self.prompt(run, key, side_name=side_name, position=position,
                           debate=self._debate_text(run, "quotes"))
        n = run.protocol.get("best_of_n", 1)
        if n <= 1:
            self.call(run, agent, name, text, P.ADVOCATE_SCHEMA, rnd=rnd)
        else:
            drafts = [self.call(run, agent, name, text, P.ADVOCATE_SCHEMA, sample=i, rnd=rnd,
                                record=False) for i in range(n)]
            listing = "\n\n".join(f"#{i + 1}: {(d.data or {}).get('argument', '')}"
                                  for i, d in enumerate(drafts))
            sel = self.call(run, judge, "selector", self.prompt(
                run, "select", n=n, side_name=side_name, drafts=listing), P.SELECT_SCHEMA,
                rnd=rnd, record=False)
            idx = int((sel.data or {}).get("choice", 1)) - 1 if isinstance(sel.data, dict) else 0
            best = drafts[idx if 0 <= idx < n else 0]
            d = best.data if isinstance(best.data, dict) else {}
            run.turns.append({
                "n": len(run.turns) + 1, "round": rnd, "agent": name, "model": agent["model"],
                "family": _family(self.gw.cfg, agent["model"]),
                "text": d.get("argument", ""), "position": agent.get("side"),
                "belief": _clamp01(d.get("belief")) if "belief" in d else None,
                "cites": d.get("cites", []), "quotes": d.get("quotes", []),
                "tokens": sum(x.tokens for x in drafts) + sel.tokens,
                "usd": round(sum(x.usd for x in drafts) + sel.usd, 6),
                "cached": all(x.cached for x in drafts), "refused": best.refused,
                "best_of": n})
        turn = run.turns[-1]
        if sees == "quotes" or run.protocol.get("quotes", {}).get("verify"):
            self._verify_quotes(run, turn)
        return turn

    def _rule(self, run: Run, judge: dict, rnd: int, end_option: bool = False) -> Vote:
        judge_ev, view, sees = self._judge_view(run)
        hint = (" Also set end_debate to true if the debate has already settled the question."
                if end_option else "")
        text = self.prompt(run, "judge", judge_evidence=judge_ev, judge_view=view,
                           debate="Debate transcript:\n" + self._debate_text(run, sees),
                           end_hint=hint)
        return self.answer(run, judge, "judge", text, rnd=rnd, end_option=end_option)

    def _p_debate(self, run: Run):
        p = run.protocol
        judge = next(a for a in p["agents"] if a["role"] == "judge")
        advs = [a for a in p["agents"] if a["role"] == "advocate"]
        rounds = max(1, p.get("rounds", 2))
        es = p.get("early_stop", {})
        for r in range(1, rounds + 1):
            beliefs = {}
            for i, a in enumerate(advs):
                side = a["side"]
                name = f"advocate-{side}" + (f"-{i + 1}" if len(advs) > 2 else "")
                pos = "the claim is TRUE" if side == "affirm" else "the claim is FALSE"
                t = self._argue(run, a, name, "advocate", pos, side, r, judge)
                if t.get("belief") is not None:
                    beliefs.setdefault(side, []).append(t["belief"])
            if beliefs.get("affirm") and beliefs.get("deny"):
                ba = sum(beliefs["affirm"]) / len(beliefs["affirm"])
                bd = sum(beliefs["deny"]) / len(beliefs["deny"])
                run.agreement.append(1 - abs(ba - bd))
            if r < rounds and es.get("agree") and run.agreement and run.agreement[-1] >= 0.85:
                break
            if r < rounds and es.get("judge_can_end") and r >= es.get("min_rounds", 1):
                v = self._rule(run, judge, r, end_option=True)
                if v.data.get("end_debate") and v.verdict:
                    return v.verdict, v.confidence, v.data.get("rationale", ""), \
                        v.data.get("reasons", [])
        v = self._rule(run, judge, rounds + 1)
        return v.verdict or "abstain", v.confidence, v.data.get("rationale", ""), \
            v.data.get("reasons", [])

    def _p_consultancy(self, run: Run):
        p = run.protocol
        judge = next(a for a in p["agents"] if a["role"] == "judge")
        cons = next(a for a in p["agents"] if a["role"] == "consultant")
        # Michael et al.: the consultant is assigned the correct or incorrect side at random.
        side = cons.get("side") or ("affirm" if _seed_int(run.item["id"], p["id"]) % 2
                                    else "deny")
        pos = "TRUE" if side == "affirm" else "FALSE"
        agent = dict(cons, side=side)
        for r in range(1, max(1, p.get("rounds", 2)) + 1):
            self._argue(run, agent, "consultant", "consultant", pos, side, r, judge)
        v = self._rule(run, judge, p.get("rounds", 2) + 1)
        run.agreement.append(v.confidence)
        return v.verdict or "abstain", v.confidence, v.data.get("rationale", ""), \
            v.data.get("reasons", [])

    # ---- persona panels (ChatEval) ---------------------------------------------------
    def _p_chateval(self, run: Run):
        p = run.protocol
        judges = [a for a in p["agents"] if a["role"] == "judge"]
        mode = p.get("communication", "one_by_one")
        rounds = max(1, p.get("rounds", 2))
        names = [a.get("name", f"judge-{i + 1}") for i, a in enumerate(judges)]
        history: list[str] = []
        votes: list[Vote] = []
        for r in range(1, rounds + 1):
            this_round: list[Vote] = []
            for i, a in enumerate(judges):
                seen = list(history)
                if mode == "one_by_one":
                    seen += [f"- {v.agent}: {v.verdict} ({v.confidence:.2f}). "
                             f"{v.data.get('rationale', '')}" for v in this_round]
                text = self.prompt(run, "persona_judge",
                                   persona=a.get("persona", "a careful, neutral fact-checker"),
                                   discussion="\n".join(seen) or "(you speak first)")
                this_round.append(self.answer(run, a, names[i], text, sample=i, rnd=r))
            votes = this_round
            run.agreement.append(self.plurality_share(votes))
            if mode == "simultaneous_summarizer":
                history = [f"Summary of round {r}: " + self._summarize(run, judges[0], votes, r)]
            else:
                history += [f"- {v.agent} (round {r}): {v.verdict} ({v.confidence:.2f}). "
                            f"{v.data.get('rationale', '')}" for v in votes]
        rule = p["aggregation"] if p["aggregation"] in ("majority", "weighted", "mean_prob") \
            else "majority"
        verdict, conf = self.aggregate(run, votes, rule)
        rat, reasons = self.best_rationale(votes, verdict)
        return verdict, conf, rat, reasons

    # ---- evidence-first ----------------------------------------------------------------
    def _p_evidence_first(self, run: Run):
        if not run.evidence:
            run.agreement.append(0.0)
            return ("not_enough_evidence" if "not_enough_evidence" in run.label_set
                    else "abstain"), 0.5, "No usable evidence was found.", \
                ["No evidence retrieved"]
        graders = run.protocol["agents"]
        per_grader = []
        for i, a in enumerate(graders):
            resp = self.call(run, a, a.get("name", f"grader-{i + 1}"),
                             self.prompt(run, "grade"), P.GRADE_SCHEMA, sample=i, rnd=1)
            grades = (resp.data or {}).get("grades", []) if isinstance(resp.data, dict) else []
            per_grader.append({g["ev"]: (g["stance"], _clamp01(g.get("strength")))
                               for g in grades if isinstance(g, dict) and "ev" in g})
        sup = ref = 0.0
        tallies: dict[str, list[float]] = defaultdict(list)
        for ev in run.evidence:
            for g in per_grader:
                stance, s = g.get(ev["id"], ("neutral", 0.0))
                tallies[ev["id"]].append(s if stance == "supports" else
                                         -s if stance == "refutes" else 0.0)
        for vals in tallies.values():
            m = sum(vals) / len(vals)
            sup += max(m, 0)
            ref += max(-m, 0)
        total = sup + ref
        labels = run.label_set
        if total < 0.5 and "not_enough_evidence" in labels:
            verdict, conf = "not_enough_evidence", 0.6
        elif min(sup, ref) / max(total, 1e-9) > 0.35 and "conflicting" in labels:
            verdict, conf = "conflicting", 0.5 + min(sup, ref) / (2 * total)
        else:
            verdict = AFFIRM_LABEL if sup >= ref else DENY_LABEL
            conf = 0.5 + abs(sup - ref) / (2 * total)
        signs = [1 if sum(v) > 0 else -1 if sum(v) < 0 else 0 for v in tallies.values()]
        nonzero = [s for s in signs if s]
        run.agreement.append(abs(sum(nonzero)) / len(nonzero) if nonzero else 0.0)
        top = sorted(run.evidence, key=lambda e: -abs(sum(tallies[e["id"]])))[:2]
        reasons = [f"{e.get('domain', 'source')}: {'supports' if sum(tallies[e['id']]) > 0 else 'refutes' if sum(tallies[e['id']]) < 0 else 'neutral'}"  # noqa: E501
                   for e in top]
        rationale = (f"{sum(1 for s in signs if s > 0)} sources support the claim and "
                     f"{sum(1 for s in signs if s < 0)} refute it, weighted by how strongly "
                     f"each grader read them.")
        return verdict, conf, rationale, reasons


def transcript_json(t: dict) -> bytes:
    return json.dumps(t, ensure_ascii=False, sort_keys=True).encode()
