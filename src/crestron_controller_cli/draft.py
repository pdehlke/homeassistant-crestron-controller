"""Turn a Project into a CSV inventory, a draft join map, and a short summary.

Project files are untrusted, so everything taken from one is quoted or cleaned
on its way into the output; see _q and _finish.
"""

from __future__ import annotations

import csv
import io
import json
import re
import textwrap
from dataclasses import dataclass, field

from .project import ANALOG, DIGITAL, SERIAL, Control, Project

JOIN_MAP_DOC = "docs/configuration/join-map-reference.md"
_UNRESOLVED_SHOWN = 20

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
    """Join draft lines, cleaning every comment line of characters that could end it early.

    This is the last point before the draft is written, and it relies on one
    rule: a line that is not a comment holds only fixed text, integers, and
    strings passed through _q. Text from a project file must never reach such
    a line any other way, or a crafted label could add YAML of its own.
    """
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

    @property
    def key(self) -> tuple[str, int, int]:
        """What makes two buttons the same entity: one join, of one kind, in one SmartObject."""
        return (self.kind, self.join, self.smart_object)


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
            new = _Candidate(kind, join, c.smart_object, c)
            cand = found.setdefault(new.key, new)
            if cand is new:
                continue
            if _better_name(c, cand.first):
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


def draft_join_map(project: Project, source: str = "a panel project") -> str:
    """Render the draft join map as commented YAML."""
    lines = _HEADER.format(source=source, join_map_doc=JOIN_MAP_DOC).splitlines()
    if project.panel_type:
        lines.insert(1, f"# Panel type: {project.panel_type}")
    for caveat in project.caveats:
        lines += ["#", *_wrap_comment(caveat)]
    if project.unresolved:
        lines += [
            "#",
            f"# {len(project.unresolved)} join attributes name a signal this tool could not turn",
            "# into a join number. They are not in this draft:",
        ]
        for line in _unresolved_shown(project):
            lines += _wrap_comment(line, indent="  ")

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
        label_keys.setdefault(cand.label, set()).add(cand.key)
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


def _unresolved_shown(project: Project) -> list[str]:
    """The unresolved attributes worth printing, so a broken project cannot bury the output."""
    shown = project.unresolved[:_UNRESOLVED_SHOWN]
    rest = len(project.unresolved) - len(shown)
    return [*shown, f"... and {rest} more"] if rest else shown


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
        out += [f"  {line}" for line in _unresolved_shown(project)]
    for caveat in project.caveats:
        out += textwrap.wrap(caveat, 96, break_long_words=False)
    return "\n".join(_clean(line) for line in out)
