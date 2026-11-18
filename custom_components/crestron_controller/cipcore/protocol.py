"""CIP wire format: framing, registration, and join encoding.

Everything here is a pure function of bytes. Nothing opens a socket, so the
encodings can be tested exactly against frames recorded from real processors.

Packet framing is `<type> <len hi> <len lo> <payload>`. Joins are 1-based in
every API in this project, because every Crestron join map is written that way;
the wire is 0-based, hence the -1 and +1 at each boundary below.

The wire format was first worked out from klenae/python-cipclient (MIT, see
THIRD_PARTY_NOTICES.md) and then re-implemented and checked against live
processors. Which parts were checked live and which were not is recorded in
docs/protocol/cip-wire-format.md; the short version is that registration,
heartbeat, the update request and every digital encoding were observed on real
hardware, and the analog and serial *writes* were not.
"""

from __future__ import annotations

CIP_PORT = 41794
# The same frames inside TLS. See docs/adr/0011-cip-over-tls-with-a-pinned-certificate.md.
CIP_TLS_PORT = 41796

# Packet types, as the first byte of a frame.
TYPE_REGISTER = 0x01
TYPE_REGISTER_RESULT = 0x02
TYPE_DISCONNECT = 0x03
TYPE_DATA = 0x05
TYPE_HEARTBEAT = 0x0D
TYPE_HEARTBEAT_REPLY = 0x0E
TYPE_REGISTER_REQUEST = 0x0F
TYPE_SERIAL = 0x12

# Data types, as the fourth payload byte of a type 0x05 frame.
DATA_DIGITAL = 0x00
DATA_ANALOG_SHORT = 0x01
DATA_SERIAL_INDEXED = 0x02
DATA_UPDATE = 0x03
DATA_ANALOG = 0x14
DATA_SERIAL = 0x15

END_OF_QUERY = 0x1C

HEARTBEAT = b"\x0d\x00\x02\x00\x00"
UPDATE_REQUEST = b"\x05\x00\x05\x00\x00\x02\x03\x00"
END_OF_QUERY_ACK = b"\x05\x00\x05\x00\x00\x02\x03\x1d"

# What a processor answers when the IP-ID is not defined in its program.
IPID_MISSING = b"\xff\xff\x02"

MAX_JOIN = 0x7FFF + 1
ANALOG_MAX = 0xFFFF


def frame(ciptype: int, payload: bytes) -> bytes:
    """Wrap a payload in the three-byte CIP header."""
    return bytes([ciptype, (len(payload) >> 8) & 0xFF, len(payload) & 0xFF]) + payload


def split_frames(buf: bytes) -> tuple[list[tuple[int, bytes]], bytes]:
    """Cut every complete frame off the front of a receive buffer.

    Returns the frames as (type, payload) pairs and whatever partial frame is
    left over, which belongs at the front of the next read.
    """
    frames: list[tuple[int, bytes]] = []
    while len(buf) >= 3:
        length = (buf[1] << 8) + buf[2]
        if len(buf) < length + 3:
            break
        frames.append((buf[0], buf[3 : 3 + length]))
        buf = buf[length + 3 :]
    return frames, buf


def registration(ipid: int) -> bytes:
    """The packet a client sends to claim one IP-ID."""
    if not 0x03 <= ipid <= 0xFE:
        raise ValueError(f"IP-ID 0x{ipid:02X} is outside 0x03-0xFE")
    return b"\x01\x00\x0b\x00\x00\x00\x00\x00" + bytes([ipid]) + b"\x40\xff\xff\xf1\x01"


def _check_join(join: int) -> int:
    if not 1 <= join <= MAX_JOIN:
        raise ValueError(f"join {join} is outside 1-{MAX_JOIN}")
    return join - 1


def digital_packet(join: int, pressed: bool) -> bytes:
    """Encode a digital join press or release.

    The encoding is identical in both directions: datatype 0x00, the 0-based
    join's low byte, then a byte carrying the high bits whose top bit is SET for
    low and CLEAR for high. Pressing join 24 is `05 00 06 00 00 03 00 17 00` and
    releasing it is `05 00 06 00 00 03 00 17 80`.
    """
    n = _check_join(join)
    body = bytes([DATA_DIGITAL, n & 0xFF, ((n >> 8) & 0x7F) | (0x00 if pressed else 0x80)])
    return frame(TYPE_DATA, bytes([0x00, 0x00, len(body)]) + body)


def analog_packet(join: int, value: int) -> bytes:
    """Encode an analog join write.

    Taken from klenae/python-cipclient and not yet observed working against a
    live processor by this project: the one system this was developed on has no
    program logic that accepts an analog write from a panel. See
    docs/protocol/cip-wire-format.md.
    """
    n = _check_join(join)
    if not 0 <= value <= ANALOG_MAX:
        raise ValueError(f"analog value {value} is outside 0-{ANALOG_MAX}")
    body = bytes([DATA_ANALOG, (n >> 8) & 0xFF, n & 0xFF, (value >> 8) & 0xFF, value & 0xFF])
    return frame(TYPE_DATA, bytes([0x00, 0x00, len(body)]) + body)


def serial_packet(join: int, text: str) -> bytes:
    """Encode a serial join write. Same provenance and caveat as analog_packet."""
    n = _check_join(join)
    data = text.encode("latin-1")
    body = bytes([0x34, (n >> 8) & 0xFF, n & 0xFF, 0x03]) + data
    return frame(TYPE_SERIAL, bytes([0x00, 0x00, 0x00, len(body)]) + body)


def decode_digitals(body: bytes) -> list[tuple[int, int]]:
    """Decode a digital data body into (join, value) pairs.

    One frame can carry several joins. Some processors pack five into a single
    frame, and reading only the first loses the rest.
    """
    out: list[tuple[int, int]] = []
    for i in range(0, len(body) - 1, 2):
        join = (((body[i + 1] & 0x7F) << 8) | body[i]) + 1
        out.append((join, ((body[i + 1] & 0x80) >> 7) ^ 1))
    return out


def decode_analogs(body: bytes) -> list[tuple[int, int]]:
    """Decode a datatype 0x14 body: four bytes per join, join then value."""
    out: list[tuple[int, int]] = []
    for i in range(0, len(body) - 3, 4):
        join = ((body[i] << 8) | body[i + 1]) + 1
        out.append((join, (body[i + 2] << 8) | body[i + 3]))
    return out
