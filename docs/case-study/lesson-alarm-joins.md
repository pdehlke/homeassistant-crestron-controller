# Lesson: the alarm keypad that shared join numbers with the lights

On the system this project was developed on, the touch panel project used the same block of
digital join numbers for two things: buttons on one room's lighting page, and buttons on the alarm
keypad page, including its emergency buttons. Nothing on the wire said which was which. That one
fact decided the whole write-safety design: listen-only by default, an allow list derived from the
join map, and a never-write list checked at the last point before the socket.

No alarm was ever triggered. This page is about why, and about two checks in the private project
that looked like protection and were not.

Background: [joins.md](../concepts/joins.md), [subsystems.md](../concepts/subsystems.md) and
[write-safety.md](../configuration/write-safety.md).

## What the panel project showed

The panel project, read from the panel itself, had an alarm keypad page whose digits, arm buttons
and emergency buttons sat on a block of about twenty consecutive digital joins. One room's lighting
page used the same numbers for its load buttons and group-off buttons. Every page had a join offset
of zero, so this was one join space genuinely shared, not an artifact of how the file was read. The
home page had a separate entry button for the alarm subsystem and another for lights, and the
processor was believed to decide which meaning applied by which subsystem the panel had entered.

That belief was inferred from the project and never confirmed. Confirming it would have meant
pressing unidentified joins on the processor that carried the alarm interface. So the rule became:
treat the whole block, and the alarm entry button, as never writable, in every subsystem.

## What it cost

Most loads with a button inside the block appeared on other pages too, outside it, so the
integration pressed them through the safe alias. Several loads report their state on a join inside
the block, which is fine: receiving those joins is expected, and only writing is refused. A few
loads had no button outside the block anywhere in the project, and those were reached through a
second processor with no alarm in its program at all. See
[two-processor-house.md](two-processor-house.md).

## A join that looked safe and was not

Weeks after one lighting button had been wired up, pressed and verified many times, a page nobody
had read yet turned out to use that same join for an alarm zone. Nothing bad came of it. The point
is that "this join is a light, I have watched it work" is not evidence that the join means only
that. You cannot know what a join does on pages you have not read.

## Two checks that were not protection

**A check that could never fire.** The private integration enforced the forbidden block in two
places: a validation of its load table when the module loaded, and a refusal inside the client's
press function, with the bytes in hand. There was also a third check in between, which applied the
first check's own test to the first check's own data one call later. Any table that could trip it
had already failed at import, so the module never loaded with such a table. It ran on every write
and could never fire. Mutation testing (deliberately breaking the code to see whether any test
notices) proved it dead, and it was deleted. A check that reads like defence in depth and is not is
worse than none, because it stops anyone looking for the real gap.

**A check keyed on an address.** The private project's test scripts shared a guard that only ran
when the target host matched the alarm processor's address. When that processor's DHCP lease moved
it to a new address, the guard silently stopped checking anything. See
[post-mortem-dhcp-address-change.md](post-mortem-dhcp-address-change.md).

The check that mattered was the one at the wire, because some writes never come from the load
table at all: subsystem entry presses, and presses typed on a command line.

## What this framework does about it

- Every link starts [listen-only](../configuration/write-safety.md): it writes nothing at all,
  including entry joins, until you switch `allow_writes` on in the integration's options.
- Once writes are on, only the [allow list](../concepts/glossary.md) can be written: every join an
  entity writes, plus the subsystem entry joins. `JoinMap.policy()` in
  `custom_components/cip_panel/cipcore/joinmap.py` derives it; nobody writes it by hand.
- The `never_write` list in the join map wins over everything. `WritePolicy.check()` in
  `cipcore/policy.py` checks it first, before even the listen-only test.
- That check runs in the client at the last point before bytes reach the socket: `CipClient._press()`
  (which covers entity presses and entry presses), `CipClient.async_set_analog()` and
  `CipClient.async_send_serial()` in `cipcore/client.py`. The CLI uses the same client, so
  `cip-panel listen --enter` and `watch` get the same check, with their own `--never-write` option.
- The join map is also checked when it loads. `_check()` in `joinmap.py` refuses a map in which an
  entity would write a never-write join, or in which a subsystem's entry join is on the list, and
  the message suggests mapping a safe alias instead. Unlike the deleted check above, the wire check
  is not redundant with this one: CLI presses never pass through a join map's entity table.
- Mapping a forbidden join as something that only reports is allowed: list it under
  `also_reports` on the load's entity. `examples/join-map-gated.yaml` does exactly this.
- There is no join-scanning command. See [ADR 0007](../adr/0007-no-join-scanning-in-the-cli.md).

## What to check on a different system

- Fetch and read the panel project before enabling writes. Look for any page whose buttons reach
  an alarm, a gate, a garage door, locks or anything else where a stray press matters, and list
  every one of its joins, plus the entry button for its subsystem, under `never_write`.
- Treat a whole shared block as forbidden, not just the buttons you think are dangerous.
- Prefer ranges (`"200-219"`) to hand-typed lists, so a gap cannot slip in.
- If a load's only button is inside the forbidden block, do not map its press. Look for an alias on
  another page, a second processor that reaches it, or leave it read-only.
- If you add your own safety checks in scripts or automations, key them on what the thing is (this
  link, this join map), never on an address, and break them on purpose once to prove they fire.
