"""Protocol YAML schema (spec §5) and transcript schema (spec §5.4).

A protocol picks a `pattern` (how agents interact) and tunes it with knobs. The experimenter
writes new protocols as YAML in lab/protocols/library/ or experiments/E-NNNN/protocol.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import yaml

PATTERNS = {
    "single":       "One model, one answer.",
    "sample_vote":  "One model sampled N times; majority vote; confidence = agreement.",
    "panel":        "K independent answerers; aggregated by majority, weighted or mean_prob.",
    "society":      "Answer, read peers' answers, revise for R rounds; majority (Du et al.).",
    "debate":       "Advocates argue assigned sides for R rounds; a judge rules.",
    "consultancy":  "One advocate argues a randomly assigned side; a judge rules (control).",
    "chateval":     "Persona judges discuss in a communication mode; majority (Chan et al.).",
    "evidence_first": "Each model grades each source's stance; stances are aggregated.",
}
ROLES = ["answerer", "advocate", "judge", "consultant", "summarizer", "grader"]
AGGREGATIONS = ["judge", "majority", "weighted", "mean_prob", "stance", "jev"]

AGENT_SCHEMA = {
    "type": "object",
    "required": ["role", "model"],
    "additionalProperties": False,
    "properties": {
        "role": {"enum": ROLES},
        "model": {"type": "string"},
        "side": {"enum": ["affirm", "deny"]},
        "name": {"type": "string"},
        "persona": {"type": "string", "maxLength": 600},
        "effort": {"enum": ["low", "medium", "high"]},
        "samples": {"type": "integer", "minimum": 1, "maximum": 15},
        "weight": {"type": "number", "minimum": 0},
        "sees": {"enum": ["full", "quotes", "none"]},
    },
}

PROTOCOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["id", "description", "pattern", "agents", "aggregation"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9.-]{1,63}$"},
        "description": {"type": "string"},
        "pattern": {"enum": list(PATTERNS)},
        "paper": {"type": "string"},                    # Season 0 paper card slug
        "controls": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "evidence": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "retrieve": {"type": "boolean"},
                "max_sources": {"type": "integer", "minimum": 1, "maximum": 12},
                "per_agent": {"enum": ["shared", "independent"]},
                # What the judge sees: full evidence, only verified quotes, or nothing.
                "judge_sees": {"enum": ["full", "quotes", "none"]},
            },
        },
        "agents": {"type": "array", "items": AGENT_SCHEMA, "minItems": 1, "maxItems": 9},
        "rounds": {"type": "integer", "minimum": 0, "maximum": 6},
        "aggregation": {"enum": AGGREGATIONS},
        "communication": {"enum": ["one_by_one", "simultaneous", "simultaneous_summarizer"]},
        "early_stop": {
            "type": "object", "additionalProperties": False,
            "properties": {"agree": {"type": "boolean"},
                           "judge_can_end": {"type": "boolean"},
                           "min_rounds": {"type": "integer", "minimum": 1}},
        },
        # Smit et al.: how strongly agents are told to seek agreement (0 = hold your view,
        # 1 = converge). Rendered into the revision prompt.
        "agreement_intensity": {"type": "number", "minimum": 0, "maximum": 1},
        "best_of_n": {"type": "integer", "minimum": 1, "maximum": 8},   # Khan et al.
        "quotes": {"type": "object", "additionalProperties": False,
                   "properties": {"verify": {"type": "boolean"},
                                  "max_words": {"type": "integer", "minimum": 5}}},
        "prompts": {"type": "object", "additionalProperties": {"type": "string"}},
        "output": {"type": "object", "additionalProperties": False,
                   "properties": {"rationale_words": {"type": "integer", "minimum": 10,
                                                      "maximum": 120},
                                  "verdict": {"type": "string"},
                                  "confidence": {"type": "string"}}},
        "budget": {"type": "object", "additionalProperties": False,
                   "properties": {"max_usd_per_item": {"type": "number", "exclusiveMinimum": 0}}},
        "max_tokens": {"type": "integer", "minimum": 256, "maximum": 8000},
    },
}

_pv = jsonschema.Draft202012Validator(PROTOCOL_SCHEMA)


class InvalidProtocol(ValueError):
    pass


def validate_protocol(p: dict[str, Any], known_models: set[str] | None = None) -> dict[str, Any]:
    errs = sorted(_pv.iter_errors(p), key=lambda e: list(e.path))
    if errs:
        e = errs[0]
        raise InvalidProtocol(f"{p.get('id', '?')}: {'/'.join(map(str, e.path)) or '<root>'}: "
                              f"{e.message}")
    roles = [a["role"] for a in p["agents"]]
    pat = p["pattern"]
    need = {
        "single": lambda: roles == ["answerer"],
        "sample_vote": lambda: roles == ["answerer"],
        "panel": lambda: set(roles) == {"answerer"} and len(roles) >= 2,
        "society": lambda: set(roles) == {"answerer"} and len(roles) >= 2,
        "debate": lambda: roles.count("judge") == 1 and roles.count("advocate") >= 2,
        "consultancy": lambda: roles.count("judge") == 1 and roles.count("consultant") == 1,
        "chateval": lambda: set(roles) <= {"judge", "summarizer"} and roles.count("judge") >= 2,
        "evidence_first": lambda: set(roles) == {"grader"},
    }[pat]
    if not need():
        raise InvalidProtocol(f"{p['id']}: agents {roles} don't fit pattern {pat!r}")
    if pat == "debate":
        sides = {a.get("side") for a in p["agents"] if a["role"] == "advocate"}
        if sides != {"affirm", "deny"}:
            raise InvalidProtocol(f"{p['id']}: debate needs affirm and deny advocates")
    if pat == "evidence_first" and not p.get("evidence", {}).get("retrieve"):
        raise InvalidProtocol(f"{p['id']}: evidence_first needs evidence.retrieve: true")
    if (pat == "evidence_first") != (p["aggregation"] == "stance"):
        raise InvalidProtocol(f"{p['id']}: aggregation stance goes with pattern evidence_first")
    if p.get("evidence", {}).get("per_agent") == "independent":
        raise InvalidProtocol(f"{p['id']}: evidence.per_agent independent is not supported yet")
    if p["aggregation"] == "judge" and "judge" not in roles:
        raise InvalidProtocol(f"{p['id']}: aggregation judge needs a judge agent")
    if known_models is not None:
        unknown = {a["model"] for a in p["agents"]} - known_models
        if unknown:
            raise InvalidProtocol(f"{p['id']}: unknown model aliases {sorted(unknown)}")
    return p


def load_protocol(path: Path, known_models: set[str] | None = None) -> dict[str, Any]:
    return validate_protocol(yaml.safe_load(Path(path).read_text()), known_models)


def models_used(p: dict[str, Any]) -> list[str]:
    return sorted({a["model"] for a in p["agents"]})


# --- transcripts --------------------------------------------------------------------------

STANCES = ["supports", "refutes", "neutral"]

TRANSCRIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["experiment", "protocol", "item", "evidence", "turns", "verdict",
                 "confidence", "rationale", "usd", "latency_s"],
    "properties": {
        "experiment": {"type": "string"},
        "protocol": {"type": "string"},
        "item": {"type": "string"},
        "split": {"enum": ["dev", "holdout"]},
        "question": {"type": "string"},
        "label_set": {"type": "array", "items": {"type": "string"}},
        "gold": {"type": ["string", "null"]},
        "evidence": {"type": "array", "items": {
            "type": "object", "required": ["id", "url", "title", "excerpt", "stance"],
            "properties": {
                "id": {"type": "string"}, "url": {"type": "string"},
                "title": {"type": "string"}, "published": {"type": ["string", "null"]},
                "excerpt": {"type": "string"},
                "stance": {"type": "object", "additionalProperties": {"enum": STANCES}},
            }}},
        "turns": {"type": "array", "items": {
            "type": "object",
            "required": ["n", "agent", "model", "text", "cites", "tokens", "usd"],
            "properties": {
                "n": {"type": "integer"}, "round": {"type": "integer"},
                "agent": {"type": "string"}, "model": {"type": "string"},
                "family": {"type": "string"}, "text": {"type": "string"},
                "position": {"type": ["string", "null"]},
                "belief": {"type": ["number", "null"]},
                "cites": {"type": "array", "items": {"type": "string"}},
                "quotes": {"type": "array"},
                "tokens": {"type": "integer"}, "usd": {"type": "number"},
                "cached": {"type": "boolean"}, "refused": {"type": "boolean"},
            }}},
        "agreement": {"type": "array", "items": {"type": "number"}},
        "verdict": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "usd": {"type": "number", "minimum": 0},
        "latency_s": {"type": "number", "minimum": 0},
        "error": {"type": ["string", "null"]},
    },
}

_tv = jsonschema.Draft202012Validator(TRANSCRIPT_SCHEMA)


def validate_transcript(t: dict[str, Any]) -> dict[str, Any]:
    errs = sorted(_tv.iter_errors(t), key=lambda e: list(e.path))
    if errs:
        e = errs[0]
        raise ValueError(f"transcript {t.get('item')}: {'/'.join(map(str, e.path))}: {e.message}")
    if t["verdict"] not in t.get("label_set", [t["verdict"]]) and t["verdict"] != "abstain":
        raise ValueError(f"transcript {t['item']}: verdict {t['verdict']!r} not in label_set")
    for ev in t["evidence"]:
        if len(ev["excerpt"].rstrip("…").split()) > 40:
            raise ValueError(f"transcript {t['item']}: excerpt {ev['id']} over 40 words")
    if len(t["rationale"].split()) > 120:
        raise ValueError(f"transcript {t['item']}: rationale too long")
    return t
