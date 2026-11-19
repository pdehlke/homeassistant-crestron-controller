# Reading and choosing from lists

Some touch-panel screens show lists: the music sources you can choose from, the rooms in the house,
a playlist, a set of saved scenes. Crestron calls each list a
[SmartObject](../concepts/glossary.md#smartobject). Home Assistant can read what those lists show,
such as the names of your music sources, which one is playing in each room, or the song a panel
displays, and use it on dashboards and in automations. With writes turned on, it can also choose
from a list, as if you had tapped it on the wall.

> **Not tested on real hardware.** Reading lists and choosing from them have been tested only
> against a simulated processor in this project's test suite. Nobody has yet confirmed that either
> works with a real Crestron system.
> The way lists are sent was worked out by another project,
> [Crestron-CIP-HA](https://github.com/rellis-erigon/Crestron-CIP-HA), which captured it from real
> processors. If you try it, an issue saying whether it worked would help everyone; see
> [what to report](#what-to-report).

If your panels have no lists, you can usually skip this page. The exception is an x60 or x70
panel whose project was built with a contract: its draft puts ordinary buttons and sliders in
SmartObjects too, so everything here about SmartObjects applies to them. See
[how much of your draft depends on SmartObjects](../inventory/panel-project-files.md#how-much-of-your-draft-depends-on-smartobjects).

## What you can and cannot do

You can show a list's text and its on/off signals in Home Assistant: a sensor for an item's name,
a binary sensor for whether an item is selected.

You can also make a drop-down (a `select`) that chooses an item, or a button that presses one, as
described [below](#choosing-from-a-list). This sends commands to your system in a way no one has
yet seen a processor accept, so it starts switched off, like every other command: the link must
have writes turned on, and only the joins you map can be pressed. Try it with someone in the room,
on a panel slot no real panel uses.

## Why lists need their own setting

Every button, slider and label on a panel is numbered, and the join map uses those numbers. A list
is numbered differently: the list itself has a number, and its items are numbered inside the list. Text 11 inside list 3 and text 11 elsewhere on the panel are two unrelated
things. So a join map entry that reads from a list has to say which list, with `smart_object:`.

## Finding a list's number

Run `crestron-controller listen` on your processor (see
[listening to a processor](../inventory/listening-to-a-processor.md)). If any list sent anything, it
prints a line for each one, such as:

```text
SmartObject 3: 12 digital and analog, 8 serial (untested on real hardware)
```

`3` is the list's number. `--draft` writes a draft entry for every list join it saw, already
carrying `smart_object: 3`. `crestron-controller watch` shows a list join that changes as
`o3:d5` (list 3, digital 5) or `o3:s11` (list 3, serial 11).

If you expected a list and see none, and your program is
[gated](../concepts/subsystems.md), the list probably sits in a subsystem that `listen` has not
entered: try again with `--enter`. If it still shows nothing, your processor may send lists in a
way this project does not know about yet, and an issue would help.

## Writing the entries

Add `smart_object:` to a `sensor` or `binary_sensor`. Everything else is as usual:

```yaml
entities:
  - {type: sensor, name: Source 1 name, serial: 11, smart_object: 3}
  - {type: sensor, name: Source 2 name, serial: 12, smart_object: 3}
  - {type: binary_sensor, name: Source 1 selected, join: 1, smart_object: 3}
```

`smart_object:` is a whole number of 1 or more. See the
[join map reference](./join-map-reference.md).

In Home Assistant, each of these entities shows a `smart_object` attribute, and the diagnostics
download lists every list's joins under `smart_objects`.

## Choosing from a list

A `select` shows a drop-down of the list's items and presses the one you choose. For each option,
write down the join that chooses it (`press`), the join that is on while it is the chosen one
(`feedback`, if different), and either a fixed `name` or the serial join that carries its name
(`name_serial`):

```yaml
entities:
  - type: select
    name: Den source
    smart_object: 3
    options:
      - {name: Radio, press: 1}
      - {name: Streaming, press: 2, name_serial: 12}
      - {name: Turntable, press: 3, name_serial: 13}
```

To find those joins, run `crestron-controller watch` and tap each item on a real panel. The digital
join that goes high, written like `o3:d2`, is that item's feedback join. The join to press is often
the same number, which is why `feedback` defaults to `press`, but that is not guaranteed. The
`listen` draft shows which serials carry the item names.

Home Assistant shows the option whose feedback join is on. Choosing an option that is already
chosen does nothing; choosing another presses its join once, and the drop-down then follows the
panel's feedback. It does not press again if nothing happens. If nothing changes, the encoding may
not work on your processor, or the joins may be wrong; please report it either way.

A `button` with `smart_object:` presses one item, for a list of scenes or macros.

Lights, switches and numbers cannot use a list.

Before turning writes on for a link that presses inside a list, check that list's joins for anything
dangerous and add them to its own never-write entries
([write safety](./write-safety.md#the-never-write-list)).

## What to report

If you have a system whose panels use lists, please open an issue with:

- your processor model, which `crestron-controller ipids` prints;
- the `SmartObject` lines that `crestron-controller listen` prints;
- whether the entities you made from them show what the panel shows;
- if you tried choosing from a list, whether the panel followed.

Do not include room names, addresses or anything else that identifies your house.

The reasoning behind how lists are handled is in
[ADR 0012](../adr/0012-smartobject-joins-are-their-own-namespace.md) (reading) and
[ADR 0013](../adr/0013-writing-to-smartobjects.md) (choosing).
