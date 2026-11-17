# Subsystems

Some Crestron programs split a touch panel's world into sections, usually called subsystems, such as
Lights, Audio, Climate or Security. On many programs that is only a matter of which page is on the
screen. On some it is more: the processor itself refuses to tell a slot anything about a subsystem
until the slot has entered it. These docs call that a **gated subsystem**.

If your program is not gated, you can skip this page. Crestron Controller's subsystem handling is
off unless the join map declares `subsystems:`.

## What gating looks like

On the system this was developed on, a registered panel slot that had not entered Lights received a
home-page menu and nothing else. It got no lighting joins at all, and every lighting join pressed at
it was silently ignored. After the slot pressed the home page's Lights button, the processor sent
that slot the lighting joins and began acting on lighting presses.

The state that says "this slot is in Lights" lives in the running program. The processor kept it
across disconnects and reconnects, which is how that system ran for five weeks without anyone
noticing the gate: the unplugged panel whose slot was borrowed had been left inside Lights. A power
cut restarted the program, cleared that state, and every lighting entity went dead while the wall
keypads kept working. See [the subsystem latch
post-mortem](../case-study/post-mortem-subsystem-latch.md).

The same program reused join numbers between subsystems. One digital join was a light inside Lights
and an audio menu button inside Audio. A slot is in exactly one subsystem at a time, so knowing
which one it is in decides what a press means.

## How to tell whether your program is gated

- Listening shows almost nothing. A listen-only link, or `crestron-controller listen` with no
  `--enter`, receives a few dozen joins that never change when you switch lights at a keypad.
- The panel's home page is a menu. If the touch panel's first page is a row of buttons such as
  Lights, Audio and Climate, and nothing else, those may be entry joins. A TSW x52 panel's project
  file names its home page and its buttons; `crestron-controller panel parse` lists likely entry
  joins. See [panel project files](../inventory/panel-project-files.md).
- Pressing the entry join changes everything. `crestron-controller listen --enter JOIN
  --allow-press` presses that one join and reports what arrived. On a gated program a burst of joins
  arrives after the press. Only do this with a join you have identified from the project file, never
  by guessing.

## How Crestron Controller handles a gated program

When the join map declares subsystems, the link:

1. Registers and receives the dump, which is only the menu.
2. Presses the **default** subsystem's entry join (only if writes are on), then collects the
   **entry dump**.
3. Re-sends the update request, the **re-poll**, to get the full state with an end marker.
4. Is then **synced**.

Before every write, it makes sure the slot is in the subsystem the entity belongs to, entering it
first if not. One lock covers the entry and the press together, so nothing can move the slot between
them. After a slot has sat idle in another subsystem for `idle_return_seconds`, it is sent back to
the default one, so changes made at keypads in the default subsystem stay visible.

Every received join is filed under the subsystem the slot was in when it arrived. An entity reads
only its own subsystem's joins.

### Entry dumps are partial

An entry dump does not always contain every join that is high. On the system this was developed on,
one logged entry left out seven joins that were high, and rebuilding state from that dump published
a lit light as dark. So Crestron Controller merges an entry dump into what it already knows and
never treats a missing join as off. The re-poll then fills in the gaps. The cost is that a light
switched off at a keypad while the slot was in another subsystem can read stale until the next
change corrects it; a stale reading was judged better than a wrong one. See [ADR
0006](../adr/0006-entry-dumps-merged-never-rebuilt.md) and [the partial dumps
post-mortem](../case-study/post-mortem-partial-entry-dumps.md).

### Entry dumps end in silence

An entry dump has no end marker, so the only way to know it is finished is that the processor goes
quiet. `quiet_seconds` sets how long that silence must be, and it must be longer than the largest
gap between two frames inside one dump, or the dump is declared complete halfway. The dump also
arrives in bursts, so a minimum collection time (`timing.entry_min_seconds`) stops the window
closing between bursts. [Subsystem gating](../configuration/subsystem-gating.md) explains how to
measure your own.

### Listen-only links never enter

Pressing an entry join is a write. A listen-only link refuses it like any other write, so it comes
up synced with no subsystem entered, and every entity in a gated subsystem shows **unavailable**.
That is deliberate: the processor has said nothing about those joins, and showing them as off would
be confidently wrong.

### Courtesy actions

A program can do something on its own when a slot enters a subsystem. On the system this was
developed on, entering Lights from some panel slots switched on a light in that panel's room. CIP
Panel enters the default subsystem at every connect, reconnect and restart, and after every idle
return, so a courtesy action would happen each time. Code cannot prevent it; choose a slot whose
entry does nothing. See [choosing an
IP-ID](../getting-started/choosing-an-ip-id.md#step-3-check-what-entering-the-slot-does).

### An unconfirmed press re-enters

If a press to a light in a gated subsystem gets no confirmation, Crestron Controller forgets which
subsystem the slot is in, so the retry presses the entry join again first. If something cleared the
processor's state without dropping the session, that makes it recoverable instead of permanent.

## Options that were rejected

- Pressing the entry join even in listen-only mode. It would make gated entities show state
  immediately, but it is a write, and the whole point of listen-only is that nothing is written
  until you have said what is safe.
- Rebuilding a subsystem's state from each entry dump. Simpler, and wrong on real hardware, as
  above.
- Holding one subsystem permanently and ignoring the rest. It would avoid all the switching, but
  on the system this was developed on, lighting and audio both lived behind gates on one slot, and
  giving each its own slot would have meant taking a second touch panel out of service.
- Always gating. Most programs are not gated, and the machinery adds entry presses a program
  does not expect. It runs only when the join map declares subsystems.

Configuration details are in [subsystem gating](../configuration/subsystem-gating.md).
