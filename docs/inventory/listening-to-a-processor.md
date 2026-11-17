# Listening to a processor

`crestron-controller listen` registers with a control processor as one of its touch panels, records
every join the processor reports for a while, and can write what it saw as a JSON inventory and as a
draft join map. By default it presses nothing. This page explains how to run it, how to read what it
prints, and what to do on a program that gates its subsystems, where listening alone shows only the
menu.

Terms used here: a [slot](../concepts/glossary.md#slot) is a touch panel IP-ID the program defines;
a [registration dump](../concepts/glossary.md#registration-dump) is the burst of join values a
processor sends when a panel connects; a [gated subsystem](../concepts/glossary.md#gated-subsystem)
is a section of the program a panel must enter by pressing a home-page button before the processor
says anything about it.

## Running it

```sh
crestron-controller listen 10.0.0.20 --ipid 0x31 --json joins.json --draft draft.yaml
```

| Option | Meaning |
| --- | --- |
| `HOST` | The control processor's address. Not a touch panel's. |
| `--ipid ID` | The slot to register as, in hex (`0x31` or `31`). A trailing `d` means decimal (`49d`). Must be between 03 and FE. |
| `--port PORT` | The CIP port. Default 41794. |
| `--seconds N` | How long to listen. Default 20. |
| `--json FILE` | Write every observed join to this file. |
| `--draft FILE` | Write a draft join map to this file. |
| `--enter JOIN` | Press this one digital join after registering, to enter a gated subsystem. Needs `--allow-press`. |
| `--allow-press` | Confirms you know what the `--enter` join does. Without it, `--enter` is refused. |
| `--never-write LIST` | Joins to refuse even with `--enter`, such as `200-219,45`. |

Use a slot nobody else is using. `listen` registers exactly as Home Assistant does, so never run it
on the IP-ID a running Home Assistant entry uses, or on a slot whose real panel is connected. See
[choosing an IP-ID](../getting-started/choosing-an-ip-id.md) and
[IP-ID conflicts](../troubleshooting/ip-id-conflicts.md).

## The pre-flight check

Before anything else, `listen` registers once, reads the processor's answer and disconnects. This
is the same check the Home Assistant setup form runs. If it fails, the tool prints the host and
IP-ID followed by one of these, and exits with status 2:

| Message | Meaning |
| --- | --- |
| `nothing answered. Is this the control processor's address?` | Nothing accepted a connection on that address and port. |
| `the program does not define that IP-ID. Try crestron-controller ipids.` | The processor answered and refused this IP-ID. Check it is in hex. |
| `registration refused. Authenticated or encrypted CIP is not supported.` | The processor answered and refused for another reason. |

Other short codes (`displaced`, `closed`) can appear if the processor ended the connection during
the check.

Registering claims the slot for a moment, which is why the slot must be one nobody is using.

## Reading the output

After `--seconds` have passed, `listen` prints one line per group of joins, then the serial count:

```text
[(none)] 14 digital (3 high), 2 analog
  high: d4, d17, d22
138 serial joins
wrote joins.json
wrote draft.yaml
```

`(none)` means "not inside any subsystem". With `--enter`, a second group named `entered` holds the
joins that arrived after the entry press.

- **Digital** joins are on or off. "High" means on. On a lighting program, the high ones are often
  the lights that are on right now.
- **Analog** joins are numbers from 0 to 65535, such as a dimmer level or a volume.
- **Serial** joins are text the program sends to panels: button labels, room names, status lines.
  They are not grouped by subsystem.

## On a program that is not gated

On a program with no gated subsystems, the registration dump carries everything the slot can see.
Expect many digital joins, with the lights that are on reading high. Go on to
[watching keypads](./watching-keypads.md) to find which join is which light, and to
[panel project files](./panel-project-files.md) if you have a TSW x52 panel and want names.

## On a gated program

On a gated program, a slot that has not entered a subsystem sees only the home menu. This is what a
real gated processor showed while this project was being built: it accepted the registration (with
status byte `03`; some CIP clients only accept `1F`, and this one accepts any), and without
`--enter` it reported about a dozen digital joins, two analog joins and around 140 serial joins.
The serial joins were labels. Nothing about any light arrived, because the slot had not entered the
lighting section of the program. The draft written from that run passed validation, but it held
only menu joins.

That result does not mean anything is broken. It means you need the subsystem's
[entry join](../concepts/glossary.md#entry-join), the home-page button that enters it, and you
need to press it once. Do it in this order:

1. **Find the entry join without pressing anything.** If you have a TSW x52 panel, fetch and parse
   its project ([panel project files](./panel-project-files.md)). The draft lists the buttons on
   the panel's home page as subsystem-entry candidates, with their labels, such as "Lights" or
   "Audio". Without a panel project, look at what the panel's home page offers and read the
   serial labels in `joins.json`; but do not guess a join number.
2. **Check the join is not on a safety page.** In the parsed draft, look for the candidate join
   anywhere else, especially in an "also appears as" comment naming an alarm, security, gate or
   lock page. A home-page button for an alarm subsystem is an entry join too. Put every join you
   must never press on `--never-write` and, later, in the join map's `never_write` list. See
   [write safety](../configuration/write-safety.md) and
   [the alarm joins lesson](../case-study/lesson-alarm-joins.md).
3. **Think about courtesy actions.** Some programs do something on their own when a slot enters a
   subsystem, such as switching on a light in that panel's room. On the system this was developed
   on, entering the lighting section from one slot did exactly that. Be ready to see a light come
   on. See [the courtesy light post-mortem](../case-study/post-mortem-courtesy-light.md).
4. **Enter, once, by name.**

   ```sh
   crestron-controller listen 10.0.0.20 --ipid 0x31 --enter 40 --allow-press \
       --never-write '200-219,45' --json lights.json --draft lights.yaml
   ```

## What `--enter` does

`--enter JOIN` presses that one digital join after the registration dump, and nothing else. The tool
builds a write policy that allows only that join. If the join is on your `--never-write` list, the
tool refuses before registering for real. Without `--allow-press`, it exits with "--enter presses a
join on your system. Add --allow-press if you mean it."

After the press, the processor sends an [entry dump](../concepts/glossary.md#entry-dump): the
subsystem's joins, in a burst with no end marker. The tool waits for the burst to go quiet for
2 seconds (deliberately wide, so the measurement is not cut short by a guess about its spacing),
gives up after 10 seconds, and then re-sends the update request to get the full state
([re-poll](../concepts/glossary.md#re-poll)), because an entry dump can leave joins out.

It also times the burst and prints a line like this:

```text
entry dump: first frame 0.142s after the press, 37 digital frames, largest gap 0.180s. Suggested quiet_seconds: 0.36 (twice the largest gap). Repeat a few times; dumps vary.
```

Only gaps shorter than 1.5 seconds count as inside the dump. The suggestion is twice the largest
gap, and never less than 0.3. Run it a few times, take the largest suggestion, and use it as that
subsystem's `quiet_seconds` in the join map
([subsystem gating](../configuration/subsystem-gating.md)). If the press produced no dump, the tool
says `dJOIN did not produce a subsystem dump within the timeout.` If that happens, check the join
number, and try a longer `--seconds`, since the entry happens only after the registration dump has
gone quiet.

## The JSON file

`--json` writes everything observed:

```json
{
  "ipid": "0x31",
  "subsystems": {
    "(none)": {"digital": {"4": 1, "17": 0}, "analog": {"2": 0}},
    "entered": {"digital": {"301": 1, "302": 0}, "analog": {}}
  },
  "serial": {"11": "Lights", "12": "Audio"}
}
```

Digital values are 1 (high) or 0 (low). Join numbers start at 1, as everywhere in this project.

## The draft join map

`--draft` writes a join map in which every entry is read-only and every name is a placeholder:

```yaml
version: 1
never_write:
  digital: []
entities:
  - {type: binary_sensor, name: Digital 4, join: 4}  # high
  - {type: sensor, name: Analog 2, analog: 2}  # was 0
  - {type: sensor, name: "Serial 11", serial: 11}  # 'Lights'
```

Each digital join becomes a `binary_sensor`, each analog join a `sensor` with `analog:`, and each
serial join a `sensor` with `serial:`; the comment shows the value seen. With `--enter`, the draft
lists only the entered subsystem's digital and analog joins (plus every serial join) and adds a
`subsystems:` section:

```yaml
subsystems:
  default: main  # rename to what the button is called on the panel
  entries:
    main: {join: 40, quiet_seconds: 0.42}  # measured once; repeat and keep the largest
```

The `quiet_seconds` value is the suggestion from this one run's entry dump. Dumps vary from one
entry to the next, so repeat the run two or three times and keep the largest suggestion. If the run
saw no dump at all, the draft falls back to 0.85 and says `# default`.

The tool validates the draft with the same code the integration uses before writing it, so a fresh
draft always passes `crestron-controller check`. Nothing in it can write to the processor. Rename
what you recognise, delete what you do not, and promote a `binary_sensor` to a `light` or `switch`
only once you know what it drives ([join map reference](../configuration/join-map-reference.md)).

## Exit status

| Status | Meaning |
| --- | --- |
| 0 | Listened for the full time. |
| 2 | The pre-flight check failed, or registration failed while listening. |
| 1 | `--enter` without `--allow-press`, `--enter` on a `--never-write` join, or an unreadable `--never-write` list. The tool exits with a message after the pre-flight check and before registering for real. |

## Options that were rejected

- **Finding entry joins by pressing each home-page button in turn.** That is a scan, with all of a
  scan's risks: one of those buttons may enter an alarm subsystem. See
  [why there is no scan command](./inventory-overview.md#why-there-is-no-scan-command).
- **Entering automatically whenever the program looks gated.** The tool cannot know which button
  is safe. A press happens only when you name the join and add `--allow-press`.
