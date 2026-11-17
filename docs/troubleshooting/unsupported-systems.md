# Unsupported systems

What CIP Panel cannot do, what it has not been tested on, and what it does without evidence that it
works. Some of these are limits of the approach and will not change; others are gaps in this
version.

## Limits of the approach

CIP Panel impersonates a touch panel. It can see and do only what the program lets a touch panel
slot see and do.

| Situation | Why it cannot work | What you can do |
| --- | --- | --- |
| The program defines no panel or XPanel IP-ID you can borrow | A processor refuses an IP-ID its program does not define, and adding one means changing the program. | Take an existing touch panel offline to free its slot ([choosing an IP-ID](../getting-started/choosing-an-ip-id.md)), or have the program changed. |
| A load does not appear on any panel page | If no panel button or feedback join exists for it, there is nothing to map. On the system this was developed on, one keypad button switched a load through a join that no panel slot on either processor could see; reaching it would have needed new program logic. | None from this project. |
| The program does not send feedback for a load to panels | Without feedback, toggle and on_off entities cannot work. | Map it as `press: momentary`, which is assumed state. |
| Devices that are not on the network | Cresnet keypads, dimmer modules and other bus devices are reached only through the processor's program. | Map their effect through panel joins, as usual. |
| A processor that requires authenticated CIP, or encrypted CIP on port 41796 | Only plain CIP on port 41794 is implemented. | The setup form reports a refused registration. No workaround in this version. |

## Not built in version 1

- `select` and `media_player` entities. Audio sources and zones are not modelled. A source
  button can be a `button`, and an audio level can be a `sensor` or `number`.
- Cursor-zone audio. Some programs control many audio zones through one set of joins plus a
  "which zone" selector. The pattern is documented in
  [cursor-zone audio](../patterns/cursor-zone-audio.md), and deferred for the reasons in
  [ADR 0009](../adr/0009-cursor-zone-audio-deferred.md).
- Settable reconnect backoff, confirmation timeout and attempts. These are fixed. The other
  timeouts can be changed in [timing](../configuration/join-map-reference.md#timing).
- Cross-processor aliases. A load on two processors cannot be one entity. See
  [multiple processors](../configuration/multiple-processors.md).
- Join scanning. There is deliberately no command that presses joins to discover what they do.
  See [ADR 0007](../adr/0007-no-join-scanning-in-the-cli.md).

## Implemented but not verified on real hardware

| Feature | Status |
| --- | --- |
| Analog writes (writable brightness, writable `number`) | The encoding comes from [klenae/python-cipclient](https://github.com/klenae/python-cipclient) and matches that client, but no processor in this project has been seen to accept one: the analog joins on the system this was developed on were feedback only. |
| Serial writes | Encoded the same way and equally unverified. No entity type writes serials in this version. |
| Console login in the command-line tool | Implemented, but untested against a processor that actually asks for a password. Both consoles on the system this was developed on had none. |
| Two clients on one IP-ID | Unknown. See [IP-ID conflicts](./ip-id-conflicts.md). |
| Panel project files other than TSW x52 `Environment.xml` | `cip-panel panel parse` reads only the x52 format. Newer panels (x60, x70) use HTML5 project archives, and older panels use other formats; both are detected and refused. See [panel project files](../inventory/panel-project-files.md). |
| Join offsets in panel projects | The parser applies page and subpage join offsets, but every project it was developed against had them all at zero. Where an offset was applied, its output says so. |

Registration, heartbeats, the update request, every digital encoding, and analog and serial reads
were all observed on real processors. See [the CIP wire format](../protocol/cip-wire-format.md).

## Processors

The project was developed against two processors in one house: an MC2E and the processor built into
an AADS. The registration result handling accepts any success code, because at least one older
processor answered with a status that the reference client did not accept; on the system this was
developed on, a borrowed panel slot registered with that status.

Any processor that accepts a plain CIP touch panel or XPanel connection on an IP-ID its program
defines should work in principle. Newer processor families have not been tested, and this project
does not know whether their default security settings allow plain CIP. If you try one, the setup
form tells you quickly: success, IP-ID not defined, or refused.

## Home Assistant

The integration is tested against Home Assistant 2026.10.4 in the
`pytest-homeassistant-custom-component` harness, and declares 2026.10.0 as its minimum. Older
versions are not supported.

## Not affiliated

This project is not affiliated with or endorsed by Crestron Electronics. See
[the disclaimer](../about/disclaimer-and-credits.md).
