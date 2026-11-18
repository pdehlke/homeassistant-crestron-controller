"""A fake Crestron processor that speaks CIP over a real TCP socket.

It models the behaviours this project has seen on real hardware and that the
client has to get right:

- registration, including an IP-ID the program does not define;
- the update request, answered with a full dump and an end-of-query marker;
- gated subsystems: before the entry join is pressed the slot gets only the
  menu, and pressing it sends that subsystem's dump with no end marker;
- partial entry dumps, by leaving chosen joins out of the entry dump;
- toggle buttons whose feedback flips on the rising edge of a press;
- a processor that ends the session, and one that never answers a re-poll;
- CIP over TLS, with a throwaway self-signed certificate like the ones
  processors present.

Every write the client sends is recorded so tests can assert exactly what went
on the wire.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import functools
import hashlib
import ssl
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from cipcore import protocol as p
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

MENU = None


@functools.cache
def self_signed_certificate() -> tuple[bytes, bytes]:
    """A throwaway (certificate, key) pair in PEM, made once per test run."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fake-processor")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return (
        cert.public_bytes(serialization.Encoding.PEM),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def _server_context() -> tuple[ssl.SSLContext, str]:
    cert_pem, key_pem = self_signed_certificate()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # load_cert_chain reads only from files.
    with tempfile.TemporaryDirectory() as tmp:
        cert_file, key_file = Path(tmp, "cert.pem"), Path(tmp, "key.pem")
        cert_file.write_bytes(cert_pem)
        key_file.write_bytes(key_pem)
        context.load_cert_chain(cert_file, key_file)
    der = ssl.PEM_cert_to_DER_cert(cert_pem.decode())
    return context, ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())


