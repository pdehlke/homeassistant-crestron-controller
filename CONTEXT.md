# CONTEXT.md

The vocabulary this project uses, for contributors and coding agents. Novice-facing definitions
of the same words, with more explanation, are in
[docs/concepts/glossary.md](./docs/concepts/glossary.md). When a term changes here, change it
there too.

## Hardware and network

**Control processor**: the Crestron box that runs the program: a processor such as an MC2E,
PRO3, CP3 or CP4, or a device with a processor built in, such as an AADS audio distribution
system. It owns the joins. Home Assistant connects to the processor, never to a touch panel.

**Touch panel**: a Crestron screen (TSW, TPMC and similar) that talks to a processor over the
network. This project impersonates one.

**Control point**: everywhere a person can control the system: touch panels, keypads, remotes.
Used in the docs only when explaining where to look for which processor a control point talks
to.

**Link**: one CIP session from Home Assistant to one processor under one IP-ID. One config entry
is one link. A house with two processors needs two links, and so two config entries.

**IP-ID**: a one-byte address (hex 03 to FE) the processor's program assigns to each network
device it expects. A panel slot is identified by its IP-ID.

**Slot**: an IP-ID the program defines for a touch panel or XPanel, which this project registers
as. "Borrowing a slot" means registering as an IP-ID whose real device is unplugged or was never
installed.

**CIP**: Crestron-IP, the TCP protocol on port 41794 that panels use to talk to processors.
**Encrypted CIP** is the same frames inside TLS, on port 41796 by default. **Authenticated CIP**
adds a username and password and is not supported.

**Older encryption** (`legacy_tls`): a per-link opt-in that also accepts TLS 1.0 and 1.1, for
processors too old for 1.2. Never a fallback the client takes on its own.

**Certificate pin**: the SHA-256 fingerprint of a processor's TLS certificate, stored in the config
entry when it is created or reconfigured. An encrypted link refuses a processor whose certificate
no longer matches.

**CTP console**: the processor's and panel's text console, on port 41795 (and telnet on 23).
Used read-only by the CLI for `VER`, `IPTABLE` and file retrieval.

## Joins

**Join**: one numbered signal between a panel and the program. Three kinds: **digital**
(on/off, buttons and feedback), **analog** (0 to 65535, levels) and **serial** (text). Numbered
from 1 in every document and API here; the wire is 0-based.

**Press**: a digital join going high then low, as a finger on a button does. Holding is not the
same as pressing: a held join can ramp a dimmer or overwrite a scene.

**Feedback join**: the digital join that reports a load's state. Often the same number as the
press join, sometimes not.

**Alias**: another join that reports the same load, because the load appears on several panel
pages. Written `also_reports` in a join map.

**SmartObject**: a list on a panel page (sources, rooms, a playlist), numbered as an object. Its
joins are a namespace of their own: object 3's serial 11 is not the program's serial 11. Read-only
here, keyed by `(kind, join, smart object)` with object 0 for the program's own joins, and not
verified on real hardware
([ADR 0012](./docs/adr/0012-smartobject-joins-are-their-own-namespace.md)).

**Registration dump**: the burst of join values a processor sends after a client registers and
asks for an update. Ends with an end-of-query marker.

## Subsystems

**Gated subsystem**: a part of the program (Lights, Audio, Climate) that a slot must enter by
pressing a home-page button before the processor reports or acts on any of its joins. Not every
program has these.

**Entry join**: the home-page button that enters a gated subsystem.

**Entry dump**: the joins a processor sends after an entry press. Partial, not deterministic,
and carries no end marker, so its end is detected by quiet. Merged into state, never used to
rebuild it.

**Re-poll**: re-sending the update request after an entry, to get the full state with an end
marker.

**Courtesy action**: anything the program does on its own when a slot enters a subsystem, such
as switching on a light in that panel's room. Code cannot stop it; only the choice of slot can.

**Idle return**: sending a slot back to its default subsystem after it has been idle elsewhere,
so changes made at wall keypads stay visible.

## Configuration

**Join map**: the YAML file, one per link, that says which joins become which Home Assistant
entities, which subsystems exist, and which joins must never be written.

**Listen-only**: a link with writes disabled. Reads every join, writes none, including entry
joins. The default.

**Never-write list**: joins that must never be written, whatever else the join map says. Checked
at the wire.

**Allow list**: the joins a link may write once writes are on: every join an entity writes, plus
entry joins. Derived from the join map, never written by hand.

**Press mode**: how a light or switch is driven: `toggle` (one join, made discrete by reading
feedback), `on_off` (separate on and off joins, still confirmed by feedback) or `momentary` (no
feedback, state assumed).

**Discrete synthesis**: turning a toggle button into separate on and off commands by reading
feedback first, pressing only on a mismatch, and waiting for confirmation.

## Failure vocabulary

**Displacement**: the processor ending our session with a disconnect frame. Repeated
displacement may mean another device is using the IP-ID; this project has not established how
processors behave with two claimants, so it is a lead, not a diagnosis.

**Greeting**: the register request (type 0F) a processor sends as soon as a client connects. No
greeting within `greeting_timeout` usually means one end expects TLS and the other does not.

**Synced**: registered, the dump received, and the default subsystem entered where there is one.
Entities only report state once their link is synced and their subsystem has been entered.
