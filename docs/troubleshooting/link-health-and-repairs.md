# Link health and repairs

Every link reports its health in two ways: a connectivity sensor that is always present, and Home
Assistant repairs for failures a person needs to act on. This page explains both, and why they
exist.

## Why

On the system this was developed on, a processor moved to a new address overnight because its DHCP
lease was not reserved. The private integration this project grew from retried the old address every
33 seconds for about 85 minutes and showed nothing a person would see. The report was "the lights do
not work", and the first suspect was the wrong one. A link that fails loudly turns that into "the
link to this processor is down" without anyone reading a log. See
[the DHCP post-mortem](../case-study/post-mortem-dhcp-address-change.md).

## The Link sensor

Each config entry has one **Link** binary sensor, device class connectivity, in the diagnostic
category. It is created even when the join map has no entities, so the first thing you see after
setup is proof that Home Assistant reached the processor.

It is **on** when the link is connected, registered, and synced: the registration dump has arrived
and, on a gated program with writes on, the default subsystem has been entered. On a gated program
with writes off, the link counts as synced without entering, so the Link sensor is on even though
gated entities are unavailable.

Its attributes:

| Attribute | Meaning |
| --- | --- |
| `host` | The processor address this link uses. |
| `ipid` | The IP-ID it registers as, in hex. |
| `writes_enabled` | Whether writes are on for this entry. |
| `subsystem` | Which gated subsystem the slot is in right now, or empty. |
| `last_error` | The last failure, kept readable through the reconnect wait, and cleared when a registration succeeds. |

## Reconnecting

When a session drops, the link reconnects on its own, waiting 1, 2, 5, 10 and then 30 seconds between
attempts and staying at 30. After any session that reached synced, the wait starts again from 1
second, so a healthy link that drops once is back quickly while a processor that keeps refusing is
not hammered. Reaching synced is used as the test, rather than "the session ended", because it is a
high bar a flapping link cannot clear: it takes a registration, a full dump and a quiet window. See
[the backoff lesson](../case-study/lesson-backoff-that-never-reset.md) for the bug this replaced.

A new session starts from an empty copy of the joins. State from a previous session is not evidence
about this one, and anything that changed while the link was down arrives in the new dump.

## Repairs

Home Assistant checks each link every 30 seconds and raises or clears these repairs, under Settings >
Repairs. Each names the entry, the processor address and the IP-ID. None can be fixed from the repair
dialog; each clears itself once the condition ends.

| Repair | Raised when | What to do |
| --- | --- | --- |
| Crestron processor unreachable | The link has not been synced for ten minutes or more, for any reason. | If the processor uses DHCP, it may have moved: find it again ([finding your control processor](../getting-started/finding-your-control-processor.md)), reserve its address in your router, and update the entry. Otherwise check that it is powered and reachable. |
| IP-ID is not defined on the processor | The link is down and the processor's last answer was that its program does not define the IP-ID. | The program was probably reloaded or changed. Run `cip-panel ipids` to see which IP-IDs it defines now and pick another slot. |
| The processor refused registration | The link is down and the processor refused the registration for another reason. | Authenticated or encrypted CIP are possible causes and are not supported ([unsupported systems](./unsupported-systems.md)). |
| The processor keeps ending the session | The processor sent a disconnect three or more times in the last ten minutes. Raised even while the link is up between drops. | One possible cause is another device using the same IP-ID, such as a real touch panel or a second Home Assistant. This is a lead, not a diagnosis; see [IP-ID conflicts](./ip-id-conflicts.md). |

Ten minutes is long enough that a processor reboot does not raise a repair, and short enough that a
processor that moved address overnight is noticed the same morning. The IP-ID and refused repairs
appear at the next 30-second check after the failure, because waiting would not change them.

Removing an entry removes its repairs.

## Two processors

Each link has its own sensor and its own repairs. If every entity on one link is unavailable and
every entity on the other is fine, the problem is that link, not Home Assistant and not anything the
two links share. On the system this was developed on, that one observation was enough to rule out the
first suspect in both of its outages. See [multiple processors](../configuration/multiple-processors.md).

## Using the sensor in automations

The Link sensor is an ordinary binary sensor, so you can notify yourself when it has been off for a
while, or show it on a dashboard. The repairs already cover the ten-minute case; an automation is
useful if you want a different delay or a different channel.
