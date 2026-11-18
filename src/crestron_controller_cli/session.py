"""`crestron-controller listen` and `watch`: register as a panel and record what arrives.

Both register on an IP-ID and press nothing by default. On a program that gates
its subsystems behind a home-page button, listening alone shows only the menu;
`--enter JOIN --allow-press` presses that one join (and nothing else) so the
subsystem's joins arrive, and measures how the entry dump is spaced so you can
set `quiet_seconds` for it. See docs/inventory/listening-to-a-processor.md.

`--tls` speaks CIP inside TLS (port 41796 by default) and prints the
processor's certificate fingerprint and the TLS version agreed. It accepts
whatever certificate the processor presents; the pinning lives in the
integration. `--legacy-tls` implies `--tls` and also accepts TLS 1.0 and 1.1.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import yaml
from cipcore.client import CipClient, Subsystem, Timing, async_probe
from cipcore.joinmap import JoinMapError, parse
from cipcore.policy import DIGITAL, LISTEN_ONLY, WritePolicy
from cipcore.protocol import (
    CIP_PORT,
    CIP_TLS_PORT,
    DATA_DIGITAL,
    TYPE_DATA,
    TYPE_EXTENDED_DATA,
    iter_records,
)

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
    parser.add_argument(
        "--port", type=int, help=f"default {CIP_PORT}, or {CIP_TLS_PORT} with --tls"
    )
    parser.add_argument(
        "--tls",
        action="store_true",
        help="encrypted CIP; prints the certificate fingerprint (not verified on real hardware)",
    )
    parser.add_argument(
        "--legacy-tls",
        action="store_true",
        help="like --tls, but also accept the older TLS 1.0 and 1.1 that old processors may need",
    )
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


def _tls(args) -> bool:
    return args.tls or args.legacy_tls


def _port(args) -> int:
    return args.port or (CIP_TLS_PORT if _tls(args) else CIP_PORT)


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
            port=_port(args),
            tls=_tls(args),
            legacy_tls=args.legacy_tls,
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
        port=_port(args),
        tls=_tls(args),
        legacy_tls=args.legacy_tls,
        subsystems={ENTERED: Subsystem(ENTERED, args.enter, quiet_seconds=2.0)},
        default_subsystem=ENTERED,
        policy=policy,
        timing=Timing(entry_timeout=10.0),
        on_join=on_join,
        on_frame=on_frame,
    )


async def _preflight(args) -> bool:
    probe = await async_probe(
        args.host, args.ipid, _port(args), tls=_tls(args), legacy_tls=args.legacy_tls
    )
    if probe.tls_version:
        print(f"TLS version: {probe.tls_version}")
    if probe.fingerprint:
        print(f"TLS certificate SHA-256: {probe.fingerprint}")
    if probe.ok:
        return True
    hints = {
        "unreachable": "nothing answered. Is this the control processor's address?",
        "ipid_missing": "the program does not define that IP-ID. Try `crestron-controller ipids`.",
        "refused": "registration refused. Authenticated CIP (username and password) is not "
        "supported.",
        "tls_failed": "the TLS handshake failed. The port may speak plain CIP (try without "
        "--tls), or the processor may be too old for TLS 1.2 (try --legacy-tls).",
        "no_greeting": "connected, but no CIP greeting arrived. If the processor requires "
        "encrypted CIP, add --tls.",
    }
    print(
        f"{args.host} IP-ID 0x{args.ipid:02X}: {hints.get(probe.result, probe.result)}",
        file=sys.stderr,
    )
    return False


class _EntryTimer:
    """Records when digital frames arrive after the entry press, to measure a dump's spacing."""

    def __init__(self) -> None:
        self.pressed_at: float | None = None
        self.stamps: list[float] = []

    def __call__(self, direction: str, ciptype: int, payload: bytes) -> None:
        if ciptype not in (TYPE_DATA, TYPE_EXTENDED_DATA):
            return
        if not any(kind == DATA_DIGITAL for kind, _ in iter_records(ciptype, payload)):
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
    objects: dict = {}
    for obj in client.smart_objects():
        objects[str(obj)] = {
            "subsystems": {
                (name or "(none)"): {
                    "digital": dict(sorted(client.digital_for(name, obj).items())),
                    "analog": dict(sorted(client.analog_for(name, obj).items())),
                }
                for name in client.buckets(obj)
            },
            "serial": dict(sorted(client.serial_for(obj).items())),
        }
    if objects:
        out["smart_objects"] = objects
    return out


def _joined(obj: int, letter: str, join: int) -> str:
    """How the CLI writes a join: d5 for the program's own, o3:d5 inside SmartObject 3."""
    return f"o{obj}:{letter}{join}" if obj else f"{letter}{join}"


def _draft(client: CipClient, args, quiet: float | None = None) -> str:
    """A draft join map: every observed join as a read-only entity with a placeholder name."""
    lines = [
        "# Draft join map from `crestron-controller listen`. Every entry is read-only and every",
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
    objects = client.smart_objects()
    if objects:
        lines += [
            "  # SmartObject joins (lists on the panel). Untested on real hardware: see",
            "  # docs/configuration/reading-lists.md before relying on these.",
        ]
    for obj in objects:
        where = f"smart_object: {obj}"
        for join, value in sorted(client.digital_for(bucket, obj).items()):
            state = "high" if value else "low"
            lines.append(
                f"  - {{type: binary_sensor, name: List {obj} digital {join}, join: {join}, "
                f"{where}}}  # {state}"
            )
        for join, value in sorted(client.analog_for(bucket, obj).items()):
            lines.append(
                f"  - {{type: sensor, name: List {obj} analog {join}, analog: {join}, "
                f"{where}}}  # was {value}"
            )
        for join, text in sorted(client.serial_for(obj).items()):
            shown = text.strip().replace("#", "")[:40]
            name = json.dumps(f"List {obj} serial {join}")
            lines.append(
                f"  - {{type: sensor, name: {name}, serial: {join}, {where}}}  # {shown!r}"
            )
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
    for obj, data in snap.get("smart_objects", {}).items():
        count = sum(len(b["digital"]) + len(b["analog"]) for b in data["subsystems"].values())
        print(
            f"SmartObject {obj}: {count} digital and analog, {len(data['serial'])} serial "
            "(untested on real hardware)"
        )
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
    burst: list[tuple[str, int, int | str, int]] = []
    started = time.monotonic()

    def on_join(kind: str, join: int, value, subsystem, obj: int = 0) -> None:
        if not client.synced:
            return  # the initial dump is state, not something you just pressed
        shown = _joined(obj, kind[0], join)
        print(f"{time.monotonic() - started:8.2f}s  {shown} = {value!r}", flush=True)
        burst.append((kind, join, value, obj))

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


async def _label(path: Path, burst: list[tuple[str, int, int | str, int]]) -> None:
    # Sorted with the program's own joins first, so one of those is preferred.
    joins = sorted({(obj, j) for kind, j, v, obj in burst if kind == DIGITAL and v})
    if not joins:
        return
    shown = ", ".join(_joined(obj, "d", j) for obj, j in joins)
    name = (await asyncio.to_thread(input, f"Name for {shown} (Enter to skip): ")).strip()
    if not name:
        return
    note = "" if len(joins) == 1 else f"  # also went high: {shown}"
    obj, join = joins[0]
    where = f", smart_object: {obj}" if obj else ""
    entry = f"  - {{type: binary_sensor, name: {json.dumps(name)}, join: {join}{where}}}{note}\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry)
    print(f"appended to {path}")


def run_watch(args) -> int:
    return asyncio.run(_watch(args))
