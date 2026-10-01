"""Locked-path enforcement (spec §10): anything the experimenter changes outside its
allowed paths is reverted, as in checkworthy. Uses git, so it also catches deletions."""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

from lab import paths

ALLOWED = [
    "experiments/E-*/**", "experiments/E-*",
    "lab/protocols/library/**",
    "library/cards/**",
    "viz/variants/**",
    "zones/*/sub/**",
    "learnings/proposals/**",
    "ops/experimenter/**",          # its fix plan and notes
]


def _git(*args: str, root: Path) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True).stdout


def allowed(path: str, extra: list[str] | None = None) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in ALLOWED + (extra or []))


def changed_paths(root: Path, since: str) -> list[str]:
    """Paths changed in commits since `since` plus uncommitted and untracked changes."""
    out = set(_git("diff", "--name-only", since, root=root).split())
    out |= set(_git("diff", "--name-only", "HEAD", root=root).split())
    for line in _git("status", "--porcelain", "--untracked-files=all", root=root).splitlines():
        out.add(line[3:].split(" -> ")[-1])
    return sorted(p for p in out if p)


def snapshot(root: Path | None = None) -> tuple[str, set[str]]:
    """Call before the experimenter runs: (HEAD, paths already dirty)."""
    root = root or paths.ROOT
    head = _git("rev-parse", "HEAD", root=root).strip()
    return head, set(changed_paths(root, head))


def enforce(root: Path | None = None, since: str = "HEAD",
            extra_allowed: list[str] | None = None, ignore: set[str] | None = None) -> list[str]:
    """Revert every disallowed change made since `since`. Returns the reverted paths.
    `ignore` holds paths that were already dirty before the experimenter started."""
    root = root or paths.ROOT
    bad = [p for p in changed_paths(root, since)
           if not allowed(p, extra_allowed) and p not in (ignore or set())]
    for p in bad:
        tracked = subprocess.run(["git", "cat-file", "-e", f"{since}:{p}"], cwd=root,
                                 capture_output=True).returncode == 0
        if tracked:
            _git("checkout", since, "--", p, root=root)
        else:
            f = root / p
            if f.is_file() or f.is_symlink():
                f.unlink()
            subprocess.run(["git", "rm", "--cached", "-q", "--ignore-unmatch", p], cwd=root,
                           capture_output=True)
    return bad
