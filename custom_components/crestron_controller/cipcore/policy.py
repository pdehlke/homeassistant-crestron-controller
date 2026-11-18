"""Which joins a session may ever write.

Crestron programs reuse join numbers freely, and on some systems a join that
looks like a spare is wired to something that must never be pressed by
accident: an alarm keypad's panic button, a gate, a garage door. Nothing on the
wire says which joins those are. So the default is to write nothing, and once
writes are switched on, to write only the joins the user has mapped to
something, with a user-maintained deny list that wins over everything.

The check runs in the client at the last point before bytes reach the socket.
That is deliberate: subsystem-entry presses and CLI presses never come from the
join map's entity table, so a check anywhere higher up would miss them. See
docs/adr/0003-listen-only-by-default-with-allow-and-deny-lists.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DIGITAL = "digital"
ANALOG = "analog"
SERIAL = "serial"
KINDS = (DIGITAL, ANALOG, SERIAL)


class WriteRefused(Exception):
    """A write was stopped by the policy before it reached the wire."""


# Joins per kind, as the allow and deny lists hold them.
JoinSets = dict[str, frozenset[int]]


@dataclass(frozen=True)
class WritePolicy:
    """Writes allowed and denied, per join kind and per SmartObject.

    `enabled` False means listen-only: every write is refused, whatever the
    allow list says. The deny list is checked first and cannot be overridden.

    `allow` and `deny` cover the program's own joins. A SmartObject numbers its
    joins in a range of its own, so its lists live apart, keyed by object, and
    object 3's digital 5 is never confused with the program's digital 5. See
    docs/adr/0013-writing-to-smartobjects.md.
    """

    enabled: bool = False
    allow: JoinSets = field(default_factory=dict)
    deny: JoinSets = field(default_factory=dict)
    object_allow: dict[int, JoinSets] = field(default_factory=dict)
    object_deny: dict[int, JoinSets] = field(default_factory=dict)

    def _lists(self, obj: int) -> tuple[JoinSets, JoinSets]:
        if obj == 0:
            return self.allow, self.deny
        return self.object_allow.get(obj, {}), self.object_deny.get(obj, {})

    def check(self, kind: str, join: int, obj: int = 0) -> None:
        """Raise WriteRefused unless this write is permitted."""
        if kind not in KINDS:
            raise ValueError(f"unknown join kind {kind!r}")
        allow, deny = self._lists(obj)
        what = f"{kind} join {join}" + (f" in SmartObject {obj}" if obj else "")
        if join in deny.get(kind, frozenset()):
            raise WriteRefused(f"{what} is on the never-write list")
        if not self.enabled:
            raise WriteRefused(f"writes are disabled (listen-only), refusing {what}")
        if join not in allow.get(kind, frozenset()):
            raise WriteRefused(f"{what} is not mapped to anything writable")

    def permits(self, kind: str, join: int, obj: int = 0) -> bool:
        try:
            self.check(kind, join, obj)
        except WriteRefused:
            return False
        return True

    def conflicts(self) -> list[tuple[str, int, int]]:
        """(kind, join, object) both allowed and denied, which a valid map never has."""
        out = []
        for obj in {0, *self.object_allow, *self.object_deny}:
            allow, deny = self._lists(obj)
            for kind in KINDS:
                both = allow.get(kind, frozenset()) & deny.get(kind, frozenset())
                out += [(kind, join, obj) for join in both]
        return sorted(out)


LISTEN_ONLY = WritePolicy()
