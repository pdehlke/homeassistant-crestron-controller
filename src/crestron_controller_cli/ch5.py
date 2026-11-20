"""Read an x60/x70 HTML5 (CH5) panel project, packed as a .ch5z archive.

EXPERIMENTAL. Everything here was learned from Crestron's published npm
packages and from public sample projects (see docs/inventory/panel-project-files.md);
none of it has been checked against a project taken from a real panel, or
against what a real processor sends.

What the reader relies on:

- A .ch5z is a zip holding `<name>.ch5` and `<name>_manifest.json`. The .ch5
  is itself a zip of the built web project, with `index.html` at its root
  (`Ch5Archiver.js` in `@crestron/ch5-utilities`).
- Joins are HTML attributes on CH5 components: `receivestate*` for what the
  processor sends, `sendevent*` for what the panel sends. ch5_signals.py says
  which join kind each attribute carries. A value is either a join number or a
  Contract Editor signal name. Plain HTML elements act only on `data-ch5-*`
  attributes, so other join attributes on them are ignored.
- A project built with Contract Editor carries `config/contract.cse2j`, plain
  JSON. Feedback is `signals.states.<kind>.<smart object>.<join>` -> name;
  presses are `signals.events.<kind>.<name>` -> `{joinId, smartObjectId}`.
  Every contract signal therefore lives in a SmartObject. The contract lists
  each list item's signals separately, so a list's joins come from the
  contract, never from guessing at the template.
- Construct projects describe their pages in `assets/data/project-config.json`
  (`content.pages`, `content.$defaultView` for the home page) and keep each
  reusable widget as a `<template id=...>` in its own file, placed on a page
  by `<ch5-template templateid=...>` or repeated by
  `<ch5-subpage-reference-list widgetid=...>`. A placement's `contractname`
  is prefixed to the signal names inside it; for a list, each item is
  `<contractname>.Items[<i>].<name>`. `booleanjoinoffset` and its kin shift a
  template's join numbers, and a list's `booleanjoinincrement` and kin shift
  each item's; both are applied here but unverified.
- Files under `app/template/` are Construct's own shell (logs, theme menu,
  version box). Their signals stay inside the panel, so they are skipped.
- Joins set from JavaScript (projects built with React, Vue or similar) cannot
  be read without running the code. A project whose HTML carries no joins and
  no contract is refused with that explanation.
"""

from __future__ import annotations

import dataclasses
import html
import io
import json
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from . import ch5_signals as sig
from .project import FORMATS_DOC, Control, Project, UnsupportedFormat

CONTRACT_PATH = "config/contract.cse2j"
PROJECT_CONFIG = "assets/data/project-config.json"
SHELL_PREFIX = "app/template/"
CONTRACT_ENABLED = "Contract Enabled"

# Limits on what is read into memory from an archive. Real projects seen were
# under 25 MB in all; these leave plenty of room while refusing a zip bomb.
_MAX_INNER = 256 * 1024 * 1024
_MAX_FILE = 16 * 1024 * 1024

_TEMPLATE_VAR = re.compile(r"\{\{\s*[\w.]+\s*\}\}")
_JOIN_NUMBER = re.compile(r"[0-9]+")
_KIND_INDEX = {sig.DIGITAL: 0, sig.ANALOG: 1, sig.SERIAL: 2}

EXPERIMENTAL = (
    "EXPERIMENTAL: this came from an HTML5 (.ch5z) project, which this tool has read only "
    "from public sample projects, never from a real panel. Check every join with "
    "`crestron-controller watch` before relying on it. Entries with `smart_object:` read "
    f"SmartObject joins, which are also untested on real hardware. See {FORMATS_DOC}."
)


def load_ch5z(raw: bytes) -> Project:
    """Read a .ch5z archive into a Project."""
    files = _web_files(raw)
    contract = Contract.parse(files.get(CONTRACT_PATH))
    reader = _Reader(files, contract)
    project = reader.read()
    if not project.controls and not project.unresolved and not contract.signals:
        raise UnsupportedFormat(
            "this HTML5 project has no join attributes in its HTML and no Contract Editor "
            "contract. Its joins are probably set from JavaScript (projects built with "
            "React, Vue or similar), which this tool cannot read without running the code. "
            f"See {FORMATS_DOC}."
        )
    return project


# ---- the archive -----------------------------------------------------------


