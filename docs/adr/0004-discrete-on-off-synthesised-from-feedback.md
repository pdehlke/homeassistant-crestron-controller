---
status: accepted
---

# Discrete on and off are synthesised from feedback, inside the integration

Crestron lighting buttons are usually toggles: one press flips the load, and there is no separate
"off". Home Assistant's `turn_on` and `turn_off` are discrete. So for a light or switch in `toggle`
press mode, `Hub.async_set()` in `hub.py` reads the load's feedback join, presses only if the state
differs from what was asked, and waits up to three seconds for the processor to confirm the new
state. If no confirmation arrives it forgets which subsystem the slot is in, re-enters, and tries
once more; after a second failure it raises an error naming the feedback and press joins to check.
All of this happens under the link's lock, because each decision depends on the state the previous
press produced and must be serialised against feedback arriving from wall keypads at the same
moment.

## Considered options

| Option | Why not |
| --- | --- |
| A template light in Home Assistant whose actions check the feedback entity and press | Races. Between the template reading state and the press landing on the wire, a wall keypad can change the same load, and a template cannot serialise against other entities or against feedback arriving asynchronously. The failure is a press that turns the light off when someone asked for on. |
| Press unconditionally and assume the result | `turn_on` on a light already on would turn it off. A change that presses unconditionally still passes a naive on/off test while turning lights off in the house, which is why it deserves its own test. |
| Optimistic state: report the requested state without waiting | A press that the processor ignored (an unentered subsystem, a wrong join) would show success. See [post-mortem-subsystem-latch.md](../case-study/post-mortem-subsystem-latch.md), where exactly this kind of silent failure lasted four hours. |
| Treat every light as `momentary` | Throws away the feedback that makes state trustworthy. `momentary` exists for buttons with no feedback at all, and those entities are marked `assumed_state`. |

## Consequences

`turn_on` on a light that is already on presses nothing, so automations can call it without
tracking state. A load whose state is unknown (link not synced, subsystem not entered) refuses
rather than pressing blind. `on_off` press mode, for loads with separate on and off buttons, goes
through the same confirm-and-retry path. A press that confirms reports success; one that does not
reports failure, which is what an automation needs to hear. See
[press-modes.md](../configuration/press-modes.md).
