# How it works

CIP Panel makes Home Assistant pretend to be one of your Crestron touch panels. This page explains
what that means, from the wire up, without assuming you have used Crestron software. Terms in bold
are defined in the [glossary](../concepts/glossary.md).

## The pieces of a Crestron system

A Crestron installation has one or more **control processors**. A processor runs the **program**,
which an installer wrote in Crestron's own tools. The program decides everything: which button
switches which light, what a scene does, what the audio system plays. The processor is the brain.

Everything a person touches is a **control point**: wall keypads, touch panels, remotes. None of
them decide anything. A keypad wired to the processor's Cresnet bus reports "button 3 pressed" and
lights the LEDs it is told to light. A **touch panel** on the network does the same thing with a
screen. When you tap a light button on a panel, the panel tells the processor "join 317 went high", and
the program decides what that means.

A **join** is one numbered signal between a panel and the program. There are three kinds:
**digital** (on or off, used for buttons and their feedback), **analog** (a number from 0 to
65535, used for levels) and **serial** (text, used for labels). [Joins](../concepts/joins.md) has
the details.

## How a touch panel talks to the processor

A networked touch panel opens a TCP connection to the processor on port 41794 and speaks
**CIP** (Crestron-IP). It identifies itself with an **IP-ID**, a one-byte address the program has
set aside for that panel. The processor answers, and then:

1. The panel asks for everything, and the processor sends the current value of every join it
   reports to that IP-ID. This is the **registration dump**, and it ends with an explicit
   end-of-query marker.
2. From then on, whenever something changes (a light switched at a wall keypad, a scene run from
   another panel), the processor sends the new value of the affected join.
3. When someone presses a button on the panel, the panel sends that join high, then low. The
   program acts on it.
4. Both sides send small heartbeat frames to keep the session alive.

The processor keeps a table of which IP-IDs its program defines and which are connected right now.
An IP-ID that is not in the program's table cannot register at all.

## What CIP Panel does

CIP Panel registers with the processor under the IP-ID of a panel slot that nothing else is using:
usually a panel that was unplugged, or a software panel slot (an XPanel or app slot) that was never
used. From the processor's point of view, that panel has simply come back online.

Then it does what the panel would do:

- It receives the registration dump and every change after it, and keeps a copy of every join.
- It turns the joins you list in a [join map](../configuration/join-map-reference.md) into Home
  Assistant entities: lights, switches, binary sensors, buttons, sensors and numbers.
- When you turn a light on in Home Assistant, it presses the join a person would press on the
  panel.

Nothing is installed on the processor and the program is not changed. This also means Home
Assistant can only see and do what the program already lets a panel see and do. If no panel page
shows a load, CIP Panel cannot reach it.

## The safety model

Crestron programs reuse join numbers, and on some systems a join that looks spare is wired to an
alarm keypad's panic button. Nothing on the wire says which joins are dangerous. So:

- A new link is **listen-only**. It reads every join and writes none, not even the home-page
  button that a gated program needs pressed.
- When you turn writes on, Home Assistant can write only joins that an entity in your join map
  writes, plus the entry joins of declared subsystems. This **allow list** is worked out from the
  join map; you never write it by hand.
- Your **never-write list** wins over everything. It is checked in the CIP client at the last
  moment before bytes reach the socket, so no code path can get around it.

[Write safety](../configuration/write-safety.md) explains each of these and the alternatives that
were rejected.

## Turning toggles into on and off

Most Crestron buttons are toggles: one press turns a light on, the next turns it off. Home
Assistant needs separate on and off commands. CIP Panel bridges that with **discrete synthesis**:
it reads the light's **feedback join**, presses only if the light is not already in the state you
asked for, then waits for the processor to confirm the change. If no confirmation arrives it tries
once more, then reports an error rather than guessing. [Press modes](../configuration/press-modes.md)
covers this and the two other ways to drive a load.

## Gated subsystems

Some programs hide whole sections behind a home-page button. Until a panel presses "Lights", the
processor tells that IP-ID nothing about lights and ignores every lighting button pressed there.
Such programs also tend to reuse the same join numbers in different sections. CIP Panel handles
this if your join map declares `subsystems:`; otherwise none of that machinery runs.
[Subsystems](../concepts/subsystems.md) explains the idea, and
[subsystem gating](../configuration/subsystem-gating.md) the configuration.

## Link health

Each link gets a **Link** connectivity sensor, present even when the join map is empty, so the
first thing you see after setup is proof that Home Assistant reached the processor. If the link
stays down for ten minutes, or the processor refuses the IP-ID, Home Assistant raises a repair.
See [link health and repairs](../troubleshooting/link-health-and-repairs.md).

## Where the code lives

The protocol code is in `custom_components/cip_panel/cipcore/` and imports nothing from Home
Assistant. The `cip-panel` command-line tool uses the same code, so what the tool sees and what the
integration sees cannot drift apart. See
[ADR 0002](../adr/0002-protocol-code-lives-inside-the-integration.md), and
[ADR 0001](../adr/0001-impersonate-a-touch-panel-over-cip.md) for why impersonating a panel was
chosen over the alternatives.

Next: [finding your control processor](./finding-your-control-processor.md).
