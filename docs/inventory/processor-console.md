# The processor console

Crestron processors and many touch panels have a plain-text console, the
[CTP console](../concepts/glossary.md#ctp-console). The `cip-panel` tool uses it for two jobs:
`cip-panel ipids` reads the processor's IP table, and `cip-panel console` sends commands you type.
This page covers both. How the console works on the wire, and why file transfer needs port 41795,
is in [the CTP console and file retrieval](../protocol/ctp-console-and-file-retrieval.md).

## Ports

| Port | What it is | Use it for |
| --- | --- | --- |
| 23 | Telnet. The default for `ipids` and `console`. | Reading commands such as `VER` and `IPTABLE`. |
| 41795 | CTP, the same console without telnet negotiation. Pass `--port 41795`. | The same commands, plus file transfer (see [panel project files](./panel-project-files.md)). Some commands blocked on port 23 are allowed here. |

The tool refuses every telnet option the device offers rather than implementing any, because
nothing it does needs one.

## `cip-panel ipids`: list the IP-IDs

```sh
cip-panel ipids 10.0.0.20
```

This connects, sends `VER` and then `IPTABLE`, and nothing else. It prints the first line of the
`VER` reply and the IP table as a table. The output looks like this (invented values):

```text
Version: <the first line of the processor's VER reply>

IP-ID  Type  Status   Address          Port   Description
0x0A   CIP   ONLINE   MC2E
0x2A   Gway  ONLINE   127.000.000.001  41794
0x31   Gway  ONLINE   127.000.000.001  41794
0x40   Peer  OFFLINE  10.0.0.45        41794

Defined but not online: 0x40. These are candidate slots to borrow.

Note: 'Gway' entries can read ONLINE with no panel connected. Before borrowing one, make sure its physical panel is unplugged or switched off.
```

The columns:

| Column | Meaning |
| --- | --- |
| IP-ID | The slot's address, in hex. `16` in a raw `IPTABLE` reply is hex 16, which is 22 in decimal. Always enter IP-IDs in hex. |
| Type | What kind of connection the program defines for that IP-ID, as the processor names it (for example `Gway`, `Peer`, `CIP`). |
| Status | `ONLINE`, `OFFLINE` and similar, as the processor reports it. See the caution below. |
| Address | The address of whatever is connected, or another identifier the processor puts there. |
| Port | The remote port, when the processor prints one. |
| Description | Extra descriptive columns newer firmware prints, when present. |

An IP-ID that is missing from the table cannot be used at all: the processor refuses to register
it. The line "Defined but not online" lists every entry whose status is anything other than
`ONLINE`, as candidates for Home Assistant to borrow.

### What one real processor showed

`ipids` was run against a real processor while this project was being built. On that one system:

- The table parsed correctly.
- The processor's own CIP connection to a second processor appeared as an entry of type `CIP`,
  with the second processor's model name in the address column. That is one way to discover that
  a house has two processors.
- Touch panel slots appeared as type `Gway`, at address `127.000.000.001` (the processor's own
  loopback address). They go through the processor's internal gateway.
- **Gateway panel slots read `ONLINE` even with the physical panel unplugged**, and one slot's
  status changed between two reads a few minutes apart with nothing touched.

So `ONLINE` on a `Gway` entry does not prove a panel is connected, and `OFFLINE` there would not
prove it is free either. The candidate list can miss a slot that is really free, and the tool
prints the note shown above whenever any `Gway` entry reads `ONLINE`. Check the physical panel:
make sure the panel whose slot you want to borrow is unplugged or switched off, and will stay that
way. [Choosing an IP-ID](../getting-started/choosing-an-ip-id.md) covers how to pick.

### When the table does not parse

The parser expects a header line containing `CIP_ID` followed by one row per entry. If the reply
does not look like that, `ipids` prints "Could not parse the IP table; the raw reply follows." and
the raw text, rather than a table that might be wrong. Read the raw text yourself; the IP-ID is the
first column.

### Pointing it at a panel

The host can be a touch panel instead of a processor. On the system this was developed on, a
TSW-752's own `IPTABLE` listed exactly one entry: the processor it registers with, and the IP-ID it
registers as. That is the most direct answer to "which processor does this panel belong to". See
[finding your control processor](../getting-started/finding-your-control-processor.md#ask-the-touch-panel-itself).

## `cip-panel console`: send a command

```sh
cip-panel console 10.0.0.20 VER
cip-panel console 10.0.0.20 --each VER IPTABLE WHO
```

**Console commands can change processor state, and some can restart the program or erase it. You
are responsible for what you send.**

By default every argument after the host is joined into one command line. With `--each`, each
argument is sent as a separate command. Each reply is printed under a `=== COMMAND ===` heading,
with the echoed command and the trailing prompt removed. `--wait SECONDS` sets how long to wait for
each reply (default 4).

Commands that were read-only on the system this was developed on: `VER`, `IPTABLE`, `WHO` (lists
the clients connected right now), `ERR`, `PROGUPTIME` and `REPORTCRESNET` (lists the keypads and
modules on the processor's Cresnet bus). The tool's own help also suggests `PROGCOMMENTS`. Firmware
varies, so check your own model's documentation before sending anything else.

`REPORTCRESNET` was slow there: one reply arrived after a 45-second window had closed and turned up
inside the next command's reply. Give slow commands a long `--wait`, or send a cheap command after
them and read the reply from that.

### The denylist

Before connecting, the tool checks every command against a small denylist and refuses with exit
status 2 if one matches. Nothing is sent. It refuses:

- Commands that restart, erase, reflash or rewrite the program, files, users or IP table, whatever
  their arguments: `REBOOT`, `PROGRESET`, `PROGLOAD`, `INITIALIZE`, `DEL`, `ERASE`, `FORMAT`,
  `PUF`, `FWUPDATE`, `PASSWORD`, `ADDUSER` and similar.
- Commands that read a setting bare and change it with arguments, when given arguments:
  `IPTABLE`, `IPT`, `IPADDRESS`, `DHCP`, `HOSTNAME`, `TIME`, `DATE`, `AUTHENTICATION`, `SSL` and
  similar. Bare, they are allowed.
- Any command starting with `ADD`, `REM`, `DEL` or `SET`.

This list is a seatbelt. It cannot promise safety: Crestron firmware has hundreds of commands, varies by
model and version, and accepts abbreviations. A command the list does not refuse is not thereby
safe.

## Logging in

None of the consoles on the system this was developed on asked for a password. If yours does,
pass `--username NAME`. The tool answers one username prompt and one password prompt. The password
comes from the environment variable named by `--password-env VAR`, or, without that, from a prompt
that appears only if the console asks. There is no option to put a password on the command line,
because it would land in shell history.

Login support has not been tested against a real processor with authentication enabled. If it
misbehaves, run with `-v` (`cip-panel -v ipids ...`) to see what was sent and received.

## Exit status

| Status | Meaning |
| --- | --- |
| 0 | Done. For `ipids`, this includes printing the raw reply when the table did not parse. |
| 1 | Could not connect, or the console refused the login. The message says which. |
| 2 | `console` refused a command on the denylist before connecting. |