def _web_files(raw: bytes) -> dict[str, bytes]:
    """The HTML, contract and config files of the web project inside a .ch5z."""
    try:
        outer = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as err:
        raise UnsupportedFormat(
            f"the zip archive does not open ({err}); the file may be damaged. See {FORMATS_DOC}."
        ) from err
    inner_names = [n for n in outer.namelist() if n.lower().endswith(".ch5")]
    if len(inner_names) != 1:
        raise UnsupportedFormat(
            "this zip archive is not a .ch5z project: a .ch5z holds exactly one .ch5 file "
            "and a manifest. VT Pro-e source projects (.vtz) are zip archives too, and are "
            f"not supported. See {FORMATS_DOC}."
        )
    info = outer.getinfo(inner_names[0])
    if info.file_size > _MAX_INNER:
        raise UnsupportedFormat(f"the .ch5 inside is {info.file_size} bytes, too large to read")
    try:
        inner = zipfile.ZipFile(io.BytesIO(_read(outer, info)))
    except zipfile.BadZipFile as err:
        raise UnsupportedFormat(f"the .ch5 inside the archive does not open ({err})") from err

    files: dict[str, bytes] = {}
    for item in inner.infolist():
        name = item.filename
        if item.is_dir() or "node_modules/" in name or item.file_size > _MAX_FILE:
            continue
        if name.lower().endswith((".html", ".htm")) or name in (CONTRACT_PATH, PROJECT_CONFIG):
            files[name] = _read(inner, item)
    if "index.html" not in files:
        raise UnsupportedFormat(
            f"the .ch5 inside has no index.html, so it is not a CH5 project. See {FORMATS_DOC}."
        )
    return files


def _read(archive: zipfile.ZipFile, item: zipfile.ZipInfo) -> bytes:
    try:
        return archive.read(item)
    except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError) as err:
        # A failed checksum, a truncated member, an encrypted one, or a
        # compression method Python does not support.
        raise UnsupportedFormat(
            f"{item.filename} inside the archive cannot be read ({err}); the file may be damaged"
        ) from err


def _json(data: bytes | None, what: str) -> dict:
    if data is None:
        return {}
    try:
        value = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as err:
        raise UnsupportedFormat(f"{what} is not valid JSON ({err})") from err
    return value if isinstance(value, dict) else {}


# ---- the contract ----------------------------------------------------------

_CONTRACT_KINDS = {"boolean": sig.DIGITAL, "numeric": sig.ANALOG, "string": sig.SERIAL}


@dataclass(frozen=True)
class Signal:
    name: str
    direction: str  # sig.STATE or sig.EVENT
    kind: str
    smart_object: int
    join: int


@dataclass
class Contract:
    signals: list[Signal] = field(default_factory=list)
    by_name: dict[str, list[Signal]] = field(default_factory=dict)

    @classmethod
    def parse(cls, data: bytes | None) -> Contract:
        contract = cls()
        tree = _json(data, CONTRACT_PATH).get("signals")
        if not isinstance(tree, dict):
            return contract
        for direction, key in ((sig.STATE, "states"), (sig.EVENT, "events")):
            section = tree.get(key)
            if not isinstance(section, dict):
                continue
            for ckind, entries in section.items():
                kind = _CONTRACT_KINDS.get(ckind)
                if kind is None or not isinstance(entries, dict):
                    continue
                for a, b in entries.items():
                    if direction == sig.STATE and isinstance(b, dict):
                        # smart object -> {join: name}
                        for join, name in b.items():
                            contract.add(Signal(str(name), direction, kind, _num(a), _num(join)))
                    elif direction == sig.EVENT and isinstance(b, dict):
                        # name -> {joinId, smartObjectId}
                        contract.add(
                            Signal(
                                a,
                                direction,
                                kind,
                                _num(b.get("smartObjectId")),
                                _num(b.get("joinId")),
                            )
                        )
        return contract

    def add(self, signal: Signal) -> None:
        if signal.join <= 0:
            return
        self.signals.append(signal)
        self.by_name.setdefault(signal.name, []).append(signal)

    def lookup(self, name: str, direction: str, kind: str) -> Signal | None:
        """The signal of this kind, preferring this direction. Another kind is no match."""
        found = [s for s in self.by_name.get(name, []) if s.kind == kind]
        for s in found:
            if s.direction == direction:
                return s
        return found[0] if found else None


