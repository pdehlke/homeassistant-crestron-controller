# Panel project files

A touch panel does not decide what its buttons do; the processor's program does. But the panel has
to know what to draw: every page, every button, its label, and which
[join](../concepts/glossary.md#join) each button sends and listens on. That information is the
panel's project. Reading it is the safe way to learn a system's joins, because it names them
without pressing anything.

Two kinds of project can be read:

| Panel family | Project file | Support |
| --- | --- | --- |
| TSW x52 (TSW-552, TSW-752, TSW-1052 and related models) | `Environment.xml`, fetched from the panel with `crestron-controller panel fetch` | Tested on a real TSW-752 project. |
| TSW x60 and x70 (TSW-760, TSW-770, TSW-1070 and related models) | An HTML5 project packed as a `.ch5z` file, which you get from whoever programmed the system | **Experimental, and untested on real hardware.** See [x60 and x70 panels](#x60-and-x70-panels-html5-projects). |

`crestron-controller panel parse` turns either file into an inventory and a draft
[join map](../concepts/glossary.md#join-map). If you have not yet found which panel you have, or
where its file is, start with
[finding your touch panel's project file](./finding-your-panel-project.md).

## What a panel project is

Crestron touch panel projects for x52 panels are designed in Crestron's VT Pro-e software and
compiled for the panel. On a TSW x52 panel (TSW-552, TSW-752, TSW-1052 and related models) the compiled project is
an XML file, `Environment.xml`, stored at `\display\swf\Environment.xml` on the panel. It is
UTF-16 text and names every page, button and join number in the clear.

On the system this was developed on, the same project was found on every TSW-752 panel, so one
fetch covered them all. That will not be true of every house: a program can give each panel its
own project. Panels of different models will certainly differ.

## Fetching it

```sh
crestron-controller panel fetch 10.0.0.31 -o Environment.xml
```

Point it at the touch panel's address, not the processor's. The tool connects to the panel's
[CTP console](../concepts/glossary.md#ctp-console) on port 41795, sends `XGETFILE` with the path,
and receives the file by XMODEM over the same connection. It is read-only.

| Option | Meaning |
| --- | --- |
| `HOST` | The touch panel's address. |
| `-o FILE`, `--output FILE` | Where to write the file. Required. |
| `--remote-path PATH` | The file on the panel. Default `\display\swf\Environment.xml`. |
| `--port` | 41795 (the default) or 23. Use 41795: the telnet console on port 23 refuses the transfer ("Command Blocked from this console type"), and telnet would corrupt binary data anyway. |
| `--username`, `--password-env` | For a console that asks for a login. Untested against a real one; see [the processor console](./processor-console.md#logging-in). |

### It is slow

The panel sets the speed, because it reads its storage slowly. On a TSW-752, a 3.5 MB
project took about 705 seconds, roughly five 1 KB blocks a second. The tool warns that it takes
roughly 10 to 15 minutes, and prints progress every two seconds:

```text
  1240 KiB received, 5.0 KiB/s
```

The panel keeps working normally while it sends. When the file arrives the tool reports its size
and time and suggests the next command:

```text
wrote Environment.xml: 3583494 bytes in 705s
next: crestron-controller panel parse Environment.xml -o draft.yaml
```

### When it fails

If the panel turns the request down, the tool prints its refusal and suggests checking the path with
`crestron-controller console HOST --port 41795 DIR \display`. If the transfer is cancelled or the
panel goes silent, the tool reports how many bytes had arrived and writes nothing: a truncated file
reported as success would be the worse outcome after a ten-minute wait. Either way the exit status
is 1. Run it again.

How the transfer works on the wire is in
[the CTP console and file retrieval](../protocol/ctp-console-and-file-retrieval.md).

## Parsing it

```sh
crestron-controller panel parse Environment.xml -o draft.yaml
crestron-controller panel parse Environment.xml --format csv -o inventory.csv
```

| Option | Meaning |
| --- | --- |
| `FILE` | The `Environment.xml` or `.ch5z` to read. The tool tells them apart by their contents, not their names. Nothing touches the network. |
| `-o FILE`, `--output FILE` | Write here. Without it, the result goes to standard output. |
| `--format yaml` | The default: a draft join map. |
| `--format csv` | An inventory of every control that carries a join. |

With `-o`, the tool also prints a summary: the panel type, the home page, and how many controls
with joins each page has. For a `.ch5z` it also lists any joins it could not work out, and reminds
you that the format is experimental. Exit status is 0 on success, 1 if the file cannot be read, and 2 if it is
not a format the parser understands.

On a real TSW-752 project, the parser produced a valid draft of about 260 entities and correctly
flagged the home-page buttons that enter the program's gated subsystems.

### How controls become joins

The parser walks the project the way the panel would draw it:

- Every page and subpage is defined once. A page is a full screen; a subpage is a reusable panel
  that pages place on themselves, sometimes several times. The page the panel shows at startup is
  the **home page**.
- Each page's controls are read in order. A placed subpage is followed into, so its controls are
  listed under every page that places it.
- A control's joins are the properties whose names end in `Join`. The digital press join becomes
  the control's digital join. Its analog feedback join becomes its analog join. Its indirect text
  join becomes its serial join; so does text the processor fills in at run time, which appears in
  the label as a numbered placeholder. Every other join (visibility, enable, mode, a second press
  join, and kinds the parser has not met before) is kept in the inventory and never turned into an
  entity.
- A button has no separate feedback join in this format. Its feedback arrives on its press join.
- Each direction of a directional pad is its own row with its own join.
- Physical buttons on the panel bezel ("hardkeys") are listed too.
- A page's own digital join, which the processor uses to flip the panel to that page, and a placed
  subpage's visibility join are listed in the inventory but not made into entities.
- Subpages that no page places are still listed, under `(unplaced)`.

### The draft join map

The draft follows the same rule as every other draft in this project: **every entry is read-only**.
Digital joins become `binary_sensor` entries and analog or serial joins become `sensor` entries,
named after the label a person sees on the button. A label the processor supplies at run time
appears as its placeholder text or as `[sN]`.

One join on several buttons becomes one entry. One load is routinely on several pages, so that is
normal. The entry takes its name from the first labelled button that carries the join, and a
comment names the other places it appears. When the same label means different joins on different
pages ("Off" on every room page), the page name is added to the entity name. Entries are grouped by
page, home page first and the project-wide hardkeys last, each preceded by a comment giving the
page path and control type:

```yaml
  # ---- page: Lighting --------------------
  # Lighting > Kitchen, Button
  - type: binary_sensor
    id: "pendants"
    name: "Pendants"
    join: 117
```

The header of the file explains how to promote an entry to a `light` once you know what it drives.
See the [join map reference](../configuration/join-map-reference.md) and
[press modes](../configuration/press-modes.md).

### Subsystem-entry candidates

On a program with [gated subsystems](../concepts/subsystems.md), the buttons on the home page are
usually what enter them. The draft's header lists every labelled home-page button as a
**candidate**, in a commented-out `subsystems:` block ready to copy:

```yaml
#   subsystems:
#     default: <the subsystem most entities belong to>
#     entries:
#       lights: {join: 40}    # "Lights", flips the panel to Lighting
#       audio: {join: 41}    # "Audio", flips the panel to Audio
```

Unlabelled home-page buttons are listed separately as less likely. These are candidates and
nothing more: some home-page buttons only navigate. Confirm one with
`crestron-controller listen --enter JOIN --allow-press` after checking it is not on a safety page
([listening to a processor](./listening-to-a-processor.md#on-a-gated-program)). An alarm
subsystem's entry button is on the home page too, and belongs in `never_write`.

### "Also appears as", and why it matters for safety

When a join appears on more than one button, the draft adds a comment:

```yaml
  # also appears as: Zone 7 Bypass on Security
  - type: binary_sensor
    id: "hall_lights"
    name: "Hall Lights"
    join: 218
```

If the other labels describe the same thing (the same light on a room page and an all-lights
page), the join is an ordinary [alias](../concepts/glossary.md#alias). If they describe different
things, the program reuses that join number across [subsystems](../concepts/subsystems.md), and
what pressing it does depends on which subsystem the slot is in.

This is how you spot an alarm collision. On the real TSW-752 project the parser was tried against,
a join reused by an alarm keypad page showed up with an "also appears as" comment naming that page.
On the system this was developed on, a block of lighting joins was shared with an alarm keypad's
buttons, including fire, medical and panic. Before you promote any entry with such a comment:

- Put the alarm page's joins, and the alarm subsystem's entry join, in `never_write`. That list
  wins over everything and is checked at the last moment before anything is sent.
- If the load has another join that does not collide, map that one and list the colliding join
  under `also_reports` only, so it is read and never written.
- If every join for a load collides, consider reaching it through another processor. That is what
  the system this was developed on did for a few lights.

See [write safety](../configuration/write-safety.md),
[multiple processors](../configuration/multiple-processors.md) and
[the alarm joins lesson](../case-study/lesson-alarm-joins.md).

### Join offsets

VT Pro-e lets a page or a placed subpage shift its joins by an offset, so one subpage design can be
placed several times, each copy on its own range of joins. The parser adds up the offsets of every
page and placement on the way down to a control.

Every project this was developed against had all offsets at zero, so that arithmetic has been
tested only against a constructed example, never a real project with non-zero offsets. Wherever an
offset was applied, the draft says so above the entry:

```yaml
  # join offset applied (d+20); verify this number
```

and the CSV fills in its `offsets_applied` column. Check those joins with
[`crestron-controller watch`](./watching-keypads.md) before relying on them.

### The CSV inventory

`--format csv` writes one row per control that carries a join, per page it appears on, with these
columns: `page`, `path`, `control`, `object_name`, `label`, `digital_press`, `digital_feedback`,
`analog`, `serial`, `page_flip`, `other_joins`, `offsets_applied`, `smart_object`. The last is
always empty for an x52 project; for an HTML5 project it is the
[SmartObject](../concepts/glossary.md#smartobject) the joins belong to. It includes every join the draft
leaves out (visibility, page flips, enable joins), which makes it the place to search when you want
to know everywhere a join number is used.

## x60 and x70 panels (HTML5 projects)

> **Experimental, and untested on real hardware.** This reader was built from Crestron's published
> developer packages and from public sample projects found on GitHub. Nobody has yet run it on a
> project taken from a real house, or checked its join numbers against what a real processor sends.
> Check every join it gives you with [`crestron-controller watch`](./watching-keypads.md) before you
> rely on it, and please report how it went; see [open questions](../project/open-questions.md).

Newer Crestron panels, the TSW x60 and x70 families, draw their screens as web pages. Their
projects are written in HTML5, either by hand or with Crestron's Construct design tool, and packed
into a single `.ch5z` file that is loaded onto the panel.

### Getting the file

Ask whoever programmed your system for the `.ch5z` file. Programmers keep it, because it is what
they load onto the panel. It may also be called the panel's project or "UI file".

`crestron-controller panel fetch` is written for x52 panels, and whether an x60 or x70 panel will
hand its project over the same way has never been tried. Crestron's own tools load a `.ch5z` onto
a panel over SFTP and offer no way to download it again.

### Reading it

```sh
crestron-controller panel parse MyProject.ch5z -o draft.yaml
crestron-controller panel parse MyProject.ch5z --format csv -o inventory.csv
```

The commands, options and outputs are the same as for an x52 project. The draft starts with a
comment block marking it as experimental.

### How joins are found

In an HTML5 project each button, slider or label names its joins in its own settings: one for what
it sends to the processor when touched, others for the feedback it shows. The reader collects
those and works out each one's kind (digital, analog or serial) from Crestron's published list of
component settings. A setting can hold a join number, or a name.

- **Join numbers** are used as they are. These are the program's ordinary joins.
- **Names** come from Crestron's Contract Editor, a tool that lets a designer give signals names
  instead of numbers. The project then carries a contract file that turns each name into a join
  number inside a [SmartObject](../concepts/glossary.md#smartobject). The reader looks every name
  up there, and the draft gives those entries a `smart_object:` line. Reading SmartObject joins is
  itself untested on real hardware; see [reading lists](../configuration/reading-lists.md).
- **Signals in the contract that no button names** are listed too, under a page called
  `(contract only)`, so nothing in the contract goes missing.
- **Pages** come from the project's configuration file when Construct made it, with the start page
  first. A hand-written project's pages are its HTML files, starting with `index.html`. A page's
  own visibility join is listed in the inventory, like an x52 page-flip join.
- **Widgets**, reusable pieces placed on several pages, are followed into wherever they are placed,
  so their controls appear under every page that uses them, the same way x52 subpages do.
- **Lists** repeat one widget for each item. With a contract, each item's joins are read from the
  contract, which lists every item separately. Without one, a list item's join is often written as
  a pattern such as `1{{idx}}`, filled in by the panel at run time; the reader reports those
  instead of guessing.
- **Offsets and increments.** A widget placement can shift its joins by an offset, and a list can
  shift each item's joins by a step. The reader applies both, but neither has been seen working on
  a real panel. The draft and the CSV mark every join that was shifted, as they do for x52 offsets.
- **Construct's own screens** (logs, version information, the theme menu) use signals that stay
  inside the panel and never reach the processor, so they are skipped.

Anything the reader could not turn into a join number is listed in the summary and at the top of
the draft, with where it was found and why, for example a name missing from the contract. A widget
used on every page is listed once, with a count of the other pages.

### How much of your draft depends on SmartObjects

Whether a project uses a contract decides how much of its draft rests on SmartObject reading,
which is untested on real hardware. In a project built with a contract, every named signal lives
inside a SmartObject, not only lists: an ordinary button, toggle or slider does too, and Construct
even puts each page's visibility join in a SmartObject of its own. In the public samples this
reader was checked against, nearly every entry in a contract project's draft carried
`smart_object:` (196 of 201 in the largest, and all of them in the others). Projects that use plain
join numbers instead, such as hand-written projects and Construct projects with an empty contract
(including one converted from VT Pro-e), produced no SmartObject entries at all.

So look at your draft. If most entries have a `smart_object:` line, both this reader and
SmartObject reading are unproven for your system, and every entry needs checking with
[`watch`](./watching-keypads.md) before you rely on it. If none do, only this reader is unproven,
and a wrong join will show up in a `watch` check like any other draft's.

### What it cannot read

Some projects are written with web frameworks such as React or Vue. They set their joins from
program code rather than in the page itself, and the only way to learn those joins would be to run
the code. If a project has no joins in its pages and no contract, the reader refuses it and says so.
Use [`listen`](./listening-to-a-processor.md) and [`watch`](./watching-keypads.md) for those panels.

### Where this came from

The archive layout comes from Crestron's `@crestron/ch5-utilities` package, and the list of
component settings and their join kinds from `@crestron/ch5-crcomlib`
([notices](../../THIRD_PARTY_NOTICES.md)). It was then checked against public projects on GitHub:
Construct projects with and without a contract, hand-written ones, a Construct project converted
from VT Pro-e, and framework-built ones. Two of those, published under the MIT licence, are part of
this project's tests.

## Formats that are not supported

The parser understands the TSW x52 `Environment.xml` and, experimentally, the x60/x70 `.ch5z`. It
looks at the file and refuses anything else with a message saying what it appears to be:

| What you have | What the parser says | Why |
| --- | --- | --- |
| A VT Pro-e source project (`.vtz`), or another zip archive that is not a `.ch5z` | Refused as not a `.ch5z` project | A `.vtz` is the designer's working copy, not what the panel runs. Ask for the compiled project, or fetch `Environment.xml` from the panel. |
| A `.ch5z` whose joins are set in program code | Refused; see [what it cannot read](#what-it-cannot-read) | The joins cannot be found without running the code. |
| A loose HTML page | Refused | Pass the whole `.ch5z` instead. |
| XML whose root is not a Crestron VT Pro-e project | Refused | It is not a panel project. |
| XML that declares a DTD | Refused | An x52 project never does, and refusing it closes off entity expansion tricks. |
| A file that is not XML, or never closes its root element | Refused; a truncated file should be fetched again | |

Older panel families use other formats again. Writing a parser for a format without a real file to
test it against would produce drafts that look right and may not be; a confidently wrong join map
is worse than none. If you have a project from another panel family, or an x60 or x70 project the
reader gets wrong, and can share a copy with private details removed, see
[open questions](../project/open-questions.md).

The file as fetched ends with transfer padding after the closing `</Crestron>` tag, which makes it
invalid XML until the tail is cut. The parser cuts it. UTF-8 files, and UTF-16 files without a
byte-order mark (for example after an editor has re-saved one), are accepted too.

## Keep it private

A panel project describes a house in detail: every room, every load, the alarm page. Do not commit
one, or a draft made from one, to a public repository.
