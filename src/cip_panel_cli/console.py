"""A small client for a Crestron processor's text console, and the commands built on it.

Crestron processors and touch panels expose the same plain-text console in two
places. Port 23 is telnet: the device opens with option negotiation, which this
client refuses outright rather than implementing, because nothing here needs a
single telnet option. Port 41795 is CTP, the same console with no negotiation at
all, which matters for file transfer: binary passes through it unescaped, and
some commands that port 23 blocks ("Command Blocked from this console type")
are allowed there. See ctp.py.

Everything this module sends on its own initiative is read-only. `ipids` sends
`VER` and `IPTABLE` and nothing else. `console` sends whatever the user types,
behind a denylist that is a seatbelt, not a guarantee.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

TELNET_PORT = 23
CTP_PORT = 41795

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240

# A console prompt is a short word ending in ">" on a line of its own, such as
# "CP3>" or "TSW-752>". Seeing one lets a read finish as soon as the reply is
# complete instead of always waiting out the quiet window.
_PROMPT = re.compile(r"(?:^|\n)[A-Za-z0-9_.\-]{1,32}>\s*$")
_LOGIN_PROMPT = re.compile(r"(?:user\s*name|login)\s*:\s*$", re.IGNORECASE)
_PASSWORD_PROMPT = re.compile(r"password\s*:\s*$", re.IGNORECASE)


class ConsoleError(Exception):
    """The console could not be reached, or refused what was asked of it."""


class TelnetFilter:
    """Strips telnet option negotiation out of a byte stream and refuses every option.

    State carries across reads, because a negotiation sequence can be split
    between two TCP segments and a filter that only looked inside one read
    would leak half of it into the text.
    """

    def __init__(self, send: Callable[[bytes], None]) -> None:
        self._send = send
        self._pending = b""

    def feed(self, data: bytes) -> bytes:
        data = self._pending + data
        self._pending = b""
        out = bytearray()
        i = 0
        while i < len(data):
            byte = data[i]
            if byte != IAC:
                out.append(byte)
                i += 1
                continue
            if i + 1 >= len(data):
                self._pending = data[i:]
                break
            cmd = data[i + 1]
            if cmd in (DO, DONT, WILL, WONT):
                if i + 2 >= len(data):
                    self._pending = data[i:]
                    break
                # Refuse whatever is offered or asked. Answering DONT and WONT
                # with silence is correct: they already describe the state we
                # want, and replying to them can start a negotiation loop.
                reply = {DO: WONT, WILL: DONT}.get(cmd)
                if reply is not None:
                    self._send(bytes([IAC, reply, data[i + 2]]))
                i += 3
            elif cmd == SB:
                end = data.find(bytes([IAC, SE]), i)
                if end < 0:
                    self._pending = data[i:]
                    break
                i = end + 2
            elif cmd == IAC:
                out.append(IAC)  # an escaped literal 0xFF
                i += 2
            else:
                i += 2
        return bytes(out)


@dataclass
class Credentials:
    """A username and a way to get the password only if a device asks for one.

    The password is fetched lazily so that nobody is prompted for a secret
    that an unauthenticated processor never wanted.
    """

    username: str | None = None
    password_env: str | None = None

    def password(self) -> str:
        if self.password_env:
            value = os.environ.get(self.password_env)
            if value is None:
                raise ConsoleError(f"environment variable {self.password_env} is not set")
            return value
        return getpass.getpass("Console password: ")


class Console:
    """One connection to a processor or panel console.

    Login support is untested against real authenticated processors: it was
    written from the prompts such devices are documented to show and checked
    only against a local fake. If a device with authentication enabled does
    something different, `-v` logs what it sent.
    """

    def __init__(
        self,
        host: str,
        port: int = TELNET_PORT,
        *,
        telnet: bool | None = None,
        credentials: Credentials | None = None,
        connect_timeout: float = 8.0,
    ) -> None:
        self.host = host
        self.port = port
        # Port 23 negotiates; CTP does not. Filtering CTP for IAC bytes would
        # corrupt binary transfers, so the default follows the port.
        self.telnet = (port == TELNET_PORT) if telnet is None else telnet
        self.credentials = credentials or Credentials()
        self.connect_timeout = connect_timeout
        self.sock: socket.socket | None = None
        self._filter: TelnetFilter | None = None

    def __enter__(self) -> Console:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def open(self, banner_seconds: float = 3.0) -> str:
        """Connect, read the banner, and log in if asked. Returns the banner text."""
        try:
            self.sock = socket.create_connection(
                (self.host, self.port), timeout=self.connect_timeout
            )
        except OSError as err:
            raise ConsoleError(f"could not connect to {self.host}:{self.port}: {err}") from err
        if self.telnet:
            self._filter = TelnetFilter(self.sock.sendall)
        banner = self.read(banner_seconds)
        return banner + self._login(banner)

    def _login(self, text: str) -> str:
        """Answer up to one username and one password prompt."""
        seen = ""
        for _ in range(2):
            tail = text.rstrip(" ")
            if _LOGIN_PROMPT.search(tail):
                if not self.credentials.username:
                    raise ConsoleError(
                        "the console asked for a username; pass --username "
                        "(and --password-env, or answer the prompt)"
                    )
                self.send_line(self.credentials.username)
            elif _PASSWORD_PROMPT.search(tail):
                self.send_line(self.credentials.password())
            else:
                return seen
            text = self.read(3.0)
            seen += text
            if re.search(r"(incorrect|invalid|failed|denied)", text, re.IGNORECASE):
                raise ConsoleError("the console rejected the username or password")
        return seen

    def send_line(self, line: str) -> None:
        assert self.sock is not None, "open() first"
        self.sock.sendall(line.encode("latin-1") + b"\r\n")

    def read(self, seconds: float = 2.0, *, quiet: float = 0.4) -> str:
        """Read until a prompt appears, the device goes quiet, or `seconds` pass.

        Quiet alone is not enough to end a read before anything has arrived,
        because some commands take a second or more to start answering.
        """
        assert self.sock is not None, "open() first"
        chunks: list[bytes] = []
        deadline = time.monotonic() + seconds
        while (remaining := deadline - time.monotonic()) > 0:
            self.sock.settimeout(min(quiet, remaining))
            try:
                data = self.sock.recv(4096)
            except TimeoutError:
                if chunks:
                    break
                continue
            if not data:
                break
            chunks.append(self._filter.feed(data) if self._filter else data)
            text = b"".join(chunks).decode("latin-1")
            if _PROMPT.search(text) or _PASSWORD_PROMPT.search(text.rstrip(" ")):
                break
        return b"".join(chunks).decode("latin-1")

    def command(self, line: str, seconds: float = 4.0) -> str:
        """Send one command line and return its reply with echo and prompt removed."""
        self.send_line(line)
        return clean_reply(self.read(seconds), line)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None


def clean_reply(text: str, command: str) -> str:
    """Drop the echoed command and the trailing prompt from a console reply."""
    lines = text.replace("\r", "").split("\n")
    if lines and lines[0].strip().lower() == command.strip().lower():
        lines = lines[1:]
    while lines and (not lines[-1].strip() or _PROMPT.search("\n" + lines[-1])):
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines)


# ---- IPTABLE ---------------------------------------------------------------


@dataclass(frozen=True)
class IpTableEntry:
    ipid: int
    kind: str
    status: str
    address: str
    port: int | None = None
    device_id: str = ""
    description: str = ""

    @property
    def online(self) -> bool:
        return self.status.upper() == "ONLINE"


_STATUSES = {"ONLINE", "OFFLINE", "CONNECTING", "DISCONNECTED", "NOT", "PENDING"}


def parse_iptable(text: str) -> list[IpTableEntry] | None:
    """Parse `IPTABLE` output, or return None if it does not look like a table.

    The layout assumed is the one Crestron processors print: a header line
    naming `CIP_ID`, then one row per entry with the IP-ID in hex, a type
    (such as Gway or Peer), a status, an often-empty device ID, a port, the
    remote address, and on newer firmware some extra descriptive columns.
    Because the device ID column is usually blank, whitespace splitting cannot
    find columns by position, so a row is anchored on its status word and its
    port number instead. Anything unrecognised returns None so the caller can
    show the raw text rather than a confidently wrong table.
    """
    lines = text.replace("\r", "").split("\n")
    start = next((i for i, line in enumerate(lines) if "CIP_ID" in line.upper()), None)
    if start is None:
        return None
    entries: list[IpTableEntry] = []
    for line in lines[start + 1 :]:
        tokens = line.split()
        if not tokens:
            continue
        if not re.fullmatch(r"[0-9A-Fa-f]{1,2}", tokens[0]):
            if entries:
                break  # the table has ended, likely at the prompt
            continue
        status_at = next((i for i, t in enumerate(tokens) if t.upper() in _STATUSES), None)
        if status_at is None or status_at < 1:
            return None
        kind = " ".join(tokens[1:status_at])
        status = tokens[status_at].upper()
        rest = tokens[status_at + 1 :]
        if status == "NOT" and rest and rest[0].upper() in ("CONNECTED", "ONLINE"):
            status = f"NOT {rest.pop(0).upper()}"
        port_at = next((i for i, t in enumerate(rest) if re.fullmatch(r"\d{2,5}", t)), None)
        if port_at is not None and port_at + 1 < len(rest):
            device_id = " ".join(rest[:port_at])
            port: int | None = int(rest[port_at])
            address = rest[port_at + 1]
            description = " ".join(rest[port_at + 2 :])
        elif rest:
            device_id, port, address, description = "", None, rest[0], " ".join(rest[1:])
        else:
            return None
        entries.append(
            IpTableEntry(
                ipid=int(tokens[0], 16),
                kind=kind,
                status=status,
                address=address,
                port=port,
                device_id=device_id,
                description=description,
            )
        )
    return entries or None


def format_iptable(entries: list[IpTableEntry]) -> str:
    rows = [("IP-ID", "Type", "Status", "Address", "Port", "Description")]
    for e in entries:
        port = "" if e.port is None else str(e.port)
        rows.append((f"0x{e.ipid:02X}", e.kind, e.status, e.address, port, e.description))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)).rstrip()
        for row in rows
    )


# ---- the denylist ----------------------------------------------------------

# Commands refused whatever their arguments. Each restarts, erases, reflashes,
# or rewrites the program, its files, its users, or its IP table.
_ALWAYS_DENY = {
    "reboot",
    "restart",
    "progreset",
    "progload",
    "progrestart",
    "stopprog",
    "killprog",
    "initialize",
    "del",
    "delete",
    "erase",
    "format",
    "rmdir",
    "mkdir",
    "rename",
    "copyfile",
    "xputfile",
    "puf",
    "fwupdate",
    "firmware",
    "upgrade",
    "restore",
    "factory",
    "resetpassword",
    "password",
    "adduser",
    "deleteuser",
}

# Commands that report a setting when given no argument and change it when
# given one. They are refused only with arguments.
_DENY_WITH_ARGS = {
    "iptable",
    "ipt",
    "ipaddress",
    "ipmask",
    "defrouter",
    "dhcp",
    "hostname",
    "domain",
    "sntp",
    "timezone",
    "time",
    "date",
    "authentication",
    "auth",
    "ssl",
    "telnetport",
    "ctpport",
    "cipport",
    "webport",
    "webserver",
    "autodiscovery",
}

# Prefixes that, across Crestron firmware, name commands that add to, remove
# from, or set something: ADDMASTER, REMPEER, DELETEUSER, SETCSLOG and so on.
_DENY_PREFIXES = ("add", "rem", "del", "set")


def denied(line: str) -> str | None:
    """Return why a console command is refused, or None if it may be sent.

    This is a seatbelt, not a guarantee. Crestron firmware has hundreds of
    commands, varies by model and version, and accepts abbreviations, so a
    command missing from these lists is not thereby safe.
    """
    tokens = line.split()
    if not tokens:
        return "empty command"
    word = tokens[0].lower()
    if word in _ALWAYS_DENY:
        return f"{tokens[0]} can restart, erase or reconfigure the device"
    if word in _DENY_WITH_ARGS and len(tokens) > 1:
        return f"{tokens[0]} with arguments changes a setting; run it bare to read it"
    if word.startswith(_DENY_PREFIXES):
        return f"{tokens[0]} looks like a command that adds, removes or sets something"
    return None


# ---- command-line plumbing -------------------------------------------------


def add_connection_args(parser: argparse.ArgumentParser, *, default_port: int) -> None:
    """The host, port and login options every console-based command takes."""
    parser.add_argument("host", help="processor or panel address")
    parser.add_argument(
        "--port",
        type=int,
        choices=(TELNET_PORT, CTP_PORT),
        default=default_port,
        help=f"{TELNET_PORT} for telnet, {CTP_PORT} for CTP (default {default_port})",
    )
    parser.add_argument(
        "--username", help="username, if the console asks for one (login is untested)"
    )
    parser.add_argument(
        "--password-env",
        metavar="VAR",
        help="read the password from this environment variable; without it you are "
        "prompted, and only if the console asks. There is no option to pass a "
        "password on the command line, because it would land in shell history",
    )


def open_console(args: argparse.Namespace) -> Console:
    console = Console(
        args.host,
        args.port,
        credentials=Credentials(args.username, args.password_env),
    )
    console.open()
    return console


def run_ipids(args: argparse.Namespace) -> int:
    try:
        with open_console(args) as con:
            version = con.command("VER")
            table = con.command("IPTABLE", seconds=6.0)
    except ConsoleError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    first = next((line.strip() for line in version.splitlines() if line.strip()), "")
    print(f"Version: {first or '(no reply)'}")
    print()
    entries = parse_iptable(table)
    if entries is None:
        print("Could not parse the IP table; the raw reply follows.")
        print(table)
        return 0
    print(format_iptable(entries))
    offline = [e for e in entries if not e.online]
    if offline:
        ids = ", ".join(f"0x{e.ipid:02X}" for e in offline)
        print()
        print(f"Defined but not online: {ids}. These are candidate slots to borrow.")
    if any(e.online and e.kind.lower() == "gway" for e in entries):
        # Observed on one processor: touch panel slots that go through the
        # processor's internal gateway (listed at 127.0.0.1) read ONLINE
        # whether or not a panel is connected, including one whose panel had
        # been unplugged. So ONLINE there does not mean the slot is in use.
        print()
        print(
            "Note: 'Gway' entries can read ONLINE with no panel connected. Before "
            "borrowing one, make sure its physical panel is unplugged or switched off."
        )
    return 0


def run_console(args: argparse.Namespace) -> int:
    commands = [" ".join(args.command)] if not args.each else list(args.command)
    for line in commands:
        reason = denied(line)
        if reason:
            print(f"refused: {line!r}: {reason}", file=sys.stderr)
            return 2
    try:
        with open_console(args) as con:
            for line in commands:
                print(f"=== {line} ===")
                print(con.command(line, seconds=args.wait))
    except ConsoleError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    ipids = subparsers.add_parser(
        "ipids",
        help="list the IP-IDs a processor's program defines and which are online",
        description=(
            "Send the read-only VER and IPTABLE commands and print the IP table. "
            "The table lists every IP-ID the running program defines and its "
            "status. An IP-ID that is defined but offline is a candidate slot "
            "for this integration to borrow. Panel slots routed through the "
            "processor's internal gateway ('Gway', at 127.0.0.1) have been seen "
            "reading ONLINE with their panel unplugged, so for those, check the "
            "physical panel instead of trusting the status. An IP-ID missing from "
            "the table cannot be used at all: the processor refuses to register it."
        ),
    )
    add_connection_args(ipids, default_port=TELNET_PORT)
    ipids.set_defaults(func=run_ipids)

    con = subparsers.add_parser(
        "console",
        help="send console commands (WARNING: you are responsible for what they do)",
        description=(
            "WARNING: console commands can change processor state, and some can "
            "restart the program or erase it. You are responsible for what you "
            "send. A small denylist refuses the obviously destructive commands "
            "(reboot, progreset, erase, IP table and settings changes, and so on), "
            "but it is a seatbelt, not a guarantee: firmware varies and accepts "
            "abbreviations, so a command it does not refuse is not thereby safe. "
            "Stick to commands you know are read-only, such as VER, IPTABLE, WHO, "
            "ERR and PROGCOMMENTS."
        ),
    )
    add_connection_args(con, default_port=TELNET_PORT)
    con.add_argument("command", nargs="+", help="the command line to send")
    con.add_argument(
        "--each",
        action="store_true",
        help="treat each argument as a separate command instead of one command line",
    )
    con.add_argument(
        "--wait", type=float, default=4.0, help="seconds to wait for each reply (default 4)"
    )
    con.set_defaults(func=run_console)
