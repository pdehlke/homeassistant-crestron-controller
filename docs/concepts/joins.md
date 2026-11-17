# Joins

A join is one numbered signal between a touch panel and the program on the processor. Everything
Crestron Controller reads or writes is a join, so understanding them is most of understanding the
integration.

## Three kinds

| Kind | Values | Typical use | In a join map |
| --- | --- | --- | --- |
| Digital | 0 or 1 | Buttons, and the feedback that lights a button up | `feedback`, `press_join`, `on_join`, `off_join`, `join`, `also_reports` |
| Analog | 0 to 65535 | Levels: brightness, volume, a temperature reading | `analog`, `brightness.join` |
| Serial | Text | Labels and names the processor fills in on a page | `serial` |

Each kind has its own numbering. Digital join 11, analog join 11 and serial join 11 are three
different signals.

Joins are numbered from 1 in these docs, in join maps, in the command-line tool and in every
Crestron join list. The bytes on the wire count from 0, and the code converts at the boundary, so
you never need to think about that.

## Which direction they go

The same join number usually carries traffic both ways:

- When you tap a button on a panel, the panel sends that digital join high, then low. That is a
  **press**.
- When the program wants the button to light up, it sends the same join high to the panel. That is
  **feedback**.

A button with feedback on its own join is the common case, and why a join map can say just
`feedback: 317` for a light: the code reads join 317 for the state and presses join 317 to change
it. Some panels use separate numbers, such as an "On" button and an "Off" button that each light up
when that state is current. [Press modes](../configuration/press-modes.md) covers how to map those.

On the system this was developed on, the first test press showed feedback staying high after the
press was released 120 milliseconds later. That is how you know the processor is driving the join as
real feedback rather than echoing what was sent.

## A press is not a hold

A press goes high and comes back low quickly. If it stays high, the program sees a finger held on
the button, and a held button can ramp a dimmer up or down, or on some programs save the current
scene over a preset. Crestron Controller holds each press for 0.12 seconds by default
(`timing.press_hold_seconds`) and makes sure every press it starts is released, even if the
connection drops or Home Assistant shuts down in the middle of it.

## The registration dump and later changes

After Crestron Controller registers, it asks the processor for everything, and the processor sends
the current value of every join it reports to that slot, ending with an end-of-query marker. After
that it sends only changes. Crestron Controller keeps a copy of every value, which is what entities
read from and what the diagnostics download lists.

A join the processor never mentioned after a full dump is treated as low. That has held on every
system observed so far, but it is an observation, not a rule from Crestron.

## One load, several joins

A load often appears on more than one panel page. On the system this was developed on, one
light had buttons on five different pages, each with its own join number, and pressing one sent all
five high at the same instant. In a join map you pick one join as the `feedback` (and normally the
one to press) and list the rest under `also_reports`. A change on any of them updates the entity.

Scene buttons behave like loads too. On that system, two "everything off" scene buttons cleared
whenever any light came on, because the program kept their feedback honest. You will see those move
whenever you switch a light; they are not your light.

## One join number, several meanings

Programs reuse join numbers. Two things to know:

- Across sections of the program. In a program with [gated subsystems](./subsystems.md), digital
  join 310 can be a light in the Lights section and a media transport button in the Audio section.
  Crestron Controller files every join under the subsystem that reported it, which is why the join
  map has a `subsystem:` key on each entity.
- Across unrelated functions. On the system this was developed on, a block of about twenty
  digital joins was shared between lighting pages and an alarm keypad page, including the keypad's
  panic buttons. Pressing the "wrong" light join could have meant pressing an alarm button. This is
  the reason for the [never-write list](../configuration/write-safety.md).

Nothing on the wire tells you a join's meaning. The processor sends numbers; meaning comes from the
panel's project file, from watching what changes when you press a keypad, or from someone who knows
the program. See [the inventory overview](../inventory/inventory-overview.md).

## Reading a join is always safe

Receiving a join changes nothing. Feedback for a light can arrive on a join that must never be
written, and Crestron Controller reads it happily: a join on the never-write list may still appear
in `also_reports`, a `binary_sensor` or a `sensor`. Only writes are restricted.

## Analog and serial writes

Crestron Controller can write analog joins (for a writable `number` or a dimmable light) and the
protocol code can encode serial writes. The encodings come from
[klenae/python-cipclient](https://github.com/klenae/python-cipclient) and have never been seen
accepted by a processor in this project: the analog joins on the system this was developed on were
feedback only. Registration, heartbeats, the update request, every digital encoding, and analog and
serial reads were all observed on real hardware. See [the CIP wire
format](../protocol/cip-wire-format.md).
