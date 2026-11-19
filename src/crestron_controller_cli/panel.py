"""Fetch a touch panel's project file and turn it into an inventory and a draft join map.

A TSW x52-series panel (TSW-552, TSW-752, TSW-1052 and their kin) keeps its
compiled VT Pro-e project on its own flash as one XML file, `Environment.xml`,
and hands it over through `XGETFILE` on its CTP console. The file names every
page, every button and every join number in the clear. Reading the joins from
it is the safe way to build a join map; the alternative, pressing joins to see
what they do, risks arming an alarm or opening a gate on a program that reuses
join numbers across subsystems.

Two formats are understood: the x52 Environment.xml, described below, and the
HTML5 .ch5z archives that x60 and x70 panels run, read by ch5.py. Support for
.ch5z is experimental and untested against a real panel. Older panels use other
formats, which are detected and refused with a pointer to
docs/inventory/panel-project-files.md.

What the parser relies on, learned from real x52 project files:

- The root element is `<Crestron>` with `<TargetControl>Project</TargetControl>`.
  `Properties/Pages` holds every page *and* every subpage as `<Page uid=.. Name=..>`;
  `Properties/IsSubpage` (spelled "False" on pages and "true" on subpages, so
  compared without case) tells them apart. `Properties/FirstToLoad` is the uid
  of the page the panel shows at startup, which is the home page.
- A page's controls are under `Properties/Children`, as `<Child>` elements, and
  `<Subpage>` elements whose `TargetControl` is `SubpageRef` and whose
  `Properties/PageID` is the uid of the subpage drawn there.
- A control's joins are elements under its `Properties` whose names end in
  `Join`: `DigitalPressJoin`, `AnalogFeedbackJoin`, `IndirectTextJoin` and so
  on, with 0 meaning unused. A D-pad carries one `Type="JoinCommand"` element
  per direction instead. Physical hardkeys are `Hardkeys/Hardkey/JoinNumber`.
- Labels are HTML stored as escaped text. Text the processor supplies at run
  time appears inside the label as `<cips>N?placeholder</cips>`, where N is
  the serial join, and on those controls `IndirectTextJoin` usually reads 0.
- A button has no separate feedback join in this format. Its feedback arrives
  on its press join, and `ShowSelectFeedback` says whether the panel draws it.
- Pages and subpage references both carry `DigitalJoinOffset`,
  `AnalogJoinOffset` and `SerialJoinOffset`. VT Pro-e uses these so one
  subpage can be placed several times, each placement shifted to its own join
  range. The parser adds the offsets of every page and reference on the way
  down to a control. Every file this was developed against had them all at 0,
  so the arithmetic is unverified against a real non-zero case; wherever an
  offset was applied the output says so, and those joins deserve a check.
- The file as retrieved ends with XMODEM padding after `</Crestron>`, which
  makes it invalid XML until the tail is cut off.
"""

from __future__ import annotations

import argparse
import codecs
import csv
import html
import io
import json
import re
import sys
import textwrap
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from . import ctp
from .console import CTP_PORT, ConsoleError, add_connection_args, open_console

DEFAULT_REMOTE_PATH = "\\display\\swf\\Environment.xml"
FORMATS_DOC = "docs/inventory/panel-project-files.md"
JOIN_MAP_DOC = "docs/configuration/join-map-reference.md"


class UnsupportedFormat(Exception):
    """The file is not a panel project this tool can read. The message says what it looks like."""


# ---- decoding --------------------------------------------------------------


