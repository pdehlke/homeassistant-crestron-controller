"""Tests for the console client, the IPTABLE parser, and the console denylist.

Every IPTABLE sample here is synthetic: invented IP-IDs and 10.0.0.x
addresses laid out the way Crestron processors print the table.
"""

from __future__ import annotations

import argparse
import socket

import pytest
from cli_fakes import read_line

from crestron_controller_cli import console as c

# A newer-firmware layout: blank DevID column and trailing descriptive columns.
IPTABLE_WIDE = """\
IPTABLE

IP Table:
CIP_ID  Type    Status    DevID   Port   IP Address/SiteName   Model Name   Description
     3  Gway    ONLINE            41794  10.0.0.21             TSW-752      Den Panel
     4  Gway    OFFLINE           41794  10.0.0.22             TSW-752      Spare Panel
     A  Peer    ONLINE            41794  10.0.0.5
    1F  Gway    OFFLINE           41794  127.000.000.001
CP4>"""

# An older layout with fewer columns.
IPTABLE_NARROW = """\
IP Table:
CIP_ID  Type    Status    DevID   Port   IP Address/SiteName
     5  Peer    ONLINE            41794  10.0.0.9
    11  Gway    OFFLINE           41794  127.0.0.1
"""


# ---- TelnetFilter ------------------------------------------------------------


def test_telnet_filter_refuses_every_option():
    sent: list[bytes] = []
    f = c.TelnetFilter(sent.append)
    data = bytes([c.IAC, c.DO, 1, c.IAC, c.WILL, 3, c.IAC, c.DONT, 5]) + b"hello"
    assert f.feed(data) == b"hello"
    assert sent == [bytes([c.IAC, c.WONT, 1]), bytes([c.IAC, c.DONT, 3])]


def test_telnet_filter_handles_a_sequence_split_across_reads():
    sent: list[bytes] = []
    f = c.TelnetFilter(sent.append)
    assert f.feed(b"ab" + bytes([c.IAC])) == b"ab"
    assert f.feed(bytes([c.DO])) == b""
    assert f.feed(bytes([24]) + b"cd") == b"cd"
    assert sent == [bytes([c.IAC, c.WONT, 24])]


def test_telnet_filter_skips_subnegotiation_and_unescapes_iac():
    f = c.TelnetFilter(lambda _: None)
    data = bytes([c.IAC, c.SB, 24, 1, c.IAC, c.SE]) + b"x" + bytes([c.IAC, c.IAC]) + b"y"
    assert f.feed(data) == b"x\xffy"


# ---- IPTABLE -----------------------------------------------------------------


def test_parse_iptable_wide_layout():
    entries = c.parse_iptable(IPTABLE_WIDE)
    assert entries is not None
    assert [e.ipid for e in entries] == [0x03, 0x04, 0x0A, 0x1F]
    den = entries[0]
    assert (den.kind, den.status, den.port, den.address) == ("Gway", "ONLINE", 41794, "10.0.0.21")
    assert den.description == "TSW-752 Den Panel"
    assert den.online and not entries[1].online
    assert entries[2].description == ""
    assert entries[3].address == "127.000.000.001"


def test_parse_iptable_narrow_layout():
    entries = c.parse_iptable(IPTABLE_NARROW)
    assert entries is not None
    assert [(e.ipid, e.kind, e.status) for e in entries] == [
        (0x05, "Peer", "ONLINE"),
        (0x11, "Gway", "OFFLINE"),
    ]


def test_parse_iptable_without_a_port_column():
    text = "CIP_ID Type Status Address\n  12  Gway  ONLINE  10.0.0.40\n"
    entries = c.parse_iptable(text)
    assert entries is not None
    assert entries[0].port is None and entries[0].address == "10.0.0.40"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Bad or Incomplete Command\r\nCP4>",
        "CIP_ID Type Status\n",  # a header and no rows
        "CIP_ID Type Status\n  3  Gway  WEIRD  41794 10.0.0.1\n",  # no status word
    ],
)
def test_parse_iptable_returns_none_for_unrecognised_output(text):
    assert c.parse_iptable(text) is None


def test_format_iptable_renders_hex_ids():
    out = c.format_iptable(c.parse_iptable(IPTABLE_NARROW) or [])
    assert "IP-ID" in out.splitlines()[0]
    assert "0x11" in out and "OFFLINE" in out


def test_clean_reply_drops_echo_and_prompt():
    assert c.clean_reply("VER\r\nCP4 Cntrl Eng [v1.0]\r\nCP4>", "VER") == "CP4 Cntrl Eng [v1.0]"


# ---- denylist ------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "reboot",
        "PROGRESET -P:1",
        "initialize",
        "del \\simpl\\*.*",
        "ERASE",
        "format \\nvram",
        "puf firmware.puf",
        "ADDMASTER 3 10.0.0.1",
        "remmaster 3",
        "addpeer 5 10.0.0.2",
        "setcslog on",
        "ipaddress 0 10.0.0.50",
        "IPTABLE -c",
        "ipt 3 10.0.0.1",
        "dhcp off",
        "hostname newname",
    ],
)
def test_denied_commands(line):
    assert c.denied(line)


@pytest.mark.parametrize("line", ["VER", "iptable", "IPT", "who", "ERR", "ipaddress", "hostname"])
def test_allowed_commands(line):
    assert c.denied(line) is None


