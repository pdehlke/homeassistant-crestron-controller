# Pattern: cursor-zone audio

Some Crestron programs drive multi-room audio through a **zone cursor**: the panel picks a room,
and one shared set of buttons and feedback joins then acts on whichever room is picked. This
project does not support that pattern in version 1
([ADR 0009](../adr/0009-cursor-zone-audio-deferred.md)). This page describes it, as observed on
the one system it was built against privately, so you can recognise it in your own panel project
and know what you would be taking on.

Everything below was observed on one AADS-based system. Treat each behaviour as something to test
on yours, not as how Crestron audio works in general.

## How a cursor program works

Lighting on that system gave every load its own join, and pressing one cold, with nothing selected
first, worked. Audio did not. The audio pages had:

- one zone-select join per room, which moves the cursor,
- one set of source buttons, volume up, volume down, mute and power-off joins, which act on the
  cursor's room,
- a serial join carrying the name of the cursor's room, and an analog join carrying its volume
  (0 to 65535).

So a room's state is readable only while the cursor is on it. Six rooms cannot be live at once from
one slot, however the entities are arranged.

## Behaviours the private implementation had to handle

| Behaviour | Consequence |
| --- | --- |
| The cursor is per slot. Four panel slots registered read-only reported four different cursors, and moving one slot's cursor did not move the others. | Home Assistant gets a cursor of its own and does not drag the wall panels around. Sharing a live panel's slot would mean fighting a person for its cursor. |
| A cursor move blanks the per-room digital joins for about 60 ms before repopulating them. | Anything read inside that window reports a dead room with full confidence. Wait, then confirm. |
| The room-name serial updates as soon as the cursor lands. | Use it to confirm the cursor really moved before attributing any reading to a room. |
| The volume analog is not resent when the new room's level equals the old room's. | Clearing a cached value before moving and waiting for a fresh one waits forever in the equal-level case. Wait for any analog traffic, with a grace period. |
| Selecting a source powers the room on. There is no separate power-on join. | "Turn this room on" has to choose a source and a level. |
| One source applied a volume preset on selection (exactly 40% of full scale); others did not. | Always set volume after source, and re-read the level rather than assuming it survived. |
| Volume is hold-to-ramp. About 6570 units per second of hold, linear in both directions; a 0.12 s tap moves about 800. | Setting a level means holding up or down for a computed time, then correcting against the feedback. |
| Two direct analog writes to the volume join produced no response. | Not proof (the project offered no analog control to test the encoding against), but no panel could set a level numerically either. |
| Power-off cleared the room's remembered source, and sometimes zeroed its level. | There is no "off, remembering the source" state to return to. |
| Per-source display-page joins stayed high as the cursor moved to other rooms. | They are slot state, not room state. Reading a room's source from them made every room report the same source. The source buttons' own feedback joins were the per-room truth. |
| Audio was a gated subsystem with its own entry button, and its pages reused join numbers that meant lights on the lighting pages. | Audio and lighting can share one slot only by taking turns, under a lock. |
| Volume and room name survived four round trips between subsystems. | A paused ramp can resume after a lighting command. |

## How the private integration carried it

- One slot time-sliced between Lights and audio, under the same lock lighting writes take, with no
  single operation allowed to hold that lock for more than about one second. A lighting command
  queued behind audio waited at most that plus one entry to Lights (measured worst case 1.09
  seconds, budgeted 1.9).
- An idle return sent the slot back to Lights five seconds after the last audio operation, because
  while the slot is in audio, lighting changes made at wall keypads are invisible.
- Per room: a power switch, a source select, a volume number and a mute switch, backed by a cache of
  each room's last reading and when it was taken. A `media_player` per room was rejected because
  its volume is normalised 0.0 to 1.0 with no minimum or step, and that system's speakers were
  inaudible below about 80% of full scale.
- Nothing polled. Walking six rooms took a few seconds of a slot that lighting shares, so rooms were
  read at startup, on demand, and by a refresh button.

## What you can do in version 1

Without cursor support you can still read the cursor's room and its volume, and press individual
buttons:

- a `sensor` on the room-name serial and another on the volume analog, both with
  `subsystem: audio` (the gated example in `examples/join-map-gated.yaml` has exactly these),
- a `button` per zone-select join and per source join, if writes are on and those joins are safe,
- `momentary` switches for buttons that have no feedback.

What version 1 will not do is confirm a cursor move, ramp volume to a target, or present one entity
per room. Those need the logic above, and that logic was written for one program. If you build it
on top of this project, measure every number on this page on your own system first.
