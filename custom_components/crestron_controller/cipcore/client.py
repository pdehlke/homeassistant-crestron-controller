"""Asyncio CIP client that registers as a touch panel and holds the session.

One client is one IP-ID on one processor. It registers, keeps the session alive
with heartbeats, reconnects with backoff when the session drops, and keeps a
copy of every join the processor reports.

Some programs gate whole subsystems behind a button on the panel's home page:
until the panel presses "Lights", the processor sends that IP-ID a menu and
nothing else, and ignores every lighting join pressed at it. Such programs also
tend to reuse join numbers across subsystems, so the same digital join can be a
light in one subsystem and a media transport button in another. For those
systems the client tracks which subsystem the slot is in, enters the right one
before each write, and files every join it receives under the subsystem that
reported it. On a program with no gating none of that machinery does anything.
See docs/concepts/subsystems.md.

CIP over TLS carries the same frames inside a TLS stream. Processors present
self-signed certificates, so the client does not verify them against any
authority; it pins the certificate's SHA-256 fingerprint instead and refuses a
processor whose certificate has changed. See
docs/adr/0011-cip-over-tls-with-a-pinned-certificate.md.

This module imports nothing from Home Assistant, so the inventory CLI uses it
unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import ssl
import time
import warnings
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from . import protocol as p
from .policy import ANALOG, DIGITAL, LISTEN_ONLY, SERIAL, WritePolicy

_LOGGER = logging.getLogger(__name__)

# Called for every join whose value changed: (kind, join, value, subsystem,
# smart object). `value` is an int for digital and analog joins and a str for
# serials. The smart object is 0 for an ordinary join; a SmartObject's joins
# are numbered in a range of their own, so its serial 11 is not the program's.
JoinCallback = Callable[[str, int, int | str, str | None, int], None]

ENTRY_POLL_SECONDS = 0.02
DISPLACEMENT_WINDOW_SECONDS = 600.0

# Record types laid out as a join, one format byte, then the text.
_SERIALS = (p.DATA_SERIAL, p.DATA_UNMANGLED_SERIAL, p.DATA_SERIAL_EXTENDED)
# Record types a SmartObject can carry. Anything else inside one is skipped.
_OBJECT_JOINS = (
    p.DATA_DIGITAL,
    p.DATA_REPEAT_DIGITAL,
    p.DATA_ANALOG,
    p.DATA_ANALOG_SHORT,
    *_SERIALS,
)


@dataclass(frozen=True)
class Subsystem:
    """One gated subsystem: the home-page join that enters it, and how its dump ends.

    An entry dump carries no end marker, so the only signal that it is complete
    is the processor going quiet. `quiet_seconds` must be longer than the largest
    gap between two frames inside one dump, or the dump is declared complete in
    the middle and the subsystem is rebuilt from partial state. The default is
    twice the worst gap measured on the system this was developed on; measure
    your own with `crestron-controller listen --enter`.
    """

    name: str
    entry_join: int
    quiet_seconds: float = 0.85


@dataclass(frozen=True)
class Timing:
    """Timeouts and windows. Defaults are measurements from one real system.

    They are starting points, not universal truths. Each is explained in
    docs/configuration/join-map-reference.md.
    """

    heartbeat_interval: float = 15.0
    sync_quiet_seconds: float = 2.0
    press_hold_seconds: float = 0.12
    entry_min_seconds: float = 0.9
    entry_timeout: float = 3.0
    repoll_timeout: float = 5.0
    bringup_retry_seconds: float = 5.0
    connect_timeout: float = 10.0
    # A processor sends its register request (type 0F) as soon as a client
    # connects. Silence past this means the port is not speaking plain CIP to
    # us, most likely because it expects TLS.
    greeting_timeout: float = 5.0
    reconnect_backoff: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0)


class CipError(Exception):
    """A command could not be carried out safely or at all."""


# Values for CipClient.last_error_kind, which the integration turns into repairs.
ERROR_UNREACHABLE = "unreachable"
ERROR_IPID_MISSING = "ipid_missing"
ERROR_REFUSED = "refused"
ERROR_DISPLACED = "displaced"
ERROR_CLOSED = "closed"
ERROR_TLS = "tls_failed"
ERROR_NO_GREETING = "no_greeting"
ERROR_CERT_CHANGED = "cert_changed"


class TlsHandshakeError(OSError):
    """TCP connected but the TLS handshake on top of it did not complete."""


def tls_context(legacy: bool = False) -> ssl.SSLContext:
    """A client context that encrypts without checking the certificate's issuer.

    Processors present self-signed certificates no authority vouches for, so
    the check that does mean something is the fingerprint pin, done after the
    handshake by the caller.

    `legacy` also accepts TLS 1.0 and 1.1, for processors too old for 1.2. It
    takes both settings below: OpenSSL 3 refuses the old versions at its
    default security level even when the minimum version allows them, and
    level 0 also admits the weak ciphers and SHA-1 certificates such processors
    tend to use. It only works if the OpenSSL that Python was built against
    still includes the old versions. Opt-in per link; see
    docs/configuration/encrypted-cip.md.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    if legacy:
        with warnings.catch_warnings():
            # Python warns that TLS 1.0 is deprecated. Reaching old processors
            # is the whole point of this setting, and the user chose it.
            warnings.simplefilter("ignore", DeprecationWarning)
            context.minimum_version = ssl.TLSVersion.TLSv1
        context.set_ciphers("DEFAULT:@SECLEVEL=0")
    return context


