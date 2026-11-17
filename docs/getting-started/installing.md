# Installing

There are two parts. The Home Assistant integration is what you will use every day. The `cip-panel`
command-line tool is optional and runs on any computer on the same network; it helps you find IP-IDs
and joins before Home Assistant is involved.

## The integration

### With HACS

CIP Panel is a custom integration, so HACS needs to be told about its repository once. Add
`https://github.com/pdehlke/homeassistant-crestron-controller` to HACS as a custom repository of
type Integration, then install "CIP Panel (for Crestron)" from HACS and restart Home Assistant. HACS's own documentation
describes adding a custom repository; the menu names have changed between HACS versions, so follow
the version you have.

### By hand

Copy the `custom_components/cip_panel` folder from this repository into the `custom_components`
folder inside your Home Assistant configuration directory, so that you end up with
`<config>/custom_components/cip_panel/manifest.json`. Restart Home Assistant.

The integration has no Python requirements beyond what Home Assistant already ships.

## Adding a processor

You need the processor's address and a free IP-ID first. If you do not have them, read
[finding your control processor](./finding-your-control-processor.md) and
[choosing an IP-ID](./choosing-an-ip-id.md).

1. In Home Assistant, go to Settings > Devices & services, choose Add integration, and pick
   "CIP Panel (for Crestron)".
2. Fill in the form:

   | Field | What to enter |
   | --- | --- |
   | Name | A label you will recognise, such as "Main processor". It becomes the device name, and the default join map file name is made from it. |
   | Processor address | The control processor's IP address or DNS name. Not a touch panel's. |
   | Panel IP-ID | The slot to borrow, in hex as Crestron writes it (`0x2A` or `2A`), or decimal with a `d` suffix (`42d`). Must be between 03 and FE. |
   | CIP port | Leave at 41794 unless you know otherwise. |
   | Join map file | A path under your config folder. Leave blank to use `cip_panel/<name>.yaml`. |

3. Submit. The form checks the join map, creating the starter one if the file does not exist yet,
   then registers once with the processor to prove the address and IP-ID. It presses nothing. If
   anything is wrong it tells you which field, and nothing is saved.

When it succeeds you get one device for the processor, with a **Link** connectivity sensor. The
starter join map has no entities, on purpose: a Link sensor that turns on proves the connection
before you map a single light.

Each processor is a separate entry. Run the flow again for a second processor. See
[multiple processors](../configuration/multiple-processors.md).

### The join map file

The join map is a YAML file you edit by hand, under your Home Assistant config folder. The starter
template contains only a `version`, an empty `never_write` list and an empty `entities` list, with
comments. Its format is in the [join map reference](../configuration/join-map-reference.md), and
the [first light walkthrough](./first-light-walkthrough.md) builds one step by step.

After every edit, reload the entry: Settings > Devices & services > CIP Panel, then the three-dot
menu on the entry, then Reload. No restart is needed. If the file is invalid, the entry fails to set
up and the error message names the entity and the problem. Fix it and reload again.

### Writes are off

A new entry is **listen-only**. To let Home Assistant press joins, open the entry's Configure
dialog and turn on "Allow Home Assistant to press joins". Do that only after your `never_write`
list is complete. Changing this option reloads the entry. See
[write safety](../configuration/write-safety.md).

## The command-line tool

The tool needs Python 3.14 and is installed with `uv`. From a clone of this repository:

```sh
uv tool install .
cip-panel --help
```

Or run it without installing, from the repository folder:

```sh
uv run cip-panel --help
```

Subcommands:

| Command | What it does | Presses anything? |
| --- | --- | --- |
| `cip-panel ipids HOST` | Sends `VER` and `IPTABLE` to a processor's console and lists the IP-IDs its program defines and which are online. | No. |
| `cip-panel console HOST COMMAND...` | Sends console commands you type, behind a small denylist of destructive ones. You are responsible for what you send. | It can change things. See [the processor console guide](../inventory/processor-console.md). |
| `cip-panel listen HOST --ipid ID` | Registers as a panel, records every join reported for a number of seconds, and can write a JSON inventory and a draft join map. | No, unless you add `--enter JOIN --allow-press`. |
| `cip-panel watch HOST --ipid ID` | Registers as a panel and prints join changes live while you press keypads. With `--label FILE` it asks you to name each change and appends entries to a join map. | No, unless you add `--enter JOIN --allow-press`. |
| `cip-panel panel fetch` / `panel parse` | Downloads a TSW x52 panel's project file over its console and turns it into an inventory or draft join map. | No. |
| `cip-panel check FILE` | Validates a join map exactly as the integration will and prints what it would let Home Assistant write. | No. |

There is deliberately no command that presses a range of joins to see what happens; see
[ADR 0007](../adr/0007-no-join-scanning-in-the-cli.md).

`listen` and `watch` register on an IP-ID just as Home Assistant does. Do not run them on the IP-ID a
running Home Assistant entry is using. See [IP-ID conflicts](../troubleshooting/ip-id-conflicts.md).

Next: [your first light](./first-light-walkthrough.md).
