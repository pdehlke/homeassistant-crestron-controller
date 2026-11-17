# The CTP console and file retrieval

Crestron processors and touch panels run a plain-text console. The `cip-panel` CLI uses it, read-only,
to identify a processor (`VER`), list the IP-IDs its program expects (`IPTABLE`), and fetch a
touch panel's project file so the joins can be read by name instead of discovered by pressing. This
page explains the two console ports, why file retrieval only works on one of them, and how the
transfer itself works. The code is `src/cip_panel_cli/console.py` and `src/cip_panel_cli/ctp.py`.

What follows was observed on one system: two processors (an AADS and an MC2E) and TSW-752 panels.
Other models and firmware may behave differently.

## Two ports, one console

| Port | What it is | Notes |
| --- | --- | --- |
| 23 | Telnet | Opens with telnet option negotiation. Doubles every `FF` byte in data, as telnet must. Some commands are refused here with "Command Blocked from this console type". |
| 41795 | CTP | The same console with no negotiation and no byte doubling, so binary data arrives exactly as sent. Commands blocked on port 23 were allowed here. |

The CLI's console client refuses every telnet option outright rather than implementing any,
because nothing it does needs one. On CTP it skips that filtering entirely: scanning CTP traffic
for telnet escape bytes would corrupt a binary transfer.

None of the consoles on the system this was developed on asked for a password. The CLI can answer
one username prompt and one password prompt (`--username`, and `--password-env` to read the
password from an environment variable rather than the command line), but that path has not been
tested against a processor that actually requires a login.

## Read-only by intent

`cip-panel ipids` sends `VER` and `IPTABLE` and nothing else. `cip-panel console` sends whatever you
type, after checking it against a small deny list of commands that restart, erase, reflash or change
settings. That list is a guard against slips. It cannot know every command or every abbreviation a
given firmware accepts, so a command it does not refuse is not thereby safe. Commands that earned
their place in diagnosing real problems on the system this was developed on, all read-only there,
include `VER`, `IPTABLE`, `WHO`, `ERR`, `PROGUPTIME` and `REPORTCRESNET`. See
[processor-console.md](../inventory/processor-console.md).

One practical note: `REPORTCRESNET` on one processor replied well after a 45-second read window had
closed, and its output turned up inside the next command's reply. A slow command may need a cheap
command sent after it, with the reply read from that one.

## Fetching a file with XGETFILE

`XGETFILE <path>` makes the device send a file over the same console connection using XMODEM. It
works on port 41795 and not on port 23, for two independent reasons:

- The telnet console refuses it ("Command Blocked from this console type").
- Even if it were allowed, telnet's doubling of `FF` bytes and its interleaved negotiation would
  corrupt a binary transfer. CTP has neither.

The path goes unquoted. Quoting it made the device look for a name that includes the quote marks,
and it answered "Not Found" for a valid path. `ctp.request_file()` sends the command and reads the
device's reply up to the start of the transfer; `ctp.refusal()` recognises the device turning the
request down.

### The transfer

`ctp.receive()` is a standard XMODEM receiver:

- It asks for CRC-16 first by sending `C`. Until the sender starts, it alternates `C` with `NAK`, so
  a sender that only knows the older checksum variant still starts.
- It accepts both 128-byte (`SOH`) and 1024-byte (`STX`) blocks, checks the block number and its
  complement and the CRC (polynomial 1021, zero seed, no reflection) or checksum, and sends `NAK`
  for anything damaged so the sender repeats it.
- A repeat of the previous block means an acknowledgement was lost; it is acknowledged again and
  only the first copy kept. A block that passes its check but is out of sequence cancels the
  transfer rather than silently dropping data.
- Mid-transfer silence is left to the sender's own retry timer. A panel reading slow flash pauses,
  and a `NAK` sent into that pause would only make it resend a block already on its way.
- If the sender cancels or goes silent, the receiver raises an error instead of returning partial
  data, because writing a truncated file and reporting success is the worse failure after a
  ten-minute wait.

XMODEM carries no file length, so the last block is padded. `ctp.strip_padding()` removes trailing
`SUB` (`1A`) bytes. The panel project file observed here was padded with NUL bytes after its closing
`</Crestron>` tag instead, which makes it invalid XML until the tail is cut;
`cip_panel_cli/panel.py` trims it.

## How long it takes

The speed is the device's, not the network's.

| File | Size | Time |
| --- | --- | --- |
| TSW-752 project, `\display\swf\Environment.xml` | about 3.5 MB (3,583,494 bytes) | 705 seconds, roughly five 1K blocks per second |
| A processor's compiled program file | much smaller | about four seconds |

The panel reads its flash slowly and keeps working normally while it does. `cip-panel panel fetch`
warns that a TSW-752 takes roughly 10 to 15 minutes.

The panel project is UTF-16 XML that names every page, button and join number in the clear. The
same project was found on all four panels in that house, so one fetch covered them all. Only the
TSW x52 format is understood by `cip-panel panel parse`; newer panels pack HTML5 projects in
archives, which are detected and refused. See
[panel-project-files.md](../inventory/panel-project-files.md).

## Why bother

Reading the joins from a project file is the safe way to learn them. The alternative, pressing
joins to see what they do, risks arming an alarm or opening a gate on a program that reuses join
numbers across pages. That is why this project has a file fetcher and deliberately has no
join-scanning command ([ADR 0007](../adr/0007-no-join-scanning-in-the-cli.md)).

The CLI only fetches panel project files. Processors also answered `XGETFILE` for their own program
files on the system this was developed on, but the CLI has no command for that and a compiled
program is not something it can parse.

A project file describes a private residence in detail. Do not commit one to a public repository.
