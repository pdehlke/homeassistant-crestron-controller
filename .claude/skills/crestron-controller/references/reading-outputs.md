# Reading crestron-controller output

Join numbers are 1-based everywhere. `d`, `a` and `s` prefix digital, analog and serial joins.
`o3:d5` is digital 5 inside SmartObject (list) 3, a separate numbering from the program's `d5`.
Digital values are 1 (high, on) or 0 (low, off); analog values are 0 to 65535; serial values are
text.

## `ipids`

```text
Version: <first line of VER>

IP-ID  Type  Status   Address          Port   Description
...
Defined but not online: 0x40. These are candidate slots to borrow.
Note: 'Gway' entries can read ONLINE with no panel connected. ...
```

- `Gway` at `127.000.000.001` is a touch panel slot through the processor's internal gateway.
  Observed on one processor: these read `ONLINE` with the panel unplugged, and one changed status
  between two reads minutes apart. Status is not evidence either way; the physical panel is.
- `CIP` with a model name in the address column was that processor's link to a second processor.
- An IP-ID absent from the table cannot be registered.
- "Could not parse the IP table; the raw reply follows." means read the raw text yourself; the
  first column is the IP-ID in hex.
- Exit 1: could not connect or login rejected.

## `listen`

```text
[(none)] 14 digital (3 high), 2 analog
  high: d4, d17, d22
138 serial joins
```

`(none)` is joins outside any subsystem; `entered` is joins after an `--enter` press. Serial joins
are not grouped. A `SmartObject N: ...` line per list follows when lists sent anything; their joins
go in a join map with `smart_object: N` on a `sensor` or `binary_sensor` to read them, or a `button`
or `select` to press them. SmartObject support is untested on real hardware, and pressing inside a
list uses an encoding no processor has been seen to accept; tell the user so, suggest reading
before pressing, and ask them to report the result.

The gated-program result: about a dozen digitals, a couple of analogs and over a hundred serials
(labels), with nothing moving when lights change. Observed on a real processor that accepted
registration with status byte `03`. This is success: the slot is registered and sees only the home
menu. Next step is the entry join (workflow.md steps 4 and 5). Retrying or changing IP-ID will not
help.

Many digitals with the lights that are on reading high: the program is not gated, or the entered
subsystem is the right one.

`entry dump: first frame ...s after the press, N digital frames, largest gap ...s. Suggested
quiet_seconds: X` gives the value for that subsystem's `quiet_seconds`. Take the largest over
several runs. `dN did not produce a subsystem dump within the timeout.` means wrong join or too
short `--seconds`.

Pre-flight messages (exit 2): `nothing answered` (wrong address or unreachable), `the program does
not define that IP-ID` (check hex; run `ipids`), `registration refused` (authenticated CIP is
unsupported), `the TLS handshake failed` (drop `--tls`, check the port, or try `--legacy-tls` on
an old processor), `no CIP greeting arrived` (the port may need `--tls`). With `--tls` or
`--legacy-tls`, the first lines printed are the TLS version agreed and the processor's certificate
fingerprint. Exit 1 with a message: `--enter` without `--allow-press`, or `--enter` on a
`--never-write` join.

The draft: every entry read-only, names are placeholders (`Digital 17`), comments carry the value
seen. It always passes `check`.

## `watch`

`   14.20s  d317 = 1` is seconds since start, join, new value. The initial dump is not printed;
nothing counts until `ready`. Several joins in one burst are normal: aliases and scene feedback.
With `--label`, the prompt lists the digitals that went high; the appended entry uses the lowest
of them and a comment lists all, so confirm which one actually tracks the load.

Nothing at all when keypads are pressed: gated program (needs `--enter`), wrong processor, or the
load is not on this slot.

## `panel parse`

The YAML draft's header holds subsystem-entry candidates as a commented `subsystems:` block, one
line per labelled home-page button. They are candidates only; some are plain navigation and one
may be the alarm's entry.

Per entry comments:

- `# Page > Subpage, Button`: where the control is.
- `# also appears as: LABEL on PAGE; ...`: the same join on other buttons. Same meaning elsewhere
  is an alias. A different meaning, especially an alarm/security page, is a reused join: put it in
  `never_write` or use only as `also_reports`, never as a press join.
- `# join offset applied (d+N); verify this number`: offset arithmetic is unverified against a real
  non-zero case. Confirm with `watch` before use.

Summary (with `-o`): panel type, home page, controls with joins per page. One real TSW-752
project gave about 260 entities. Exit 2 means an unsupported format (zip archive for x60/x70
`.ch5z` or `.vtz`, HTML, non-project XML); exit 1 means the file could not be read.

## `panel fetch`

Progress lines every two seconds in KiB/s; about 5 KiB/s is normal on a TSW-752. "the panel
refused" means a wrong path or blocked command (check `--port 41795`). An XMODEM error means
nothing was written; run it again.

## `check`

```text
lights.yaml: valid, 24 entities
  binary_sensor: 4
  light: 20
subsystems (default lights):
  lights: entry d40, quiet 0.36s
with writes enabled, Home Assistant may write:
  digital: 40, 301-320
  analog: none
  serial: none
never written, whatever else happens:
  digital: 45, 200-219
  analog: none
  serial: none
```

Exit 1 prints `FILE: <message>` naming the entry and the problem; fix and re-run. "May write" is
derived from the entities and entry joins; it is never written by hand. If a safety join appears in
"may write", stop: it must be in `never_write` (which wins) and should not be an entity's press
join.
