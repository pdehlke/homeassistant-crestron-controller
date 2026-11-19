# Taking an inventory of your system

Before Home Assistant can show or control anything, you need to know which
[joins](../concepts/glossary.md#join) on your [control
processor](../concepts/glossary.md#control-processor) mean what. A join is one numbered signal
between a touch panel and the processor's program: a button press, a light's on or off state, a
level, a line of text. Nobody hands you that list. The program that defines it was written by an
installer, and most owners do not have its source.

Taking an inventory means building that list from the outside, safely, and turning it into a
[join map](../concepts/glossary.md#join-map), the YAML file that tells the integration which joins
become which entities. This page gives the order to do it in, compares the tools, and explains why
one obvious tool is deliberately missing.

The `crestron-controller` command-line tool does most of the work. Install it as described in
[installing](../getting-started/installing.md#the-command-line-tool).

## The order of operations

1. **Find the processor.** Home Assistant talks to the processor, never to a panel. A house can
   have more than one: the system this project was developed on had an AADS (Crestron's Adagio
   audio distribution system, which has a control processor built in and ran the lighting and
   audio program) and an MC2E control processor running a separate, older program that reached a
   few loads the AADS could not safely reach. Each needs its own inventory. See
   [finding your control processor](../getting-started/finding-your-control-processor.md).
2. **List the IP-IDs.** `crestron-controller ipids HOST` reads the processor's IP table, the list of
   every [IP-ID](../concepts/glossary.md#ip-id) its program expects. See [the processor
   console](./processor-console.md).
3. **Choose a slot.** Pick a touch panel IP-ID whose real panel is unplugged or was never
   installed. See [choosing an IP-ID](../getting-started/choosing-an-ip-id.md).
4. **Listen.** `crestron-controller listen HOST --ipid ID --draft draft.yaml` registers as that
   panel, presses nothing, records every join the processor reports, and writes a draft join map.
   See [listening to a processor](./listening-to-a-processor.md).
5. **Read the panel project, if you have a TSW x52 panel.** `crestron-controller panel fetch`
   downloads the panel's compiled project and `crestron-controller panel parse` turns it into a
   draft with real names, and flags the buttons that may enter a gated subsystem. See [finding your
   touch panel's project file](./finding-your-panel-project.md) for a first walk-through, and
   [panel project files](./panel-project-files.md) for the reference.
6. **Watch while pressing keypads.** `crestron-controller watch HOST --ipid ID` prints joins as they
   change, so you can switch a light at the wall and see which join tracks it. See [watching
   keypads](./watching-keypads.md).
7. **Check the join map.** `crestron-controller check FILE` validates it exactly as the integration
   will and prints what Home Assistant would be allowed to write.
8. **Paste it in.** Copy the checked file to the join map path for that entry (by default
   `/config/crestron_controller/<name>.yaml`) and reload the entry. No restart is needed. Writes
   stay off until you turn them on; read [write safety](../configuration/write-safety.md) first.

If step 4 shows only a handful of joins and none of them move when you switch lights, your program
is probably [gated](../concepts/subsystems.md): the slot has to enter a section of the program
before the processor says anything about it. Step 5 is the safe way to find the button that enters
it, and [listening to a processor](./listening-to-a-processor.md#on-a-gated-program) explains what
to do next.

## The zero-install route

If you would rather not install the command-line tool, Home Assistant itself can do a rough
inventory. Add the processor as a listen-only entry with an empty join map, then use the entry's
Download diagnostics. The file lists every join the processor has reported on that link, high and
low, plus analog values and serial text. Switch a light at a keypad, download again, and compare.
The [first light
walkthrough](../getting-started/first-light-walkthrough.md#option-a-diagnostics-no-install) does
exactly this.

It is slower than `watch`, gives no names, and on a gated program a listen-only link never enters
the subsystem, so you will only see the menu there.

## What each method can and cannot tell you

| Method | Needs | Presses anything? | Gives names? | Gives which joins? |
| --- | --- | --- | --- | --- |
| `crestron-controller ipids` | The processor's address; its console on port 23 or 41795 | No. Sends `VER` and `IPTABLE` only. | Model and firmware, sometimes a description per IP-ID | None. It tells you which IP-IDs exist, which is what you need first. |
| `crestron-controller console` | The same | Only if the command you type does. You are responsible. | Whatever the command prints | None directly |
| `crestron-controller listen` | A free IP-ID | No | No. Draft names are placeholders such as `Digital 17`. Serial joins often carry labels. | Every join the processor reports to that slot. On a gated program, only the menu. |
| `crestron-controller listen --enter JOIN --allow-press` | A free IP-ID and the entry join's number, checked first | Yes, that one join, once | No | Every join in that subsystem, and a measured `quiet_seconds` |
| `crestron-controller watch` | A free IP-ID and someone at a keypad | No (unless given `--enter`) | Yours, if you type them with `--label` | The joins that changed when you pressed something |
| `crestron-controller panel fetch` and `parse` | A TSW x52 panel on the network, and about 10 to 15 minutes | No | Yes, the labels the panel shows, with page names | Every join the panel project uses, including ones the processor has not reported yet |
| Home Assistant diagnostics | A listen-only entry | No | No | Every join reported to the entry's slot |
| `crestron-controller check` | A join map file | No. It touches no network. | Not applicable | The allow list and never-write list the map implies |

None of these tells you what a join physically does. The panel project gives you the label on the
button; `watch` tells you which join moved when you pressed something. Put the two together, and
check anything that looks like it belongs to an alarm, a gate, a lock or a pump before you let Home
Assistant write it.

## One IP-ID, one client

`listen` and `watch` register exactly as Home Assistant does. Never point them at the IP-ID a
running Home Assistant entry is using, or at a slot a real panel is using. What a processor does
when two clients claim one IP-ID is something this project has not established. Use a second free
slot, or disable the Home Assistant entry while the tool runs. See
[IP-ID conflicts](../troubleshooting/ip-id-conflicts.md).

## Why there is no scan command

The obvious way to learn a program is to press every join from 1 upward and see what happens. The
tool deliberately has no command for that, and will not get one
([ADR 0007](../adr/0007-no-join-scanning-in-the-cli.md)).

The reason is safety. On the system this was developed on, an alarm keypad page shared a block of
digital joins with the panel slot Home Assistant used, including joins for fire, medical and panic.
A scan would have pressed them. Programs also reuse join numbers across
[subsystems](../concepts/subsystems.md), so a join that is a light in one section is a media menu in
another, and a spare-looking join can arm an alarm or open a gate. Holding a join is
not the same as pressing it either: a held join can ramp a dimmer or overwrite a scene. See
[the alarm joins lesson](../case-study/lesson-alarm-joins.md).

Options that were considered and rejected:

- **A scan that skips a user-supplied deny list.** The deny list is exactly what you do not know
  before the inventory. A scan is only safe once you have the information that makes it pointless.
- **A scan limited to "safe-looking" ranges.** Nothing about a join number says what it does.
  Alarm joins on that system sat in the middle of ordinary lighting numbers.

The tools that do exist answer the same question without pressing: `listen` and diagnostics read
what the processor volunteers, the panel project names every join in the clear, and `watch` lets a
person do the pressing at a real keypad, where they can see the result. The one press the tool will
make, `--enter`, is a single join you name, with `--allow-press` confirming you have checked it.

## Keep it private

An inventory, a panel project file and a join map describe the inside of a house: room names, what
is controllable, and where the alarm is. Do not commit them to a public repository.
