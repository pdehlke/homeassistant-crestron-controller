# IP-ID conflicts

An IP-ID conflict is two clients registering with one processor under the same IP-ID: Home Assistant
and a real touch panel, Home Assistant and the command-line tool, or two Home Assistant
installations. This page explains what is known about it, which is less than you might hope, and how
to avoid it.

## What is not known

**This project has not established what a Crestron processor does when two clients claim one
IP-ID.** It might refuse the second, drop the first, accept both, or do different things on
different models and firmware. Nothing here asserts any of those.

The private notes this project grew from disagree with each other. One records that claiming a slot
displaced nothing. Another, written later on the same system, planned a deliberate collision on a
slot expecting the processor to end the other session, and left that call to the system's owner
because the slot was in production use. A third warned that registering on a slot in use would
take the device that normally uses it offline.
None of them is a controlled test, and the test was never run.

So treat a conflict as something to avoid, not something with known consequences.

## How to avoid one

- Pick a slot that is defined but offline. `cip-panel ipids` shows each IP-ID's status. An IP-ID
  that is online has something connected to it right now. See
  [choosing an IP-ID](../getting-started/choosing-an-ip-id.md).
- Cross-check with `WHO`. The `WHO` console command lists the clients connected right now. On the
  system this was developed on, it confirmed which panels were live. Run it with
  `cip-panel console HOST WHO`.
- Never run the command-line tool on Home Assistant's IP-ID. `listen`, `watch`, and the
  registration check they start with all register. Use a second free slot for the tool, or disable
  the Home Assistant entry while the tool runs.
- Make sure the borrowed panel stays unplugged. If you freed a slot by unplugging a touch panel,
  label it. Someone plugging it back in creates a conflict.
- One slot per Home Assistant. A test instance and a production instance must not share an IP-ID.
  Home Assistant refuses to add the same processor address and IP-ID twice within one installation,
  but it cannot see another installation.

The setup form's registration check does claim the slot for a moment. If a real panel is online with
that IP-ID, what the processor does about it is the same unknown.

## What the integration reports

When the processor ends a session it sends a disconnect message. The link records each one. If three
or more arrive within ten minutes, Home Assistant raises the "processor keeps ending the session"
repair, which names the IP-ID and says another device using it is one possible cause. The
diagnostics download shows `recent_displacements`, the count in the last ten minutes.

That repair is a lead, not a diagnosis. Other causes could end a session too: a program reload, a
processor reboot, a network problem. And a conflict might not produce disconnects at all, depending
on what the processor does. Repeated displacement says "look here first", nothing more.

## If you suspect one

1. Run `cip-panel ipids` and look at the status of your IP-ID. With Home Assistant connected it should
   be online. Disable the entry and run it again: if it is still online, something else is using it.
2. Run `WHO` and look for an address that is not your Home Assistant host.
3. Find that device. Its address in the router's client list usually identifies it.
4. Either take that device offline or move Home Assistant to a different free slot.

## If you learn more

If you observe what your processor does with two clients on one IP-ID, under controlled conditions
and on a slot whose joins are harmless, that is useful evidence for this project. Record the
processor model and firmware (`VER`), what each client saw, and what the processor's IP table showed.
