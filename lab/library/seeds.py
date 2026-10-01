"""Extract the seed protocols proposed in paper cards into lab/protocols/library/seed/.

    uv run python -m lab.library.seeds          # write YAMLs, print ids

Each YAML block under a card's "## Proposed protocol" heading becomes one protocol file.
Season 0 fairness edits (spec §5.3) are applied uniformly: debates swap sides per item so
model family and side aren't confounded.
"""

from __future__ import annotations

import re
import sys

import yaml

from lab import paths
from lab.library.cards import CARDS, parse_card
from lab.protocols.schema import validate_protocol

SEED_DIR = paths.ROOT / "lab" / "protocols" / "library" / "seed"
BLOCK = re.compile(r"```yaml\n(.*?)```", re.S)


def extract() -> list[dict]:
    out = []
    for card in sorted(CARDS.glob("*.md")):
        meta, body = parse_card(card)
        sec = body.split("## Proposed protocol", 1)
        if len(sec) < 2:
            continue
        for block in BLOCK.findall(sec[1]):
            p = yaml.safe_load(block)
            if not isinstance(p, dict) or "id" not in p:
                continue
            p.setdefault("paper", meta["paper"])
            if p["pattern"] == "debate":
                p.setdefault("swap_sides", True)
            out.append(validate_protocol(p))
    return out


def write() -> list[str]:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    ids = []
    for p in extract():
        (SEED_DIR / f"{p['id']}.yaml").write_text(yaml.safe_dump(p, sort_keys=False, width=100))
        ids.append(p["id"])
    return ids


if __name__ == "__main__":
    for i in write():
        print(i)
    sys.exit(0)