@dataclass
class FakeProcessor:
    ipids: set[int] = field(default_factory=lambda: {0x2A})
    # subsystem name -> entry join. Empty means an ungated program.
    entries: dict[str, int] = field(default_factory=dict)
    # subsystem (None for menu / ungated) -> join -> value
    digital: dict[str | None, dict[int, int]] = field(default_factory=dict)
    analog: dict[str | None, dict[int, int]] = field(default_factory=dict)
    serial: dict[int, str] = field(default_factory=dict)
    # subsystem -> press join -> feedback join that toggles on press
    toggles: dict[str | None, dict[int, int]] = field(default_factory=dict)
    # subsystem -> join -> value that a press of the key sets (for on/off pairs)
    setters: dict[str | None, dict[int, tuple[int, int]]] = field(default_factory=dict)
    # joins left out of the entry dump for a subsystem, to model partial dumps
    omit_on_entry: dict[str, set[int]] = field(default_factory=dict)
    # an entry join whose press turns this (subsystem, join) on as a side effect
    courtesy: dict[int, tuple[str, int]] = field(default_factory=dict)
    answer_repoll: bool = True
    entry_gap: float = 0.0
    tls: bool = False
    # Serve only this TLS version and older, like a processor too old for 1.2.
    tls_max_version: ssl.TLSVersion | None = None

    presses: list[int] = field(default_factory=list)
    releases: list[int] = field(default_factory=list)
    analog_writes: list[tuple[int, int]] = field(default_factory=list)
    serial_writes: list[tuple[int, str]] = field(default_factory=list)
    registrations: list[int] = field(default_factory=list)
    update_requests: int = 0

    def __post_init__(self) -> None:
        self._server: asyncio.Server | None = None
        self._writers: list[asyncio.StreamWriter] = []
        self.slot_subsystem: str | None = None
        self.connections = 0
        # SHA-256 of the certificate served over TLS, in the client's format.
        self.fingerprint: str | None = None

    # ---- server ------------------------------------------------------------

    async def start(self) -> int:
        if self.tls:
            self._context, self.fingerprint = _server_context()
            if self.tls_max_version is not None:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    self._context.minimum_version = ssl.TLSVersion.TLSv1
                    self._context.maximum_version = self.tls_max_version
                self._context.set_ciphers("DEFAULT:@SECLEVEL=0")
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        return self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        for writer in list(self._writers):
            writer.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def drop(self, *, disconnect_frame: bool = False) -> None:
        """End every session, optionally telling the client first."""
        for writer in list(self._writers):
            if disconnect_frame:
                writer.write(p.frame(p.TYPE_DISCONNECT, b"\x00\x00"))
                with contextlib.suppress(Exception):
                    await writer.drain()
            writer.close()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        self.slot_subsystem = None
        self._writers.append(writer)
        try:
            if self.tls:
                # Upgraded here rather than in start_server so that a client
                # hanging up mid-handshake lands in the except below instead of
                # the event loop's exception handler.
                await writer.start_tls(self._context)
            writer.write(p.frame(p.TYPE_REGISTER_REQUEST, b"\x00\x00\x00\x00"))
            await writer.drain()
            buf = b""
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    return
                frames, buf = p.split_frames(buf + chunk)
                for ciptype, payload in frames:
                    await self._handle(writer, ciptype, payload)
        except ConnectionError, OSError:
            return
        finally:
            if writer in self._writers:
                self._writers.remove(writer)
            writer.close()

    # ---- behaviour ---------------------------------------------------------

    def _current(self) -> str | None:
        return self.slot_subsystem if self.entries else None

    async def _send_digital(self, writer, join: int, value: int) -> None:
        n = join - 1
        body = bytes([p.DATA_DIGITAL, n & 0xFF, ((n >> 8) & 0x7F) | (0 if value else 0x80)])
        writer.write(p.frame(p.TYPE_DATA, bytes([0, 0, len(body)]) + body))
        await writer.drain()

    async def _send_analog(self, writer, join: int, value: int) -> None:
        n = join - 1
        body = bytes([p.DATA_ANALOG, n >> 8, n & 0xFF, value >> 8, value & 0xFF])
        writer.write(p.frame(p.TYPE_DATA, bytes([0, 0, len(body)]) + body))
        await writer.drain()

    async def _send_serial(self, writer, join: int, text: str) -> None:
        n = join - 1
        data = bytes([0x34, n >> 8, n & 0xFF, 0x03]) + text.encode("latin-1")
        writer.write(p.frame(p.TYPE_SERIAL, bytes([0, 0, 0, len(data)]) + data))
        await writer.drain()

    async def _dump(self, writer, subsystem: str | None, omit: set[int] = frozenset()) -> None:
        for join, value in sorted(self.digital.get(subsystem, {}).items()):
            if join not in omit:
                await self._send_digital(writer, join, value)
        for join, value in sorted(self.analog.get(subsystem, {}).items()):
            await self._send_analog(writer, join, value)

    async def _end_of_query(self, writer) -> None:
        writer.write(p.frame(p.TYPE_DATA, bytes([0, 0, 2, p.DATA_UPDATE, p.END_OF_QUERY])))
        await writer.drain()

    async def push_digital(self, subsystem: str | None, join: int, value: int) -> None:
        """A change made at a wall keypad: update state and tell the client if it can see it."""
        self.digital.setdefault(subsystem, {})[join] = value
        if subsystem == self._current():
            for writer in list(self._writers):
                await self._send_digital(writer, join, value)

    async def _handle(self, writer, ciptype: int, payload: bytes) -> None:
        if ciptype == p.TYPE_REGISTER:
            ipid = payload[5]
            self.registrations.append(ipid)
            if ipid in self.ipids:
                writer.write(p.frame(p.TYPE_REGISTER_RESULT, b"\x00\x00\x00\x1f"))
            else:
                writer.write(p.frame(p.TYPE_REGISTER_RESULT, p.IPID_MISSING))
            await writer.drain()
        elif ciptype == p.TYPE_HEARTBEAT:
            writer.write(p.frame(p.TYPE_HEARTBEAT_REPLY, b"\x00\x00"))
            await writer.drain()
        elif ciptype == p.TYPE_DATA:
            datatype = payload[3]
            body = payload[4:]
            if datatype == p.DATA_UPDATE and body[:1] == b"\x00":
                self.update_requests += 1
                if self.update_requests > 1 and not self.answer_repoll:
                    return
                await self._dump(writer, self._current())
                for join, text in sorted(self.serial.items()):
                    await self._send_serial(writer, join, text)
                await self._end_of_query(writer)
            elif datatype == p.DATA_DIGITAL:
                for join, value in p.decode_digitals(body):
                    if value:
                        self.presses.append(join)
                        await self._press(writer, join)
                    else:
                        self.releases.append(join)
            elif datatype == p.DATA_ANALOG:
                for join, value in p.decode_analogs(body):
                    self.analog_writes.append((join, value))
        elif ciptype == p.TYPE_SERIAL:
            join = ((payload[5] << 8) | payload[6]) + 1
            self.serial_writes.append((join, payload[8:].decode("latin-1")))

    async def _press(self, writer, join: int) -> None:
        for name, entry in self.entries.items():
            if join == entry:
                self.slot_subsystem = name
                await self._dump(writer, name, self.omit_on_entry.get(name, set()))
                if self.entry_gap:
                    await asyncio.sleep(self.entry_gap)
                if join in self.courtesy:
                    sub, light = self.courtesy[join]
                    await self.push_digital(sub, light, 1)
                return
        current = self._current()
        if self.entries and current is None:
            return  # an ungated press at a gated slot is ignored, like the real thing
        feedback = self.toggles.get(current, {}).get(join)
        if feedback is not None:
            value = 0 if self.digital.get(current, {}).get(feedback) else 1
            await self.push_digital(current, feedback, value)
            return
        setter = self.setters.get(current, {}).get(join)
        if setter is not None:
            await self.push_digital(current, setter[0], setter[1])
