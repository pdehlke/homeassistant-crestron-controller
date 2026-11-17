# Case study: a house with two control processors

This project grew out of one real house. That house had two Crestron
[control processors](../concepts/glossary.md), each running its own program, and controlling it
from Home Assistant needed two [links](../concepts/glossary.md), one to each. This page tells that
story because the situation is more common than a newcomer expects, and because finding out which
processor owns what is the first job on any system, before a single light is mapped.

Site details are removed. The model names are kept on purpose: the equipment is ordinary, and
seeing real model names helps you recognise the same arrangement in your own rack.

## What was in the house

Two boxes ran programs.

The first was an **AADS**, Crestron's Adagio audio distribution system. It is an amplifier and
audio matrix, and it also has a control processor built in. In this house that built-in processor
ran the main program: lighting and room-by-room audio, driven from
several TSW-752 touch panels on the walls. The touch panels talked to the AADS over the network.

The second was an **MC2E**, a separate control processor running an older program from the late
2000s, written for an earlier phase of the house. It owned the Cresnet bus (Crestron's wired
device bus) that the lighting dimmer modules and the wall keypads hang off. Its program also
defined one XPanel slot (an IP-ID set aside for Crestron's software touch panel) that reached the
lights in a single room.

The two processors were joined by an Ethernet intersystem link, so a press on an AADS touch panel
travelled AADS, then intersystem link, then MC2E, then Cresnet, then dimmer. That chain matters
later: it is why the wall keypad LEDs updated correctly when Home Assistant switched a light
through the AADS. The MC2E's keypad logic sits downstream of the point where the press entered.

The lesson for a newcomer: **the processor a touch panel talks to is not necessarily the
processor that drives the load.** You have to find out both.

## How the owner found out which processor owned what

None of this came from program source code. The owner did not have it. Everything came from
read-only console commands, the panels' own project files, and the data the processors sent when
something registered.

| Question | How it was answered |
| --- | --- |
| Which boxes on the network are processors at all? | A processor answers on CIP (TCP 41794) and on its console ports (23 and 41795). The console banner names the model. |
| Which IP-IDs does each processor's program expect, and which are online? | `IPTABLE` on each processor's console. The AADS listed four touch panels, two app slots, an audio source and the intersystem link. The MC2E listed the XPanel slot and the same intersystem link. |
| Which physical panel holds which IP-ID? | `WHO` on the console shows live connections with their addresses. After the bridge registered on a borrowed slot, the processor's own state dump named the room that slot belonged to, in a serial join. |
| What is on the Cresnet bus, and whose bus is it? | `REPORTCRESNET` on each processor. The MC2E's bus held all the dimmer modules and all the keypads. The AADS's bus held one unrelated I/O module. |
| Which joins does a touch panel use, and for what? | The panel's own compiled project file, fetched from its console. It names every page, button and join number. See [panel-project-files.md](../inventory/panel-project-files.md). |
| Which joins does the XPanel slot reach? | The MC2E's compiled program was retrieved and read. Because that program was searched and found to contain no alarm, security or access control of any kind, its press joins were also pressed one at a time and the results watched. See [lesson-alarm-joins.md](lesson-alarm-joins.md) for why that was acceptable on that processor and nowhere else. |

`crestron-controller ipids` runs exactly the read-only part of this for you (`VER` and `IPTABLE`),
and the rest of the inventory tooling is described in
[inventory-overview.md](../inventory/inventory-overview.md). The broader procedure is in
[finding-your-control-processor.md](../getting-started/finding-your-control-processor.md).

## Why one link was not enough

The AADS panel project was the obvious place to start. A touch panel slot on the AADS reached
every lighting load in the house by name, and borrowing one (unplugging that panel and registering
in its place) gave read and write access to all of them. So why keep a second link to the MC2E?

Because of the alarm keypad. The panel project also contained an alarm keypad page, and that page
reused a block of about twenty digital joins that a lighting page in one room also used. One
number meant a light on the lighting page and a keypad button on the alarm page. Some of those
keypad buttons were emergency buttons. The panel project has a separate subsystem-entry button for
alarm and for lights on its home page, and the AADS was believed to decide which meaning applied
by which subsystem the panel had entered, but that was inferred from the project and never
confirmed against the program. The only way to confirm it would have been to press unidentified
joins on the processor that carried the alarm interface. That was rejected outright, and the whole
block, plus the alarm subsystem's entry button, was treated as never writable.

Most loads with a button inside that block also appeared on another page, outside it. Those were
pressed through the safe alias and read on either join. A few loads did not: their only buttons in
the whole panel project sat inside the alarm block. Every page and every load button was walked to
confirm that.

The MC2E's XPanel slot reached exactly those loads, and the MC2E's program had no alarm in it. So
the house got a second link: AADS for almost everything, MC2E for the few loads the AADS could not
safely reach. A second TCP connection was a small price.

The rejected alternatives, for the record:

| Option | Why not |
| --- | --- |
| Confirm the subsystem gating, then write the shared block on one link | Confirming it means pressing unknown joins next to an alarm. |
| Hire a programmer to put those loads on safe joins | Correct at the source, but it needs Crestron tooling and the program source, and every later change costs another visit. |
| Leave those loads out of Home Assistant | They were real, everyday lights. |

## What two links cost

Two independent connection lifecycles, two reconnect loops, and two connectivity sensors. A load
is unavailable when its own link is down even if the other link is up. In this project that maps
directly onto two config entries, each with its own join map: a gated map for the AADS (with
`subsystems:` and a `never_write:` list covering the alarm block) and a simple map for the MC2E.
See [multiple-processors.md](../configuration/multiple-processors.md) and the two files in
`examples/`.

## What the failure split taught

Twice in the first two months, everything on the AADS link stopped working while the MC2E's loads
kept working.

The first time, a power cut restarted the AADS program and cleared a subsystem latch the bridge
had been relying on without knowing it. The wall keypads kept working too, because they are
Cresnet devices on the MC2E and never touch the AADS. See
[post-mortem-subsystem-latch.md](post-mortem-subsystem-latch.md).

The second time, the AADS's address changed overnight. The bridge's slot had been changed the day
before, so the slot was the obvious suspect. It was ruled out without opening a log, by the split
itself: lighting and audio shared the AADS link, the MC2E was a separate connection to a separate
processor, and any explanation that blamed the slot would also have had to explain why the other
connection was untouched. See
[post-mortem-dhcp-address-change.md](post-mortem-dhcp-address-change.md).

The sentence worth keeping is the owner's: **"All AADS loads dead, MC2E fine" is a statement about
the link, not the slot.** Whatever is shared by everything that broke, and not shared by anything
that kept working, is where to look first. In a two-processor house that is almost always one
link: its address, its connection, or the processor at the far end of it.

## What to check on your own system

- Run `IPTABLE` on every processor you can find, not only the first one. A device in someone
  else's IP table may itself be a processor.
- For each touch panel, find out which processor it registers with. For each load you care about,
  find out which processor's bus or program actually drives it. They may differ.
- Read the panel project before writing anything. If a safety page (alarm, gate, door) shares join
  numbers with a lighting page, put the whole shared block on the `never_write` list and look for
  aliases. See [write-safety.md](../configuration/write-safety.md).
- If one link fails and another does not, start with what the failed link has to itself.
