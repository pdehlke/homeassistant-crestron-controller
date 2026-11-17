"""`cip-panel listen` and `cip-panel watch`: register as a panel and record what arrives.

Both register on an IP-ID and press nothing by default. On a program that gates
its subsystems behind a home-page button, listening alone shows only the menu;
`--enter JOIN --allow-press` presses that one join (and nothing else) so the
subsystem's joins arrive, and measures how the entry dump is spaced so you can
set `quiet_seconds` for it. See docs/inventory/listening-to-a-processor.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import yaml
from cipcore.client import PROBE_OK, CipClient, Subsystem, Timing, async_probe
from cipcore.joinmap import JoinMapError, parse
from cipcore.policy import DIGITAL, LISTEN_ONLY, WritePolicy
from cipcore.protocol import CIP_PORT, DATA_DIGITAL, TYPE_DATA

ENTERED = "entered"


def _ipid(text: str) -> int:
    value = text.strip().lower()
    number = int(value[:-1]) if value.endswith("d") else int(value.removeprefix("0x"), 16)
    if not 0x03 <= number <= 0xFE:
        raise argparse.ArgumentTypeError(f"IP-ID {text} is outside 03-FE")
    return number


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("host", help="control processor address (not the touch panel)")
    parser.add_argument(
        "--ipid", type=_ipid, required=True, help="panel IP-ID in hex, e.g. 0x2A (or 42d)"
    )
    parser.add_argument("--port", type=int, default=CIP_PORT)
    parser.add_argument(
        "--enter",
        type=int,
        metavar="JOIN",
        help="press this one digital join after registering, to enter a gated subsystem",
    )
    parser.add_argument(
        "--allow-press",
        action="store_true",
        help="required with --enter: confirms you know what that join does",
    )
    parser.add_argument(
        "--never-write",
        default="",
        metavar="LIST",
        help="joins to refuse even with --enter, e.g. '45,200-219'",
    )


def register(subparsers) -> None:
    listen = subparsers.add_parser(
        "listen",
        help="register as a panel, record every join the processor reports, draft a join map",
    )
    _common(listen)
    listen.add_argument("--seconds", type=float, default=20.0, help="how long to listen")
    listen.add_argument("--json", type=Path, help="write every observed join to this file")
    listen.add_argument("--draft", type=Path, help="write a draft join map to this file")
    listen.set_defaults(func=run_listen)

    watch = subparsers.add_parser(
        "watch",
        help="show join changes live while you press keypads; optionally name them",
    )
    _common(watch)
    watch.add_argument(
        "--label",
        type=Path,
        metavar="FILE",
        help="after each burst of changes, ask for a name and append an entry to FILE",
    )
    watch.set_defaults(func=run_watch)


def _deny(text: str) -> frozenset[int]:
    if not text.strip():
        return frozenset()
    items: list[object] = []
    for part in text.split(","):
        part = part.strip()
        items.append(part if "-" in part else int(part))
    jm = parse({"never_write": {"digital": items}})
    return jm.never_write[DIGITAL]


def _build_client(args, on_join=None, on_frame=None) -> CipClient:
    if args.enter is not None and not args.allow_press:
        sys.exit("--enter presses a join on your system. Add --allow-press if you mean it.")
    try:
        deny = _deny(args.never_write)
    except (JoinMapError, ValueError) as err:
        sys.exit(f"--never-write: {err}")
    if args.enter is None:
        return CipClient(
            "cli",
            args.host,
            args.ipid,
            port=args.port,
            policy=LISTEN_ONLY,
            on_join=on_join,
            on_frame=on_frame,
        )
    if args.enter in deny:
        sys.exit(f"d{args.enter} is on your --never-write list; refusing to press it.")
    policy = WritePolicy(
        enabled=True, allow={DIGITAL: frozenset({args.enter})}, deny={DIGITAL: deny}
    )
    # The quiet window is set wide on purpose: this run is measuring the dump,
    # so it must not cut the dump short on a guess about its spacing.
    return CipClient(
        "cli",
        args.host,
        args.ipid,
        port=args.port,
        subsystems={ENTERED: Subsystem(ENTERED, args.enter, quiet_seconds=2.0)},
        default_subsystem=ENTERED,
        policy=policy,
        timing=Timing(entry_timeout=10.0),
        on_join=on_join,
        on_frame=on_frame,
    )


async def _preflight(args) -> bool:
    result = await async_probe(args.host, args.ipid, args.port)
    if result == PROBE_OK:
        return True
    hints = {
        "unreachable": "nothing answered. Is this the control processor's address?",
        "ipid_missing": "the program does not define that IP-ID. Try `cip-panel ipids`.",
        "refused": "registration refused. Authenticated or encrypted CIP is not supported.",
    }
    print(f"{args.host} IP-ID 0x{args.ipid:02X}: {hints.get(result, result)}", file=sys.stderr)
    return False


class _EntryTimer:
    """Records when digital frames arrive after the entry press, to measure a dump's spacing."""

    def __init__(self) -> None:
        self.pressed_at: float | None = None
        self.stamps: list[float] = []

    def __call__(self, direction: str, ciptype: int, payload: bytes) -> None:
        if ciptype != TYPE_DATA or len(payload) <= 3 or payload[3] != DATA_DIGITAL:
            return
        if direction == "tx" and self.pressed_at is None:
            self.pressed_at = time.monotonic()
        elif direction == "rx" and self.pressed_at is not None:
            self.stamps.append(time.monotonic())

    def suggested_quiet(self) -> float | None:
        """Twice the largest gap inside the measured dump, or None without a dump."""
        if self.pressed_at is None or len(self.stamps) < 2:
            return None
        stamps = self.stamps
        gaps = [b - a for a, b in zip(stamps, stamps[1:], strict=False)]
        # Only gaps inside the dump count; a long pause after it is just a quiet house.
        inside = [g for g in gaps if g < 1.5]
        return round(max(0.3, 2 * max(inside, default=0.0)), 2)

    def report(self) -> str | None:
        if self.suggested_quiet() is None:
            return None
        stamps = self.stamps
        gaps = [b - a for a, b in zip(stamps, stamps[1:], strict=False)]
        worst = max((g for g in gaps if g < 1.5), default=0.0)
        return (
            f"entry dump: first frame {stamps[0] - self.pressed_at:.3f}s after the press, "
            f"{len(stamps)} digital frames, largest gap {worst:.3f}s. Suggested "
            f"quiet_seconds: {max(0.3, 2 * worst):.2f} (twice the largest gap). "
            "Repeat a few times; dumps vary."
        )


