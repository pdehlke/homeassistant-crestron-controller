# Finding your control processor

Before anything else, you need the network address of the right Crestron box. This page is about
getting that right, because pointing Home Assistant at the wrong device is the most common way to
lose an afternoon.

## Home Assistant connects to the processor, never to a panel

**Crestron Controller connects to the control processor.** It does not connect to a touch panel, a
keypad, a remote or an app. Whatever address you type into the setup form must be the processor's.

The reason is where the program lives. A [control
processor](../concepts/glossary.md#control-processor) runs the program and owns every
[join](../concepts/joins.md). A touch panel is a screen that connects to the processor and asks it
what to show. A wall keypad is a set of buttons wired to the processor's Cresnet bus, and usually
has no network address at all. Crestron Controller replaces one touch panel, so it has to talk to
the thing a touch panel talks to.

It is an easy mistake to make. The touch panel is the box you can see and the one you think of as
"the Crestron". The processor is often in a rack, a closet or an equipment cabinet, and may not
look like a computer at all. It may not even be a standalone processor: some Crestron products have
a processor built in.

## A house can have more than one processor

Do not assume there is one. The house this project was developed in had two:

- An **AADS**, Crestron's Adagio audio distribution system. It is the whole-house amplifier and
  audio switcher, and it also has a control processor built in. Its program ran the lighting pages
  and the audio. All the TSW-752 touch panels registered with the AADS, and with nothing else.
- An **MC2E**, a separate control processor running a separate, older program. The wall keypads
  and the lighting dimmer modules were on its Cresnet bus. Its program also defined one XPanel
  slot (a software touch panel) that nothing was using.

The two programs were linked to each other over the network, so a button on a touch panel (talking
to the AADS) could switch a light whose dimmer hung off the MC2E's bus. That is why "which
processor does this panel talk to" and "which processor is this light wired to" can have different
answers in the same house.

Home Assistant ended up with two links: one to the AADS for almost everything, and one to the MC2E
for a few loads the AADS could not safely reach, because on the AADS the only joins for those loads
were shared with an alarm keypad. [The two-processor house](../case-study/two-processor-house.md)
tells the whole story, and [multiple processors](../configuration/multiple-processors.md) explains
how to set up more than one link.

So you need to find out three things:

1. Every processor in the house, with its address and model.
2. For each control point you care about, which processor it belongs to.
3. For each load you want in Home Assistant, which processor exposes a join for it, and whether that
   join is safe to write.

## Ways to find out

Each method below was used on the system this project was developed on. None of them changes
anything on the processor. Commands shown as `crestron-controller ...` use the command-line tool
described in [installing](./installing.md); `10.0.0.20` and similar addresses are examples.

### Look at your router's client list

Your router's DHCP lease table or client list shows every device on the network. Many routers also
show a manufacturer name, worked out from the device's network hardware address. Look for entries
the router attributes to Crestron. On the system this was developed on, a sweep of the network found
exactly two Crestron devices, which turned out to be the two processors. Touch panels are Crestron
devices too, so expect to see them in the list as well; the steps below tell them apart.

While you are in the router, reserve the address of every processor you find. A processor whose
address changes overnight takes every Home Assistant entity on that link down with it, and that
happened on the system this was developed on. See
[the DHCP post-mortem](../case-study/post-mortem-dhcp-address-change.md).

### Check which ports answer

On the system this was developed on, both processors answered on TCP 41794 (CIP), 41795 (the CTP
console), 23 (telnet) and 80. A processor must answer on 41794, or no panel could connect to it.

An open 41794 is necessary but this project has not established that it is sufficient: whether a
touch panel also listens there has not been checked. TSW-752 panels do run a console on 41795,
just as processors do. So use the port check to narrow the list, then confirm with the console.

### Read the console banner and `VER`

Processors and many panels have a plain-text console on telnet (port 23) and on CTP (port 41795).
The banner names the device. On the system this was developed on, each processor greeted a telnet
connection with a line of this form, which named the model first (one said `AADS`, the other
`MC2E`):

```text
<model> Control Console  Connected to Host: <hostname>
```

The read-only `VER` command reports the model and firmware. `crestron-controller ipids` sends `VER`
and `IPTABLE` and nothing else, and prints the first line of the `VER` reply:

```sh
crestron-controller ipids 10.0.0.20
```

You can also send `VER` alone with `crestron-controller console 10.0.0.20 VER`. Read the warning in
[the processor console guide](../inventory/processor-console.md) before sending anything else.

On the system this was developed on, identifying the device from its own banner turned out to
matter: after the DHCP move, "the only other Crestron device must be the processor" was a guess,
and the banner turned it into a fact before anything was pointed at it.

### Read the processor's IP table

`IPTABLE` on a processor's console lists every IP-ID its program defines, what type of connection
each one is, whether it is online right now, and the address of whatever is connected.
`crestron-controller ipids` prints it as a table and lists the IP-IDs that are defined but offline,
which are the candidates for Home Assistant to borrow ([choosing an IP-ID](./choosing-an-ip-id.md)).

This is also how you tie touch panels to processors. If a panel's address appears in a processor's
IP table as online, that panel belongs to that processor. On the system this was developed on, the
AADS's table listed the TSW-752 panels by address; the MC2E's table listed no panels at all,
only its link to the AADS and the unused XPanel slot.

Two cautions from that system. IP-IDs are written in hexadecimal: for example `20` in a table is hex
20, not decimal 20, and entering the decimal value produced a misleading "IP-ID does not exist"
refusal. And a processor that links to another processor shows that link in the same table; on that
system the link between the two appeared, with the same IP-ID, in both processors' tables.

The `WHO` console command, which is also read-only, lists the clients connected right now with
their addresses. It is a useful cross-check on the IP table.

### Ask the touch panel itself

A touch panel knows which processor it talks to. On the system this was developed on, running
`IPTABLE` on a TSW-752's own console listed exactly one entry: the processor it registers with,
which was the AADS. That entry gives you the processor's address and, in its IP-ID column, the
IP-ID the panel registers as.

```sh
crestron-controller console 10.0.0.31 IPTABLE
```

Here `10.0.0.31` is the panel's address and the answer names the processor's. This is the most
direct way to answer "which processor does this panel belong to".

Most panels also have an on-screen setup area that shows network settings, including the
processor address and IP-ID. How you reach it and what each screen is called vary by panel model
and firmware, and this project does not document them. Check your panel's own documentation, and be
careful: setup screens can change settings as easily as show them.

### Keypads: find the bus they are on

A Cresnet keypad has no network address. It belongs to whichever processor's Cresnet bus it is
wired to. On the system this was developed on, the MC2E's `REPORTCRESNET` console command listed
every keypad and dimmer module on its bus by model and Cresnet ID. It was slow, and its reply
arrived after a long wait, so give it time. A keypad on one processor's bus can still switch loads
that another processor's panels also control, if the two programs are linked.

You do not connect Home Assistant to keypads, and you do not need to. What you need from them is
their effect: when someone presses a keypad, the program usually updates the touch panel's feedback
joins too, and Home Assistant sees that. See
[watching keypads](../inventory/watching-keypads.md).

### Learn from what fails together

If you already have one link working, outages tell you which loads share it. On the system this
was developed on, two separate incidents killed every AADS-backed load in Home Assistant while the
MC2E-backed loads kept working: once when the AADS moved address, and once when a power cut
cleared a subsystem latch in the AADS program. In both cases "everything on one processor dead,
everything on the other fine" pointed at that processor's link before anything else was examined.

That is evidence you collect when it happens. Do not cause outages to find out.

## Which processor owns which loads

For Home Assistant, the question is not where a dimmer is physically wired. It is which processor
gives a panel slot a join for that load, and whether that join is safe to write.

- Build an inventory of each processor's joins separately, with the guides under
  [inventory](../inventory/inventory-overview.md). A load whose feedback appears on processor A's
  panel slot can be mapped through processor A.
- A load can appear on more than one processor. On the system this was developed on, one light
  could be driven from the AADS panel slot and from the MC2E XPanel slot, through different
  join numbers.
- When you have a choice, map the load through the processor where its joins are safe to write.
  On that system, a few lights had their only AADS joins inside a block shared with an
  alarm keypad, so they were mapped through the MC2E, whose program had no alarm logic in it.
  [Multiple processors](../configuration/multiple-processors.md) turns this into a general rule.

## Decision table

| What you know | How to find the processor |
| --- | --- |
| Nothing yet | Check the router's client list for Crestron devices, then the banner or `VER` on each to tell processors from panels. |
| A touch panel's address | Run `IPTABLE` on the panel's console. The entry it lists is its processor. |
| A touch panel you can stand in front of | Look in its on-screen setup for the processor address. Menus vary by model and firmware. |
| A candidate processor address | Read its banner, run `crestron-controller ipids` to get `VER` and the IP table, and check the table for your panels' addresses. |
| A wall keypad | It has no address. Run `REPORTCRESNET` on each processor's console to see which bus lists it. |
| A load you want in Home Assistant | Inventory each processor's panel joins and look for that load's feedback. Prefer the processor where its joins are safe to write. |
| A link that already works and a load that does not | Check whether the load died together with everything else on one link. That load belongs to that link. |
| The setup form says nothing answered | The address is wrong, not the processor's, or unreachable from Home Assistant. Start again from the router list. |

## What to write down

For each processor: its model, its reserved address, a name you will recognise in Home Assistant,
and the list of IP-IDs its program defines and which are online. With that in hand, go on to
[choosing an IP-ID](./choosing-an-ip-id.md).
