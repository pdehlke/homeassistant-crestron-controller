"""Read an x52 panel's Environment.xml into a Project.

A TSW x52-series panel (TSW-552, TSW-752, TSW-1052 and their kin) keeps its
compiled VT Pro-e project on its own flash as one XML file, `Environment.xml`,
and hands it over through `XGETFILE` on its CTP console. The file names every
page, every button and every join number in the clear. Reading the joins from
it is the safe way to build a join map; the alternative, pressing joins to see
what they do, risks arming an alarm or opening a gate on a program that reuses
join numbers across subsystems.

HTML5 .ch5z archives from x60 and x70 panels are read by ch5.py. Older panels
use other formats, which are detected and refused with a pointer to
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

import codecs
import html
import re
import xml.etree.ElementTree as ET

from .project import ANALOG, DIGITAL, FORMATS_DOC, SERIAL, Control, Project, UnsupportedFormat

# ---- decoding --------------------------------------------------------------


def decode_project(raw: bytes) -> str:
    """Decode the file to text and cut it off at the end of the root element.

    The panel writes UTF-16 with a byte-order mark. UTF-8 and BOM-less UTF-16
    are accepted too, in case a file has been re-saved by an editor. Zip
    archives never get here; panel.load_project sends them to ch5.py.
    """
    head = raw[:4]
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


# ---- parsing ---------------------------------------------------------------

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
