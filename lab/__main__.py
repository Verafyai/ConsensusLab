"""`python -m lab check` reports whether the lab is ready to run."""

import sys

from lab.config import LabNotReady, load_config


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "check"
    if cmd == "check":
        try:
            load_config().require_ready()
        except LabNotReady as e:
            print(e, file=sys.stderr)
            return 2
        print("Lab config ready: all budgets and prices set.")
        return 0
    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
