"""The join map: which joins on one processor become which entities.

A join map is a YAML file the user owns, usually drafted by the inventory CLI
and then edited by hand. This module turns the parsed YAML into validated
dataclasses and refuses, with a message a novice can act on, anything that
would be unsafe or ambiguous. It imports nothing from Home Assistant, so
`crestron-controller check` runs exactly the validation the integration runs.

The format is documented for users in docs/configuration/join-map-reference.md.
Keep the two in step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from typing import Any

from .client import Subsystem, Timing
from .policy import ANALOG, DIGITAL, KINDS, SERIAL, WritePolicy

SCHEMA_VERSION = 1

LIGHT = "light"
SWITCH = "switch"
BINARY_SENSOR = "binary_sensor"
BUTTON = "button"
SENSOR = "sensor"
NUMBER = "number"
ENTITY_TYPES = (LIGHT, SWITCH, BINARY_SENSOR, BUTTON, SENSOR, NUMBER)

# How a light or switch is driven. See docs/configuration/press-modes.md.
PRESS_TOGGLE = "toggle"
PRESS_ON_OFF = "on_off"
PRESS_MOMENTARY = "momentary"
PRESS_MODES = (PRESS_TOGGLE, PRESS_ON_OFF, PRESS_MOMENTARY)

SCALE_RAW = "raw"
SCALE_PERCENT = "percent"

_ID = re.compile(r"^[a-z0-9_]+$")


class JoinMapError(ValueError):
    """The join map is invalid. The message names the entry and the fix."""


@dataclass(frozen=True)
class Entity:
    """One entity. Which fields matter depends on `type`; see the reference doc."""

    type: str
    id: str
    name: str
    subsystem: str | None
    # light, switch
    feedback: int | None = None
    also_reports: tuple[int, ...] = ()
    press: str = PRESS_TOGGLE
    press_join: int | None = None
    on_join: int | None = None
    off_join: int | None = None
    brightness_join: int | None = None
    brightness_writable: bool = False
    # binary_sensor, button
    join: int | None = None
    hold_seconds: float | None = None
    device_class: str | None = None
    # sensor, number
    analog: int | None = None
    serial: int | None = None
    scale: str = SCALE_RAW
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    writable: bool = False
    icon: str | None = None
    # sensor, binary_sensor: read joins inside this SmartObject instead of the
    # program's own range. See docs/adr/0012-smartobject-joins-are-their-own-namespace.md.
    smart_object: int | None = None

    @property
    def assumed_state(self) -> bool:
        return self.type in (LIGHT, SWITCH) and self.press == PRESS_MOMENTARY

    def press_for(self, want_on: bool) -> int:
        """Which digital join to press to move a light or switch toward a state."""
        if self.press == PRESS_TOGGLE:
            assert self.press_join is not None
            return self.press_join
        if want_on:
            assert self.on_join is not None
            return self.on_join
        # A momentary entity with one join toggles blind; on_off always has both.
        join = self.off_join if self.off_join is not None else self.on_join
        assert join is not None
        return join

    def reads(self) -> list[tuple[str, int]]:
        """Every (kind, join) whose change should refresh this entity."""
        out: list[tuple[str, int]] = []
        if self.feedback is not None:
            out.append((DIGITAL, self.feedback))
        out += [(DIGITAL, j) for j in self.also_reports]
        if self.brightness_join is not None:
            out.append((ANALOG, self.brightness_join))
        if self.join is not None and self.type == BINARY_SENSOR:
            out.append((DIGITAL, self.join))
        if self.analog is not None:
            out.append((ANALOG, self.analog))
        if self.serial is not None:
            out.append((SERIAL, self.serial))
        return out

    def writes(self) -> list[tuple[str, int]]:
        """Every (kind, join) this entity could ever write, for the allow list."""
        out: list[tuple[str, int]] = []
        if self.type in (LIGHT, SWITCH):
            for j in (self.press_join, self.on_join, self.off_join):
                if j is not None:
                    out.append((DIGITAL, j))
            if self.brightness_writable and self.brightness_join is not None:
                out.append((ANALOG, self.brightness_join))
        elif self.type == BUTTON and self.join is not None:
            out.append((DIGITAL, self.join))
        elif self.type == NUMBER and self.writable and self.analog is not None:
            out.append((ANALOG, self.analog))
        return sorted(set(out))


@dataclass(frozen=True)
class JoinMap:
    subsystems: dict[str, Subsystem] = field(default_factory=dict)
    default_subsystem: str | None = None
    idle_return_seconds: float = 5.0
    repoll_after_entry: bool = True
    never_write: dict[str, frozenset[int]] = field(default_factory=dict)
    timing: Timing = field(default_factory=Timing)
    entities: tuple[Entity, ...] = ()

    def policy(self, enabled: bool) -> WritePolicy:
        """The write policy this map implies, with writes on or off."""
        allow: dict[str, set[int]] = {kind: set() for kind in KINDS}
        for sub in self.subsystems.values():
            allow[DIGITAL].add(sub.entry_join)
        for entity in self.entities:
            for kind, join in entity.writes():
                allow[kind].add(join)
        return WritePolicy(
            enabled=enabled,
            allow={k: frozenset(v) for k, v in allow.items()},
            deny=dict(self.never_write),
        )


# ---- parsing ---------------------------------------------------------------


def _where(index: int | None, raw: dict[str, Any] | None = None) -> str:
    if index is None:
        return "join map"
    label = (raw or {}).get("id") or (raw or {}).get("name")
    return f"entities[{index}]" + (f" ({label})" if label else "")


def _join(value: Any, where: str, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise JoinMapError(f"{where}: {what} must be a whole number, got {value!r}")
    if not 1 <= value <= 0x8000:
        raise JoinMapError(f"{where}: {what} {value} is outside 1-32768")
    return value


def _opt_join(raw: dict[str, Any], key: str, where: str) -> int | None:
    return None if raw.get(key) is None else _join(raw[key], where, key)


def _join_set(value: Any, where: str) -> frozenset[int]:
    """Accept a list of joins and "low-high" range strings."""
    if value is None:
        return frozenset()
    if not isinstance(value, list):
        raise JoinMapError(f"{where}: expected a list, got {value!r}")
    out: set[int] = set()
    for item in value:
        if isinstance(item, str):
            m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", item)
            if not m:
                raise JoinMapError(f"{where}: {item!r} is not a join or a 'low-high' range")
            low, high = int(m.group(1)), int(m.group(2))
            if low > high:
                raise JoinMapError(f"{where}: range {item!r} runs backwards")
            out.update(_join(j, where, "join") for j in range(low, high + 1))
        else:
            out.add(_join(item, where, "join"))
    return frozenset(out)


def _smart_object(raw: dict[str, Any], where: str) -> int | None:
    value = raw.get("smart_object")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise JoinMapError(f"{where}: smart_object must be a whole number, got {value!r}")
    # 0 is how the wire would spell the program's own joins, so it is refused
    # rather than read as an object.
    if not 1 <= value <= 0xFFFFFFFF:
        raise JoinMapError(f"{where}: smart_object {value} is outside 1-4294967295")
    return value


def _slug(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")


def _number(raw: dict[str, Any], key: str, where: str) -> float | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JoinMapError(f"{where}: {key} must be a number, got {value!r}")
    return float(value)


_KNOWN_KEYS = {
    LIGHT: {"feedback", "also_reports", "press", "press_join", "on_join", "off_join", "brightness"},
    SWITCH: {"feedback", "also_reports", "press", "press_join", "on_join", "off_join"},
    BINARY_SENSOR: {"join", "device_class", "smart_object"},
    BUTTON: {"join", "hold_seconds"},
    SENSOR: {"analog", "serial", "scale", "unit", "device_class", "smart_object"},
    NUMBER: {"analog", "scale", "unit", "min", "max", "step", "writable"},
}
_COMMON_KEYS = {"type", "id", "name", "subsystem", "icon"}


def _parse_entity(
    index: int, raw: Any, subsystems: dict[str, Subsystem], default: str | None
) -> Entity:
    if not isinstance(raw, dict):
        raise JoinMapError(f"entities[{index}]: each entity must be a mapping")
    where = _where(index, raw)
    kind = raw.get("type")
    if kind not in ENTITY_TYPES:
        raise JoinMapError(f"{where}: type must be one of {', '.join(ENTITY_TYPES)}")
    if "smart_object" in raw and kind not in (SENSOR, BINARY_SENSOR):
        # Writing into a SmartObject has never been seen to work, so nothing
        # that can write may name one. See issue #4.
        raise JoinMapError(
            f"{where}: smart_object is read-only for now; only a sensor or binary_sensor "
            "can read a SmartObject"
        )
    unknown = set(raw) - _COMMON_KEYS - _KNOWN_KEYS[kind]
    if unknown:
        raise JoinMapError(f"{where}: unknown key(s) for a {kind}: {', '.join(sorted(unknown))}")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise JoinMapError(f"{where}: every entity needs a name")
    entity_id = raw.get("id") or _slug(name)
    if not isinstance(entity_id, str) or not _ID.match(entity_id):
        raise JoinMapError(f"{where}: id {entity_id!r} may use only a-z, 0-9 and _")

    subsystem = raw.get("subsystem", default)
    if subsystems:
        if subsystem not in subsystems:
            raise JoinMapError(
                f"{where}: subsystem {subsystem!r} is not one of {', '.join(sorted(subsystems))}"
            )
    elif raw.get("subsystem") is not None:
        raise JoinMapError(f"{where}: names a subsystem, but the map declares none")
    else:
        subsystem = None

    values: dict[str, Any] = {
        "type": kind,
        "id": entity_id,
        "name": name.strip(),
        "subsystem": subsystem,
        "icon": raw.get("icon"),
        "smart_object": _smart_object(raw, where),
    }

    if kind in (LIGHT, SWITCH):
        press = raw.get("press", PRESS_TOGGLE)
        if press not in PRESS_MODES:
            raise JoinMapError(f"{where}: press must be one of {', '.join(PRESS_MODES)}")
        feedback = _opt_join(raw, "feedback", where)
        on_join = _opt_join(raw, "on_join", where)
        off_join = _opt_join(raw, "off_join", where)
        press_join = _opt_join(raw, "press_join", where)
        if press == PRESS_TOGGLE:
            if feedback is None:
                raise JoinMapError(
                    f"{where}: press: toggle needs a feedback join, because a toggle can only "
                    "be made discrete by reading state first. Use press: momentary if there "
                    "is no feedback."
                )
            if on_join is not None or off_join is not None:
                raise JoinMapError(f"{where}: on_join/off_join need press: on_off or momentary")
            press_join = press_join if press_join is not None else feedback
        elif press == PRESS_ON_OFF:
            if feedback is None or on_join is None or off_join is None:
                raise JoinMapError(f"{where}: press: on_off needs feedback, on_join and off_join")
            if press_join is not None:
                raise JoinMapError(f"{where}: press_join is only for press: toggle")
        else:
            if on_join is None:
                raise JoinMapError(f"{where}: press: momentary needs on_join")
            if feedback is not None or raw.get("also_reports"):
                raise JoinMapError(
                    f"{where}: press: momentary is for joins with no feedback; with a "
                    "feedback join, use toggle or on_off instead"
                )
            if press_join is not None:
                raise JoinMapError(f"{where}: press_join is only for press: toggle")
        also = raw.get("also_reports") or []
        if not isinstance(also, list):
            raise JoinMapError(f"{where}: also_reports must be a list of joins")
        values.update(
            press=press,
            feedback=feedback,
            also_reports=tuple(_join(j, where, "also_reports") for j in also),
            press_join=press_join,
            on_join=on_join,
            off_join=off_join,
        )
        if kind == LIGHT and raw.get("brightness") is not None:
            bright = raw["brightness"]
            if not isinstance(bright, dict) or "join" not in bright:
                raise JoinMapError(f"{where}: brightness must be a mapping with a join")
            unknown = set(bright) - {"join", "writable"}
            if unknown:
                raise JoinMapError(
                    f"{where}: unknown brightness key(s): {', '.join(sorted(unknown))}"
                )
            values["brightness_join"] = _join(bright["join"], where, "brightness join")
            values["brightness_writable"] = bool(bright.get("writable", False))
    elif kind in (BINARY_SENSOR, BUTTON):
        if raw.get("join") is None:
            raise JoinMapError(f"{where}: a {kind} needs a join")
        values["join"] = _join(raw["join"], where, "join")
        if kind == BUTTON:
            values["hold_seconds"] = _number(raw, "hold_seconds", where)
        else:
            values["device_class"] = raw.get("device_class")
    else:
        analog = _opt_join(raw, "analog", where)
        serial = _opt_join(raw, "serial", where) if kind == SENSOR else None
        if (analog is None) == (serial is None):
            need = "exactly one of analog or serial" if kind == SENSOR else "an analog join"
            raise JoinMapError(f"{where}: a {kind} needs {need}")
        scale = raw.get("scale", SCALE_RAW)
        if scale not in (SCALE_RAW, SCALE_PERCENT):
            raise JoinMapError(f"{where}: scale must be raw or percent")
        if serial is not None and "scale" in raw:
            raise JoinMapError(f"{where}: scale applies to analog joins only")
        values.update(analog=analog, serial=serial, scale=scale, unit=raw.get("unit"))
        if kind == SENSOR:
            values["device_class"] = raw.get("device_class")
        if kind == NUMBER:
            top = 100.0 if scale == SCALE_PERCENT else 65535.0
            minimum = _number(raw, "min", where)
            maximum = _number(raw, "max", where)
            step = _number(raw, "step", where)
            values.update(
                minimum=0.0 if minimum is None else minimum,
                maximum=top if maximum is None else maximum,
                step=1.0 if step is None else step,
                writable=bool(raw.get("writable", False)),
            )
            if not 0 <= values["minimum"] < values["maximum"] <= top:
                raise JoinMapError(f"{where}: need 0 <= min < max <= {top:g}")
    return Entity(**values)


def _parse_subsystems(raw: Any) -> tuple[dict[str, Subsystem], str | None, float, bool]:
    if raw is None:
        return {}, None, 5.0, True
    if not isinstance(raw, dict):
        raise JoinMapError("subsystems: must be a mapping")
    entries = raw.get("entries")
    if not isinstance(entries, dict) or not entries:
        raise JoinMapError("subsystems: needs at least one entry under entries")
    subsystems: dict[str, Subsystem] = {}
    for name, spec in entries.items():
        where = f"subsystems.entries.{name}"
        if not isinstance(spec, dict) or "join" not in spec:
            raise JoinMapError(f"{where}: needs a join")
        unknown = set(spec) - {"join", "quiet_seconds"}
        if unknown:
            raise JoinMapError(f"{where}: unknown key(s): {', '.join(sorted(unknown))}")
        quiet = _number(spec, "quiet_seconds", where)
        if quiet is not None and quiet <= 0:
            raise JoinMapError(f"{where}: quiet_seconds must be a positive number of seconds")
        subsystems[str(name)] = Subsystem(
            str(name), _join(spec["join"], where, "join"), 0.85 if quiet is None else quiet
        )
    joins = [s.entry_join for s in subsystems.values()]
    if len(set(joins)) != len(joins):
        raise JoinMapError("subsystems: two subsystems share an entry join")
    default = raw.get("default")
    if default not in subsystems:
        raise JoinMapError(
            f"subsystems.default: {default!r} must name one of {', '.join(sorted(subsystems))}"
        )
    unknown = set(raw) - {"default", "entries", "idle_return_seconds", "repoll_after_entry"}
    if unknown:
        raise JoinMapError(f"subsystems: unknown key(s): {', '.join(sorted(unknown))}")
    idle = _number(raw, "idle_return_seconds", "subsystems")
    if idle is not None and idle <= 0:
        raise JoinMapError("subsystems.idle_return_seconds: must be a positive number of seconds")
    return (
        subsystems,
        default,
        5.0 if idle is None else idle,
        bool(raw.get("repoll_after_entry", True)),
    )


def _parse_timing(raw: Any) -> Timing:
    if raw is None:
        return Timing()
    if not isinstance(raw, dict):
        raise JoinMapError("timing: must be a mapping")
    names = {f.name for f in fields(Timing)} - {"reconnect_backoff"}
    unknown = set(raw) - names
    if unknown:
        raise JoinMapError(f"timing: unknown key(s): {', '.join(sorted(unknown))}")
    values = {}
    for key in raw:
        number = _number(raw, key, "timing")
        if number is None or number <= 0:
            raise JoinMapError(f"timing.{key}: must be a positive number of seconds")
        values[key] = number
    return Timing(**values)


def parse(raw: Any) -> JoinMap:
    """Validate a parsed join map. Raises JoinMapError naming the first problem."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise JoinMapError("join map: the file must be a YAML mapping")
    known = {"version", "subsystems", "never_write", "timing", "entities"}
    unknown = set(raw) - known
    if unknown:
        raise JoinMapError(f"join map: unknown top-level key(s): {', '.join(sorted(unknown))}")
    version = raw.get("version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise JoinMapError(f"join map: version {version!r} is not supported, use {SCHEMA_VERSION}")

    subsystems, default, idle, repoll = _parse_subsystems(raw.get("subsystems"))

    deny_raw = raw.get("never_write") or {}
    if not isinstance(deny_raw, dict):
        raise JoinMapError("never_write: must be a mapping of digital/analog/serial lists")
    unknown = set(deny_raw) - set(KINDS)
    if unknown:
        raise JoinMapError(f"never_write: unknown key(s): {', '.join(sorted(unknown))}")
    never_write = {kind: _join_set(deny_raw.get(kind), f"never_write.{kind}") for kind in KINDS}

    entities_raw = raw.get("entities") or []
    if not isinstance(entities_raw, list):
        raise JoinMapError("entities: must be a list")
    entities = tuple(
        _parse_entity(i, item, subsystems, default) for i, item in enumerate(entities_raw)
    )

    jm = JoinMap(
        subsystems=subsystems,
        default_subsystem=default,
        idle_return_seconds=idle,
        repoll_after_entry=repoll,
        never_write=never_write,
        timing=_parse_timing(raw.get("timing")),
        entities=entities,
    )
    _check(jm)
    return jm


def _check(jm: JoinMap) -> None:
    """Cross-entity rules: unique ids, no shared joins, nothing denied is writable."""
    ids: dict[str, int] = {}
    for i, entity in enumerate(jm.entities):
        if entity.id in ids:
            raise JoinMapError(
                f"entities[{i}]: id {entity.id!r} is already used by entities[{ids[entity.id]}]; "
                "give one of them an explicit id"
            )
        ids[entity.id] = i

    # A join may be read by several entities (a sensor and a light on the same
    # feedback is legitimate), but may be *written* by only one: two entities
    # pressing one toggle would each undo the other.
    writers: dict[tuple[str | None, str, int], str] = {}
    for entity in jm.entities:
        for kind, join in entity.writes():
            key = (entity.subsystem, kind, join)
            if key in writers and writers[key] != entity.id:
                raise JoinMapError(
                    f"{entity.id}: writes {kind} join {join}, which {writers[key]} also writes"
                )
            writers[key] = entity.id

    for name, sub in jm.subsystems.items():
        if sub.entry_join in jm.never_write.get(DIGITAL, frozenset()):
            raise JoinMapError(
                f"subsystems.entries.{name}: entry join {sub.entry_join} is on the never-write "
                "list, so this subsystem could never be entered"
            )
    for entity in jm.entities:
        for kind, join in entity.writes():
            if join in jm.never_write.get(kind, frozenset()):
                raise JoinMapError(
                    f"{entity.id}: would write {kind} join {join}, which is on the never-write "
                    "list. If the join has a safe alias elsewhere in the program, map that one."
                )