def fingerprint(writer: asyncio.StreamWriter) -> str | None:
    """SHA-256 of the peer's certificate as colon-separated hex, or None on plain TCP."""
    tls = writer.get_extra_info("ssl_object")
    der = tls.getpeercert(binary_form=True) if tls else None
    if not der:
        return None
    return ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())


def same_fingerprint(a: str, b: str) -> bool:
    """Compare fingerprints however they were written: case, colons and spaces ignored."""

    def norm(text: str) -> str:
        return "".join(c for c in text.lower() if c in "0123456789abcdef")

    return norm(a) == norm(b)


class CipClient:
    """Holds one registered CIP session, reconnecting for as long as it is running."""

    def __init__(
        self,
        name: str,
        host: str,
        ipid: int,
        *,
        port: int = p.CIP_PORT,
        tls: bool = False,
        legacy_tls: bool = False,
        pinned_fingerprint: str | None = None,
        subsystems: dict[str, Subsystem] | None = None,
        default_subsystem: str | None = None,
        repoll_after_entry: bool = True,
        policy: WritePolicy = LISTEN_ONLY,
        timing: Timing | None = None,
        on_join: JoinCallback | None = None,
        on_state: Callable[[], None] | None = None,
        on_frame: Callable[[str, int, bytes], None] | None = None,
    ) -> None:
        p.registration(ipid)  # validates the range before anything connects
        self.name = name
        self.host = host
        self.port = port
        self.tls = tls
        # None on a TLS link accepts any certificate. The integration always
        # pins one, from the probe that created the entry; the CLI does not.
        self.pinned_fingerprint = pinned_fingerprint
        self.legacy_tls = legacy_tls
        self.peer_fingerprint: str | None = None
        # The TLS version the last session agreed on, such as "TLSv1.2".
        self.tls_version: str | None = None
        self.ipid = ipid
        self.subsystems = dict(subsystems or {})
        if default_subsystem is not None and default_subsystem not in self.subsystems:
            raise ValueError(f"default subsystem {default_subsystem!r} has no entry join")
        if self.subsystems and default_subsystem is None:
            raise ValueError("a gated link needs a default subsystem")
        self.default_subsystem = default_subsystem
        self.repoll_after_entry = repoll_after_entry
        self.policy = policy
        self.timing = timing or Timing()
        self._on_join = on_join
        self._on_state = on_state
        # Raw traffic tap for the CLI: ("rx" | "tx", type, payload).
        self._on_frame = on_frame

        # Which subsystem the slot is in. None means unknown, which is what a
        # fresh session starts as and what a failed entry leaves behind, and
        # nothing gated may be written while it holds.
        self.current_subsystem: str | None = None
        # Subsystems whose state has been loaded at least once this session.
        # A subsystem never entered has no state worth reporting, and reading
        # its joins as off would be confidently wrong.
        self.entered: set[str] = set()

        # Joins bucketed by (the subsystem that reported them, smart object).
        # The None subsystem is the pre-entry menu on a gated link and
        # everything on an ungated one; smart object 0 is ordinary joins.
        self._digital: dict[tuple[str | None, int], dict[int, int]] = {}
        self._analog: dict[tuple[str | None, int], dict[int, int]] = {}
        # Serials are not bucketed by subsystem. On the system this was
        # developed on, the label serials arrive once per session rather than
        # once per entry, so bucketing them would lose them at the first
        # subsystem switch. SmartObject serials are assumed to behave the same.
        self.serial: dict[int, str] = {}
        self._object_serial: dict[int, dict[int, str]] = {}

        self.connected = False
        self.registered = False
        self.synced = False
        self.generation = 0
        self.last_error: str | None = None
        self.last_error_kind: str | None = None
        self.disconnected_since: float | None = time.monotonic()
        self._displacements: deque[float] = deque(maxlen=32)

        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._bringup: asyncio.Task | None = None
        self._running = False
        self._last_rx = 0.0
        self._last_data_rx = 0.0
        self._last_bringup = 0.0
        # (smart object, join) -> value, for the digitals of a dump in flight.
        self._collecting: dict[tuple[int, int], int] | None = None
        self._collecting_for: str | None = None
        self._end_of_query = asyncio.Event()
        self._write_lock = asyncio.Lock()
        # One collection buffer, so one collection at a time. The bring-up
        # enters without holding any caller's lock, so this is what serialises
        # an entry against it. Without it, a bring-up and a command retry racing
        # after a reconnect overwrite each other's buffer and the loser times
        # out reporting no joins at all.
        self._collect_lock = asyncio.Lock()

    # ---- state -------------------------------------------------------------

    def digital_for(self, subsystem: str | None, obj: int = 0) -> dict[int, int]:
        return self._digital.setdefault((subsystem, obj), {})

    def analog_for(self, subsystem: str | None, obj: int = 0) -> dict[int, int]:
        return self._analog.setdefault((subsystem, obj), {})

    def serial_for(self, obj: int = 0) -> dict[int, str]:
        return self.serial if obj == 0 else self._object_serial.setdefault(obj, {})

    def buckets(self, obj: int = 0) -> list[str | None]:
        """Every subsystem that has reported joins for this smart object, None first."""
        found = {sub for sub, o in (*self._digital, *self._analog) if o == obj}
        return sorted(found, key=lambda s: "" if s is None else s)

    def smart_objects(self) -> list[int]:
        """Every SmartObject that has reported a join, in order."""
        found = {o for _, o in (*self._digital, *self._analog)} | set(self._object_serial)
        return sorted(found - {0})

    def has_state_for(self, subsystem: str | None) -> bool:
        """Whether joins read from this subsystem mean anything yet."""
        if not self.synced:
            return False
        if not self.subsystems or subsystem is None:
            return True
        return subsystem in self.entered

    @property
    def _incoming(self) -> str | None:
        """Which subsystem the frames arriving right now belong to.

        During an entry `current_subsystem` is deliberately None, because nothing
        may be written while the slot is in flight. The dump arriving in that
        window still belongs to the subsystem being entered.
        """
        return self._collecting_for if self._collecting is not None else self.current_subsystem

    def recent_displacements(self, window: float = DISPLACEMENT_WINDOW_SECONDS) -> int:
        """How many times the processor has dropped us inside the window."""
        cutoff = time.monotonic() - window
        return sum(1 for t in self._displacements if t >= cutoff)

    # ---- lifecycle ---------------------------------------------------------

    async def async_start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run(), name=f"crestron_controller-{self.name}")

    async def async_stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._close()

    async def _close(self) -> None:
        writer, self._writer = self._writer, None
        was_up = self.connected
        self.connected = False
        self.registered = False
        self.synced = False
        self.current_subsystem = None
        self.entered.clear()
        self._collecting = None
        self._collecting_for = None
        if was_up:
            self.disconnected_since = time.monotonic()
        bringup, self._bringup = self._bringup, None
        if bringup:
            bringup.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bringup
        if writer:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    def _fail(self, kind: str, message: str) -> OSError:
        self.last_error_kind = kind
        self.last_error = message
        return OSError(message)

    # ---- connection loop ---------------------------------------------------

    async def _run(self) -> None:
        attempt = 0
        backoff = self.timing.reconnect_backoff
        while self._running:
            reached_sync = False
            try:
                await self._session()
            except asyncio.CancelledError:
                raise
            except (OSError, asyncio.IncompleteReadError, TimeoutError) as err:
                if self.last_error_kind is None:
                    self.last_error_kind = ERROR_CLOSED
                    self.last_error = str(err) or type(err).__name__
                _LOGGER.warning("%s: connection lost (%s)", self.name, err or type(err).__name__)
            except Exception:
                _LOGGER.exception("%s: unexpected failure in CIP session", self.name)
            finally:
                # Captured before _close(), which clears it. Reading it after is
                # the obvious way to write this and is silently wrong.
                reached_sync = self.synced
                await self._close()
                if self._on_state:
                    self._on_state()

            if not self._running:
                return
            # Syncing is a high bar a flapping link cannot clear: it takes a
            # registration, a full dump and a quiet window. A session that got
            # that far and then dropped is not the same as a processor refusing
            # us, so the backoff starts again from the top.
            if reached_sync:
                attempt = 0
            delay = backoff[min(attempt, len(backoff) - 1)]
            attempt += 1
            _LOGGER.debug("%s: reconnecting in %.0fs", self.name, delay)
            await asyncio.sleep(delay)

    async def _session(self) -> None:
        try:
            reader, writer = await asyncio.wait_for(
                _open(self.host, self.port, self.tls, self.timing.connect_timeout, self.legacy_tls),
                self.timing.connect_timeout,
            )
        except TlsHandshakeError as err:
            raise self._fail(
                ERROR_TLS,
                f"TLS handshake with {self.host}:{self.port} failed ({err}); the port may "
                "speak plain CIP, or the processor may need old TLS turned on",
            ) from err
        except (OSError, TimeoutError) as err:
            raise self._fail(
                ERROR_UNREACHABLE, f"cannot reach {self.host}:{self.port} ({err or 'timeout'})"
            ) from err
        if self.tls:
            self.peer_fingerprint = fingerprint(writer)
            self.tls_version = _tls_version(writer)
            if self.pinned_fingerprint and not (
                self.peer_fingerprint
                and same_fingerprint(self.peer_fingerprint, self.pinned_fingerprint)
            ):
                writer.close()
                raise self._fail(
                    ERROR_CERT_CHANGED,
                    f"{self.host}:{self.port} presented certificate {self.peer_fingerprint}, "
                    f"expected {self.pinned_fingerprint}",
                )
        self._writer = writer
        self.connected = True
        self.synced = False
        self.generation += 1
        self.current_subsystem = None
        self._collecting = None
        self._collecting_for = None
        # State from a previous session is not evidence about this one. Anything
        # that changed while we were away arrives in the new dump.
        self._digital.clear()
        self._analog.clear()
        _LOGGER.info("%s: connected to %s:%d", self.name, self.host, self.port)

        loop = asyncio.get_running_loop()
        self._last_rx = loop.time()
        self._last_data_rx = loop.time()
        self._last_bringup = 0.0
        connected_at = last_beat = loop.time()
        greeted = False
        buf = b""

        while self._running:
            try:
                chunk = await asyncio.wait_for(reader.read(8192), timeout=1.0)
            except TimeoutError:
                chunk = b""
            if chunk == b"" and reader.at_eof():
                raise self._fail(ERROR_CLOSED, "processor closed the connection")
            if chunk:
                self._last_rx = loop.time()
                greeted = True
                buf += chunk
            elif not greeted and loop.time() - connected_at > self.timing.greeting_timeout:
                raise self._fail(ERROR_NO_GREETING, _no_greeting(self.host, self.port, self.tls))

            frames, buf = p.split_frames(buf)
            for ciptype, payload in frames:
                await self._handle(ciptype, payload)

            now = loop.time()
            # The processor marks the end of its registration dump explicitly,
            # but a slot with nothing to say would never send it, so quiet also
            # counts. The bring-up runs as its own task because it waits on
            # traffic only this loop can receive.
            if (
                self.registered
                and not self.synced
                and now - self._last_rx > self.timing.sync_quiet_seconds
            ):
                self._start_bring_up()

            if now - last_beat >= self.timing.heartbeat_interval:
                await self._send(p.HEARTBEAT)
                last_beat = now

    def _start_bring_up(self) -> None:
        if self.synced or self._bringup is not None:
            return
        loop = asyncio.get_running_loop()
        if loop.time() - self._last_bringup < self.timing.bringup_retry_seconds:
            return
        self._last_bringup = loop.time()
        self._bringup = asyncio.create_task(
            self._bring_up(), name=f"crestron_controller-up-{self.name}"
        )

    async def _bring_up(self) -> None:
        """Finish coming up, entering the default subsystem first where there is one.

        On a gated program a registered slot is not yet a useful one: until the
        entry press arrives the processor reports none of that subsystem's joins.
        So the session is only synced once the subsystem's own dump has landed.

        In listen-only mode the entry press is a write and is refused, so a gated
        link comes up synced but with no subsystem entered, and every entity in
        a gated subsystem reports unavailable rather than off. That is honest:
        the processor has not said anything about those joins.
        """
        try:
            default = self.default_subsystem
            if default is not None:
                entry = self.subsystems[default].entry_join
                if not self.policy.permits(DIGITAL, entry):
                    _LOGGER.warning(
                        "%s: cannot enter the %s subsystem in listen-only mode, so its "
                        "joins stay unknown until writes are enabled",
                        self.name,
                        default,
                    )
                elif not await self.async_enter(default):
                    return
                elif self.repoll_after_entry:
                    # An entry dump is partial and not deterministic, so a join
                    # that is high but absent from it would read low for the
                    # life of the session. The update request returns the full
                    # state and ends with an explicit marker.
                    await self.async_repoll(default)
            self.synced = True
            self.disconnected_since = None
            _LOGGER.info(
                "%s: synced, %d digital joins (%d high), %d analog, %d serial",
                self.name,
                len(self.digital_for(self.current_subsystem)),
                sum(1 for v in self.digital_for(self.current_subsystem).values() if v),
                len(self.analog_for(self.current_subsystem)),
                len(self.serial),
            )
            if self._on_state:
                self._on_state()
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("%s: bring-up failed", self.name)
        finally:
            self._bringup = None

    # ---- subsystems --------------------------------------------------------

    async def async_enter(self, subsystem: str | None) -> bool:
        """Put the slot into one subsystem and merge that subsystem's state.

        Returns False rather than raising when the processor does not answer, so
        a caller can refuse its own command instead of pressing into a slot whose
        subsystem it does not know.
        """
        if subsystem is None or not self.subsystems:
            return True
        if subsystem not in self.subsystems:
            raise CipError(f"{self.name}: no entry join for subsystem {subsystem!r}")
        if self.current_subsystem == subsystem:
            return True
        async with self._collect_lock:
            # Re-checked under the lock: whoever we queued behind may have put
            # the slot exactly where we wanted it, and pressing again could
            # leave the subsystem rather than re-enter it.
            if self.current_subsystem == subsystem:
                return True
            return await self._enter_locked(subsystem)

    async def _enter_locked(self, name: str) -> bool:
        subsystem = self.subsystems[name]
        loop = asyncio.get_running_loop()
        _LOGGER.info(
            "%s: entering %s on d%d (was %s)",
            self.name,
            name,
            subsystem.entry_join,
            self.current_subsystem or "unknown",
        )
        self.current_subsystem = None
        self._collecting = {}
        self._collecting_for = name
        landed = False
        try:
            self._last_data_rx = loop.time()
            started = loop.time()
            await self._press(subsystem.entry_join)
            while True:
                await asyncio.sleep(ENTRY_POLL_SECONDS)
                now = loop.time()
                # The floor matters as much as the quiet window. A dump arrives
                # in bursts, and a gap between bursts can exceed the quiet
                # threshold; without the floor the window closes mid-dump.
                if (
                    self._collecting
                    and now - started > self.timing.entry_min_seconds
                    and now - self._last_data_rx > subsystem.quiet_seconds
                ):
                    landed = True
                    break
                if now - started > self.timing.entry_timeout:
                    _LOGGER.warning(
                        "%s: pressed d%d and %s reported %d joins in %.1fs; entry failed",
                        self.name,
                        subsystem.entry_join,
                        name,
                        len(self._collecting or {}),
                        self.timing.entry_timeout,
                    )
                    break
        finally:
            collected, self._collecting = self._collecting or {}, None
            self._collecting_for = None

        if not landed:
            return False
        self._merge(name, collected)
        self.current_subsystem = name
        self.entered.add(name)
        return True

    async def async_repoll(self, subsystem: str | None) -> bool:
        """Ask the processor to re-send everything, and merge what comes back.

        Returns False on timeout rather than raising. Some processors never
        answer a second update request; the caller still has the entry dump,
        which is incomplete but not wrong.
        """
        async with self._collect_lock:
            self._end_of_query.clear()
            self._collecting = {}
            self._collecting_for = subsystem
            answered = True
            try:
                await self._send(p.UPDATE_REQUEST)
                try:
                    await asyncio.wait_for(self._end_of_query.wait(), self.timing.repoll_timeout)
                except TimeoutError:
                    _LOGGER.warning(
                        "%s: update request unanswered after %.1fs; set repoll_after_entry: "
                        "false if this processor never answers one",
                        self.name,
                        self.timing.repoll_timeout,
                    )
                    answered = False
            finally:
                collected, self._collecting = self._collecting or {}, None
                self._collecting_for = None
            # Merged even without the marker: every digital frame was diverted
            # into the buffer while it was open, and discarding it would lose
            # real feedback, such as a wall-panel press, outright.
            self._merge(subsystem, collected)
            return answered

    def invalidate_subsystem(self) -> None:
        """Forget which subsystem the slot is in, forcing the next write to re-enter.

        Called when a press goes unconfirmed. If something cleared the
        processor's latch without dropping the session, this is what makes that
        recoverable instead of permanent.
        """
        if self.current_subsystem is not None:
            _LOGGER.info(
                "%s: forgetting %s, next write re-enters", self.name, self.current_subsystem
            )
        self.current_subsystem = None

    def _merge(self, subsystem: str | None, collected: dict[int, int]) -> None:
        """Apply a dump to a subsystem's state. A merge, never a rebuild.

        An entry dump is a statement about the joins it contains and says nothing
        about the ones it omits. Treating an absent join as low was tried on the
        system this was developed on and published a lit light as dark. The cost
        of merging is that a light switched off elsewhere while the slot was in
        another subsystem can read stale until a later frame corrects it; a stale
        reading is better than a wrong one.
        """
        changed = [
            (obj, join, value)
            for (obj, join), value in collected.items()
            if self.digital_for(subsystem, obj).get(join) != value
        ]
        # Every bucket is updated before anything is told, so a listener reading
        # a neighbouring join mid-merge never sees half a dump.
        for (obj, join), value in collected.items():
            self.digital_for(subsystem, obj)[join] = value
        for obj, join, value in changed:
            self._emit(DIGITAL, join, value, subsystem, obj)

    def _emit(
        self, kind: str, join: int, value: int | str, subsystem: str | None, obj: int = 0
    ) -> None:
        if self._on_join:
            self._on_join(kind, join, value, subsystem, obj)

    # ---- protocol ----------------------------------------------------------

    async def _handle(self, ciptype: int, payload: bytes) -> None:
        if self._on_frame:
            self._on_frame("rx", ciptype, payload)
        if ciptype == p.TYPE_REGISTER_REQUEST:
            await self._send(p.registration(self.ipid))
        elif ciptype == p.TYPE_REGISTER_RESULT:
            # klenae's client accepts only status 0x1f; at least one 2009-era
            # processor answers 0x03. Accept any 00 00 00 xx and log the code.
            if len(payload) == 4 and payload[:3] == b"\x00\x00\x00":
                self.registered = True
                # The last error describes the last failure, and stays readable
                # through the backoff for that reason; registering ends it.
                self.last_error_kind = None
                self.last_error = None
                _LOGGER.info(
                    "%s: registered as IP-ID 0x%02X (status 0x%02x)",
                    self.name,
                    self.ipid,
                    payload[3],
                )
                await self._send(p.UPDATE_REQUEST)
            elif payload == p.IPID_MISSING:
                raise self._fail(
                    ERROR_IPID_MISSING,
                    f"IP-ID 0x{self.ipid:02X} is not defined in the program on {self.host}",
                )
            else:
                raise self._fail(ERROR_REFUSED, f"registration refused: {payload.hex(' ')}")
        elif ciptype == p.TYPE_DISCONNECT:
            self._displacements.append(time.monotonic())
            raise self._fail(ERROR_DISPLACED, "processor ended the session")
        elif ciptype in (p.TYPE_DATA, p.TYPE_EXTENDED_DATA):
            records = p.iter_records(ciptype, payload)
            if records:
                # Tracked separately from _last_rx, which a heartbeat reply also
                # moves. An entry dump is detected by quiet, so counting
                # keepalives as traffic would stretch a window that is under a
                # second wide.
                self._last_data_rx = asyncio.get_running_loop().time()
            for datatype, body in records:
                await self._handle_record(datatype, body)

    def _set_serial(self, join: int, text: str, obj: int = 0) -> None:
        bucket = self.serial_for(obj)
        if bucket.get(join) != text:
            bucket[join] = text
            self._emit(SERIAL, join, text, None, obj)

    def _set_analog(self, join: int, value: int, obj: int = 0) -> None:
        subsystem = self._incoming
        bucket = self.analog_for(subsystem, obj)
        if bucket.get(join) != value:
            bucket[join] = value
            self._emit(ANALOG, join, value, subsystem, obj)

    async def _handle_record(self, datatype: int, body: bytes, obj: int = 0) -> None:
        # Records are handled alike whichever packet type carried them: some
        # processors send one IP-ID everything as EXTENDED_DATA. SmartObject
        # joins come back through here with their object, so they take exactly
        # the same collect-and-merge path as ordinary ones.
        if obj and datatype not in _OBJECT_JOINS:
            _LOGGER.debug(
                "%s: skipping record type 0x%02x inside SmartObject %d", self.name, datatype, obj
            )
            return
        if datatype in (p.DATA_DIGITAL, p.DATA_REPEAT_DIGITAL):
            pairs = p.decode_digitals(body)
            if self._collecting is not None:
                # An entry or re-poll is in flight. Collect rather than publish:
                # the diff happens once the dump is complete.
                self._collecting.update(((obj, join), value) for join, value in pairs)
                return
            subsystem = self.current_subsystem
            bucket = self.digital_for(subsystem, obj)
            for join, value in pairs:
                if bucket.get(join) != value:
                    bucket[join] = value
                    self._emit(DIGITAL, join, value, subsystem, obj)
        elif datatype == p.DATA_ANALOG:
            for join, value in p.decode_analogs(body):
                self._set_analog(join, value, obj)
        elif datatype == p.DATA_ANALOG_SHORT and len(body) >= 3:
            self._set_analog(body[0] + 1, (body[1] << 8) | body[2], obj)
        elif datatype in _SERIALS and len(body) >= 3:
            join, text = p.decode_serial(body)
            self._set_serial(join, text, obj)
        elif datatype == p.DATA_SERIAL_INDEXED:
            text = body.decode("latin-1")
            head = text.split(",", 1)[0].lstrip("#")
            self._set_serial(int(head) if head.isdigit() else 0, text)
        elif datatype == p.DATA_UPDATE and body and body[0] == p.END_OF_QUERY:
            await self._send(p.END_OF_QUERY_ACK)
            await self._send(p.HEARTBEAT)
            self._end_of_query.set()
            self._start_bring_up()
        elif datatype in (p.DATA_SMART_OBJECT, p.DATA_SMART_OBJECT_EXTENDED):
            for inner, kind, record in p.smart_object_records(body):
                if inner == 0:
                    # Object 0 would land in the program's own join range,
                    # which is exactly the mix-up the object number prevents.
                    _LOGGER.debug("%s: skipping SmartObject 0 record %s", self.name, body.hex(" "))
                    continue
                await self._handle_record(kind, record, inner)

    # ---- writing -----------------------------------------------------------

    async def _send(self, packet: bytes) -> None:
        writer = self._writer
        if writer is None:
            raise OSError(f"{self.name}: not connected")
        async with self._write_lock:
            if self._on_frame:
                self._on_frame("tx", packet[0], packet[3:])
            writer.write(packet)
            await writer.drain()

    def _require_subsystem(self, what: str, subsystem: str | None) -> None:
        if self.subsystems and subsystem is not None and self.current_subsystem != subsystem:
            raise CipError(
                f"{self.name}: refusing {what} for {subsystem}, the slot is in "
                f"{self.current_subsystem or 'no'} subsystem"
            )

    async def _press(self, join: int, hold: float | None = None) -> None:
        """Tap a digital join. The policy check here is the one that covers every write."""
        self.policy.check(DIGITAL, join)
        hold = self.timing.press_hold_seconds if hold is None else hold
        # Captured now rather than re-read in the finally: _close() nulls
        # self._writer before it cancels the bring-up task, so a press cancelled
        # by exactly that path would otherwise find nothing and leave the join
        # held down.
        writer = self._writer
        released = False
        try:
            await self._send(p.digital_packet(join, True))
            await asyncio.sleep(hold)
            await self._send(p.digital_packet(join, False))
            released = True
        finally:
            if not released and writer is not None:
                # A press never released is a press-and-hold as far as the
                # processor is concerned, and holding is not a no-op: it ramps
                # dimmers and can overwrite a learnable scene. write() is not a
                # coroutine, so a cancellation already in flight cannot preempt it.
                with contextlib.suppress(Exception):
                    writer.write(p.digital_packet(join, False))

    async def async_press(
        self, join: int, subsystem: str | None, hold: float | None = None
    ) -> None:
        """Tap a digital join, refusing unless the slot is in the named subsystem."""
        self._require_subsystem(f"d{join}", subsystem)
        await self._press(join, hold)

    async def async_set_analog(self, join: int, value: int, subsystem: str | None) -> None:
        self._require_subsystem(f"a{join}", subsystem)
        self.policy.check(ANALOG, join)
        await self._send(p.analog_packet(join, value))

    async def async_send_serial(self, join: int, text: str, subsystem: str | None) -> None:
        self._require_subsystem(f"s{join}", subsystem)
        self.policy.check(SERIAL, join)
        await self._send(p.serial_packet(join, text))


