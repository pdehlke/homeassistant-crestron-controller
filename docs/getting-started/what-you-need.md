# What you need

This page lists what has to be true before Crestron Controller can work in your house, and what is
optional. If a word here is new, the [glossary](../concepts/glossary.md) explains it.

## Required

| You need | Why | How to check |
| --- | --- | --- |
| Home Assistant 2026.10.0 or newer | The integration is tested against 2026.10.4 and declares 2026.10.0 as its minimum in `hacs.json`. | Settings > About in Home Assistant. |
| A Crestron control processor that Home Assistant can reach on TCP port 41794 | Home Assistant talks to the [control processor](../concepts/glossary.md#control-processor), the box that runs the program, using CIP, the same protocol the touch panels use. | [Finding your control processor](./finding-your-control-processor.md). |
| A free panel IP-ID on that processor | Home Assistant registers as one of the processor's touch panels, so the program must already define a panel slot that nothing else is using. You cannot add one without reprogramming the processor. | [Choosing an IP-ID](./choosing-an-ip-id.md). |
| A processor that accepts plain CIP | Authenticated CIP and encrypted CIP (port 41796) are not supported in this version. | The setup form reports a refused registration. See [unsupported systems](../troubleshooting/unsupported-systems.md). |
| Knowledge of which joins must never be pressed | Some programs share join numbers between lights and an alarm keypad, a gate or a garage door. Nothing on the wire says which. You list those joins before turning writes on. | [Write safety](../configuration/write-safety.md). |

One processor is one link and one config entry. A house with two processors needs two of each, and
that is common enough to have its own page: [multiple
processors](../configuration/multiple-processors.md).

## Not required

- Crestron software. You do not need SIMPL Windows, VT Pro-e, Toolbox or a dealer login.
  Everything this project does uses the network ports the processor and panels already expose.
- The program source. You do not need the `.smw` file or anyone's notes. The joins can be read
  from what the processor sends, from a touch panel's own project file, or both. See the inventory
  guides under `docs/inventory/`, starting with
  [the inventory overview](../inventory/inventory-overview.md).
- Changes to the Crestron program. Nothing is loaded onto the processor. Home Assistant looks to
  the program exactly like a touch panel would.

## Optional, but useful

| Optional | What it gives you |
| --- | --- |
| The `crestron-controller` command-line tool, installed with `uv` on a computer with Python 3.14 | Lists the IP-IDs a processor defines (`crestron-controller ipids`), shows join changes live while you press keypads (`crestron-controller watch`), records a full join inventory (`crestron-controller listen`), reads a TSW x52 panel's project file (`crestron-controller panel`), and validates a join map (`crestron-controller check`). See [installing](./installing.md). |
| Access to the processor's text console (telnet on port 23, or the CTP console on port 41795) | Lets you identify the processor model and read its IP table, which is the most direct way to find a free IP-ID. On the system this was developed on, both consoles answered with no password. Console login is implemented in the CLI but has not been tested against a processor that asks for one. |
| A touch panel you can take offline | If no spare slot exists, unplugging a panel frees its IP-ID. Its project file is also the safest source of join numbers. |
| A DHCP reservation for the processor | Not strictly required, but strongly advised. A processor that changes address overnight takes every entity on that link with it. See [the DHCP post-mortem](../case-study/post-mortem-dhcp-address-change.md). |

## What it will not do

Version 1 has no `select` or `media_player` entities, does not support authenticated or encrypted
CIP, and has never seen a processor accept the analog or serial write encodings it uses. Audio
zones driven through a cursor are documented as a [pattern](../patterns/cursor-zone-audio.md), not
built. The full list is in [unsupported systems](../troubleshooting/unsupported-systems.md).

Next: [how it works](./how-it-works.md).