def _num(value: object) -> int:
    try:
        return int(str(value).strip())
    except ValueError:
        return 0


# ---- HTML ------------------------------------------------------------------


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str]


@dataclass
class _Parsed:
    elements: list[_Element] = field(default_factory=list)
    templates: dict[str, list[_Element]] = field(default_factory=dict)


class _Collector(HTMLParser):
    """Every element with its attributes, with `<template id=...>` contents set aside."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out = _Parsed()
        self.stack: list[tuple[str | None, list[_Element]]] = []

    def _target(self) -> list[_Element]:
        for template_id, elements in reversed(self.stack):
            if template_id is not None:
                return elements
        return self.out.elements

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k: v or "" for k, v in attrs}
        if tag == "template":
            # A template with an id is a widget placed elsewhere; one without
            # is a list item drawn in place, so its contents stay where they are.
            template_id = values.get("id") or None
            elements: list[_Element] = []
            if template_id is not None:
                self.out.templates[template_id] = elements
            self.stack.append((template_id, elements))
            return
        self._target().append(_Element(tag, values))

    def handle_endtag(self, tag: str) -> None:
        if tag == "template" and self.stack:
            self.stack.pop()


def _parse_html(data: bytes) -> _Parsed:
    collector = _Collector()
    collector.feed(data.decode("utf-8", errors="replace"))
    collector.close()
    return collector.out


def _label(attrs: dict[str, str]) -> str:
    for key in ("label", "labelinnerhtml", "aria-label", "title"):
        text = attrs.get(key, "")
        if text:
            text = html.unescape(re.sub(r"<[^>]+>", " ", text))
            return " ".join(text.split())
    return ""


# ---- walking pages ---------------------------------------------------------


@dataclass(frozen=True)
class _Context:
    page: str
    trail: tuple[str, ...]
    offsets: tuple[int, int, int] = (0, 0, 0)
    prefix: str = ""  # contract name prefix, ending in "."
    widgets: tuple[str, ...] = ()  # widget ids on the way down, to stop recursion

    def into(self, name: str, **changes: Any) -> _Context:
        return dataclasses.replace(self, trail=(*self.trail, name), **changes)


class _Reader:
    def __init__(self, files: dict[str, bytes], contract: Contract) -> None:
        self.contract = contract
        self.config = _json(files.get(PROJECT_CONFIG), PROJECT_CONFIG)
        self.parsed: dict[str, _Parsed] = {}
        self.templates: dict[str, list[_Element]] = {}
        self.template_file: dict[str, str] = {}
        for name, data in sorted(files.items()):
            if not name.lower().endswith((".html", ".htm")) or name.startswith(SHELL_PREFIX):
                continue
            parsed = _parse_html(data)
            self.parsed[name] = parsed
            for template_id, elements in parsed.templates.items():
                self.templates.setdefault(template_id, elements)
                self.template_file.setdefault(template_id, name)
        self.controls: list[Control] = []
        # One entry per (place within a page, attribute, value, reason), with
        # the pages it was found on, so a widget repeated on every page is
        # reported once.
        self.unresolved: dict[tuple[str, str, str, str], list[str]] = {}
        self.used: set[Signal] = set()
        self.placed: set[str] = set()

    def read(self) -> Project:
        pages, home = self._pages()
        for label, path, visibility in pages:
            ctx = _Context(label, (label,))
            if visibility:
                self._page_join(ctx, visibility)
            self._walk(self.parsed[path].elements, ctx)
        for template_id, elements in self.templates.items():
            if template_id not in self.placed:
                name = f"(unplaced) {template_id}"
                self._walk(elements, _Context(name, (name,), widgets=(template_id,)))
        self._contract_only()
        return Project(
            panel_type=None,
            home_page=home,
            pages=[label for label, _, _ in pages],
            controls=self.controls,
            unresolved=[
                f'{pages[0]}{place}: {attr}="{value}" ({reason}'
                + (f"; also on {len(pages) - 1} other pages)" if len(pages) > 1 else ")")
                for (place, attr, value, reason), pages in self.unresolved.items()
            ],
            caveats=[EXPERIMENTAL],
        )

    def _pages(self) -> tuple[list[tuple[str, str, str]], str | None]:
        """(label, file, visibility signal) per page, home page first, and the home page's label."""
        content = self.config.get("content") if isinstance(self.config, dict) else None
        pages: list[tuple[str, str, str]] = []
        home: str | None = None
        if isinstance(content, dict) and isinstance(content.get("pages"), list):
            default = content.get("$defaultView")
            for page in content["pages"]:
                if not isinstance(page, dict):
                    continue
                path = (str(page.get("fullPath", "")) + str(page.get("fileName", ""))).lstrip("./")
                if path not in self.parsed:
                    continue
                name = str(page.get("pageName") or path)
                nav = page.get("navigation")
                label = str(nav.get("label") or name) if isinstance(nav, dict) else name
                props = page.get("triggerViewChildProperties")
                visibility = (
                    str(props.get("receiveStateShow", "")) if isinstance(props, dict) else ""
                )
                entry = (label, path, visibility)
                if name == default:
                    home = label
                    pages.insert(0, entry)
                else:
                    pages.append(entry)
        if not pages:
            # A hand-written project: every HTML file that is not a widget is a page.
            widget_files = set(self.template_file.values())
            for path, parsed in self.parsed.items():
                if path in widget_files and not parsed.elements:
                    continue
                label = path.rsplit(".", 1)[0]
                pages.append((label, path, ""))
            pages.sort(key=lambda p: p[1] != "index.html")
            home = pages[0][0] if pages and pages[0][1] == "index.html" else None
        return pages, home

    def _page_join(self, ctx: _Context, value: str) -> None:
        joins = self._resolve(value, "receivestateshow", sig.STATE, sig.DIGITAL, ctx, ctx.page)
        for obj, join in joins:
            self.controls.append(
                Control(
                    ctx.page,
                    ctx.page,
                    "Page",
                    ctx.page,
                    ctx.page,
                    other=(("receivestateshow (page visibility)", join),),
                    smart_object=obj,
                )
            )

    def _walk(self, elements: list[_Element], ctx: _Context) -> None:
        for el in elements:
            self._element(el, ctx)
            if el.tag == "ch5-template":
                self._place_template(el, ctx)
            elif el.tag == "ch5-subpage-reference-list":
                self._place_list(el, ctx)

    def _place_template(self, el: _Element, ctx: _Context) -> None:
        template_id = el.attrs.get("templateid", "")
        elements = self.templates.get(template_id)
        if elements is None or template_id in ctx.widgets:
            return
        self.placed.add(template_id)
        own = (
            _num(el.attrs.get("booleanjoinoffset", 0)),
            _num(el.attrs.get("numericjoinoffset", 0)),
            _num(el.attrs.get("stringjoinoffset", 0)),
        )
        offsets = tuple(a + b for a, b in zip(ctx.offsets, own, strict=True))
        contract = el.attrs.get("contractname", "")
        self._walk(
            elements,
            ctx.into(
                el.attrs.get("componentname") or template_id,
                offsets=offsets,
                prefix=f"{ctx.prefix}{contract}." if contract else ctx.prefix,
                widgets=(*ctx.widgets, template_id),
            ),
        )

    def _place_list(self, el: _Element, ctx: _Context) -> None:
        widget_id = el.attrs.get("widgetid", "")
        elements = self.templates.get(widget_id)
        if elements is None or widget_id in ctx.widgets:
            return
        self.placed.add(widget_id)
        count = _num(el.attrs.get("numberofitems", 0))
        step = (
            _num(el.attrs.get("booleanjoinincrement", 0)),
            _num(el.attrs.get("numericjoinincrement", 0)),
            _num(el.attrs.get("stringjoinincrement", 0)),
        )
        contract = el.attrs.get("contractname", "")
        name = el.attrs.get("componentname") or widget_id
        for index in range(count):
            offsets = tuple(o + index * s for o, s in zip(ctx.offsets, step, strict=True))
            prefix = f"{ctx.prefix}{contract}.Items[{index}]." if contract else ctx.prefix
            self._walk(
                elements,
                ctx.into(
                    f"{name} item {index + 1}",
                    offsets=offsets,
                    prefix=prefix,
                    widgets=(*ctx.widgets, widget_id),
                ),
            )

    def _element(self, el: _Element, ctx: _Context) -> None:
        object_name = el.attrs.get("componentname") or el.attrs.get("id") or el.tag
        by_object: dict[int, dict[str, object]] = {}
        for attr, value in el.attrs.items():
            if not (el.tag.startswith("ch5-") or attr.startswith("data-ch5-")):
                continue  # plain HTML elements only act on data-ch5-* attributes
            spec = sig.BY_TAG.get((el.tag, attr)) or sig.DEFAULT.get(attr)
            if spec is None or not value.strip():
                continue
            direction, kind = spec
            for obj, join in self._resolve(value, attr, direction, kind, ctx, object_name):
                roles = by_object.setdefault(obj, {"other": []})
                role = _role(attr, direction, kind)
                if role is not None and role not in roles:
                    roles[role] = join
                else:
                    roles["other"].append((attr, join))  # type: ignore[union-attr]
        for obj, roles in by_object.items():
            other = tuple(roles.pop("other"))  # type: ignore[arg-type]
            self.controls.append(
                Control(
                    ctx.page,
                    " > ".join(ctx.trail),
                    el.tag,
                    object_name,
                    _label(el.attrs),
                    other=other,
                    offsets=ctx.offsets,
                    smart_object=obj,
                    **roles,  # type: ignore[arg-type]
                )
            )

    def _resolve(
        self, value: str, attr: str, direction: str, kind: str, ctx: _Context, where: str
    ) -> list[tuple[int, int]]:
        """(smart object, join) for an attribute value, or [] after noting why not."""
        value = value.strip()
        if _JOIN_NUMBER.fullmatch(value):
            join = int(value)
            return [(0, join + ctx.offsets[_KIND_INDEX[kind]])] if join else []
        if _TEMPLATE_VAR.search(value):
            # A list item template. With a contract, each item's signals are
            # listed in the contract and reported from there; without one, the
            # numbering is decided at run time and is not guessed at here.
            if not self.contract.signals:
                self._note(ctx, where, attr, value, "a list template, numbered at run time")
            return []
        if value == CONTRACT_ENABLED and self.contract.signals:
            # Construct's marker for "this component's joins come from the
            # contract under its contractname"; they are reported from there.
            return []
        name = ctx.prefix + value
        found = self.contract.lookup(name, direction, kind)
        if found is None:
            other = sorted({s.kind for s in self.contract.by_name.get(name, [])})
            if other:
                reason = f"in the contract as {' and '.join(other)}, but this attribute is {kind}"
            elif self.contract.signals:
                reason = "not in the contract"
            else:
                reason = "no contract to look it up in"
            self._note(ctx, where, attr, name, reason)
            return []
        self.used.add(found)
        return [(found.smart_object, found.join)]

    def _note(self, ctx: _Context, where: str, attr: str, value: str, reason: str) -> None:
        place = "".join(f" > {t}" for t in ctx.trail[1:]) + f", {where}"
        pages = self.unresolved.setdefault((place, attr, value, reason), [])
        if ctx.page not in pages:
            pages.append(ctx.page)

    def _contract_only(self) -> None:
        """Contract signals no HTML attribute pointed at, so none goes missing from the draft."""
        page = "(contract only)"
        for s in self.contract.signals:
            if s in self.used:
                continue
            role = _role("", s.direction, s.kind)
            roles = {role: s.join} if role else {}
            other = () if role else ((f"{s.direction} {s.kind}", s.join),)
            group = s.name.rsplit(".", 1)[0] if "." in s.name else page
            self.controls.append(
                Control(
                    page,
                    group,
                    "contract signal",
                    s.name,
                    s.name,
                    other=other,
                    smart_object=s.smart_object,
                    **roles,  # type: ignore[arg-type]
                )
            )


def _role(attr: str, direction: str, kind: str) -> str | None:
    """Which Control field a join fills; None sends it to `other`."""
    if kind == sig.DIGITAL:
        if direction == sig.EVENT and attr in (
            "",
            "sendeventonclick",
            "sendeventontouch",
            "buttonsendeventonclick",
        ):
            return "press"
        if direction == sig.STATE and attr in (
            "",
            "receivestateselected",
            "receivestatevalue",
            "buttonreceivestateselected",
        ):
            return "feedback"
        return None
    if kind == sig.ANALOG:
        return "analog" if attr in ("", "receivestatevalue", "sendeventonchange") else None
    if direction == sig.STATE and attr in (
        "",
        "receivestatelabel",
        "receivestatescriptlabelhtml",
        "receivestatevalue",
        "buttonreceivestatelabel",
        "data-ch5-textcontent",
        "data-ch5-innerhtml",
    ):
        return "serial"
    return None
