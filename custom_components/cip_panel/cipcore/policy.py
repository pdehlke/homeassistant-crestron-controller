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


@dataclass(frozen=True)
class WritePolicy:
    """Writes allowed and denied, per join kind.

    `enabled` False means listen-only: every write is refused, whatever the
    allow list says. The deny list is checked first and cannot be overridden.
    """

    enabled: bool = False
    allow: dict[str, frozenset[int]] = field(default_factory=dict)
    deny: dict[str, frozenset[int]] = field(default_factory=dict)

    def check(self, kind: str, join: int) -> None:
        """Raise WriteRefused unless this write is permitted."""
        if kind not in KINDS:
            raise ValueError(f"unknown join kind {kind!r}")
        if join in self.deny.get(kind, frozenset()):
            raise WriteRefused(f"{kind} join {join} is on the never-write list")
        if not self.enabled:
            raise WriteRefused(f"writes are disabled (listen-only), refusing {kind} join {join}")
        if join not in self.allow.get(kind, frozenset()):
            raise WriteRefused(f"{kind} join {join} is not mapped to anything writable")

    def permits(self, kind: str, join: int) -> bool:
        try:
            self.check(kind, join)
        except WriteRefused:
            return False
        return True

    def conflicts(self) -> list[tuple[str, int]]:
        """Joins that are both allowed and denied, which a valid map never has."""
        return sorted(
            (kind, join)
            for kind in KINDS
            for join in self.allow.get(kind, frozenset()) & self.deny.get(kind, frozenset())
        )


LISTEN_ONLY = WritePolicy()