def test_run_console_refuses_before_connecting(capsys):
    # Port 9 on loopback has nothing listening; a refusal must come first.
    args = argparse.Namespace(
        host="127.0.0.1",
        port=9,
        username=None,
        password_env=None,
        command=["reboot"],
        each=False,
        wait=1.0,
    )
    assert c.run_console(args) == 2
    assert "refused" in capsys.readouterr().err


# ---- talking to a fake console ------------------------------------------------------


def _console_handler(replies: dict[str, str], banner: bytes = b"\r\nCP4 Console\r\nCP4>"):
    def handle(conn: socket.socket) -> None:
        conn.sendall(banner)
        while line := read_line(conn):
            conn.sendall(replies.get(line.upper(), "Bad or Incomplete Command").encode() + b"\r\n")
            conn.sendall(b"CP4>")

    return handle


def test_console_refuses_telnet_negotiation_from_the_banner(fake_server):
    seen: list[bytes] = []

    def handle(conn: socket.socket) -> None:
        conn.sendall(bytes([c.IAC, c.DO, 1, c.IAC, c.WILL, 3]) + b"Welcome\r\nCP4>")
        # The two refusals may arrive in separate segments.
        refusals = b""
        while len(refusals) < 6:
            refusals += conn.recv(6 - len(refusals))
        seen.append(refusals)
        assert read_line(conn) == "VER"
        conn.sendall(b"VER\r\nCP4 Cntrl Eng [v9.9.9]\r\nCP4>")

    server = fake_server(handle)
    with c.Console("127.0.0.1", server.port, telnet=True) as con:
        banner = con.open()
        assert "Welcome" in banner and "\xff" not in banner
        assert con.command("VER") == "CP4 Cntrl Eng [v9.9.9]"
    assert seen == [bytes([c.IAC, c.WONT, 1, c.IAC, c.DONT, 3])]


def test_run_ipids_prints_version_and_table(fake_server, capsys):
    server = fake_server(
        _console_handler({"VER": "CP4 Cntrl Eng [v9.9.9]", "IPTABLE": IPTABLE_WIDE})
    )
    args = argparse.Namespace(host="127.0.0.1", port=server.port, username=None, password_env=None)
    assert c.run_ipids(args) == 0
    out = capsys.readouterr().out
    assert "Version: CP4 Cntrl Eng [v9.9.9]" in out
    assert "0x0A" in out and "10.0.0.21" in out
    assert "Defined but not online: 0x04, 0x1F" in out


def test_run_ipids_prints_raw_text_when_unparseable(fake_server, capsys):
    server = fake_server(_console_handler({"VER": "X", "IPTABLE": "Something unexpected"}))
    args = argparse.Namespace(host="127.0.0.1", port=server.port, username=None, password_env=None)
    assert c.run_ipids(args) == 0
    out = capsys.readouterr().out
    assert "Could not parse" in out and "Something unexpected" in out


def test_login_answers_username_and_password(fake_server, monkeypatch):
    monkeypatch.setenv("TEST_CONSOLE_PW", "s3cret")
    got: list[str] = []

    def handle(conn: socket.socket) -> None:
        conn.sendall(b"Console\r\nUsername: ")
        got.append(read_line(conn))
        conn.sendall(b"Password: ")
        got.append(read_line(conn))
        conn.sendall(b"\r\nCP4>")
        assert read_line(conn) == "VER"
        conn.sendall(b"v1\r\nCP4>")

    server = fake_server(handle)
    creds = c.Credentials("admin", "TEST_CONSOLE_PW")
    with c.Console("127.0.0.1", server.port, credentials=creds) as con:
        con.open()
        assert con.command("VER") == "v1"
    assert got == ["admin", "s3cret"]


def test_login_without_username_is_an_error(fake_server):
    def handle(conn: socket.socket) -> None:
        conn.sendall(b"Login: ")
        conn.recv(16)

    server = fake_server(handle)
    with (
        c.Console("127.0.0.1", server.port) as con,
        pytest.raises(c.ConsoleError, match="username"),
    ):
        con.open()


def test_rejected_login_is_an_error(fake_server, monkeypatch):
    monkeypatch.setenv("TEST_CONSOLE_PW", "wrong")

    def handle(conn: socket.socket) -> None:
        conn.sendall(b"Password: ")
        read_line(conn)
        conn.sendall(b"Login incorrect\r\n")

    server = fake_server(handle)
    creds = c.Credentials(None, "TEST_CONSOLE_PW")
    con = c.Console("127.0.0.1", server.port, credentials=creds)
    with con, pytest.raises(c.ConsoleError, match="rejected"):
        con.open()


def test_missing_password_env_is_an_error(monkeypatch):
    monkeypatch.delenv("TEST_CONSOLE_PW_UNSET", raising=False)
    with pytest.raises(c.ConsoleError, match="not set"):
        c.Credentials("admin", "TEST_CONSOLE_PW_UNSET").password()


def test_unreachable_host_is_a_console_error(socket_enabled):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with pytest.raises(c.ConsoleError, match="could not connect"):
        c.Console("127.0.0.1", port, connect_timeout=1).open()


def test_password_is_never_a_command_line_option():
    parser = argparse.ArgumentParser()
    c.add_connection_args(parser, default_port=c.TELNET_PORT)
    options = {opt for action in parser._actions for opt in action.option_strings}
    assert "--password" not in options and "--password-env" in options
