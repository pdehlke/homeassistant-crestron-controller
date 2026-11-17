---
status: accepted
---

# Cursor-zone audio is deferred, documented as a pattern only

Version 1 has no support for audio programs that drive rooms through a zone cursor, and has no
`select` or `media_player` platform. The private integration this project grew from did control six
audio rooms this way, and its behaviour is written up in
[cursor-zone-audio.md](../patterns/cursor-zone-audio.md). It is not carried over because almost
every rule that made it work was a measured property of one program: the 60 ms blank after a cursor
move, which joins are room state and which are slot state, a source that resets volume to a preset,
volume set by holding a ramp button for a computed time, power-off clearing the remembered source,
and what "turn the room on" should mean when there is no power-on join.

## Considered options

| Option | Why not |
| --- | --- |
| Ship the private implementation, configured from the join map | Every behaviour above would become a configuration key whose correct value nobody but the original author has measured. Wrong values produce entities that report a room's state with full confidence and are wrong, which is worse than no entity. |
| Six `media_player` entities per program | Only the cursor's room is readable at any moment, so five would show cached values. Its volume is normalised 0.0 to 1.0 with no minimum or step, and the original system's speakers were inaudible below about 80% of full scale, so the slider would be four-fifths silence or would show a number the amplifier is not at. |
| One generic "cursor" select plus a volume number | Honest, but it cannot show several rooms at once, which is what people want from audio, and it still needs per-program confirmation logic. |
| Wait for more systems | Chosen. A second and third real program would show which of these behaviours are common and which were one integrator's choices. |

## Consequences

Users can still read the cursor's room name and volume with `sensor` entities and press zone and
source buttons with `button` entities, as `examples/join-map-gated.yaml` shows. A contributor with a
cursor-based audio program is the way forward; the pattern page lists what to measure first.
