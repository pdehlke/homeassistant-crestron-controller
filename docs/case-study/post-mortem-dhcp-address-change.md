# Post-mortem: the processor that moved address overnight

One morning every load on one processor's link, lighting and audio alike, was dead from Home
Assistant, while the few loads on the house's second processor worked normally. The processor had
not failed. Its DHCP lease had never been reserved, it renewed onto a different address overnight,
and the private integration kept trying the old one. The outage lasted roughly 85 minutes and ended
with a one-line address change.

The fix is not the interesting part. The symptom pointed convincingly at something else, the
integration surfaced nothing a person would see, and chasing it turned up a safety check that had
quietly stopped working. This is the reason this project raises Home Assistant repairs for link
health. The house is described in [two-processor-house.md](two-processor-house.md).

## How it looked from outside

- The report was simply: the only controls that work are the few lights on the second processor.
- The bridge's panel slot had been changed the previous day, which was the most recent change to
  the integration. A slot problem would plausibly take out lighting and audio together while
  leaving the other processor alone. It looked like a regression.
- Nothing on any dashboard said a link was down. The integration retried a dead address every 33
  seconds for the whole outage and logged a warning each time, and nobody reads logs at breakfast.

## How it was diagnosed

The slot was ruled out by reasoning before any tool was opened. Lighting and audio shared that
processor's link, and the second processor was a separate TCP connection to a separate box.
"Everything on one link is dead, everything on the other is fine" is a statement about the link, not
about anything layered on top of it. Any explanation that needed the slot would also have had to
explain why the other connection was untouched.

The log then said it outright: the connect call was failing with errno 113, which on Linux is
`EHOSTUNREACH`, a failure to reach the host at all. That sits below anything the integration does
with slots, subsystems or joins.

From a laptop on the same network segment:

| Check | The configured address | The other processor |
| --- | --- | --- |
| Ping | 100% loss | replies |
| ARP | incomplete | resolves to a Crestron hardware prefix |
| TCP 41794 (CIP) | no answer | open |

An incomplete ARP entry means nothing on the segment claims the address. The processor was not
firewalled or wedged; it was simply not there. A sweep of the subnet for Crestron hardware
prefixes found the known second processor and one other device with a processor's port profile
(41794, 41795, 80 and 23 open). Its web server identified nothing, so the confirmation came from
the console banner on port 23, which named the model. That is identification rather than
inference. Pointing a bridge at the wrong processor because "it must be the only other one" is not
a harmless experiment.

## Root cause

An unreserved DHCP lease on a device the configuration named by literal address. Nothing in the
control system or the integration changed, and no deploy was involved. The lesson is to reserve
every device a configuration names by address, all at once, rather than one outage at a time.

## The fix in the private integration

The address was reserved in the router, and the integration's configured host was updated. A
restart was required, because that integration had no config entry to reload.

## The latent problem it turned up

Several of the private project's command-line test scripts shared a guard that refused to press
the joins the alarm keypad shares. It decided whether to check at all by comparing the target
host with the processor's configured address, and returned without checking when they differed.

With the processor at its new address that comparison stopped matching, and the guard returned
without checking anything. Two scripts that relied on it would have pressed alarm keypad joins
without refusal the moment either was pointed at the processor's real address. It was not an
active hole that day, only because both defaulted to the other processor. An address change
elsewhere in the network had silently disarmed it.

The integration's own guard was unaffected. It was keyed on the link's role (which link this was),
not its address. Identity by logical role survives a network change; identity by address does not.

## What this framework does about it

- Link health is visible without reading a log. Every link has a connectivity `binary_sensor`,
  present even with an empty join map. `evaluate_health()` in
  `custom_components/crestron_controller/__init__.py` opens a repair when a link has been
  disconnected for `UNREACHABLE_REPAIR_SECONDS` (600 seconds, in `const.py`): long enough that a
  processor reboot pages nobody, short enough that an overnight move is noticed the same morning.
  Repairs also cover an IP-ID the program does not define, a refused registration, and repeated
  displacement. See [link-health-and-repairs.md](../troubleshooting/link-health-and-repairs.md).
- The kind of failure is kept. `CipClient._session()` in `cipcore/client.py` records an
  unreachable host as `ERROR_UNREACHABLE` with the address in the message, and that text appears in
  the repair.
- The never-write list belongs to the link's join map, which is attached to the config entry. It
  does not compare addresses, so moving the processor cannot disarm it. See
  [write-safety.md](../configuration/write-safety.md).
- The host is stored in the config entry. After a processor moves, open the integration's menu
  and choose Reconfigure: it registers once at the new address to prove it, presses nothing, and
  keeps every entity, its history and the join map. Deleting and re-adding the entry would have
  orphaned every entity id an automation refers to, which is why the step exists
  (`async_step_reconfigure` in `config_flow.py`).

## What to check on a different system

- Reserve a DHCP address for every processor and every panel the configuration names, or give
  them static addresses. Do it for all of them at once.
- If a link goes down, check that the address still answers before looking at anything above it:
  ping, ARP, then TCP 41794.
- Confirm a processor's identity from its console banner or `VER` before pointing anything at it.
- Look for any safety check in your own tooling that decides whether to run based on an address. It
  will stop running the day the address changes.
