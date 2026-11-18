# Glossary

Plain definitions of the words these docs use. The terse version for contributors is
[CONTEXT.md](../../CONTEXT.md); when a term changes there, it changes here too. Terms are grouped by
topic, and each heading is a link target other pages use.

## Hardware and network

### Control processor

The Crestron box that runs the program. It may be a dedicated processor (an MC2E, PRO3, CP3 or CP4,
for example) or a product with a processor built in, such as an AADS audio distribution system. The
processor owns every join. **Home Assistant connects to the processor, never to a touch panel.** A
house can have more than one. See [finding your control
processor](../getting-started/finding-your-control-processor.md).

### Program

The logic an installer wrote for your system and loaded onto the processor, usually built in
Crestron's SIMPL Windows. It decides what every button does. Crestron Controller does not change it
and does not need its source.

### Touch panel

A Crestron screen (TSW, TPMC and similar) that connects to a processor over the network and shows
pages the installer designed. Crestron Controller impersonates one.

### XPanel

A software touch panel that runs on a computer, with its own IP-ID in the program. An unused XPanel
slot can be borrowed the same way as an unplugged touch panel's.

### Keypad

A wall plate of buttons, usually wired to the processor's Cresnet bus. Keypads have no network
address and Home Assistant never talks to them; it sees their effect through the joins the program
updates.

### Cresnet

Crestron's wired bus between a processor and its keypads, dimmer modules and other devices. It is
not on your network. Each processor has its own.

### Control point

Anywhere a person can control the system: touch panels, keypads, remotes. Used when explaining how
to find out which processor a control point belongs to.

### CIP

Crestron-IP, the TCP protocol on port 41794 that touch panels use to talk to a processor. Crestron
Controller speaks plain CIP, and encrypted CIP (CIP inside TLS, port 41796) though that has not
been verified on real hardware. Authenticated CIP, which needs a username and password, is not
supported.

### TLS

The encryption standard behind encrypted CIP, and the same one web browsers use for `https`
websites. It comes in versions: 1.2 and 1.3 are current, while 1.0 and 1.1 are older and weaker.
Crestron Controller uses 1.2 or newer unless you turn on the older-encryption setting for a
processor. See [encrypted CIP](../configuration/encrypted-cip.md).

### Certificate

A processor's digital ID card, which it shows whenever something connects over encrypted CIP. Its
fingerprint is a long string unique to that certificate. Home Assistant remembers the fingerprint
when you set up a processor and refuses to connect if it changes.

### CTP console

The plain-text command console on processors and many panels, on TCP port 41795. The same console is
usually also on telnet, port 23. The command-line tool uses it read-only for `VER`, `IPTABLE` and
file retrieval.

### IP-ID

A one-byte address, between hex 03 and FE, that the program assigns to each network device it
expects. Written in hex: `2A` means hex 2A, decimal 42. A processor refuses to register an IP-ID its
program does not define. See [choosing an IP-ID](../getting-started/choosing-an-ip-id.md).

### Slot

An IP-ID the program defines for a touch panel or XPanel. Borrowing a slot means registering as an
IP-ID whose real device is unplugged or was never installed.

### Link

One CIP session from Home Assistant to one processor under one IP-ID. One config entry is one link.
Two processors need two links. Each link has its own Link sensor.

## Joins

### Join

One numbered signal between a panel and the program. Numbered from 1 in these docs and in join
maps. See [joins](./joins.md).

### Digital join

An on or off signal. Buttons send digital joins; the processor sends digital joins back as feedback.

### Analog join

A number from 0 to 65535, used for levels such as brightness or volume.

### Serial join

Text, used for labels and names the processor fills in on a panel page.

### SmartObject

A list on a touch-panel screen: the music sources you can choose from, the rooms in the house, a
playlist, a set of saved scenes. Each list is a SmartObject, with a number of its own. The system
sends a list's contents in a separate format from ordinary buttons and sliders, and numbers the
list's joins in the list's own range, so a list's text 11 is a different signal from the rest of
the system's text 11. That is why a join map entry that reads from a list says which list, with
`smart_object:`.

Crestron Controller can read lists and, with writes turned on, choose from them, but has not been
tested against a real processor that uses them, so nobody has confirmed either works yet. If your
panels have no lists, SmartObjects do not affect you. See
[reading and choosing from lists](../configuration/reading-lists.md).

### Press

A digital join going high and then low, as a finger on a button does. Crestron Controller holds it
high for 0.12 seconds by default.

### Hold

Keeping a digital join high. Not the same as a press: holding can ramp a dimmer or overwrite a
scene. Crestron Controller makes sure every press it starts is released.

### Feedback join

The digital join that reports a load's state. Often the same number as the button that switches it,
sometimes not.

### Alias

Another join that reports the same load, usually because the load appears on more than one panel
page. Written `also_reports` in a join map.

### Registration dump

The burst of join values a processor sends after a panel registers and asks for an update. It ends
with an end-of-query marker.

## Subsystems

### Subsystem

A section of the program, such as Lights, Audio or Climate. See [subsystems](./subsystems.md).

### Gated subsystem

A subsystem a slot has to enter, by pressing a home-page button, before the processor reports or
acts on any of its joins. Not every program has these.

### Entry join

The home-page button join that enters a gated subsystem.

### Entry dump

The joins a processor sends after an entry press. It is partial, not the same from one entry to the
next, and has no end marker, so its end is detected by the processor going quiet. Crestron
Controller merges it into what it already knows and never rebuilds state from it.

### Re-poll

Sending the update request again after an entry, to get the full state with an end marker.

### Courtesy action

Anything the program does on its own when a slot enters a subsystem, such as switching on a light in
that panel's room. Code cannot stop it; only the choice of slot can.

### Idle return

Sending a slot back to its default subsystem after it has been idle in another one, so changes made
at wall keypads stay visible.

### Synced

Registered, the dump received, and the default subsystem entered where there is one. Entities only
report state once their link is synced and their subsystem has been entered.

## Configuration

### Join map

The YAML file, one per link, that says which joins become which Home Assistant entities, which
subsystems exist, and which joins must never be written. See the
[join map reference](../configuration/join-map-reference.md).

### Listen-only

A link with writes turned off. It reads every join and writes none, not even entry joins. The
default.

### Never-write list

Joins that must never be written, whatever else the join map says. Checked at the last moment before
bytes reach the network. See [write safety](../configuration/write-safety.md).

### Allow list

The joins a link may write once writes are on: every join an entity writes, plus entry joins. Worked
out from the join map, never written by hand.

### Press mode

How a light or switch is driven: `toggle`, `on_off` or `momentary`. See
[press modes](../configuration/press-modes.md).

### Discrete synthesis

Turning a toggle button into separate on and off commands: read the feedback first, press only if it
differs from what was asked, and wait for the processor to confirm.

### Assumed state

Home Assistant's term for an entity whose state is whatever it was last told, because nothing
reports the real state. `momentary` lights and switches are assumed state.

## Failures

### Displacement

The processor ending the session by sending a disconnect. Repeated displacement may mean another
device is using the same IP-ID. This project has not established how processors behave with two
claimants, so it is a lead, not a diagnosis. See [IP-ID
conflicts](../troubleshooting/ip-id-conflicts.md).

### Repair

A Home Assistant notice under Settings > Repairs. Crestron Controller raises one when a link has
been down for ten minutes or more, when the processor refuses the IP-ID, and when the session keeps
being ended. See [link health and repairs](../troubleshooting/link-health-and-repairs.md).
