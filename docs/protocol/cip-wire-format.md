# CIP wire format

This is the byte-level description of the CIP traffic this project sends and understands, written
for contributors and for anyone debugging with a packet capture. You do not need it to use the
integration.

CIP (Crestron-IP) is the TCP protocol, on port 41794, that touch panels use to talk to a
[control processor](../concepts/glossary.md). Crestron does not publish it. The format here was
first worked out from [klenae/python-cipclient](https://github.com/klenae/python-cipclient) (MIT)
and then re-implemented and checked against real processors. The code is
`custom_components/crestron_controller/cipcore/protocol.py` (pure byte functions, no sockets) and
`cipcore/client.py` (the session). Where the two disagree with this page, the code is right and
this page needs fixing.

All byte values below are hexadecimal. Joins are numbered from 1 in every document, join map and
API in this project, as Crestron join maps are; on the wire they are 0-based, so join 24 travels as
`17`.

Only plain CIP is covered. Authenticated or TLS CIP (port 41796) is not supported; see
[ADR 0008](../adr/0008-plain-cip-only-for-now.md).

## What was observed and what was not

Everything in this table is implemented. The right-hand column says how much trust it deserves.
"Observed" means seen working against a real processor on the system this was developed on, with
the exact bytes recorded in tests. "From klenae" means taken from klenae/python-cipclient and not
yet seen accepted by a processor in this project.

| Message | Direction | Status |
| --- | --- | --- |
| Register request (type `0F`) | processor to client | Observed |
| Registration (type `01`) | client to processor | Observed |
| Registration result, success | processor to client | Observed, with a status byte klenae's client rejects (see below) |
| Registration result, IP-ID not defined (`ff ff 02`) | processor to client | From klenae, not recorded in the notes this was written from |
| Disconnect (type `03`) | processor to client | From klenae, not recorded in the notes this was written from |
| Heartbeat (type `0D`) and reply (type `0E`) | both | Observed |
| Update request, end-of-query, end-of-query acknowledgement | both | Observed |
| Digital join, press and release | client to processor | Observed |
| Digital join feedback, including several joins in one frame | processor to client | Observed |
| Analog and serial feedback | processor to client | Observed. Which of the variants below carried it was not recorded variant by variant; the decoder accepts all of them. |
| Analog join write | client to processor | From klenae. Never seen accepted (see below). |
| Serial join write | client to processor | From klenae. Never seen accepted. |

The analog write caveat in full: the system this was developed on had no program logic that
accepts an analog value from a panel. Its only two analog joins were feedback-only, and two writes
to one of them produced no response. That is not evidence the encoding is wrong, because there was
no join that should have accepted it. It is simply untested. If you get analog or serial writes
working on your system, an issue with a packet capture would let this table change.

## Framing

Every message in both directions is one frame:

```text
<type> <length hi> <length lo> <payload ...>
```

The length is the payload length in bytes, big-endian, not counting the three header bytes. A
single TCP read can hold several frames or part of one, so `split_frames()` cuts complete frames off
the front of a buffer and keeps the remainder for the next read.

| Type | Meaning |
| --- | --- |
| `01` | Registration, client to processor |
| `02` | Registration result |
| `03` | Disconnect: the processor ends the session |
| `05` | Data: joins, update request, end-of-query |
| `0D` | Heartbeat |
| `0E` | Heartbeat reply |
| `0F` | Register request: the processor asks the client to register |
| `12` | Serial join data in its own frame type |

## Registering

1. The client opens TCP 41794. The processor sends a register request, type `0F`.
2. The client answers with its registration, which carries the IP-ID it claims:

   ```text
   01 00 0b 00 00 00 00 00 <ipid> 40 ff ff f1 01
   ```

   The IP-ID must be between `03` and `FE`. The other bytes are copied from klenae's client; their
   individual meanings are not established here.
3. The processor answers with type `02`:
   - `00 00 00 <status>` means registered. klenae's client accepts only status `1f`. A 2009-era
     processor on the system this was developed on answered `00 00 00 03` and was registered
     perfectly well, so this project accepts any `00 00 00 xx` and logs the status byte.
   - `ff ff 02` means the IP-ID is not defined in the running program. The integration turns this
     into a repair.
   - Anything else is treated as a refusal and shown with its bytes.
4. On success the client sends an update request and the processor sends its registration dump.

`async_probe()` in `client.py` runs exactly this much and disconnects, pressing nothing. The config
flow uses it to check an address and IP-ID before saving.

Registration through the end of the dump took about 1.1 seconds on the system this was developed
on, with roughly 150 frames arriving in under a second.

## Data frames (type 05)

The payload of a type `05` frame is:

```text
00 00 <count> <datatype> <body ...>
```

`<count>` is the number of bytes from `<datatype>` to the end. The data types:

| Datatype | Meaning |
| --- | --- |
| `00` | Digital joins |
| `01` | Analog join, short form |
| `02` | Serial join, indexed text form |
| `03` | Update request and end-of-query |
| `14` | Analog joins |
| `15` | Serial join |

### Digital joins (datatype 00)

Identical in both directions. For each join, two bytes: the 0-based join's low byte, then a byte
holding its next seven bits with the top bit **set for low** and **clear for high**.

```text
press join 24     05 00 06 00 00 03 00 17 00
release join 24   05 00 06 00 00 03 00 17 80
```

A press is a high followed by a low after a short hold (`Timing.press_hold_seconds`, 0.12 s by
default). `CipClient._press()` guarantees the release is sent even if the press is cancelled
halfway, because a join left high is a press-and-hold, and holding can ramp a dimmer or overwrite a
scene.

One feedback frame can carry several joins as consecutive pairs. The processor this was developed
against packed five into a single frame; reading only the first pair loses the rest.
`decode_digitals()` reads them all. The highest join the encoding can carry is 32768.

### Analog joins (datatypes 14 and 01)

Datatype `14`: four bytes per join, the 0-based join big-endian then the value big-endian (0 to
65535). Several joins can follow one another.

Datatype `01`: one byte of 0-based join, then two bytes of value.

An analog write, from klenae, is datatype `14` with one join:

```text
05 00 08 00 00 05 14 <join hi> <join lo> <value hi> <value lo>
```

### Serial joins (datatypes 15 and 02, and type 12)

Datatype `15`: the 0-based join big-endian, one further byte, then the text (decoded as Latin-1).

Datatype `02`: text of the form `#N,...`; the number before the comma is taken as the join.

Type `12` frames carry serial data in their own frame type. The client reads the 0-based join from
payload bytes 5 and 6 and the text from byte 8 on. A serial write, from klenae, is:

```text
12 <len hi> <len lo> 00 00 00 <count> 34 <join hi> <join lo> 03 <text ...>
```

### Update request and end-of-query (datatype 03)

```text
update request              05 00 05 00 00 02 03 00
end-of-query (processor)    a type 05 frame whose datatype is 03 and whose body starts with 1c
acknowledgement             05 00 05 00 00 02 03 1d
```

When the client sees end-of-query it sends the acknowledgement, then a heartbeat, marks the dump
complete, and starts bring-up (entering the default subsystem, on a gated program). A slot with
nothing to report might never send end-of-query, so two seconds of quiet after registering
(`Timing.sync_quiet_seconds`) also counts.

The marker is not the last word. On the system this was developed on, the registration dump's
final frame arrived 38 ms after its end-of-query marker, so anything that waits for the marker
alone must still accept frames that follow it.

Re-sending the update request in the middle of a session returned the full state again, about 149
frames in 0.86 seconds, ending with the marker. The client uses that as its
[re-poll](../concepts/glossary.md) after entering a subsystem. Some processors may never answer a
second update request; set `repoll_after_entry: false` for those.

### Entry dumps have no end marker

When a slot presses a subsystem's entry join, the processor sends that subsystem's joins, and no
end-of-query marker follows: none of the entries timed on the system this was developed on
produced one. The only signal that an entry dump has finished is the link going quiet, so the
client waits for both a minimum time (`Timing.entry_min_seconds`) and a quiet window
(`quiet_seconds` per subsystem), measured on data frames only. Entry dumps are also partial. See
[post-mortem-partial-entry-dumps.md](../case-study/post-mortem-partial-entry-dumps.md).

## Heartbeat

```text
heartbeat (client)    0d 00 02 00 00
```

The client sends one every 15 seconds (`Timing.heartbeat_interval`). The processor replies with
type `0E`. The client also sends one straight after acknowledging an end-of-query.

The interval is comfortable rather than tight. One processor on the system this was developed on
kept a registered client connected and still sending it data after 149 seconds of complete silence
from the client, with no heartbeats at all. Do not rely on that being true of every processor.

## Disconnects

A type `03` frame from the processor ends the session. The client records it as a
[displacement](../concepts/glossary.md) and reconnects with backoff. Three or more displacements
inside ten minutes raise a repair suggesting that something else may be using the IP-ID. What a
processor does when two clients claim one IP-ID is not established by this project; see
[ip-id-conflicts.md](../troubleshooting/ip-id-conflicts.md).
