---
status: accepted
---

# Entry dumps are merged into state, never used to rebuild it

When a slot enters a gated subsystem, the processor sends a burst of that subsystem's join values,
the entry dump. `CipClient._merge()` in `cipcore/client.py` applies every join the dump contains and
leaves every other join as it was. It never treats a join's absence as meaning low. At bring-up the
client also re-polls with an update request, which returns the full state with an end marker, so a
join that is high but missing from the entry dump does not read low for the whole session.

The evidence, from the system this was developed on: an entry dump is partial and not
deterministic. One entry omitted seven joins that were high, including four that appeared in every
read-only registration ever taken from that processor. Three registrations in a row reported 23
high joins and a fourth, with nothing changed, reported 24. A design that rebuilt state from each
entry dump went live and, within four minutes, published a lit light as dark. See
[post-mortem-partial-entry-dumps.md](../case-study/post-mortem-partial-entry-dumps.md).

## Considered options

| Option | Why not |
| --- | --- |
| Rebuild: a join absent from the dump is low | Absence carries no information in an entry dump. This was built, deployed and wrong. |
| Rebuild only when the dump looks complete | There is no way to tell. Entry dumps carry no end marker, and their size varies with nothing changed. |
| Re-poll after every entry instead of merging the entry dump | The re-poll is the right tool at bring-up, but it costs most of a second each time. Some processors may not answer a second update request at all, which is why `repoll_after_entry` can be switched off. |
| Mark a subsystem's entities unavailable while the slot is in another subsystem | Flaps every entity for sub-second excursions, churns the recorder, and breaks automations that test for unavailable. |

## Consequences

A load switched off at a wall keypad while the slot was in another subsystem can read on until a
later frame corrects it: the next time the load changes, a later entry dump that happens to
mention it, or the full re-poll after the next reconnect. That is a stale
reading, and it was accepted deliberately: the wrong direction (a lit load reading off) is exactly
what the [subsystem latch outage](../case-study/post-mortem-subsystem-latch.md) looked like. Idle
return (`idle_return_seconds`) keeps those excursions short. The same rule applies to a re-poll that
times out: what arrived is merged rather than discarded.