def _snapshot(client: CipClient) -> dict:
    out: dict = {"ipid": f"0x{client.ipid:02X}", "subsystems": {}}
    for name in client.buckets():
        label = name or "(none)"
        out["subsystems"][label] = {
            "digital": dict(sorted(client.digital_for(name).items())),
            "analog": dict(sorted(client.analog_for(name).items())),
        }
    out["serial"] = dict(sorted(client.serial.items()))
    return out


def _draft(client: CipClient, args, quiet: float | None = None) -> str:
    """A draft join map: every observed join as a read-only entity with a placeholder name."""
    lines = [
        "# Draft join map from `cip-panel listen`. Every entry is read-only and every",
        "# name is a placeholder: rename what you recognise, delete what you do not.",
        "# Promote a binary_sensor to a light or switch only once you know what it",
        "# drives. Format: docs/configuration/join-map-reference.md",
        "version: 1",
    ]
    if args.enter is not None:
        lines += [
            "subsystems:",
            "  default: main  # rename to what the button is called on the panel",
            "  entries:",
            f"    main: {{join: {args.enter}, quiet_seconds: {quiet or 0.85}}}"
            + ("  # measured once; repeat and keep the largest" if quiet else "  # default"),
        ]
    lines += ["never_write:", "  digital: []", "entities:"]
    bucket = ENTERED if args.enter is not None else None
    for join, value in sorted(client.digital_for(bucket).items()):
        state = "high" if value else "low"
        lines.append(f"  - {{type: binary_sensor, name: Digital {join}, join: {join}}}  # {state}")
    for join, value in sorted(client.analog_for(bucket).items()):
        lines.append(f"  - {{type: sensor, name: Analog {join}, analog: {join}}}  # was {value}")
    for join, text in sorted(client.serial.items()):
        shown = text.strip().replace("#", "")[:40]
        name = json.dumps(f"Serial {join}")
        lines.append(f"  - {{type: sensor, name: {name}, serial: {join}}}  # {shown!r}")
    return "\n".join(lines) + "\n"


