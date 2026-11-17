# Choosing an IP-ID

Home Assistant registers with the processor as one of its touch panels, so it needs an
[IP-ID](../concepts/glossary.md#ip-id): the one-byte address the program assigns to each network
device it expects. This page explains how to pick one that is safe to use.

## What an IP-ID is

When an installer writes a Crestron program, they list every network device the program will talk
to and give each one an IP-ID between hex 03 and FE. A touch panel registers with its IP-ID, and the
program answers it with the joins that slot has been wired to. The program's list is fixed: a
processor refuses to register an IP-ID its program does not define.

IP-IDs are written in hexadecimal. `2A` means hex 2A (decimal 42). The setup form accepts `0x2A`,
`2A` (read as hex, the way Crestron writes them) or `42d` (decimal, with a `d` suffix). On the
system this was developed on, typing the decimal value where hex was expected produced a refusal
saying the IP-ID did not exist, which looked like a much bigger problem than it was.

A **slot** in these docs is an IP-ID the program defines for a touch panel or software panel.
"Borrowing a slot" means registering under an IP-ID whose real device is unplugged or was never
installed.

## Step 1: list the IP-IDs the program defines

The most direct way is the processor's IP table:

```sh
crestron-controller ipids 10.0.0.20
```

This sends the read-only `VER` and `IPTABLE` console commands and prints a table of every IP-ID
the program defines, its type, whether it is online right now, and the address of whatever is
connected. It ends by listing the IP-IDs that are defined but not online, "candidate slots to
borrow". See [the processor console guide](../inventory/processor-console.md) for what the columns
mean and for what to do if the table cannot be parsed.

If you cannot reach the console, a touch panel's own IP table or setup screen shows the IP-ID that
panel uses ([finding your control
processor](./finding-your-control-processor.md#ask-the-touch-panel-itself)).

## Step 2: pick a slot nobody is using

In order of preference:

| Option | When it fits | Watch out for |
| --- | --- | --- |
| A touch panel slot that is defined but offline | A panel was removed, broken or never installed. | Make sure the panel is really gone and will not be plugged back in. |
| A touch panel you take offline on purpose | Every slot is in use and one panel is expendable. Unplugging it frees its IP-ID. | That panel stops working while Home Assistant holds its slot. This is what the system this was developed on did. |
| A software panel slot (XPanel or app) that is defined but offline | The program defines an XPanel or app slot nobody uses. | Its joins may not match a touch panel's. On the system this was developed on, an unused XPanel slot on the second processor gave access to a few loads; the app slots on the first were never tried. |

Whatever you pick, the slot's joins are whatever the program wired to that IP-ID. Two touch panels
running the same project usually expose the same joins, but a program can treat each slot
differently. On the system this was developed on, each panel slot also reported its own room name
as a serial join, which is how one unplugged panel was identified.

## Step 3: check what entering the slot does

Some programs do something on their own when a panel slot enters a section of the program, such as
switching on a light in that panel's room. These docs call that a
[courtesy action](../concepts/glossary.md#courtesy-action). Code cannot stop it; only the choice of
slot can.

On the system this was developed on, entering the lighting section from one panel's slot switched on
a light in that panel's room, and from another slot it switched on a different one. Home Assistant
enters that section at every connect, reconnect and restart, so a light came on each time. The fix
was moving to a third slot whose entry turned nothing on, tested by hand at that panel and over CIP
before the move. See [the courtesy light post-mortem](../case-study/post-mortem-courtesy-light.md).

This matters only on programs with [gated subsystems](../concepts/subsystems.md), and only once
writes are on, because a listen-only link never presses the entry join. Watch the house the first
time you turn writes on.

## Step 4: let the setup form prove it

The setup form registers once with the address and IP-ID you give it, then disconnects. It presses
nothing. The possible answers:

| Result | Meaning |
| --- | --- |
| Success | The processor accepted the IP-ID. |
| "Nothing answered on that address and port" | Wrong address, or Home Assistant cannot reach it. |
| "Its program does not define that IP-ID" | The processor answered and refused this IP-ID. Check you entered it in hex. |
| "Did not accept the registration" | Something else refused it. Authenticated or encrypted CIP is one possible cause. |

`crestron-controller listen` and `crestron-controller watch` run the same check before they start.

## Options that were rejected

- Adding a new IP-ID to the program. This would be the cleanest answer, but it requires the
  program source and Crestron's programming software, which most owners do not have. This project
  is built for people who cannot change the program.
- Sharing a live panel's IP-ID. What a processor does when two clients claim one IP-ID has not been
  established by this project. The private notes this project grew from even disagree with each
  other about it. Do not do it on purpose. See [IP-ID
  conflicts](../troubleshooting/ip-id-conflicts.md).
- Trying IP-IDs one after another until one registers. Each attempt registers, which claims
  that slot for a moment, and a slot in use may belong to a panel someone is holding. The IP table
  answers the same question without touching any slot.

## Cautions

- Never point the command-line tool at the same IP-ID that Home Assistant is using. That is two
  clients on one IP-ID. Either use a second free slot for the tool, or disable the Home Assistant
  entry while the tool runs.
- Two Home Assistant installations, or a test and a production instance, must not share a slot for
  the same reason.
- The setup form refuses to add the same processor address and IP-ID twice within one Home
  Assistant. It cannot see anything outside that Home Assistant.

Next: [installing](./installing.md).
