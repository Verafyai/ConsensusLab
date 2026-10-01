"""Live smoke run (E02 acceptance): one tiny call per configured provider, then compare the
metered cost with what each provider reports.

    uv run python -m lab.clients.smoke [alias ...]
"""

from __future__ import annotations

import sys

from lab.clients.base import Request
from lab.clients.gateway import Gateway
from lab.clients.meter import Scope


def main(argv: list[str]) -> int:
    gw = Gateway.default()
    aliases = argv or ["claude-haiku", "grok-fast"]
    gw.cfg.require_ready(aliases)
    scope = Scope(experiment="smoke", caps={"smoke": 0.05})
    print(f"{'alias':14} {'in':>6} {'out':>6} {'metered $':>11} {'provider $':>11}  cached")
    for a in aliases:
        r = gw.call(Request(model=a, max_tokens=64, sample=0,
                            messages=[{"role": "user", "content": "Reply with the word: ready"}]),
                    scope)
        rep = r.usage.provider_usd
        print(f"{a:14} {r.usage.input_tokens:6} {r.usage.output_tokens:6} {r.usd:11.6f} "
              f"{'' if rep is None else f'{rep:11.6f}':>11}  {r.cached}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