def decode_project(raw: bytes) -> str:
    """Decode the file to text and cut it off at the end of the root element.

    The panel writes UTF-16 with a byte-order mark. UTF-8 and BOM-less UTF-16
    are accepted too, in case a file has been re-saved by an editor.
    """
    head = raw[:4]
    if head.startswith(b"PK\x03\x04"):
        raise UnsupportedFormat(
            "this is a zip archive, not an x52 Environment.xml. If it is an x60 or x70 "
            f".ch5z project, read it with load_project(). See {FORMATS_DOC}."
        )
    if head.startswith(codecs.BOM_UTF8):
        text = raw[3:].decode("utf-8", errors="replace")
    elif head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        text = _decode_utf16(raw)
    elif len(raw) >= 2 and raw[1] == 0 and raw[0] != 0:
        text = _decode_utf16(codecs.BOM_UTF16_LE + raw)
    else:
        text = raw.decode("utf-8", errors="replace")

    # A project file never declares a DTD. Refusing one closes off entity
    # expansion tricks without needing a hardened XML parser.
    if re.search(r"<!(DOCTYPE|ENTITY)", text[:4096], re.IGNORECASE) and not text.lstrip(
        "\ufeff \t\r\n"
    ).lower().startswith(("<!doctype html", "<html")):
        raise UnsupportedFormat("the file declares a DTD, which an x52 Environment.xml never does")

    # The XML declaration, if any, names an encoding that no longer applies
    # once the text is a Python str, and ElementTree rejects the mismatch.
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    stripped = text.lstrip("﻿ \t\r\n")
    lowered = stripped[:200].lower()
    if lowered.startswith(("<!doctype html", "<html")):
        raise UnsupportedFormat(
            f"this is an HTML page, not an x52 Environment.xml. For an x60 or x70 panel, "
            f"pass the whole .ch5z project instead. See {FORMATS_DOC}."
        )
    match = re.match(r"<([A-Za-z_][\w.\-]*)", stripped)
    if not match:
        raise UnsupportedFormat(
            f"this does not look like XML at all, so it is not an x52 Environment.xml. "
            f"See {FORMATS_DOC} for the formats panels use."
        )
    root = match.group(1)
    end = stripped.rfind(f"</{root}>")
    if end < 0:
        raise UnsupportedFormat(
            f"the root element <{root}> is never closed; the file may be truncated. Fetch it again."
        )
    # Everything after the root closes is transfer padding (NULs or SUBs) or
    # junk, and ElementTree reports it as a confusing "not well-formed" error
    # on the last line rather than as trailing garbage.
    return stripped[: end + len(root) + 3]


def _decode_utf16(raw: bytes) -> str:
    # The padding may leave an odd byte at the end; it is part of the tail
    # that gets trimmed, so drop it rather than fail on it.
    if len(raw) % 2:
        raw = raw[:-1]
    return raw.decode("utf-16", errors="replace")


# ---- the model -------------------------------------------------------------

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
    # Join attributes an HTML5 project names but this tool could not turn into
    # a number, one human-readable line each. Always empty for an x52 project.
    unresolved: list[str] = field(default_factory=list)
    experimental: bool = False


_CIPS = re.compile(r"<cips>\s*(\d+)\s*\?([^<]*)</cips>", re.IGNORECASE)


def _int(text: str | None) -> int:
    try:
        return int((text or "").strip())
    except ValueError:
        return 0


def _kind_of(tag: str) -> str:
    if "Analog" in tag:
        return ANALOG
    if "Serial" in tag or "Text" in tag:
        return SERIAL
    return DIGITAL


def _own_elements(props: ET.Element):
    """Every element under a control's Properties, not descending into child controls."""
    stack = list(props)[::-1]
    while stack:
        el = stack.pop()
        if el.tag == "Children":
            continue
        yield el
        stack.extend(list(el)[::-1])


def clean_label(raw: str | None) -> tuple[str, int | None]:
    """Turn a stored label into plain text, and pull out its first indirect serial join.

    Indirect text is replaced by its placeholder, or by "[sN]" when the
    placeholder is empty, so a label like "Zone: <cips>11?Name</cips>" reads
    "Zone: Name".
    """
    if not raw:
        return "", None
    serial = None
    found = _CIPS.search(raw)
    if found:
        serial = int(found.group(1))

    def placeholder(m: re.Match[str]) -> str:
        return m.group(2).strip() or f"[s{m.group(1)}]"

    text = _CIPS.sub(placeholder, raw)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return " ".join(text.split()), serial


def _label_of(props: ET.Element) -> tuple[str, int | None]:
    direct = props.find("Label")
    if direct is not None and (direct.text or "").strip():
        return clean_label(direct.text)
    # Advanced buttons keep a label per state; the normal state's is the one
    # a person sees at rest.
    for path in (".//NormalModeState/Label", ".//Label"):
        for el in props.iterfind(path):
            if (el.text or "").strip():
                return clean_label(el.text)
    return "", None


