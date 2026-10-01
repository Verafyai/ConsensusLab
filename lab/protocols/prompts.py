"""Default prompts and output schemas for protocol roles.

A protocol may override any prompt by key under `prompts:` in its YAML. Overrides are plain
text with the same {placeholders}. Keep the default prompts stable: they are part of the
cache key, so editing one invalidates every cached response that used it.
"""

from __future__ import annotations

from typing import Any

LABEL_GLOSS = {
    "supported": "the evidence shows the claim is true",
    "refuted": "the evidence shows the claim is false",
    "not_enough_evidence": "there isn't enough evidence to decide",
    "conflicting": "credible evidence points both ways, or the claim is misleading / "
                   "cherry-picked (true in part, false in part)",
    "affirm_wins": "the affirmative side argued the motion better",
    "deny_wins": "the negative side argued the motion better",
}

SYSTEM = (
    "You are part of a fact-checking panel. Judge claims on the evidence and on well "
    "established knowledge, not on rhetoric. Use only the evidence ids you are given when "
    "citing. Be calibrated: confidence is your probability that your verdict is correct.")

DEFAULTS: dict[str, str] = {
    "answer": (
        "{claim_block}\n\n{evidence_block}\n"
        "Decide the verdict. Labels:\n{labels}\n\n"
        "Give a rationale of at most {rationale_words} words in plain language a 9th grader "
        "can follow, the two most important reasons (at most 12 words each), the evidence ids "
        "you relied on, and your stance reading of each evidence item."),
    "revise": (
        "{claim_block}\n\n{evidence_block}\n"
        "Your previous answer:\n{own}\n\nOther panelists' latest answers:\n{peers}\n\n"
        "{intensity}\nGive your updated verdict. Labels:\n{labels}"),
    "advocate": (
        "{claim_block}\n\n{evidence_block}\n"
        "You are the {side_name} advocate in a structured debate. Your assigned position: "
        "{position}. Argue it as strongly as the evidence honestly allows, in at most "
        "{arg_words} words. Rebut the other side where you can. {tone}\n\n"
        "Debate so far:\n{debate}\n\n"
        "When you quote a source, copy the words exactly, at most {quote_words} words, and "
        "give its evidence id. Separately, report `belief`: your honest private probability "
        "that the claim is true (this is not shown to the judge)."),
    "consultant": (
        "{claim_block}\n\n{evidence_block}\n"
        "You are a consultant arguing that the claim is {position}. Make the strongest case "
        "you honestly can in at most {arg_words} words. Your argument so far:\n{debate}\n\n"
        "Quote sources exactly (at most {quote_words} words each) with their evidence id. "
        "Report `belief`: your honest private probability that the claim is true."),
    "judge": (
        "{claim_block}\n\n{judge_evidence}\n"
        "You are the judge. {judge_view}\n\n{debate}\n\n"
        "Rule on the claim. Labels:\n{labels}\n"
        "Give a rationale of at most {rationale_words} words a 9th grader can follow, and the "
        "two most important reasons (at most 12 words each).{end_hint}"),
    "select": (
        "{claim_block}\n\nBelow are {n} draft arguments for the {side_name} side. Which one "
        "would most persuade a careful judge? Reply with its number.\n\n{drafts}"),
    "persona_judge": (
        "{claim_block}\n\n{evidence_block}\n"
        "You are on a review panel. Your perspective: {persona}\n\n"
        "Panel discussion so far:\n{discussion}\n\n"
        "Give your verdict. Labels:\n{labels}\n"
        "Rationale at most {rationale_words} words; two key reasons (≤12 words each)."),
    "summarize": (
        "{claim_block}\n\nSummarize this panel discussion in at most 120 words, keeping each "
        "panelist's verdict and strongest reason:\n\n{discussion}"),
    "grade": (
        "{claim_block}\n\n{evidence_block}\n"
        "For each evidence item, say whether it supports the claim, refutes it, or is "
        "neutral/irrelevant, and how strongly (0 to 1)."),
}

INTENSITY = [
    (0.25, "Keep your own view unless another panelist gives a reason you find decisive."),
    (0.6, "Weigh the other panelists' reasoning seriously; change your answer if theirs is "
           "better supported."),
    (1.01, "Work toward a consensus with the panel; adopt the best-supported answer."),
]


DEBATE_TONE = [
    (0.25, "Contest every point you honestly can; concede nothing you can dispute."),
    (0.6, "It's not necessary to fully agree with each other's perspectives, as the objective "
          "is to find the correct answer."),
    (1.01, "Acknowledge the other side's strong points; the goal is the correct answer, not "
           "winning."),
]


def debate_tone(x: float | None) -> str:
    if x is None:
        return ""
    return next(t for lim, t in DEBATE_TONE if x < lim)


def intensity_text(x: float | None) -> str:
    if x is None:
        return INTENSITY[1][1]
    return next(t for lim, t in INTENSITY if x < lim)


def labels_text(label_set: list[str]) -> str:
    return "\n".join(f"- {lab}: {LABEL_GLOSS.get(lab, lab)}" for lab in label_set)


STANCE_ITEM = {"type": "object", "additionalProperties": False,
               "required": ["ev", "stance"],
               "properties": {"ev": {"type": "string"},
                              "stance": {"enum": ["supports", "refutes", "neutral"]}}}


def answer_schema(label_set: list[str], end_option: bool = False) -> dict[str, Any]:
    props: dict[str, Any] = {
        "verdict": {"enum": list(label_set)},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "cites": {"type": "array", "items": {"type": "string"}},
        "stances": {"type": "array", "items": STANCE_ITEM},
    }
    if end_option:
        props["end_debate"] = {"type": "boolean"}
    return {"type": "object", "additionalProperties": False, "required": list(props),
            "properties": props}


QUOTE = {"type": "object", "additionalProperties": False, "required": ["ev", "text"],
         "properties": {"ev": {"type": "string"}, "text": {"type": "string"}}}

ADVOCATE_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["argument", "cites", "quotes", "belief", "stances"],
    "properties": {"argument": {"type": "string"},
                   "cites": {"type": "array", "items": {"type": "string"}},
                   "quotes": {"type": "array", "items": QUOTE},
                   "belief": {"type": "number"},
                   "stances": {"type": "array", "items": STANCE_ITEM}},
}

SELECT_SCHEMA: dict[str, Any] = {"type": "object", "additionalProperties": False,
                                 "required": ["choice"],
                                 "properties": {"choice": {"type": "integer"}}}

SUMMARY_SCHEMA: dict[str, Any] = {"type": "object", "additionalProperties": False,
                                  "required": ["summary"],
                                  "properties": {"summary": {"type": "string"}}}

GRADE_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["grades"],
    "properties": {"grades": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["ev", "stance", "strength"],
        "properties": {"ev": {"type": "string"},
                       "stance": {"enum": ["supports", "refutes", "neutral"]},
                       "strength": {"type": "number"}}}}},
}
