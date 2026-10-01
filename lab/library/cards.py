"""Paper cards (spec §5.3, E04b): page-text extraction and page-reference verification.

Page references in cards use the PDF's physical page number (1 = first page of the file)
and carry a verbatim snippet, so code can check them:

    [p.4: "the judge sees only the debate transcript"]

A reference resolves when the snippet (normalized: case, whitespace, hyphenation,
ligatures, quote marks) appears on that page, or runs across the boundary into the next.

    uv run python -m lab.library.cards pages 02-du-2023-multiagent-debate      # all pages
    uv run python -m lab.library.cards pages 02-du-2023-multiagent-debate 5    # one page
    uv run python -m lab.library.cards check                                  # all cards
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from lab import paths

LIB = paths.ROOT / "library"
PDFS = LIB / "pdfs"
CARDS = LIB / "cards"
TEXT = LIB / "text"
REF = re.compile(r"\[p\.(\d+):\s*[\"“](.+?)[\"”]\]", re.S)
REQUIRED_SECTIONS = ["Setup and task", "Roles, rounds and what the judge sees",
                     "How a verdict is reached", "Headline finding", "Reported settings",
                     "Faithfulness note"]
FRONT = ["paper", "title", "authors", "year", "arxiv", "protocol", "zone", "controls", "claim"]
LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}


def normalize(s: str) -> str:
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    s = s.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                                   "–": "-", "—": "-", " ": " ", "−": "-"}))
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)       # undo end-of-line hyphenation
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def papers() -> list[str]:
    return [ln.split()[0].removesuffix(".pdf") for ln in (LIB / "MANIFEST").read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]


@cache
def pages(paper: str) -> list[str]:
    """Raw text per physical page (index 0 = page 1). Cached under library/text/."""
    cached = TEXT / f"{paper}.txt"
    if cached.exists():
        raw = cached.read_text()
    else:
        pdf = PDFS / f"{paper}.pdf"
        if not pdf.exists():
            raise FileNotFoundError(f"{pdf} missing: run library/fetch.sh")
        raw = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"], check=True,
                             capture_output=True, text=True).stdout
        TEXT.mkdir(parents=True, exist_ok=True)
        cached.write_text(raw)
    return raw.split("\f")


@dataclass
class RefResult:
    page: int
    snippet: str
    ok: bool
    why: str


def check_ref(paper: str, page: int, snippet: str) -> RefResult:
    pg = pages(paper)
    n = normalize(snippet)
    if len(n.split()) < 4:
        return RefResult(page, snippet, False, "snippet shorter than 4 words")
    if not 1 <= page <= len(pg):
        return RefResult(page, snippet, False, f"page out of range 1..{len(pg)}")
    here = normalize(pg[page - 1])
    if n in here:
        return RefResult(page, snippet, True, "found")
    nxt = normalize(pg[page - 1] + " " + pg[page]) if page < len(pg) else here
    if n in nxt:
        return RefResult(page, snippet, True, "found across page break")
    return RefResult(page, snippet, False, "not on that page")


@dataclass
class CardCheck:
    card: str
    meta: dict
    refs: list[RefResult]
    problems: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems and all(r.ok for r in self.refs)


def parse_card(path: Path) -> tuple[dict, str]:
    text = path.read_text()
    if not text.startswith("---"):
        raise ValueError(f"{path.name}: missing front matter")
    _, fm, body = text.split("---", 2)
    return yaml.safe_load(fm) or {}, body


def check_card(path: Path) -> CardCheck:
    problems: list[str] = []
    meta, body = parse_card(path)
    for k in FRONT:
        if k not in meta:
            problems.append(f"front matter missing {k!r}")
    paper = meta.get("paper", path.stem)
    if paper not in papers():
        problems.append(f"unknown paper {paper!r}")
        return CardCheck(path.name, meta, [], problems)
    for sec in REQUIRED_SECTIONS:
        if not re.search(rf"^##\s+{re.escape(sec)}", body, re.M):
            problems.append(f"missing section '## {sec}'")
    refs = [check_ref(paper, int(p), s) for p, s in REF.findall(body)]
    if len(refs) < 5:
        problems.append(f"only {len(refs)} page references (need ≥ 5)")
    return CardCheck(path.name, meta, refs, problems)


def check_all() -> list[CardCheck]:
    return [check_card(p) for p in sorted(CARDS.glob("*.md"))]


def main(argv: list[str]) -> int:
    if argv[:1] == ["pages"]:
        pg = pages(argv[1])
        sel = [int(argv[2])] if len(argv) > 2 else range(1, len(pg) + 1)
        for i in sel:
            print(f"\n===== PAGE {i} =====\n{pg[i - 1]}")
        return 0
    if argv[:1] == ["check"] or not argv:
        bad = 0
        for c in check_all():
            print(f"{'OK ' if c.ok else 'BAD'} {c.card}: {sum(r.ok for r in c.refs)}/"
                  f"{len(c.refs)} refs resolve")
            for p in c.problems:
                print(f"     - {p}")
            for r in c.refs:
                if not r.ok:
                    print(f"     - p.{r.page} {r.why}: \"{r.snippet[:70]}\"")
            bad += not c.ok
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
