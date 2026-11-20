"""What a panel project reader produces: the controls it found, and how it refuses a file.

x52.py reads an x52 Environment.xml and ch5.py an x60/x70 .ch5z archive; both
fill in the same Project, which draft.py turns into an inventory and a draft
join map.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FORMATS_DOC = "docs/inventory/panel-project-files.md"


class UnsupportedFormat(Exception):
    """The file is not a panel project this tool can read. The message says what it looks like."""


DIGITAL = "digital"
ANALOG = "analog"
SERIAL = "serial"


@dataclass(frozen=True)
class Control:
    """One control that carries at least one join, as placed on one page.

    A subpage placed on two pages yields its controls twice, once per page,
    because each placement can shift the joins by its own offset.
    """

    page: str
    path: str
    control: str
    object_name: str
    label: str
    press: int | None = None
    feedback: int | None = None
    analog: int | None = None
    serial: int | None = None
    page_flip: str | None = None
    other: tuple[tuple[str, int], ...] = ()
    offsets: tuple[int, int, int] = (0, 0, 0)
    # The SmartObject the joins belong to, 0 for the program's own joins. Only
    # HTML5 projects built with Contract Editor put joins in SmartObjects.
    smart_object: int = 0

    @property
    def offset_note(self) -> str:
        d, a, s = self.offsets
        parts = [f"{k}+{v}" for k, v in (("d", d), ("a", a), ("s", s)) if v]
        return " ".join(parts)


@dataclass
class Project:
    panel_type: str | None
    home_page: str | None
    pages: list[str] = field(default_factory=list)
    controls: list[Control] = field(default_factory=list)
    # Join attributes a reader found but could not turn into a number, one
    # human-readable line each. The x52 reader never produces any.
    unresolved: list[str] = field(default_factory=list)
    # Warnings the reader wants shown with every output, one paragraph each:
    # the draft carries them as comments and the summary prints them.
    caveats: list[str] = field(default_factory=list)
