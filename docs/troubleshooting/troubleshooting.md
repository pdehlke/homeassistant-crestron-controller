# Troubleshooting

Find the symptom, then work down its list. Most problems are one of three things: the wrong address,
the wrong IP-ID, or a join map that maps something other than what you think.

## Getting the logs

Add this to `configuration.yaml` and restart to see the integration's protocol detail in the Home
Assistant log:

```yaml
logger:
  default: warning
  logs:
    custom_components.cip_panel: debug
```

The diagnostics download (entry three-dot menu > Download diagnostics) shows the link's state, the
last error, recent displacements, every join the processor has reported grouped by subsystem, and
what each entity reads and writes. It contains the processor's address, so check it before sharing.

## The setup form will not accept the processor

| Message | What to check |
| --- | --- |
| Nothing answered on that address and port | The address is not the control processor, or Home Assistant cannot reach it. Check you entered the processor's address and not a touch panel's ([finding your control processor](../getting-started/finding-your-control-processor.md)), that port 41794 is reachable from the Home Assistant host, and that no firewall or VLAN separates them. |
| The processor answered, but its program does not define that IP-ID | The IP-ID is not in the program. IP-IDs are hex: `14` is hex 14. Run `cip-panel ipids` to list the ones it defines. If you have two processors, check that this IP-ID came from this processor's table. |
| The processor answered but did not accept the registration | Something other than a missing IP-ID refused it, or it answered with something that was not CIP within 10 seconds. A processor requiring authenticated or encrypted CIP is one possible cause and is not supported ([unsupported systems](./unsupported-systems.md)). A processor that ended the session straight away is reported this way too; see [IP-ID conflicts](./ip-id-conflicts.md). |
| Enter an IP-ID between 03 and FE | Use hex (`2A` or `0x2A`) or decimal with a `d` suffix (`42d`). |
| The join map could not be used | The detail says what is wrong with the file. See [validation errors](../configuration/join-map-reference.md#validation-errors). |
| This processor and IP-ID are already set up | An entry with the same address and IP-ID exists. |

## The entry fails to set up after a join map edit

The entry card shows the validation error, which names the entity (`entities[3] (porch)`) and the
fix. Correct the file and reload. `cip-panel check FILE` gives the same message without a reload.
Every message is listed in [validation errors](../configuration/join-map-reference.md#validation-errors).

If the file is valid but an entity type fails to load, look in the log: an unrecognised
`device_class` is the usual cause.

## The Link sensor is off

Look at its `last_error` attribute.

| `last_error` says | Meaning |
| --- | --- |
| `cannot reach <host>:<port> ...` | Nothing answers at that address. The processor may be off, or may have moved to a new address. See [the DHCP post-mortem](../case-study/post-mortem-dhcp-address-change.md). |
| `IP-ID 0x.. is not defined in the program on <host>` | The program no longer defines this IP-ID, perhaps because the program was reloaded or changed. |
| `registration refused: ...` | The processor refused for another reason. |
| `processor ended the session` | The processor sent a disconnect. Once is not alarming; repeatedly may mean another device is using the IP-ID. See [IP-ID conflicts](./ip-id-conflicts.md). |
| `processor closed the connection` | The TCP connection closed without a disconnect message. |
| empty, but still off | The link is connected and registered but not yet synced. On a gated program with writes on, the entry into the default subsystem may be failing; the log says so. |

The link retries on its own, waiting 1, 2, 5, 10 and then 30 seconds between attempts. If it stays
down for ten minutes, a repair appears. See [link health and repairs](./link-health-and-repairs.md).

## Entities are unavailable

- Is the Link sensor on? If not, every entity on that link is unavailable. Start there.
- Is the program gated and the link listen-only? A listen-only link never presses the entry join,
  so gated entities stay unavailable. This is deliberate. Turn on writes once your never-write list
  is complete. The diagnostics' `entered_subsystems` is empty in this state.
- Did an entry fail? With writes on, if the default subsystem cannot be entered, entities in it
  stay unavailable. The log has a warning naming the entry join and how many joins arrived. Check
  the entry join number and see [subsystem gating](../configuration/subsystem-gating.md).

## An entity shows the wrong state, or never changes

- Wrong join. Switch the load at a keypad and watch which joins move, with diagnostics or
  `cip-panel watch` on a second slot ([the walkthrough](../getting-started/first-light-walkthrough.md#3-find-the-join-for-one-light)).
  Compare with the entity's `joins_read` attribute.
- Wrong subsystem. On a gated program, the same join number means different things in different
  subsystems. Check the entity's `subsystem`.
- Stale after the slot was elsewhere. On a gated program, a light switched at a keypad while the
  slot was in another subsystem can read stale until its next change. This is the cost of merging
  partial entry dumps instead of trusting them; see
  [subsystems](../concepts/subsystems.md#entry-dumps-are-partial). A shorter
  `idle_return_seconds` shortens the window.
- The program does not report it to panels. If no join moves when you switch the load at a
  keypad, the program may simply not tell panel slots about that load. CIP Panel can only see what
  the program shows a panel. See [unsupported systems](./unsupported-systems.md).

## Switching a light fails

### "This link is listen-only"

Writes are off. Turn them on in the entry's Configure dialog, after completing the never-write list.

### "The ... link is not connected"

The link is down or not yet synced. See the Link sensor.

### "State unknown, refusing to press blind"

The feedback join has no value yet, usually because the subsystem has not been entered. Discrete
synthesis needs to know the state before pressing, or it might do the opposite of what you asked.

### A light says it pressed twice without confirming

The full message is "pressed 2 times without the processor confirming on (or off). Check that
feedback join N really reports this load, and that the press join really drives it."

- The press join and the feedback join may belong to different loads. Check both with a keypad and
  `watch`.
- The press join may do nothing on this slot. Some programs wire a load's button on one page to do
  something different from the same load's button on another page. On the system this was developed
  on, pressing one light's own button lit its feedback but did not switch the fixture, and the button
  for the same light on another page did. Try `press: on_off` with that other join as `on_join`.
- On a gated program, something may have taken the slot out of its subsystem. The retry already
  re-enters; if both attempts fail, see [subsystem gating](../configuration/subsystem-gating.md).
- On the system this was developed on, this exact error on every light was the first sign that a
  power cut had cleared the subsystem latch. See
  [the subsystem latch post-mortem](../case-study/post-mortem-subsystem-latch.md).

### "... is on the never-write list" or "is not mapped to anything writable"

The write policy refused it at the socket. The first means the join is denied; the second means no
entity writes it. Neither can be overridden from a dashboard. See
[write safety](../configuration/write-safety.md).

### "Could not enter the ... subsystem"

The entry press produced no dump within `timing.entry_timeout`. Check the entry join number in the
join map against the panel project file.

## A light turns on by itself when Home Assistant restarts

On a gated program, entering the default subsystem can trigger a courtesy action in the program, such
as switching on a light in the borrowed panel's room. The link enters at every connect, reconnect,
restart and idle return. Code cannot stop it; choose a different slot. See
[the courtesy light post-mortem](../case-study/post-mortem-courtesy-light.md).

## The command-line tool

| Message | Meaning |
| --- | --- |
| `nothing answered. Is this the control processor's address?` | Same as the setup form's "nothing answered". |
| `the program does not define that IP-ID. Try cip-panel ipids.` | Same as the setup form. |
| `registration refused. ...` | Same as the setup form. |
| `--enter presses a join on your system. Add --allow-press if you mean it.` | `--enter` needs `--allow-press` as confirmation. |
| `dN is on your --never-write list; refusing to press it.` | The join you asked to enter is denied. |
| `dN did not produce a subsystem dump within the timeout.` | That join is not an entry join, or the slot was already inside that subsystem. |
| `Could not parse the IP table; the raw reply follows.` | `ipids` did not recognise the table layout. Read the raw text yourself. |

If the tool and Home Assistant use the same IP-ID at the same time, expect trouble on both. Use a
second slot for the tool or disable the entry while it runs.
