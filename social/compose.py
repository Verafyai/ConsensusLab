"""Post text (spec §9). Templates carry every claim; Grok may only reword the hook line,
and its output is rejected if it adds numbers, links or mentions that aren't in the data."""

from __future__ import annotations

import re

from social.policy import MENTION, load_policy

LABEL = {"supported": "Supported", "refuted": "Refuted", "not_enough_evidence":
         "Not enough evidence", "conflicting": "Conflicting / misleading"}
HOOK_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["hook"],
               "properties": {"hook": {"type": "string"}}}


def case_url(t: dict) -> str:
    return f"{load_policy()['dashboard_base_url']}/#case={t['experiment']}/{t['item']}"


def _trim(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def case_text(t: dict, hook: str | None = None) -> str:
    pol = load_policy()
    verdict = f"{LABEL.get(t['verdict'], t['verdict'])} ({round(t['confidence'] * 100)}%)"
    gold = LABEL.get(t.get("gold") or "", "n/a")
    lines = ["Claim: “{claim}”", f"AI panel: {verdict} · Human experts: {gold}"]
    if hook:
        lines.append(hook)
    lines.append(f"{pol['always']['disclosure']}. Full evidence: {case_url(t)}")
    fixed = len("\n".join(lines).replace("{claim}", ""))
    budget = pol["always"]["max_chars"] - fixed - 1
    return "\n".join(lines).replace("{claim}", _trim(t["question"], max(40, budget)))


def poll_text(t: dict) -> tuple[str, dict]:
    pol = load_policy()
    return (f"Did the AI panel get this right? {pol['always']['disclosure']}. "
            f"Evidence: {case_url(t)}",
            {"options": pol["poll"]["options"],
             "duration_minutes": pol["poll"]["duration_minutes"]})


def lab_update_text(champion: str, f1: float, usd: float, lesson: str, url: str) -> str:
    pol = load_policy()
    head = (f"Lab update: champion protocol {champion}, holdout macro-F1 {f1:.3f}, "
            f"${usd:.3f} per claim.")
    tail = f"{pol['always']['disclosure']}. Results: {url}"
    room = pol["always"]["max_chars"] - len(head) - len(tail) - 16
    return f"{head}\nTop lesson: {_trim(lesson, max(20, room))}\n{tail}"


def ack_text(feedback_no: int, url: str) -> str:
    return f"Thanks, logged as feedback #{feedback_no}. Case and evidence: {url}"


def hook_ok(hook: str, t: dict) -> bool:
    if not hook or len(hook) > 110 or MENTION.search(hook) or "http" in hook or "#" in hook:
        return False
    source = " ".join([t["question"], t.get("rationale", ""), *t.get("reasons", [])])
    for num in re.findall(r"\d[\d.,]*", hook):
        if num.strip(".,") not in source:
            return False                     # a number the data doesn't contain
    return True


def grok_hook(gateway, t: dict, scope) -> str | None:
    """One plain-language line explaining the main reason, written by the social model."""
    from lab.clients.base import Request
    alias = gateway.cfg.models.get("roles", {}).get("social_writer", "grok-fast")
    prompt = ("Write one short, neutral line (under 100 characters) that explains the main "
              "reason for this fact-check verdict to a general audience. Use only facts given "
              "below. No hashtags, links or @mentions.\n\n"
              f"Claim: {t['question']}\nVerdict: {t['verdict']}\nReasons: "
              f"{'; '.join(t.get('reasons', []))}\nRationale: {t.get('rationale', '')}")
    r = gateway.call(Request(model=alias, max_tokens=200, json_schema=HOOK_SCHEMA,
                             messages=[{"role": "user", "content": prompt}]), scope)
    hook = (r.data or {}).get("hook", "").strip() if isinstance(r.data, dict) else ""
    return hook if hook_ok(hook, t) else None
