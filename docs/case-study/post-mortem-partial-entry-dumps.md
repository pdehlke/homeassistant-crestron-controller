# Post-mortem: the entry dump that published a lit light as dark

Within four minutes of a new design going live, the private integration reported a light off that
was on, and reported another light flicking off and back on again with nobody touching it. Both
came from one plausible but wrong belief about what a processor sends when a slot enters a
subsystem. The design treated that burst of joins as a complete statement of the subsystem's state.
It is not, and the processor has no way to say when it is finished.

This is why this project merges entry dumps into state and never rebuilds state from them
([ADR 0006](../adr/0006-entry-dumps-merged-never-rebuilt.md)), and why each subsystem has its own
`quiet_seconds`. Terms: [entry dump](../concepts/glossary.md),
[registration dump](../concepts/glossary.md), [re-poll](../concepts/glossary.md).

## Background

On a gated program a slot has to enter a subsystem (press its home-page button) before the
processor reports that subsystem's joins. The processor answers an entry press with a burst of
join values, the entry dump. A digital join that is low is usually just not mentioned, so in a dump
taken at session start, "not mentioned" reads as low.

The new design let one slot move between Lights and audio. When it came back to Lights, it rebuilt
the Lights state from the new entry dump: anything the dump mentioned took the dump's value, and
anything the dump left out was set low. The reasoning was that a light switched off at a wall
keypad while the slot was away would otherwise read on forever. One earlier observation seemed to
support it: on a second entry, a light that had been switched off elsewhere was missing from the
dump, which was read as "absence reports an off".

## How it looked from outside

The log, with load names removed:

```text
+0.00   entering lights (was audio)           entry B
+0.94   light A -> off                        B's rebuild
+23.5   entering lights (was audio)           entry D
+24.0   light B -> off                        D's rebuild, 0.47 s after the press
+24.4   light A -> on                         late frames, 0.88 s after the press
+24.4   light B -> on
```

Light A was on the whole time. Entry B's dump simply did not mention it, and nothing followed to
correct the rebuild until entry D, which by luck carried it in late frames. Light B's off and on
came from entry D alone.

## How it was diagnosed

Two separate faults were in that log.

**The dump was partial.** Entry B omitted a join that was high. Once the integration logged every
join that was high before an entry and missing from it, the evidence piled up. One entry omitted
seven high joins at once, including four that appeared in the high list of every read-only
registration ever taken from that processor. Separately, three read-only registrations in a row
reported 23 high joins and a fourth, minutes later with no physical change, reported 24. Absence in
an entry dump carries no information.

To rule out a timing race, the test was repeated on a load nothing else was touching: switch it on,
do a full audio round trip, and watch. It stayed on correctly (it was in that dump); seven other
high joins were left out of the same dump.

**The collection window closed mid-dump.** Entry D's rebuild ran 0.47 seconds after the press, on a
dump whose last frame lands at about 0.53 seconds. An entry dump has no end marker, so the
integration declared it complete after a fixed quiet period. That threshold had been measured on a
different slot, where the largest gap between two frames of a Lights dump was 0.166 seconds. On
the bridge's own slot a gap between two bursts was longer than the threshold, and everything after
it arrived outside the collection and moved the same entities a second time.

## The measurements behind the numbers

A stand-alone timing script registered on a spare slot, pressed the Lights and audio entry buttons
alternately, and recorded every frame:

| Window | Frames | First | Last | Largest gap | End-of-query marker |
| --- | --- | --- | --- | --- | --- |
| Registration dump | 153 | +0.025 s | +0.964 s | 0.205 s | at +0.926 s |
| Lights entry (three runs) | 6 to 7 | about +0.1 s | +0.51 to +0.53 s | 0.144 to 0.166 s | none |
| Audio entry (two runs) | 6 | about +0.09 s | +0.52 s | 0.349 to 0.352 s | none |

A later run on a second slot found largest gaps of 0.246 seconds for Lights and 0.419 seconds for
audio. Three things follow:

- No entry ever produced an end-of-query marker. Quiet is the only signal.
- Even where the marker does appear, it is not the last word: the registration dump's final frame
  arrived 38 ms after its marker.
- The audio dump has a reproducible internal pause the Lights dump does not, and gaps differ from
  slot to slot. A timing measured on one slot does not transfer to another.

## The fix in the private integration

- Entry merges. Every join in the dump is applied; a join not in it keeps its value. The accepted
  cost is that a light switched off elsewhere while the slot was away can read on until a later
  frame corrects it. A stale reading is better than a wrong one, and the wrong direction here (a lit
  light reading off) is exactly what the [subsystem latch outage](post-mortem-subsystem-latch.md)
  looked like.
- The collection window got a floor as well as a quiet threshold, so it cannot close before the dump
  has had time to finish, whatever the silence inside it looks like.
- The quiet threshold became per subsystem, set at about twice the worst gap measured for that
  subsystem across both slots.
- Bring-up enters and then re-polls. Re-sending the registration-time update request mid-session
  returned the full state, about 149 frames in 0.86 seconds, ending with the end-of-query marker.
  At bring-up the state starts empty, so a partial entry dump would otherwise leave a lit load
  reading off for the whole session.

Three full audio round trips with the merge and the floor in place produced no spurious state
change across six entries. One entry logged an omitted high join and correctly left it alone.

## What this framework does about it

All in `custom_components/cip_panel/cipcore/client.py`:

- `CipClient._merge()` applies a dump as a merge and only emits changes for joins the dump
  mentioned. Its docstring records why.
- `CipClient._enter_locked()` waits until `Timing.entry_min_seconds` (default 0.9 s) has passed
  **and** the link has been quiet for the subsystem's `quiet_seconds`. Quiet is measured on data
  frames only (`_last_data_rx`), because counting heartbeat replies would stretch a window under a
  second wide.
- `Subsystem.quiet_seconds` defaults to 0.85 s, twice the worst gap measured on the system this was
  developed on. Set it per subsystem in the join map; see
  [join-map-reference.md](../configuration/join-map-reference.md).
- `CipClient.async_repoll()` sends the update request after entry and waits for the end-of-query
  marker. If the marker never comes it still merges what arrived, because every digital frame in
  that window was diverted into the collection and discarding it would lose real feedback. Set
  `repoll_after_entry: false` for a processor that never answers a second update request.
- `cip-panel listen --enter JOIN --allow-press` measures the gaps in your own entry dumps and
  suggests a `quiet_seconds`. See [listening-to-a-processor.md](../inventory/listening-to-a-processor.md).

## What to check on a different system

- Measure your own dump spacing on the slot you will actually use, for each subsystem. Do not copy
  another system's numbers, including the defaults here.
- Never infer "off" from a join's absence in anything except a complete registration dump at the
  start of a session.
- When one observation fits two explanations, it is evidence for neither. The single "absence means
  off" sighting fitted a partial dump just as well.
