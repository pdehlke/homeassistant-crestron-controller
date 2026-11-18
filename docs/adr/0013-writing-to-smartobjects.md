---
status: accepted
---

# Writing to SmartObjects

Builds on [ADR 0012](./0012-smartobject-joins-are-their-own-namespace.md), which made SmartObject
joins their own namespace for reading. This lets Home Assistant press a join inside a SmartObject:
a list item, from a `button` or from the new `select` entity
([issue #4](https://github.com/pdehlke/homeassistant-crestron-controller/issues/4)).

## The encoding

A press inside a SmartObject is the ordinary digital press record wrapped in a SmartObject record
addressed to the object, in a DATA frame: `smart_object_packet()` and `smart_digital_packet()` in
`protocol.py`, following rellis-erigon/Crestron-CIP-HA's `pack_smart_object()`. Nobody has seen a
processor accept one, rellis included, whose own README says writes have not been tested against
live hardware. Like analog and serial writes, it is implemented and off by default, and every
user-facing document that mentions it says so.

## The policy

The rules of [ADR 0003](./0003-listen-only-by-default-with-allow-and-deny-lists.md) apply unchanged,
with the object as part of a join's identity:

- `WritePolicy` holds a separate allow list and never-write list per SmartObject, and `check()`
  takes the object. Object 3's digital 5 and the program's digital 5 are never confused in either
  direction: denying one says nothing about the other.
- The allow list is still derived from the join map, never written by hand. A `button` or `select`
  with `smart_object:` adds its press joins to that object's list.
- The never-write list names object joins under `never_write.smart_objects`, keyed by object
  number.
- Every object press goes through `check()` inside `CipClient._press()`, at the last point before
  the socket, with the same release guarantee as any press.
- No new CLI command presses anything ([ADR 0007](./0007-no-join-scanning-in-the-cli.md)).

## The select entity

```yaml
- type: select
  name: Den source
  smart_object: 3
  options:
    - {name: Radio, press: 1}
    - {press: 2, feedback: 12, name_serial: 22}
```

- Each option names the digital join pressed to choose it and the digital join that reports it,
  `feedback`, which defaults to the press join.
- An option is labelled by the text of its `name_serial`, once the processor has sent some, else by
  its `name`, else by its place in the list. Home Assistant needs distinct labels, so a repeated
  label gets a number.
- The current option is the one whose feedback is high. With none high, or more than one, the
  select reports no current option rather than guessing.
- Before its subsystem has been entered, the select is unavailable, as every other entity is.
- Choosing an option enters the subsystem, does nothing if that option is already the current one,
  and otherwise presses its join once. It does not wait for feedback or retry.
- `smart_object` is optional, so a select can also be built from the program's own buttons.

## Considered options

| Option | Why not |
| --- | --- |
| Assume Crestron's standard join layout for list SmartObjects, so a select needs only an object number and an item count | The layouts are not documented anywhere this project has read, rellis's captures show item text on serials 21 and 31 rather than from 1, and a wrong assumption would press the wrong join. Naming every join is longer but cannot press something the user did not write down. |
| Confirm a choice by waiting for its feedback and retrying, as lights do | A light retries because a toggle press can be undone by the next one, so the state has to be read back. Pressing a list item is not undone by pressing it again, and the encoding is unverified: retrying would repeat a write that may be wrong, and hide the failure. |
| Press even when the option is already current | Some lists may treat pressing the selected item as a toggle or a deselect. Skipping it is harmless if they do not. |
| Report the first high option when several are high | Several high means the joins mapped are not a one-of-many list, or the map is wrong. Showing no choice makes that visible. |
| Let lights, switches and numbers name a SmartObject too | Nothing has needed them, and each widens what an unverified encoding can write. They can be added when a real list needs them. |
| One combined allow list keyed by `(kind, object, join)` | The same result, but it would change every existing caller and test of the policy. Keeping the program's lists where they were and adding per-object lists beside them leaves ordinary writes exactly as before. |
| A CLI option to press a list item | `listen --enter` exists because an inventory needs one entry press; nothing in an inventory needs a list press. |

## Consequences

- A link with writes off sends nothing into a SmartObject, whatever its join map says.
- `crestron-controller check` prints each SmartObject's allow and never-write lists, marked
  untested.
- Real verification needs a program that accepts list presses from a panel, tested with someone
  present, on an IP-ID no real panel uses.
