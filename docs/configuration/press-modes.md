# Press modes

A light or switch in a join map has a `press` mode that says how Home Assistant drives it. There are
three. This page explains each one, when to use it, and why it works the way it does. The keys each
mode needs are in the [join map reference](./join-map-reference.md#light-and-switch).

| Mode | Joins | State comes from | Home Assistant shows |
| --- | --- | --- | --- |
| `toggle` (default) | One button that flips the load, plus its feedback | The feedback join | A normal switch or light toggle |
| `on_off` | Separate on and off buttons, plus feedback | The feedback join | A normal switch or light toggle |
| `momentary` | One or two buttons, no feedback | Whatever Home Assistant last asked for | Separate on and off buttons (assumed state) |

## toggle

Most Crestron lighting buttons are toggles: press once for on, again for off, with the button's own
join lit as feedback while the load is on.

```yaml
- type: light
  name: Pendants
  feedback: 317
```

`press_join` defaults to the feedback join. Give it explicitly only when the button you press and
the join that reports state are different numbers.

Home Assistant needs separate on and off commands, and pressing a toggle blindly would turn a light
off when you asked for on if it was already on. So a toggle is made discrete by reading the feedback
first. This is **discrete synthesis**, and when you turn a toggle light on, the link:

1. Checks that writes are on and the link is synced. If not, it refuses with a message.
2. Takes the link's lock, so no other command and no subsystem change can interleave.
3. Enters the entity's subsystem, if the program is gated.
4. Reads the feedback join. If the state is unknown, it refuses rather than pressing blind. If the
   load is already on, it does nothing.
5. Presses the join and waits up to 3 seconds for the feedback to report on.
6. If no confirmation arrives, it forgets which subsystem the slot is in (so the next attempt
   re-enters) and tries once more from step 4.
7. After two unconfirmed attempts, it reports an error naming the feedback join and the press join,
   because the most likely cause is that they do not belong to the same load.

The whole sequence runs under the lock because each step depends on the state the previous press
produced, and because a keypad press can change the feedback at the same moment. Reading feedback
fresh before every attempt, under the lock, is what keeps two quick commands from cancelling each
other out.

## on_off

Some panels have separate On and Off buttons, often with one of them doubling as the feedback join.

```yaml
- type: light
  name: Counter Lights
  press: on_off
  feedback: 333
  on_join: 331
  off_join: 333
```

Behaviour is the same as `toggle`, including reading feedback first, confirming, and the single
retry. The only difference is which join is pressed: `on_join` to turn on, `off_join` to turn off.

Reading feedback first applies here too, even though on and off buttons are not toggles: a press is
sent only when it would change something, and every press is confirmed. What a program does with a
second press of an On button is up to the program, so not sending one is the safe default.

On the system this was developed on, one dimmer channel had a raise button and a separate
fade-to-off button, with the fade-to-off button doubling as the status join, and a short tap of the
raise button brought the light on at a low level. That is the case `on_off` exists for. Another
light needed its on press sent to a different page's button than the one whose feedback was read,
because pressing its own button lit the feedback without switching the fixture.

## momentary

For a load with no feedback join at all. Home Assistant cannot know the real state, so it remembers
what it last asked for, restores that across restarts, and marks the entity as assumed state. Home
Assistant's frontend then shows separate on and off buttons rather than a toggle that pretends to
know.

```yaml
- type: switch
  name: Fountain
  press: momentary
  on_join: 88
  off_join: 89
```

With only `on_join`, the same join is pressed for both on and off, which is a blind toggle: if
anything else changes the load, Home Assistant's idea of its state will be wrong until you correct
it. Prefer a separate `off_join` where the panel has one.

A momentary press does not wait for confirmation, because there is nothing to wait for. A momentary
entity is available whenever its link is connected and synced.

`momentary` refuses `feedback` and `also_reports`. If the load has a feedback join, use `toggle` or
`on_off`, which are always more trustworthy.

## Buttons are not press modes

A scene, macro or "all off" that has no on or off state belongs in a `button` entity, not a
momentary switch. A button presses its `join` once per press and has no state at all.

## Brightness

A light can carry `brightness: {join: N, writable: true}`. Setting a brightness writes the level to
that analog join and nothing else; whether that also turns the load on is up to the program. Turning
the light on or off without a brightness uses the press mode as usual. Analog writes use an encoding
no processor has yet been seen to accept in this project, so test it on one light first. See
[joins](../concepts/joins.md#analog-and-serial-writes).

## Options that were rejected

- Optimistic state for toggles. Pressing and immediately showing the new state is simpler and
  feels faster, but a toggle pressed when the load was already in the target state does the
  opposite of what was asked, and the dashboard would then show the opposite of the truth. Reading
  feedback first is the only way to make a toggle discrete.
- Pressing without confirming. The press would usually work, but when it did not (a slot that
  had silently dropped out of its subsystem, a feedback join mapped to the wrong load) Home Assistant
  would never know. On the system this was developed on, unconfirmed presses were exactly how a
  processor that had stopped acting on a slot first showed itself.
- Retrying until it works. More than one retry risks a toggle flipping twice if a confirmation is
  merely slow. One retry, after re-entering the subsystem, covers the real recoverable case.
- Treating no feedback as off. For a momentary entity, "unknown" is the truth. Assumed state says
  so honestly.

The decision record is [ADR 0004](../adr/0004-discrete-on-off-synthesised-from-feedback.md).
