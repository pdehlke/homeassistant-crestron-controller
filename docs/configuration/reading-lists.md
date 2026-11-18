# Reading lists

Some touch-panel screens show lists: the music sources you can choose from, the rooms in the house,
a playlist, a set of saved scenes. Crestron calls each list a
[SmartObject](../concepts/glossary.md#smartobject). Home Assistant can read what those lists show,
such as the names of your music sources, which one is playing in each room, or the song a panel
displays, and use it on dashboards and in automations.

> **Not tested on real hardware.** Reading lists has been tested only against a simulated processor
> in this project's test suite. Nobody has yet confirmed that it works with a real Crestron system.
> The way lists are sent was worked out by another project,
> [Crestron-CIP-HA](https://github.com/rellis-erigon/Crestron-CIP-HA), which captured it from real
> processors. If you try it, an issue saying whether it worked would help everyone; see
> [what to report](#what-to-report).

If your panels have no lists, you can skip this page.

## What you can and cannot do

You can show a list's text and its on/off signals in Home Assistant: a sensor for an item's name,
a binary sensor for whether an item is selected.

You cannot change anything through a list yet. Choosing a source or starting a scene from a list
in Home Assistant is planned
([issue #4](https://github.com/pdehlke/homeassistant-crestron-controller/issues/4)), but has not
been built, because no one has confirmed that a processor accepts commands sent that way.

## Why lists need their own setting

Every button, slider and label on a panel is numbered, and the join map uses those numbers. A list
is numbered differently: the list itself has a number, and its items are numbered inside the list,
starting again from 1. Text 11 inside list 3 and text 11 elsewhere on the panel are two unrelated
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

`smart_object:` is a whole number of 1 or more. Lights, switches, buttons and numbers do not accept
it, because they can send commands. See the [join map reference](./join-map-reference.md).

In Home Assistant, each of these entities shows a `smart_object` attribute, and the diagnostics
download lists every list's joins under `smart_objects`.

## What to report

If you have a system whose panels use lists, please open an issue with:

- your processor model, which `crestron-controller ipids` prints;
- the `SmartObject` lines that `crestron-controller listen` prints;
- whether the entities you made from them show what the panel shows.

Do not include room names, addresses or anything else that identifies your house.

The reasoning behind how lists are handled is in
[ADR 0012](../adr/0012-smartobject-joins-are-their-own-namespace.md).