class _Walker:
    def __init__(self, root: ET.Element) -> None:
        props = root.find("Properties")
        assert props is not None
        self.props = props
        self.defs: dict[str, ET.Element] = {}
        for page in props.iterfind("Pages/Page"):
            if page.find("Properties") is not None:
                self.defs[page.get("uid", "")] = page
        self.visited: set[str] = set()
        self.controls: list[Control] = []

    def name(self, uid: str | None) -> str | None:
        page = self.defs.get(uid or "")
        return None if page is None else page.get("Name") or f"page {uid}"

    @staticmethod
    def offsets(el: ET.Element) -> tuple[int, int, int]:
        return (
            _int(el.findtext("Properties/DigitalJoinOffset")),
            _int(el.findtext("Properties/AnalogJoinOffset")),
            _int(el.findtext("Properties/SerialJoinOffset")),
        )

    def walk_page(
        self, page: ET.Element, top: str, trail: list[str], base: tuple[int, int, int]
    ) -> None:
        uid = page.get("uid", "")
        name = page.get("Name") or f"page {uid}"
        own = self.offsets(page)
        offs = (base[0] + own[0], base[1] + own[1], base[2] + own[2])
        trail = [*trail, name]
        path = " > ".join(trail)
        self.visited.add(uid)
        props = page.find("Properties")
        assert props is not None

        # A page's own DigitalJoin is how the processor flips the panel to it.
        flip = _int(props.findtext("DigitalJoin"))
        if flip:
            self.add(
                Control(
                    top,
                    path,
                    "Page",
                    name,
                    name,
                    other=(("DigitalJoin (page flip)", flip + offs[0]),),
                    offsets=offs,
                )
            )
        self.hardkeys(props, top, path, offs)
        self.children(props, top, trail, offs)

    def hardkeys(self, props: ET.Element, top: str, path: str, offs: tuple[int, int, int]) -> None:
        for key in props.iterfind("Hardkeys/Hardkey"):
            join = _int(key.findtext("JoinNumber"))
            if join:
                label = f"Hardkey {key.get('uid', '?')}"
                self.add(
                    Control(
                        top,
                        path,
                        "Hardkey",
                        label,
                        label,
                        press=join + offs[0],
                        page_flip=self.name(key.findtext("PageFlip")),
                        offsets=offs,
                    )
                )

    def children(
        self, props: ET.Element, top: str, trail: list[str], offs: tuple[int, int, int]
    ) -> None:
        for child in props.iterfind("Children/*"):
            kind = child.findtext("TargetControl") or child.tag
            if kind == "SubpageRef":
                self.subpage_ref(child, top, trail, offs)
                continue
            cprops = child.find("Properties")
            if cprops is None:
                continue
            self.control(child, cprops, kind, top, " > ".join(trail), offs)
            if cprops.find("Children") is not None:
                # A grouped control holds further controls of its own.
                group = child.findtext("ObjectName") or kind
                self.children(cprops, top, [*trail, group], offs)

    def subpage_ref(
        self, ref: ET.Element, top: str, trail: list[str], offs: tuple[int, int, int]
    ) -> None:
        uid = ref.findtext("Properties/PageID")
        target = self.defs.get((uid or "").strip())
        ref_offs = self.offsets(ref)
        total = (offs[0] + ref_offs[0], offs[1] + ref_offs[1], offs[2] + ref_offs[2])
        name = self.name(uid) or f"missing subpage {uid}"
        visibility = _int(ref.findtext("Properties/DigitalJoin"))
        if visibility:
            self.add(
                Control(
                    top,
                    " > ".join(trail),
                    "SubpageRef",
                    ref.findtext("ObjectName") or "Subpage Reference",
                    name,
                    other=(("DigitalJoin (subpage visibility)", visibility + offs[0]),),
                    offsets=offs,
                )
            )
        if target is None or name in trail:
            return  # a dangling reference, or one that would recurse forever
        self.walk_page(target, top, trail, total)

    def control(
        self,
        child: ET.Element,
        props: ET.Element,
        kind: str,
        top: str,
        path: str,
        offs: tuple[int, int, int],
    ) -> None:
        object_name = child.findtext("ObjectName") or kind
        label, cips = _label_of(props)
        shift = {DIGITAL: offs[0], ANALOG: offs[1], SERIAL: offs[2]}
        press = analog = serial = None
        other: list[tuple[str, int]] = []
        commands: list[tuple[str, int]] = []

        for el in _own_elements(props):
            if el.get("Type") == "JoinCommand":
                join = _int(el.findtext("JoinNumber"))
                if join:
                    jtype = (el.findtext("JoinType") or "Digital").strip().lower()
                    signal = el.findtext("SignalName") or el.tag.replace("JoinCommand", "")
                    kind_of = jtype if jtype in shift else DIGITAL
                    commands.append((f"{signal}|{kind_of}", join + shift[kind_of]))
                continue
            if not el.tag.endswith("Join") or list(el):
                continue
            join = _int(el.text)
            if not join:
                continue
            effective = join + shift[_kind_of(el.tag)]
            if el.tag == "DigitalPressJoin" and press is None:
                press = effective
            elif el.tag == "IndirectTextJoin" and serial is None:
                serial = effective
            elif el.tag == "AnalogFeedbackJoin" and analog is None:
                analog = effective
            else:
                # Visibility, enable, mode and transition joins, a second press
                # join, and join elements this parser has not met before all
                # land here: kept in the inventory, never made into entities,
                # and no role guessed for them.
                other.append((el.tag, effective))
        if serial is None and cips is not None:
            serial = cips + offs[2]

        page_flip = (
            self.name(props.findtext("PageFlip")) if _int(props.findtext("PageFlip")) else None
        )
        show_feedback = (props.findtext("ShowSelectFeedback") or "").strip().lower() == "true"
        feedback = press if press is not None and show_feedback else None

        if press or analog or serial or other or page_flip:
            self.add(
                Control(
                    top,
                    path,
                    kind,
                    object_name,
                    label,
                    press=press,
                    feedback=feedback,
                    analog=analog,
                    serial=serial,
                    page_flip=page_flip,
                    other=tuple(other),
                    offsets=offs,
                )
            )
        # Each D-pad direction is its own button with its own join, so each
        # gets its own row.
        for spec, join in commands:
            signal, kind_of = spec.split("|")
            name = f"{label or object_name} {signal}".strip()
            self.add(
                Control(
                    top,
                    path,
                    kind,
                    object_name,
                    name,
                    press=join if kind_of == DIGITAL else None,
                    analog=join if kind_of == ANALOG else None,
                    serial=join if kind_of == SERIAL else None,
                    offsets=offs,
                )
            )

    def add(self, control: Control) -> None:
        self.controls.append(control)