async def _listen(args) -> int:
    if not await _preflight(args):
        return 2
    timer = _EntryTimer()
    client = _build_client(args, on_frame=timer)
    await client.async_start()
    try:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(0.1)
            if client.last_error_kind and not client.registered:
                print(f"error: {client.last_error}", file=sys.stderr)
                return 2
    finally:
        await client.async_stop()

    snap = _snapshot(client)
    for label, data in snap["subsystems"].items():
        high = [j for j, v in data["digital"].items() if v]
        print(
            f"[{label}] {len(data['digital'])} digital ({len(high)} high), "
            f"{len(data['analog'])} analog"
        )
        if high:
            print(f"  high: {', '.join(f'd{j}' for j in high)}")
    print(f"{len(snap['serial'])} serial joins")
    if args.enter is not None:
        report = timer.report()
        if report:
            print(report)
        if ENTERED not in client.entered:
            print(f"d{args.enter} did not produce a subsystem dump within the timeout.")
    if args.json:
        args.json.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    if args.draft:
        text = _draft(client, args, timer.suggested_quiet())
        parse(yaml.safe_load(text))  # the draft must be valid before anyone edits it
        args.draft.write_text(text, encoding="utf-8")
        print(f"wrote {args.draft}")
    return 0


def run_listen(args) -> int:
    return asyncio.run(_listen(args))


async def _watch(args) -> int:
    if not await _preflight(args):
        return 2
    burst: list[tuple[str, int, int | str]] = []
    started = time.monotonic()

    def on_join(kind: str, join: int, value, subsystem) -> None:
        if not client.synced:
            return  # the initial dump is state, not something you just pressed
        letter = kind[0]
        print(f"{time.monotonic() - started:8.2f}s  {letter}{join} = {value!r}", flush=True)
        burst.append((kind, join, value))

    client = _build_client(args, on_join=on_join)
    await client.async_start()
    print("Waiting for the initial dump... press keypads once this says ready. Ctrl-C to stop.")
    try:
        while not client.synced:
            await asyncio.sleep(0.2)
        print("ready")
        last_len = 0
        quiet_since = time.monotonic()
        while True:
            await asyncio.sleep(0.2)
            if len(burst) != last_len:
                last_len = len(burst)
                quiet_since = time.monotonic()
                continue
            if burst and time.monotonic() - quiet_since > 1.0:
                if args.label:
                    await _label(args.label, list(burst))
                burst.clear()
                last_len = 0
    finally:
        await client.async_stop()


async def _label(path: Path, burst: list[tuple[str, int, int | str]]) -> None:
    joins = sorted({j for kind, j, v in burst if kind == DIGITAL and v})
    if not joins:
        return
    shown = ", ".join(f"d{j}" for j in joins)
    name = (await asyncio.to_thread(input, f"Name for {shown} (Enter to skip): ")).strip()
    if not name:
        return
    note = "" if len(joins) == 1 else f"  # also went high: {shown}"
    entry = f"  - {{type: binary_sensor, name: {json.dumps(name)}, join: {joins[0]}}}{note}\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry)
    print(f"appended to {path}")


def run_watch(args) -> int:
    return asyncio.run(_watch(args))
