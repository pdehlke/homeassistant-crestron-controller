"""Retrieve a file from a Crestron device over its CTP console with XMODEM.

`XGETFILE <path>` makes the device send a file by XMODEM over the console
connection itself. It has to be the CTP console on port 41795, not telnet on
port 23, for two reasons. The telnet console refuses the command outright
("Command Blocked from this console type"). And telnet doubles every 0xFF byte
and interleaves option negotiation, which would corrupt a binary transfer even
if it were allowed; CTP is the same console with neither, so the bytes arrive
exactly as sent.

The receiver is standard XMODEM: it asks for CRC-16 first, falls back to the
plain checksum if the sender ignores that, accepts both 128-byte and 1K blocks,
and NAKs anything damaged so the sender repeats it. A touch panel reads its
flash slowly, so a large file takes many minutes, and the speed is the panel's
rather than the network's.
"""

from __future__ import annotations

import socket
from collections.abc import Callable

SOH, STX, EOT, ACK, NAK, CAN, SUB = 0x01, 0x02, 0x04, 0x06, 0x15, 0x18, 0x1A


class XmodemError(Exception):
    """The transfer failed. `partial` holds whatever arrived before it did."""

    def __init__(self, message: str, partial: bytes = b"") -> None:
        super().__init__(message)
        self.partial = partial


def crc16(data: bytes) -> int:
    """XMODEM's CRC-16/XMODEM: polynomial 0x1021, zero seed, no reflection."""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


class Reader:
    """Socket reader with pushback, so a packet can be pulled out byte-exactly.

    A single recv() can return the tail of one block and the head of the next.
    Keeping the surplus here, rather than discarding it, is what lets the
    receiver read exactly one block at a time.
    """

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.buf = b""

    def read(self, count: int, timeout: float) -> bytes:
        """Return up to `count` bytes, fewer if `timeout` passes between arrivals."""
        self.sock.settimeout(timeout)
        while len(self.buf) < count:
            try:
                chunk = self.sock.recv(65536)
            except TimeoutError:
                break
            if not chunk:
                break
            self.buf += chunk
        out, self.buf = self.buf[:count], self.buf[count:]
        return out


def receive(
    sock: socket.socket,
    reader: Reader | None = None,
    *,
    on_progress: Callable[[int], None] | None = None,
    byte_timeout: float = 3.0,
    block_timeout: float = 6.0,
    max_idle: int = 40,
) -> bytes:
    """Receive one XMODEM transfer and return its payload, padding included.

    Raises XmodemError if the sender cancels or goes silent. Returning the
    partial data instead would let a caller write a truncated file and report
    success, which for a 10-minute transfer is the worse failure.
    """
    reader = reader or Reader(sock)
    data = bytearray()
    expect = 1
    crc_mode = True
    started = False
    idle = 0

    sock.sendall(b"C")  # 'C' asks for CRC-16; NAK would ask for the plain checksum
    while idle < max_idle:
        head = reader.read(1, byte_timeout)
        if not head:
            idle += 1
            if not started:
                # Until the sender answers, alternate the two handshake bytes,
                # so a sender that only knows the checksum variant still starts.
                crc_mode = not crc_mode
                sock.sendall(b"C" if crc_mode else bytes([NAK]))
            # Mid-transfer, silence is left to the sender's own retry timer.
            # A panel reading slow flash can pause, and a NAK sent into that
            # pause would only make it resend a block that was on its way.
            continue
        marker = head[0]

        if marker == EOT:
            sock.sendall(bytes([ACK]))
            return bytes(data)
        if marker == CAN:
            raise XmodemError(f"sender cancelled after {len(data)} bytes", bytes(data))
        if marker not in (SOH, STX):
            continue  # console text or padding ahead of the first block

        size = 128 if marker == SOH else 1024
        trail_len = 2 if crc_mode else 1
        started, idle = True, 0
        body = reader.read(2 + size + trail_len, block_timeout)
        if len(body) < 2 + size + trail_len:
            sock.sendall(bytes([NAK]))
            continue

        blk, nblk = body[0], body[1]
        payload = body[2 : 2 + size]
        trail = body[2 + size :]

        good = (blk ^ 0xFF) == nblk
        if good:
            good = (
                crc16(payload) == (trail[0] << 8 | trail[1])
                if crc_mode
                else (sum(payload) & 0xFF) == trail[0]
            )
        if not good:
            sock.sendall(bytes([NAK]))
            continue

        if blk == expect:
            data += payload
            expect = (expect + 1) % 256
            if on_progress:
                on_progress(len(data))
        elif blk != (expect - 1) % 256:
            # A block that passed its checksum but is neither the next one nor
            # a repeat of the last means the two ends disagree about where they
            # are. ACKing it would silently drop data, so stop instead.
            sock.sendall(bytes([CAN, CAN]))
            raise XmodemError(
                f"block {blk} arrived when {expect} was expected; transfer out of step",
                bytes(data),
            )
        # A repeat of the last block means our ACK was lost: ACK it again and
        # keep only the first copy.
        sock.sendall(bytes([ACK]))

    raise XmodemError(f"sender went silent after {len(data)} bytes", bytes(data))


def strip_padding(data: bytes) -> bytes:
    """Drop the SUB (0x1A) bytes XMODEM pads the final block with.

    XMODEM carries no file length, so this cannot tell padding from a file
    that genuinely ends in 0x1A. Some devices pad with NUL instead; those are
    left alone here, and callers that know their format trim them.
    """
    return data.rstrip(bytes([SUB]))


def request_file(sock: socket.socket, reader: Reader, remote_path: str) -> str:
    """Send XGETFILE and return the device's reply up to the start of the transfer.

    The path goes unquoted. Quoting it makes the device look for a name that
    includes the quotes, and it answers "Not Found" even for a valid path.
    """
    sock.sendall(f"XGETFILE {remote_path}\r\n".encode("latin-1"))
    # The device prints a line saying it is ready and then waits for the
    # receiver's 'C'. Nothing of the file arrives before that, so reading the
    # line here cannot swallow the first block.
    reply = reader.read(1, 3.0)
    while reply and (more := reader.read(1, 0.3)):
        reply += more
    return reply.decode("latin-1", errors="replace")


_REFUSALS = ("not found", "blocked", "error", "invalid", "bad command", "unknown")


def refusal(prompt: str) -> str | None:
    """Return the device's refusal text if XGETFILE was turned down."""
    lowered = prompt.lower()
    if any(word in lowered for word in _REFUSALS):
        return " ".join(prompt.split())
    return None
