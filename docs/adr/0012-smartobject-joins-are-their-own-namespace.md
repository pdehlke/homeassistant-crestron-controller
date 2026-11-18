---
status: accepted
---

# SmartObject joins are their own namespace

A SmartObject is a list on a panel page: sources, rooms, a playlist. The processor sends its joins
inside SmartObject records (types `38` and `39`), each carrying a 32-bit object number, and numbers
them in the object's own range. Object 3's serial 11 is a different signal from the program's
serial 11 and from object 4's
([issue #3](https://github.com/pdehlke/homeassistant-crestron-controller/issues/3)).

Every join this project stores, reports or reads is therefore identified by its kind, its number
and its smart object, with object 0 standing for the program's own joins. The client's state, the
`on_join` callback, the collect-and-merge path for entry dumps, the hub's listeners and the
diagnostics all carry the object. A join map entity names its object with `smart_object:`, and only
`sensor` and `binary_sensor` may do so: reading lists is supported, writing to them is not.
Writing came later, in [ADR 0013](./0013-writing-to-smartobjects.md).

The record layout comes from
[rellis-erigon/Crestron-CIP-HA](https://github.com/rellis-erigon/Crestron-CIP-HA), which captured
SmartObject frames from live processors. This project has not seen a processor send one, so the
whole path is verified against fixtures only, and every user-facing document that mentions it says
so.

## Considered options

| Option | Why not |
| --- | --- |
| Keep skipping SmartObject records, as the client did after issue #2 | Throws away list names, now-playing text and selection feedback without saying so. |
| Flatten object joins into the program's range, ignoring the object number | Two signals then share one number and overwrite each other, publishing one on the other's entity. rellis-erigon/Crestron-CIP-HA did this before its 0.18.0 and recorded the fight in its changelog. |
| Offset object joins into a reserved block, such as object × 10000 + join | Keeps one integer key, but an object number is 32 bits and a join 15 bits, so no offset avoids collisions for every program, and users would have to do arithmetic to write a join map. |
| Change every `(kind, join)` key to a three-part key in one sweep | The same result with far more churn. Instead the object is an argument that defaults to 0, so every existing caller, and every ordinary join, behaves exactly as before. The entry-dump buffer is the exception: it is keyed by `(object, join)` outright, because a list on a gated page arrives inside entry dumps and must be collected and merged, never published directly, just like the joins next to it ([ADR 0006](./0006-entry-dumps-merged-never-rebuilt.md)). |
| Read an object numbered 0 as an object | 0 is how the program's own joins are spelled internally, so a record for object 0 would land in the program's range. Such records are skipped with a debug log entry, and a join map may not name object 0. |
| Accept any record type inside a SmartObject | An end-of-query marker inside an object would be taken for the real one, acknowledging it and starting bring-up. Only digital, analog and serial records are read inside an object. |
| File SmartObject serials by subsystem | Ordinary serials are not filed by subsystem, because on the development system they arrived once per session ([join map reference](../configuration/join-map-reference.md#sensor)). Nothing is known about list serials, so they follow the same rule rather than a guess in the other direction. |
| Allow `smart_object:` on lights, switches, buttons and numbers now | Each of those can write, and a write into a SmartObject has never been seen accepted by a processor. Writes, with the policy keyed by object, are [issue #4](https://github.com/pdehlke/homeassistant-crestron-controller/issues/4). |

## Consequences

- Join maps written before this change read exactly as before; `smart_object` is optional.
- `crestron-controller listen` reports SmartObject joins separately, writes them as `o3:s11`, and
  drafts them as entities with `smart_object:`. `watch` names them the same way.
- SmartObjects nested inside SmartObjects are followed, with each join belonging to the innermost
  object, up to four levels. No source describes more than one level; the cap only stops a
  malformed frame from recursing without end.
- Whether a list join the processor never mentioned should read as low, as an ordinary digital
  does after a full sync, has not been observed. The hub treats both the same.
- A `crestron-controller listen` run, with debug logging, against a system whose panels have lists
  would confirm or correct all of this.
