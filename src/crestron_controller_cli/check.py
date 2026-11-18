"""`crestron-controller check`: validate a join map exactly as the integration will."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import yaml
from cipcore.joinmap import JoinMapError, parse
from cipcore.policy import KINDS


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "check", help="validate a join map and show what it would let Home Assistant write"
    )
    parser.add_argument("file", type=Path)
    parser.set_defaults(func=run)


def _ranges(joins) -> str:
    out: list[str] = []
    for j in sorted(joins):
        if out and out[-1][1] == j - 1:
            out[-1] = (out[-1][0], j)
        else:
            out.append((j, j))
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in out) or "none"


def run(args) -> int:
    try:
        raw = yaml.safe_load(args.file.read_text(encoding="utf-8"))
        jm = parse(raw)
    except (OSError, yaml.YAMLError, JoinMapError) as err:
        print(f"{args.file}: {err}", file=sys.stderr)
        return 1
    counts = Counter(e.type for e in jm.entities)
    print(f"{args.file}: valid, {len(jm.entities)} entities")
    for kind, n in sorted(counts.items()):
        print(f"  {kind}: {n}")
    if jm.subsystems:
        print(f"subsystems (default {jm.default_subsystem}):")
        for sub in jm.subsystems.values():
            print(f"  {sub.name}: entry d{sub.entry_join}, quiet {sub.quiet_seconds}s")
    policy = jm.policy(enabled=True)
    print("with writes enabled, Home Assistant may write:")
    _lists(policy.allow, policy.object_allow)
    print("never written, whatever else happens:")
    _lists(jm.never_write, jm.never_write_objects)
    return 0


def _lists(program: dict, objects: dict) -> None:
    for kind in KINDS:
        print(f"  {kind}: {_ranges(program.get(kind, ()))}")
    for obj, sets in sorted(objects.items()):
        # Only what is there: a SmartObject with nothing in it is noise.
        shown = [f"{kind} {_ranges(sets[kind])}" for kind in KINDS if sets.get(kind)]
        if shown:
            print(f"  SmartObject {obj} (untested on real hardware): {'; '.join(shown)}")
