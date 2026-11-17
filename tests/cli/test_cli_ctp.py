"""Tests for the XMODEM receiver, against a sender running on the other end of a socketpair."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable

import pytest

from crestron_controller_cli import ctp
from crestron_controller_cli.ctp import ACK, CAN, EOT, NAK, SOH, STX, SUB


def block(num: int, payload: bytes, *, size: int = 128, crc: bool = True) -> bytes:
    payload = payload.ljust(size, bytes([SUB]))
    head = bytes([SOH if size == 128 else STX, num & 0xFF, 0xFF - (num & 0xFF)])
    if crc:
        value = ctp.crc16(payload)
        return head + payload + bytes([value >> 8, value & 0xFF])
    return head + payload + bytes([sum(payload) & 0xFF])


def run_sender(script: Callable[[socket.socket], None]):
    """Run `script` as the sender; return the receiver's socket and a join function."""
    rx, tx = socket.socketpair()
    errors: list[BaseException] = []

    def target() -> None:
        try:
            tx.settimeout(5)
            script(tx)
        except BaseException as err:
            errors.append(err)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()

    def join() -> None:
        thread.join(timeout=5)
        tx.close()
        rx.close()
        if errors:
            raise errors[0]

    return rx, join


def expect(sock: socket.socket, byte: int) -> None:
    got = sock.recv(1)
    assert got == bytes([byte]), f"expected {byte:#x}, got {got!r}"


def test_crc16_check_value():
    # The published check value for CRC-16/XMODEM.
    assert ctp.crc16(b"123456789") == 0x31C3
    assert ctp.crc16(b"") == 0


def test_receive_with_nak_retransmit_duplicate_and_eot():
    first = b"A" * 128
    second = bytes(range(256)) * 4  # a full 1K block

    def sender(tx: socket.socket) -> None:
        assert tx.recv(1) == b"C"
        tx.sendall(b"XGETFILE ready\r\n")  # console text before the first block
        good = block(1, first)
        damaged = good[:10] + bytes([good[10] ^ 0xFF]) + good[11:]
        tx.sendall(damaged)
        expect(tx, NAK)
        tx.sendall(good)
        expect(tx, ACK)
        tx.sendall(block(2, second, size=1024))
        expect(tx, ACK)
        tx.sendall(block(2, second, size=1024))  # as if our ACK had been lost
        expect(tx, ACK)
        tx.sendall(bytes([EOT]))
        expect(tx, ACK)

    rx, join = run_sender(sender)
    progress: list[int] = []
    data = ctp.receive(rx, on_progress=progress.append, byte_timeout=1.0)
    join()
    assert data == first + second
    assert progress == [128, 1152]


def test_receive_falls_back_to_checksum_mode():
    payload = b"plain checksum"

    def sender(tx: socket.socket) -> None:
        # A sender that only understands the checksum variant ignores 'C'.
        assert tx.recv(1) == b"C"
        expect(tx, NAK)
        tx.sendall(block(1, payload, crc=False))
        expect(tx, ACK)
        tx.sendall(bytes([EOT]))
        expect(tx, ACK)

    rx, join = run_sender(sender)
    data = ctp.receive(rx, byte_timeout=0.1)
    join()
    assert ctp.strip_padding(data) == payload


def test_receive_short_block_is_nakked():
    def sender(tx: socket.socket) -> None:
        assert tx.recv(1) == b"C"
        tx.sendall(block(1, b"x")[:50])
        expect(tx, NAK)
        tx.sendall(block(1, b"x"))
        expect(tx, ACK)
        tx.sendall(bytes([EOT]))
        expect(tx, ACK)

    rx, join = run_sender(sender)
    data = ctp.receive(rx, byte_timeout=1.0, block_timeout=0.2)
    join()
    assert ctp.strip_padding(data) == b"x"


def test_cancel_raises_with_partial_data():
    def sender(tx: socket.socket) -> None:
        assert tx.recv(1) == b"C"
        tx.sendall(block(1, b"part"))
        expect(tx, ACK)
        tx.sendall(bytes([CAN, CAN]))

    rx, join = run_sender(sender)
    with pytest.raises(ctp.XmodemError, match="cancelled") as info:
        ctp.receive(rx, byte_timeout=1.0)
    join()
    assert ctp.strip_padding(info.value.partial) == b"part"


def test_out_of_sequence_block_aborts():
    def sender(tx: socket.socket) -> None:
        assert tx.recv(1) == b"C"
        tx.sendall(block(1, b"one"))
        expect(tx, ACK)
        tx.sendall(block(5, b"five"))
        assert tx.recv(2) == bytes([CAN, CAN])

    rx, join = run_sender(sender)
    with pytest.raises(ctp.XmodemError, match="out of step"):
        ctp.receive(rx, byte_timeout=1.0)
    join()


def test_silent_sender_raises():
    def sender(tx: socket.socket) -> None:
        tx.recv(64)

    rx, join = run_sender(sender)
    with pytest.raises(ctp.XmodemError, match="silent"):
        ctp.receive(rx, byte_timeout=0.02, max_idle=3)
    join()


def test_block_numbers_wrap_after_255():
    payloads = [bytes([i % 256]) * 128 for i in range(1, 260)]

    def sender(tx: socket.socket) -> None:
        assert tx.recv(1) == b"C"
        for num, payload in enumerate(payloads, 1):
            tx.sendall(block(num, payload))
            expect(tx, ACK)
        tx.sendall(bytes([EOT]))
        expect(tx, ACK)

    rx, join = run_sender(sender)
    data = ctp.receive(rx, byte_timeout=1.0)
    join()
    assert data == b"".join(payloads)


def test_request_file_sends_the_path_unquoted():
    rx, tx = socket.socketpair()
    with rx, tx:
        tx.sendall(b"Ready to send\r\n")
        reply = ctp.request_file(rx, ctp.Reader(rx), "\\display\\swf\\Environment.xml")
        tx.settimeout(1)
        assert tx.recv(100) == b"XGETFILE \\display\\swf\\Environment.xml\r\n"
    assert "Ready" in reply
    assert ctp.refusal(reply) is None


def test_refusal_detection():
    assert ctp.refusal("File(s) \\x\\y Not Found\r\n")
    assert ctp.refusal("Command Blocked from this console type")


def test_strip_padding_removes_only_sub():
    assert ctp.strip_padding(b"data\x1a\x1a\x1a") == b"data"
    assert ctp.strip_padding(b"data\x00\x00") == b"data\x00\x00"
