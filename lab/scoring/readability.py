"""Readability of the verdict rationale (spec §6.1.3). Track B.

Code measures: Flesch-Kincaid grade (target ≤ 9), length within the word limit, and a
jargon check. Plus a 1-5 clarity rubric from a cheap judge (config roles.rubric_judge).
None of these blend into Track A; they tune presentation only.
"""

from __future__ import annotations

import re

WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
SENT = re.compile(r"[.!?]+(?:\s|$)")
JARGON = {
    "epistemic", "heuristic", "heuristics", "adjudicate", "adjudicated", "aforementioned",
    "corroborate", "corroborated", "corroboration", "provenance", "veracity", "substantiate",
    "substantiated", "methodological", "methodology", "stance", "credence", "posterior",
    "prior", "calibrated", "macro-f1", "dataset", "confound", "confounded", "ipso", "facto",
    "prima", "facie", "viz", "i.e", "e.g", "ergo", "notwithstanding", "inter", "alia",
    "aggregation", "adjudication", "salient", "dispositive", "evidentiary",
}

RUBRIC_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["clarity", "why"],
                 "properties": {"clarity": {"type": "integer"}, "why": {"type": "string"}}}
RUBRIC_PROMPT = (
    "Rate how clearly this fact-check explanation would read to a general audience scrolling "
    "a social feed, from 1 (confusing) to 5 (instantly clear). Judge clarity only, not whether "
    "it's correct.\n\nClaim: {claim}\nVerdict: {verdict}\nExplanation: {rationale}")


def syllables(word: str) -> int:
    w = word.lower().strip("'-")
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def fk_grade(text: str) -> float:
    words = WORD.findall(text)
    if not words:
        return 0.0
    sents = max(1, len(SENT.findall(text.strip() + " ")))
    syl = sum(syllables(w) for w in words)
    return 0.39 * len(words) / sents + 11.8 * syl / len(words) - 15.59


def jargon(text: str) -> list[str]:
    toks = re.findall(r"[A-Za-z][A-Za-z.-]*[A-Za-z]", text.lower())
    return sorted({t for t in toks if t in JARGON or (len(t) >= 15 and "-" not in t)})


def code_scores(rationale: str, max_words: int = 60, max_grade: float = 9.0) -> dict:
    n = len(rationale.split())
    g = fk_grade(rationale)
    j = jargon(rationale)
    grade_ok = 1.0 if g <= max_grade else max(0.0, 1 - (g - max_grade) / 6)
    length_ok = 1.0 if 0 < n <= max_words else (0.0 if n == 0 else max(0.0, 1 - (n - max_words)
                                                                           / max_words))
    jargon_ok = max(0.0, 1 - len(j) / 3)
    return {"grade": round(g, 2), "words": n, "jargon": j, "grade_ok": grade_ok,
            "length_ok": length_ok, "jargon_ok": jargon_ok}


def rubric(gateway, transcript: dict, scope) -> dict:
    from lab.clients.base import Request
    alias = gateway.cfg.models.get("roles", {}).get("rubric_judge", "claude-haiku")
    r = gateway.call(Request(model=alias, max_tokens=400, json_schema=RUBRIC_SCHEMA,
                             messages=[{"role": "user", "content": RUBRIC_PROMPT.format(
                                 claim=transcript["question"], verdict=transcript["verdict"],
                                 rationale=transcript["rationale"])}]), scope)
    d = r.data if isinstance(r.data, dict) else {}
    c = d.get("clarity")
    return {"clarity": int(c) if isinstance(c, int | float) and 1 <= c <= 5 else None,
            "why": str(d.get("why", ""))[:200], "usd": r.usd}


def composite(code: dict, clarity: int | None) -> float:
    parts = [code["grade_ok"], code["length_ok"], code["jargon_ok"]]
    if clarity is not None:
        parts.append((clarity - 1) / 4)
    return sum(parts) / len(parts)


def score(transcript: dict, gateway=None, scope=None, max_words: int = 60,
          max_grade: float = 9.0) -> dict:
    c = code_scores(transcript.get("rationale", ""), max_words, max_grade)
    rb = rubric(gateway, transcript, scope) if gateway is not None else {"clarity": None}
    return {**c, "clarity": rb.get("clarity"), "rubric_why": rb.get("why"),
            "readability": round(composite(c, rb.get("clarity")), 4)}