# ---- one-shot probe ---------------------------------------------------------

PROBE_OK = "ok"


@dataclass(frozen=True)
class Probe:
    """How a probe went: PROBE_OK or an ERROR_* kind, and the certificate seen over TLS."""

    result: str
    fingerprint: str | None = None
    tls_version: str | None = None

    @property
    def ok(self) -> bool:
        return self.result == PROBE_OK


async def _open(
    host: str, port: int, tls: bool, timeout: float, legacy: bool = False
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    reader, writer = await asyncio.open_connection(host, port)
    if not tls:
        return reader, writer
    # Connect first, then upgrade, so a failure can be pinned on TLS. A peer
    # that cannot agree a TLS version often just resets the connection, which
    # would otherwise read as nothing listening.
    try:
        await writer.start_tls(tls_context(legacy), ssl_handshake_timeout=timeout)
    except OSError as err:
        writer.close()
        raise TlsHandshakeError(str(err) or type(err).__name__) from err
    return reader, writer


def _tls_version(writer: asyncio.StreamWriter) -> str | None:
    tls = writer.get_extra_info("ssl_object")
    return tls.version() if tls else None


def _no_greeting(host: str, port: int, tls: bool) -> str:
    if tls:
        return f"{host}:{port} completed TLS but sent no CIP register request"
    return f"{host}:{port} sent no CIP register request; the port may expect TLS"


async def async_probe(
    host: str,
    ipid: int,
    port: int = p.CIP_PORT,
    timeout: float = 10.0,
    *,
    tls: bool = False,
    legacy_tls: bool = False,
    pinned_fingerprint: str | None = None,
    greeting_timeout: float = Timing.greeting_timeout,
) -> Probe:
    """Register once, report how it went, and disconnect. Presses nothing.

    Used by the config flow and the CLI to turn the ways a first connection
    fails (nothing listening, IP-ID not in the program, refused, TLS on one end
    only) into a message a person can act on. Over TLS the result carries the
    certificate's fingerprint, which the config flow pins, and the TLS version
    the two ends agreed on.

    Registering does claim the slot for a moment. If a real panel is online
    with the same IP-ID, what the processor does about two claimants is not
    something this project has observed; see docs/troubleshooting/ip-id-conflicts.md.
    """
    p.registration(ipid)
    try:
        reader, writer = await asyncio.wait_for(
            _open(host, port, tls, timeout, legacy_tls), timeout
        )
    except TlsHandshakeError:
        return Probe(ERROR_TLS)
    except OSError, TimeoutError:
        return Probe(ERROR_UNREACHABLE)
    seen = fingerprint(writer) if tls else None
    version = _tls_version(writer)
    try:
        if tls and pinned_fingerprint and not (seen and same_fingerprint(seen, pinned_fingerprint)):
            return Probe(ERROR_CERT_CHANGED, seen, version)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        greeted = False
        buf = b""
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return Probe(ERROR_REFUSED, seen, version)
            wait = remaining if greeted else min(remaining, greeting_timeout)
            try:
                chunk = await asyncio.wait_for(reader.read(4096), wait)
            except TimeoutError:
                return Probe(ERROR_REFUSED if greeted else ERROR_NO_GREETING, seen, version)
            except ssl.SSLError:
                return Probe(ERROR_TLS, seen, version)
            if not chunk:
                return Probe(ERROR_CLOSED, seen, version)
            greeted = True
            frames, buf = p.split_frames(buf + chunk)
            for ciptype, payload in frames:
                if ciptype == p.TYPE_REGISTER_REQUEST:
                    writer.write(p.registration(ipid))
                    await writer.drain()
                elif ciptype == p.TYPE_REGISTER_RESULT:
                    if len(payload) == 4 and payload[:3] == b"\x00\x00\x00":
                        return Probe(PROBE_OK, seen, version)
                    if payload == p.IPID_MISSING:
                        return Probe(ERROR_IPID_MISSING, seen, version)
                    return Probe(ERROR_REFUSED, seen, version)
                elif ciptype == p.TYPE_DISCONNECT:
                    return Probe(ERROR_DISPLACED, seen, version)
    finally:
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()
