"""Entry point for `crestron-controller`.

Each subcommand lives in its own module, which exposes `register(subparsers)`
to add its parser and set `func` on it. `func(args)` returns the exit status.

No subcommand presses a join unless it is given an explicit flag that says so.
There is deliberately no command that presses a range of joins to see what
happens: on some systems a spare-looking join arms an alarm or opens a gate.
See docs/inventory/inventory-overview.md.
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import check, console, panel, session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crestron-controller",
        description="Inventory a Crestron system and draft a join map for Home Assistant.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log protocol detail")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    for module in (console, session, panel, check):
        module.register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
