# Dashboards

Crestron Controller's entities are ordinary Home Assistant lights, switches, binary sensors,
buttons, sensors and numbers, so any card that works with those works with these. This page covers
what is specific to them: how they are grouped, what their states mean, and a few choices that make
a dashboard honest.

## What you get per processor

Each config entry is one device, named after the entry, with the model shown as the panel slot's
IP-ID. Under it:

- a **Link** connectivity sensor, in the diagnostic category, always present;
- one entity per item in the join map, named from its `name`.

Entities are pushed, never polled: they update the moment the processor reports a change.

Every mapped entity has a `joins_read` attribute listing the joins it reads, such as
`digital:317`, and a `subsystem` attribute on gated programs. These are for checking your join map,
not for display.

## What the states mean

| You see | Meaning |
| --- | --- |
| On or off | The processor reported it, on a link that is synced. |
| Unavailable | The link is not connected and synced, or the entity is in a gated subsystem that has not been entered yet. On a listen-only link with gated subsystems, gated entities stay unavailable by design. |
| Unknown | The processor has not reported this analog or serial join yet. |
| Separate on and off buttons instead of a toggle | The entity is `press: momentary`, so its state is assumed: whatever Home Assistant last asked for. |

Unavailable is never shown as off on purpose. If you build a card that hides unavailable entities or
treats them as off, you lose the signal that something is wrong.

## Areas

Assign areas the usual way, per entity or per device. Entities from different processors can share
an area; Home Assistant does not care which device they belong to. A room whose lights come from two
processors works like any other room. See [multiple processors](./multiple-processors.md).

## Suggestions

- Show the Link sensor somewhere you will see it. It is in the diagnostic category, so
  auto-generated dashboards may hide it. A small card or badge with each processor's Link sensor
  turns "the lights are not working" into "the processor link is down" at a glance.
- Prefer light and switch entities over buttons for loads. A light with feedback shows the real
  state and survives keypad changes. Reserve buttons for scenes and macros that have no state.
- Be careful with momentary entities on wall tablets. Their state is a guess. If a keypad
  changes the load, the dashboard does not know.
- Expect about a second of delay on toggles. A toggle or on_off light waits for the processor to
  confirm before its state changes, and the press itself takes a moment. The tile updates when the
  processor says it changed, not when you tapped it. That is the price of never showing a state the
  house is not in.
- A failed command shows an error. If the processor does not confirm a press, Home Assistant
  shows the error message, which names the joins involved. On a wall tablet it is worth making sure
  those messages are visible.
- Brightness that is read-only is not shown on the light. If a light's `brightness` is not
  writable, Home Assistant treats it as on/off and does not display a level. Add a `sensor` on the
  same analog join, with `scale: percent`, to show it.
- Serial joins make good labels. A `sensor` on a serial join shows text the processor supplies,
  such as a room or source name.

## Writes and the dashboard

A listen-only link still shows every light, and tapping one fails with a message saying the link is
listen-only. If other people use the dashboard before writes are on, consider leaving those cards
off it until you have turned writes on.
