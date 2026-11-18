"""One processor link: the CIP session, its slot lock, and the entities on it.

The hub sits between Home Assistant's entities and the CIP client. It routes
join changes to the entities that read them, turns toggle buttons into discrete
on and off, serialises everything that writes so a gated slot is never in the
wrong subsystem when a press goes out, sends an idle slot back to its default
subsystem, and watches link health for repairs.

The lock serialises the subsystem the slot is in, not merely the presses.
asyncio.Lock wakes waiters in order, so a write queued behind another runs as
soon as that one ends and needs no interrupt protocol to get there.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

from .cipcore.client import CipClient, CipError
from .cipcore.joinmap import PRESS_MOMENTARY, Entity, JoinMap, SelectOption
from .cipcore.policy import ANALOG, DIGITAL, SERIAL, WriteRefused
from .const import CONFIRM_ATTEMPTS, CONFIRM_TIMEOUT, IDLE_WATCH_INTERVAL

_LOGGER = logging.getLogger(__name__)

Listener = Callable[[], None]


class HubError(Exception):
    """A command could not be carried out. The message is shown to the user."""


class Hub:
    """Owns one CipClient and presents its joins to entities."""

    def __init__(
        self,
        name: str,
        host: str,
        port: int,
        ipid: int,
        joinmap: JoinMap,
        writes_enabled: bool,
        *,
        tls: bool = False,
        legacy_tls: bool = False,
        pinned_fingerprint: str | None = None,
    ) -> None:
        self.name = name
        self.joinmap = joinmap
        self.writes_enabled = writes_enabled
        self.client = CipClient(
            name,
            host,
            ipid,
            port=port,
            tls=tls,
            legacy_tls=legacy_tls,
            pinned_fingerprint=pinned_fingerprint,
            subsystems=joinmap.subsystems,
            default_subsystem=joinmap.default_subsystem,
            repoll_after_entry=joinmap.repoll_after_entry,
            policy=joinmap.policy(writes_enabled),
            timing=joinmap.timing,
            on_join=self._on_join,
            on_state=self._on_state,
        )
        self.lock = asyncio.Lock()
        # (kind, join, smart object) -> listeners. Smart object 0 is ordinary joins.
        self._listeners: dict[tuple[str, int, int], set[Listener]] = {}
        self._state_listeners: set[Listener] = set()
        # (subsystem, alias join) -> canonical feedback join. An alias moving is
        # the same event as the feedback join moving, so it is mirrored onto
        # the feedback join and entities have one place to read.
        self._aliases: dict[tuple[str | None, int], int] = {}
        for entity in joinmap.entities:
            for alias in entity.also_reports:
                if entity.feedback is not None:
                    self._aliases[(entity.subsystem, alias)] = entity.feedback
        self._waiters: list[tuple[str | None, int, int, asyncio.Future[None]]] = []
        self._idle_task: asyncio.Task | None = None
        self._busy_until = 0.0

    # ---- lifecycle ---------------------------------------------------------

    async def async_start(self) -> None:
        await self.client.async_start()
        if self.joinmap.subsystems:
            self._idle_task = asyncio.create_task(
                self._idle_watch(), name="crestron_controller-idle"
            )

    async def async_stop(self) -> None:
        if self._idle_task:
            # Awaited, not just cancelled: the client teardown below yields, and
            # an unawaited idle task would take its cancellation in the middle
            # of whatever press it was making.
            idle, self._idle_task = self._idle_task, None
            idle.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await idle
        await self.client.async_stop()

    # ---- observation -------------------------------------------------------

    def subscribe(
        self, reads: list[tuple[str, int]], callback: Listener, smart_object: int = 0
    ) -> Callable[[], None]:
        """Call `callback` when any of these joins changes, or the link changes state."""
        keys = [(kind, join, smart_object) for kind, join in reads]
        for key in keys:
            self._listeners.setdefault(key, set()).add(callback)
        self._state_listeners.add(callback)

        def _remove() -> None:
            for key in keys:
                self._listeners.get(key, set()).discard(callback)
            self._state_listeners.discard(callback)

        return _remove

    def subscribe_state(self, callback: Listener) -> Callable[[], None]:
        self._state_listeners.add(callback)
        return lambda: self._state_listeners.discard(callback)

    def _on_state(self) -> None:
        for callback in list(self._state_listeners):
            callback()

    def _on_join(
        self, kind: str, join: int, value: int | str, subsystem: str | None, obj: int = 0
    ) -> None:
        # Aliases and confirmation waiters belong to lights and switches, which
        # never read a SmartObject.
        if kind == DIGITAL and obj == 0:
            canonical = self._aliases.get((subsystem, join))
            if canonical is not None:
                self.client.digital_for(subsystem)[canonical] = int(value)
                join = canonical
            self._resolve_waiters(subsystem, join, int(value))
        for callback in list(self._listeners.get((kind, join, obj), ())):
            callback()

    @property
    def connected(self) -> bool:
        return bool(self.client.connected and self.client.synced)

    def available(self, entity: Entity) -> bool:
        if entity.press == PRESS_MOMENTARY and entity.feedback is None:
            return self.connected
        return self.client.has_state_for(entity.subsystem)

    def digital(self, subsystem: str | None, join: int, obj: int = 0) -> int | None:
        if not self.client.has_state_for(subsystem):
            return None
        # A dump reports only what it reports, but after a full sync a join the
        # processor never mentioned is low on every system observed so far.
        # Whether that holds for SmartObject joins has not been observed.
        return self.client.digital_for(subsystem, obj).get(join, 0)

    def analog(self, subsystem: str | None, join: int, obj: int = 0) -> int | None:
        if not self.client.has_state_for(subsystem):
            return None
        return self.client.analog_for(subsystem, obj).get(join)

    def serial(self, join: int, obj: int = 0) -> str | None:
        if not self.client.synced:
            return None
        return self.client.serial_for(obj).get(join)

    def is_on(self, entity: Entity) -> bool | None:
        if entity.feedback is None:
            return None
        value = self.digital(entity.subsystem, entity.feedback)
        return None if value is None else bool(value)

    def selected(self, entity: Entity) -> SelectOption | None:
        """The option whose feedback is high, or None when none or several are."""
        obj = entity.smart_object or 0
        high = [o for o in entity.options if self.digital(entity.subsystem, o.feedback, obj) == 1]
        return high[0] if len(high) == 1 else None

    def option_labels(self, entity: Entity) -> list[str]:
        """What each option is called right now, in order, every label distinct.

        A label read from the processor wins over the one in the join map, so a
        list renamed on the processor is renamed here too. Home Assistant needs
        the labels to be distinct, so a repeat gets a number.
        """
        obj = entity.smart_object or 0
        labels: list[str] = []
        for i, option in enumerate(entity.options, start=1):
            text = None
            if option.name_serial is not None:
                text = (self.serial(option.name_serial, obj) or "").strip() or None
            label = text or option.name or f"Option {i}"
            unique, n = label, 2
            while unique in labels:
                unique, n = f"{label} ({n})", n + 1
            labels.append(unique)
        return labels

    # ---- the shared slot ---------------------------------------------------

    def _touch(self) -> None:
        self._busy_until = asyncio.get_running_loop().time()

    def _check_ready(self, entity: Entity) -> None:
        if not self.writes_enabled:
            raise HubError(
                f"{entity.name}: this link is listen-only. Enable writes in the integration's "
                "options once your never_write list is complete."
            )
        if not self.connected:
            raise HubError(f"{entity.name}: the {self.name} link is not connected")

    async def _enter(self, entity: Entity) -> None:
        if not await self.client.async_enter(entity.subsystem):
            raise HubError(f"{entity.name}: could not enter the {entity.subsystem} subsystem")

    async def _idle_watch(self) -> None:
        """Return an idle slot to its default subsystem.

        Every second the slot spends away from the default subsystem is a
        second in which a change made at a wall keypad is invisible here.
        Skips a link that is not synced, because the client's own bring-up
        is entering then and two entries at once would collide.
        """
        default = self.joinmap.default_subsystem
        while True:
            try:
                await asyncio.sleep(IDLE_WATCH_INTERVAL)
                client = self.client
                if not self.connected or self.lock.locked():
                    continue
                if client.current_subsystem in (None, default):
                    continue
                now = asyncio.get_running_loop().time()
                if now - self._busy_until < self.joinmap.idle_return_seconds:
                    continue
                async with self.lock:
                    if not self.connected or client.current_subsystem in (None, default):
                        continue
                    _LOGGER.info(
                        "%s: idle in %s, returning to %s",
                        self.name,
                        client.current_subsystem,
                        default,
                    )
                    await client.async_enter(default)
                    self._touch()
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.exception("%s: idle subsystem watch failed", self.name)

    # ---- commands ----------------------------------------------------------

    async def async_press(self, entity: Entity, join: int, hold: float | None = None) -> None:
        """Press one join for an entity with no feedback to confirm against."""
        self._check_ready(entity)
        async with self.lock:
            try:
                await self._enter(entity)
                await self.client.async_press(
                    join, entity.subsystem, hold, entity.smart_object or 0
                )
            except (CipError, WriteRefused, OSError) as err:
                raise HubError(f"{entity.name}: {err}") from err
            finally:
                self._touch()

    async def async_set_analog(self, entity: Entity, join: int, value: int) -> None:
        self._check_ready(entity)
        async with self.lock:
            try:
                await self._enter(entity)
                await self.client.async_set_analog(join, value, entity.subsystem)
            except (CipError, WriteRefused, OSError) as err:
                raise HubError(f"{entity.name}: {err}") from err
            finally:
                self._touch()

    async def async_select(self, entity: Entity, option: SelectOption) -> None:
        """Choose an option by pressing its join, unless it is already the one chosen.

        One press and no retry. Unlike a toggle, pressing an item is not undone
        by a second press, so there is nothing to synthesise; but the encoding
        has never been seen accepted, so a failed choice is left visible rather
        than hammered. See docs/adr/0013-writing-to-smartobjects.md.
        """
        self._check_ready(entity)
        async with self.lock:
            try:
                await self._enter(entity)
                if self.selected(entity) == option:
                    return
                await self.client.async_press(
                    option.press, entity.subsystem, None, entity.smart_object or 0
                )
            except (CipError, WriteRefused, OSError) as err:
                raise HubError(f"{entity.name}: {err}") from err
            finally:
                self._touch()

    async def async_set(self, entity: Entity, want_on: bool) -> None:
        """Drive a light or switch with feedback to a discrete state.

        Crestron buttons are usually toggles. Home Assistant needs discrete
        on and off, so this reads the feedback, presses only when it differs
        from what was asked, and waits for the processor to confirm. That has
        to happen here, under the lock, because it depends on the state the
        previous press produced and must be serialised against feedback from
        a wall keypad arriving at the same moment. See
        docs/adr/0004-discrete-on-off-synthesised-from-feedback.md.
        """
        self._check_ready(entity)
        assert entity.feedback is not None
        async with self.lock:
            try:
                for attempt in range(1, CONFIRM_ATTEMPTS + 1):
                    # Revalidated every attempt: the confirmation wait is long
                    # enough for the session to drop and come back.
                    if not self.connected:
                        raise HubError(f"{entity.name}: the {self.name} link dropped mid-command")
                    await self._enter(entity)
                    current = self.is_on(entity)
                    if current is None:
                        raise HubError(f"{entity.name}: state unknown, refusing to press blind")
                    if current == want_on:
                        return
                    join = entity.press_for(want_on)
                    waiter = self._add_waiter(entity.subsystem, entity.feedback, int(want_on))
                    try:
                        await self.client.async_press(join, entity.subsystem)
                        await asyncio.wait_for(waiter, CONFIRM_TIMEOUT)
                        return
                    except TimeoutError:
                        _LOGGER.warning(
                            "%s: no feedback on d%d within %.0fs of pressing d%d (attempt %d)",
                            entity.name,
                            entity.feedback,
                            CONFIRM_TIMEOUT,
                            join,
                            attempt,
                        )
                        # The slot may have been dropped out of its subsystem
                        # without the session dropping. Forget where it is so
                        # the next attempt re-enters rather than pressing into a
                        # slot that is not listening.
                        self.client.invalidate_subsystem()
                    finally:
                        self._drop_waiter(waiter)
            except (CipError, WriteRefused, OSError) as err:
                raise HubError(f"{entity.name}: {err}") from err
            finally:
                self._touch()
        raise HubError(
            f"{entity.name}: pressed {CONFIRM_ATTEMPTS} times without the processor confirming "
            f"{'on' if want_on else 'off'}. Check that feedback join {entity.feedback} really "
            "reports this load, and that the press join really drives it."
        )

    # ---- confirmation waiters ---------------------------------------------

    def _add_waiter(self, subsystem: str | None, join: int, value: int) -> asyncio.Future[None]:
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiters.append((subsystem, join, value, future))
        return future

    def _drop_waiter(self, future: asyncio.Future[None]) -> None:
        self._waiters = [w for w in self._waiters if w[3] is not future]

    def _resolve_waiters(self, subsystem: str | None, join: int, value: int) -> None:
        for w_sub, w_join, w_value, future in self._waiters:
            if (w_sub, w_join, w_value) == (subsystem, join, value) and not future.done():
                future.set_result(None)


__all__ = ["ANALOG", "DIGITAL", "SERIAL", "Hub", "HubError"]
