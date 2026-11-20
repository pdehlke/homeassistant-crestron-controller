"""Fetch a touch panel's project file and turn it into an inventory and a draft join map.

A TSW x52-series panel (TSW-552, TSW-752, TSW-1052 and their kin) keeps its
compiled VT Pro-e project on its own flash as one XML file, `Environment.xml`,
and hands it over through `XGETFILE` on its CTP console. The file names every
page, every button and every join number in the clear. Reading the joins from
it is the safe way to build a join map; the alternative, pressing joins to see
what they do, risks arming an alarm or opening a gate on a program that reuses
join numbers across subsystems.

Two formats are understood: the x52 Environment.xml, read by x52.py, and the
HTML5 .ch5z archives that x60 and x70 panels run, read by ch5.py. Support for
.ch5z is experimental and untested against a real panel. draft.py renders
either into the outputs.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import ch5, ctp, x52
from .console import CTP_PORT, ConsoleError, add_connection_args, open_console
from .draft import draft_join_map, inventory_csv, summary
from .project import FORMATS_DOC, Project, UnsupportedFormat

DEFAULT_REMOTE_PATH = "\\display\\swf\\Environment.xml"


def load_project(path: Path) -> Project:
    """Read a panel project, choosing the reader by the file's contents."""
    raw = path.read_bytes()
    if raw.startswith(b"PK\x03\x04"):
        return ch5.load_ch5z(raw)
    return x52.parse_project(x52.decode_project(raw))


# ---- commands --------------------------------------------------------------


def run_parse(args: argparse.Namespace) -> int:
    path = Path(args.file)
    try:
        project = load_project(path)
    except OSError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except UnsupportedFormat as err:
        print(f"error: {path}: {err}", file=sys.stderr)
        return 2

    if args.format == "csv":
        text = inventory_csv(project)
    else:
        text = draft_join_map(project, source=path.name)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(summary(project), file=sys.stderr)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def run_fetch(args: argparse.Namespace) -> int:
    print(
        "This reads the project from the panel's flash over XMODEM. On a TSW-752 it "
        "takes roughly 10-15 minutes; the panel keeps working meanwhile.",
        file=sys.stderr,
    )
    started = time.monotonic()
    last = [0.0]

    def progress(count: int) -> None:
        now = time.monotonic()
        if now - last[0] >= 2.0:
            last[0] = now
            rate = count / max(now - started, 0.001) / 1024
            print(f"  {count // 1024} KiB received, {rate:.1f} KiB/s", file=sys.stderr)

    try:
        with open_console(args) as con:
            assert con.sock is not None
            reader = ctp.Reader(con.sock)
            reply = ctp.request_file(con.sock, reader, args.remote_path)
            refused = ctp.refusal(reply)
            if refused:
                print(f"error: the panel refused: {refused}", file=sys.stderr)
                print(
                    "Check the path with "
                    "`crestron-controller console HOST --port 41795 DIR \\display`.",
                    file=sys.stderr,
                )
                return 1
            data = ctp.receive(con.sock, reader, on_progress=progress)
    except ConsoleError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except ctp.XmodemError as err:
        print(f"error: {err}; nothing was written", file=sys.stderr)
        return 1

    data = ctp.strip_padding(data)
    Path(args.output).write_bytes(data)
    elapsed = time.monotonic() - started
    print(f"wrote {args.output}: {len(data)} bytes in {elapsed:.0f}s", file=sys.stderr)
    print(f"next: crestron-controller panel parse {args.output} -o draft.yaml", file=sys.stderr)
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    panel = subparsers.add_parser(
        "panel",
        help="fetch and parse a touch panel's project file",
        description=(
            "Fetch a TSW x52 panel's Environment.xml, or read an x60/x70 .ch5z project "
            "(experimental), and turn it into a draft join map."
        ),
    )
    sub = panel.add_subparsers(dest="panel_command", required=True, metavar="ACTION")

    fetch = sub.add_parser(
        "fetch",
        help="download Environment.xml from a TSW x52 panel's CTP console",
        description=(
            "Download the panel's compiled project over XMODEM on the CTP console "
            "(port 41795; telnet on port 23 refuses the transfer). Read-only. "
            "Takes roughly 10-15 minutes on a TSW-752."
        ),
    )
    add_connection_args(fetch, default_port=CTP_PORT)
    fetch.add_argument(
        "--remote-path",
        default=DEFAULT_REMOTE_PATH,
        help=f"file on the panel (default {DEFAULT_REMOTE_PATH})",
    )
    fetch.add_argument("-o", "--output", required=True, help="local file to write")
    fetch.set_defaults(func=run_fetch)

    parse = sub.add_parser(
        "parse",
        help="inventory a panel project and draft a join map",
        description=(
            "Parse an x52 Environment.xml or an x60/x70 .ch5z project. .ch5z support "
            "is experimental and untested on real panels. --format yaml (the default) "
            "writes a draft join map in which every entry is read-only; --format csv "
            "writes an inventory of every control with a join. Other panel formats are "
            f"refused; see {FORMATS_DOC}."
        ),
    )
    parse.add_argument("file", help="the Environment.xml or .ch5z to read")
    parse.add_argument("-o", "--output", help="write here instead of standard output")
    parse.add_argument("--format", choices=("yaml", "csv"), default="yaml")
    parse.set_defaults(func=run_parse)