def parse_project(text: str) -> Project:
    """Parse decoded Environment.xml text into a Project."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as err:
        raise UnsupportedFormat(f"the XML does not parse ({err}); the file may be damaged") from err
    if root.tag != "Crestron" or root.findtext("TargetControl") != "Project":
        raise UnsupportedFormat(
            f"the root element is <{root.tag}>, not a Crestron VT Pro-e project, so this "
            f"is not an x52 Environment.xml. See {FORMATS_DOC}."
        )
    if root.find("Properties/Pages") is None:
        raise UnsupportedFormat(
            f"this Crestron project has no Properties/Pages section, which an x52 "
            f"Environment.xml always has. See {FORMATS_DOC}."
        )

    walker = _Walker(root)
    home_uid = (root.findtext("Properties/FirstToLoad") or "").strip()
    tops = [
        p
        for p in walker.defs.values()
        if (p.findtext("Properties/IsSubpage") or "").strip().lower() != "true"
    ]
    home = walker.defs.get(home_uid)
    if home is None and tops:
        home = tops[0]
    # The home page goes first so that, when a join appears on several pages,
    # the draft files it under the page a person sees first.
    if home is not None and home in tops:
        tops.remove(home)
        tops.insert(0, home)

    walker.hardkeys(walker.props, "(project)", "(project hardkeys)", (0, 0, 0))
    for page in tops:
        name = page.get("Name") or f"page {page.get('uid')}"
        walker.walk_page(page, name, [], (0, 0, 0))
    for uid, page in walker.defs.items():
        if uid not in walker.visited:
            name = page.get("Name") or f"page {uid}"
            walker.walk_page(page, f"(unplaced) {name}", [], (0, 0, 0))

    return Project(
        panel_type=root.findtext("Properties/PanelType") or root.findtext("PanelType"),
        home_page=None if home is None else home.get("Name"),
        pages=[p.get("Name") or "" for p in tops],
        controls=walker.controls,
    )


def load_project(path: Path) -> Project:
    raw = path.read_bytes()
    if raw.startswith(b"PK\x03\x04"):
        from . import ch5  # imported here because ch5 imports this module

        return ch5.load_ch5z(raw)
    return parse_project(decode_project(raw))


# ---- outputs ---------------------------------------------------------------

CSV_FIELDS = (
    "page",
    "path",
    "control",
    "object_name",
    "label",
    "digital_press",
    "digital_feedback",
    "analog",
    "serial",
    "page_flip",
    "other_joins",
    "offsets_applied",
    "smart_object",
)


def inventory_csv(project: Project) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_FIELDS)
    for c in project.controls:
        writer.writerow(
            (
                c.page,
                c.path,
                c.control,
                c.object_name,
                c.label,
                c.press or "",
                c.feedback or "",
                c.analog or "",
                c.serial or "",
                c.page_flip or "",
                " ".join(f"{tag}={join}" for tag, join in c.other),
                c.offset_note,
                c.smart_object or "",
            )
        )
    return out.getvalue()


def _slug(text: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text.lower())).strip("_")


def _q(text: str) -> str:
    # A JSON string is also a valid YAML double-quoted scalar, which is the
    # simplest way to quote arbitrary label text correctly.
    # JSON leaves these three raw, and YAML reads them as line breaks.
    quoted = json.dumps(text, ensure_ascii=False)
    return quoted.replace("\x85", "\\x85").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


# Characters a terminal or a YAML parser may act on: C0 and C1 controls, and
# the Unicode line and paragraph separators. YAML treats \x85, U+2028 and
# U+2029 as line breaks, so one inside a comment would turn the rest of the
# line into YAML. Project files are untrusted, and a crafted label could
# otherwise add a writable entry to a draft that must stay read-only.
_UNSAFE = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def _clean(text: str) -> str:
    return _UNSAFE.sub(" ", text)


def _finish(lines: list[str]) -> str:
    """Join draft lines, cleaning every comment line of characters that could end it early."""
    out = [_clean(line) if line.lstrip().startswith("#") else line for line in lines]
    return "\n".join(out) + "\n"


@dataclass
class _Candidate:
    kind: str  # DIGITAL, ANALOG or SERIAL
    join: int
    smart_object: int
    first: Control
    seen: list[Control] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.first.label


def _candidates(project: Project) -> list[_Candidate]:
    """One candidate per (kind, join, smart object), grouped by page.

    One load is routinely on several pages, so the same join on many buttons
    becomes one entity. The entity takes its name from the first labelled
    button that carries the join, because a hardkey or an unlabelled button
    makes a useless name; the other places it appears are kept for the comment.
    """
    found: dict[tuple[str, int, int], _Candidate] = {}
    for c in project.controls:
        # In an x52 project feedback is always the press join; an HTML5
        # project can name a different one, and that is the join to read.
        joins = [(DIGITAL, c.press), (DIGITAL, c.feedback), (ANALOG, c.analog), (SERIAL, c.serial)]
        for kind, join in dict.fromkeys(joins):
            if join is None:
                continue
            key = (kind, join, c.smart_object)
            cand = found.get(key)
            if cand is None:
                found[key] = _Candidate(kind, join, c.smart_object, c)
            elif _better_name(c, cand.first):
                cand.seen.append(cand.first)
                cand.first = c
            else:
                cand.seen.append(c)

    # Pages in the order the panel presents them, with the project-wide
    # hardkeys last, since they are the least informative group.
    order: dict[str, int] = {}
    for c in project.controls:
        order.setdefault(c.page, len(order))
    if "(project)" in order:
        order["(project)"] = len(order)
    ranked = list(enumerate(found.values()))
    ranked.sort(key=lambda pair: (order[pair[1].first.page], pair[0]))
    return [cand for _, cand in ranked]


def _better_name(new: Control, old: Control) -> bool:
    def score(c: Control) -> int:
        return (2 if c.label else 0) + (1 if c.control != "Hardkey" else 0)

    return score(new) > score(old)


def _also_appears(cand: _Candidate) -> str:
    """Summarise the other places a join appears, one entry per label."""
    pages: dict[str, list[str]] = {}
    for o in cand.seen:
        label = o.label or o.object_name
        if (label, o.page) == (cand.first.label, cand.first.page):
            continue
        listed = pages.setdefault(label, [])
        if o.page not in listed:
            listed.append(o.page)
    return "; ".join(f"{label} on {', '.join(where)}" for label, where in pages.items())


def _entry_candidates(project: Project) -> list[Control]:
    """Buttons on the home page, which in gated programs enter the subsystems."""
    if project.home_page is None:
        return []
    out, seen = [], set()
    for c in project.controls:
        if c.page != project.home_page or c.press is None or c.control == "Hardkey":
            continue
        if c.smart_object:
            continue  # a list item; subsystem entries are the program's own joins
        if c.press in seen:
            continue
        seen.add(c.press)
        out.append(c)
    return out


_HEADER = """\
# DRAFT join map generated by `crestron-controller panel parse` from {source}.
#
# Nothing here can write to the processor. Every entry is a read-only
# binary_sensor (digital join) or sensor (analog or serial join), named after
# the label the panel shows, so you can watch what each join does before
# deciding anything. Labels that come from the processor at run time appear
# as their placeholder text or as [sN].
#
# To make an entry controllable, change it by hand once you know what it does.
# A digital binary_sensor that tracks a load becomes, for example:
#
#   - type: light
#     name: Kitchen Pendants
#     feedback: 117          # was `join: 117`
#     press: toggle
#
# Read {join_map_doc}
# before promoting anything, especially the sections on press modes and
# never_write. Delete entries you do not want.
#
# One join can appear on several buttons; it is listed once, with a comment
# naming the other places. If those labels mean different things, the program
# may reuse the join across subsystems, and it must not be written until the
# subsystems: section is set up.
"""


_EXPERIMENTAL = """\
#
# EXPERIMENTAL: this came from an HTML5 (.ch5z) project, which this tool has
# read only from public sample projects, never from a real panel. Check every
# join with `crestron-controller watch` before relying on it. Entries with
# `smart_object:` read SmartObject joins, which are also untested on real
# hardware. See {formats_doc}.
"""


def draft_join_map(project: Project, source: str = "a panel project") -> str:
    """Render the draft join map as commented YAML."""
    lines = _HEADER.format(source=source, join_map_doc=JOIN_MAP_DOC).splitlines()
    if project.panel_type:
        lines.insert(1, f"# Panel type: {project.panel_type}")
    if project.experimental:
        lines += _EXPERIMENTAL.format(formats_doc=FORMATS_DOC).splitlines()
    if project.unresolved:
        lines += [
            "#",
            f"# {len(project.unresolved)} join attributes name a signal this tool could not turn",
            "# into a join number. They are not in this draft:",
        ]
        for line in project.unresolved[:_UNRESOLVED_SHOWN]:
            lines += _wrap_comment(line, indent="  ")
        if len(project.unresolved) > _UNRESOLVED_SHOWN:
            lines.append(f"#   ... and {len(project.unresolved) - _UNRESOLVED_SHOWN} more")

    entries = _entry_candidates(project)
    if entries:
        lines += [
            "#",
            "# Subsystem-entry CANDIDATES, to verify before use. These are the buttons",
            f"# on the home page ({project.home_page!s}). In some programs each one enters",
            "# a subsystem, and joins mean nothing until it has been pressed. Others are",
            "# just navigation. Confirm with `crestron-controller listen` before copying any into",
            "# a subsystems: section like this one:",
            "#",
            "#   subsystems:",
            "#     default: <the subsystem most entities belong to>",
            "#     entries:",
        ]
        names: set[str] = set()
        unlabelled: list[str] = []
        for c in entries:
            if not c.label:
                unlabelled.append(str(c.press))
                continue
            name = _slug(c.label) or f"join_{c.press}"
            if name in names:
                name = f"{name}_{c.press}"
            names.add(name)
            note = f'"{c.label}"'
            if c.page_flip:
                note += f", flips the panel to {c.page_flip}"
            lines.append(f"#       {name}: {{join: {c.press}}}    # {note}")
        if unlabelled:
            lines += [
                "#",
                "# Unlabelled buttons on the home page, less likely to be entries:",
                *_wrap_comment(", ".join(unlabelled)),
            ]

    lines += ["", "version: 1", ""]

    candidates = _candidates(project)
    if not candidates:
        lines.append("entities: []")
        return _finish(lines)

    # Names repeat ("Off" on every room page), so a repeated label gets its
    # page appended, and the id gets the join, which is always unique per kind.
    label_keys: dict[str, set[tuple[str, int, int]]] = {}
    for cand in candidates:
        label_keys.setdefault(cand.label, set()).add((cand.kind, cand.join, cand.smart_object))
    used_ids: set[str] = set()

    lines.append("entities:")
    current_page = None
    for cand in candidates:
        if cand.first.page != current_page:
            current_page = cand.first.page
            lines += ["", f"  # ---- page: {current_page} " + "-" * 20]
        prefix = {DIGITAL: "d", ANALOG: "a", SERIAL: "s"}[cand.kind]
        if cand.smart_object:
            prefix = f"o{cand.smart_object}_{prefix}"
        base = cand.label or f"{cand.first.object_name} {prefix}{cand.join}"
        name = base
        if cand.label and len(label_keys[cand.label]) > 1:
            name = f"{base} ({cand.first.page})"
        ident = _slug(base) or f"join_{prefix}{cand.join}"
        if ident in used_ids or (cand.label and len(label_keys[cand.label]) > 1):
            ident = f"{ident}_{prefix}{cand.join}"
        while ident in used_ids:
            ident += "_x"
        used_ids.add(ident)

        where = f"{cand.first.path}, {cand.first.control}"
        lines.append(f"  # {where}")
        if cand.first.offset_note:
            lines.append(f"  # join offset applied ({cand.first.offset_note}); verify this number")
        others = _also_appears(cand)
        if others:
            lines += _wrap_comment("also appears as: " + others, indent="  ")
        if cand.kind == DIGITAL:
            lines += [
                "  - type: binary_sensor",
                f"    id: {_q(ident)}",
                f"    name: {_q(name)}",
                f"    join: {cand.join}",
            ]
        else:
            lines += [
                "  - type: sensor",
                f"    id: {_q(ident)}",
                f"    name: {_q(name)}",
                f"    {cand.kind}: {cand.join}",
            ]
        if cand.smart_object:
            lines.append(f"    smart_object: {cand.smart_object}")
    return _finish(lines)


_UNRESOLVED_SHOWN = 20


def _wrap_comment(text: str, indent: str = "") -> list[str]:
    width = 96 - len(indent)
    return [f"{indent}# {line}" for line in textwrap.wrap(text, width, break_long_words=False)]


def summary(project: Project) -> str:
    pages: dict[str, int] = {}
    for c in project.controls:
        pages[c.page] = pages.get(c.page, 0) + 1
    out = [
        f"Panel type: {project.panel_type or 'unknown'}",
        f"Home page: {project.home_page or 'unknown'}",
        f"{len(project.controls)} controls with joins on {len(pages)} pages:",
    ]
    out += [f"  {count:4d}  {page}" for page, count in pages.items()]
    if project.unresolved:
        out.append(f"{len(project.unresolved)} join attributes could not be resolved:")
        out += [f"  {line}" for line in project.unresolved[:_UNRESOLVED_SHOWN]]
        if len(project.unresolved) > _UNRESOLVED_SHOWN:
            out.append(f"  ... and {len(project.unresolved) - _UNRESOLVED_SHOWN} more")
    if project.experimental:
        out.append(
            f"HTML5 project support is experimental and untested on real panels. See {FORMATS_DOC}."
        )
    return "\n".join(_clean(line) for line in out)


# ---- commands --------------------------------------------------------------


def run_parse(args: argparse.Namespace) -> int:
    path = Path(args.file)
    try:
        project = load_project(path)
    except OSError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except UnsupportedFormat as err:
        print(f"error: {path}: {err}", file=sys.stderr)
        return 2

    if args.format == "csv":
        text = inventory_csv(project)
    else:
        text = draft_join_map(project, source=path.name)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(summary(project), file=sys.stderr)
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def run_fetch(args: argparse.Namespace) -> int:
    print(
        "This reads the project from the panel's flash over XMODEM. On a TSW-752 it "
        "takes roughly 10-15 minutes; the panel keeps working meanwhile.",
        file=sys.stderr,
    )
    started = time.monotonic()
    last = [0.0]

    def progress(count: int) -> None:
        now = time.monotonic()
        if now - last[0] >= 2.0:
            last[0] = now
            rate = count / max(now - started, 0.001) / 1024
            print(f"  {count // 1024} KiB received, {rate:.1f} KiB/s", file=sys.stderr)

    try:
        with open_console(args) as con:
            assert con.sock is not None
            reader = ctp.Reader(con.sock)
            reply = ctp.request_file(con.sock, reader, args.remote_path)
            refused = ctp.refusal(reply)
            if refused:
                print(f"error: the panel refused: {refused}", file=sys.stderr)
                print(
                    "Check the path with "
                    "`crestron-controller console HOST --port 41795 DIR \\display`.",
                    file=sys.stderr,
                )
                return 1
            data = ctp.receive(con.sock, reader, on_progress=progress)
    except ConsoleError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except ctp.XmodemError as err:
        print(f"error: {err}; nothing was written", file=sys.stderr)
        return 1

    data = ctp.strip_padding(data)
    Path(args.output).write_bytes(data)
    elapsed = time.monotonic() - started
    print(f"wrote {args.output}: {len(data)} bytes in {elapsed:.0f}s", file=sys.stderr)
    print(f"next: crestron-controller panel parse {args.output} -o draft.yaml", file=sys.stderr)
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    panel = subparsers.add_parser(
        "panel",
        help="fetch and parse a touch panel's project file",
        description=(
            "Fetch a TSW x52 panel's Environment.xml, or read an x60/x70 .ch5z project "
            "(experimental), and turn it into a draft join map."
        ),
    )
    sub = panel.add_subparsers(dest="panel_command", required=True, metavar="ACTION")

    fetch = sub.add_parser(
        "fetch",
        help="download Environment.xml from a TSW x52 panel's CTP console",
        description=(
            "Download the panel's compiled project over XMODEM on the CTP console "
            "(port 41795; telnet on port 23 refuses the transfer). Read-only. "
            "Takes roughly 10-15 minutes on a TSW-752."
        ),
    )
    add_connection_args(fetch, default_port=CTP_PORT)
    fetch.add_argument(
        "--remote-path",
        default=DEFAULT_REMOTE_PATH,
        help=f"file on the panel (default {DEFAULT_REMOTE_PATH})",
    )
    fetch.add_argument("-o", "--output", required=True, help="local file to write")
    fetch.set_defaults(func=run_fetch)

    parse = sub.add_parser(
        "parse",
        help="inventory a panel project and draft a join map",
        description=(
            "Parse an x52 Environment.xml or an x60/x70 .ch5z project. .ch5z support "
            "is experimental and untested on real panels. --format yaml (the default) "
            "writes a draft join map in which every entry is read-only; --format csv "
            "writes an inventory of every control with a join. Other panel formats are "
            f"refused; see {FORMATS_DOC}."
        ),
    )
    parse.add_argument("file", help="the Environment.xml or .ch5z to read")
    parse.add_argument("-o", "--output", help="write here instead of standard output")
    parse.add_argument("--format", choices=("yaml", "csv"), default="yaml")
    parse.set_defaults(func=run_parse)
