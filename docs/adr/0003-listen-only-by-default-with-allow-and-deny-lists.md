---
status: accepted
---

# Listen-only by default, with a derived allow list and a never-write list that wins

Every new link writes nothing, not even a subsystem entry press, until the user turns on
`allow_writes` in the integration's options. Once writes are on, only the allow list can be written:
every join an entity in the join map writes, plus the subsystem entry joins, derived by
`JoinMap.policy()` and never typed by hand. The user's `never_write` list overrides everything,
including the allow list. `WritePolicy.check()` enforces all of it inside the CIP client at the last
point before bytes reach the socket, in `CipClient._press()`, `async_set_analog()` and
`async_send_serial()`.

The reason is that nothing on the wire says which joins are dangerous. On the system this was
developed on, the touch panel project used one block of about twenty digital join numbers for both a
room's lighting buttons and an alarm keypad, including its emergency buttons. Much later a lighting
button that had been pressed many times turned out to share its join with an alarm zone on a page
nobody had read yet. A novice cannot be expected to know any of that on day one. See
[lesson-alarm-joins.md](../case-study/lesson-alarm-joins.md).

## Considered options

| Option | Why not |
| --- | --- |
| Writes on by default, protected by a deny list | The deny list is exactly what a new user has not written yet. The first minutes with a new integration are the most dangerous ones. |
| A deny list only, with every other join writable | Leaves every unmapped join writable from the CLI or a future service call. Unmapped joins are the ones nobody has looked at. |
| A hand-maintained allow list | Drifts from the join map. Deriving it means a join is writable if and only if something in the map writes it. |
| Check in the entity or hub layer instead of the client | Entry presses and CLI presses never pass through an entity. A check above the client would miss them. The private project's integration got this right; its scripts, which checked elsewhere, were where the holes were. |
| Let listen-only still press entry joins, so gated entities show state | An entry press changes processor state, can trigger a [courtesy action](../case-study/post-mortem-courtesy-light.md), and on the original system the alarm subsystem had an entry join too. Listen-only has to mean nothing is written. Gated entities show unavailable instead, which is honest: the processor has said nothing about them. |

## Consequences

The join map is also checked when it loads: `_check()` in `joinmap.py` refuses an entity that would
write a never-write join and an entry join on the never-write list, so a mistake fails at reload
instead of at the moment someone touches that light. Both checks can fire for different inputs (the
CLI's presses never come from a join map's entities), which matters: the private project once
carried a third check that could never fire, and deleted it because a check that reads like defence
and is not stops anyone looking.

A user who wants to see gated state before trusting writes can use the CLI's
`listen --enter JOIN --allow-press`, which presses that one join and nothing else.
