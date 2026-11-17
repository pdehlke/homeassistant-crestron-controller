# Inventory workflow, step by step

Run `crestron-controller <command> --help` for the authoritative flag list; this file covers order
and decisions. Run from the repo with `uv run crestron-controller ...`, or `crestron-controller ...`
after `uv tool install .`. Addresses below are placeholders.

## 1. Find each processor

Home Assistant connects to the processor, never to a panel. Ask the user what Crestron equipment
they have and where. A house can have two processors running separate programs (the developer's had
an AADS and an MC2E), and each load and control point belongs to one of them. Useful moves, all
read-only:

- `crestron-controller console PANEL_ADDR IPTABLE` on a touch panel lists the processor it registers
  with and its own IP-ID.
- `crestron-controller ipids HOST` prints the first `VER` line (model, firmware) and the IP table. A
  `CIP` entry naming another model in its address column is a link to a second processor.

Docs: `docs/getting-started/finding-your-control-processor.md`.

## 2. List IP-IDs and choose a slot

```sh
crestron-controller ipids HOST            # telnet, port 23
crestron-controller ipids HOST --port 41795
```

Choose with the user, in this order: a touch panel slot whose panel is gone; a panel they agree to
unplug for as long as Home Assistant uses its slot; an unused XPanel slot. IP-IDs are hex.

`Gway` slots were observed reading `ONLINE` with the panel unplugged, so do not treat the
"Defined but not online" list as complete or `ONLINE` as proof of use. Ask the user to confirm the
physical panel is off. Do not try IP-IDs one by one to find one that registers.

Docs: `docs/getting-started/choosing-an-ip-id.md`, `docs/inventory/processor-console.md`.

## 3. Listen

```sh
crestron-controller listen HOST --ipid 0x31 --seconds 30 --json joins.json --draft draft.yaml
```

Presses nothing. Pre-flight failures exit 2 with a hint (wrong address, IP-ID not defined,
refused). If the result is a small menu (see reading-outputs.md), the program is gated: go to
step 5 after step 4.

## 4. Panel project (TSW x52 only)

```sh
crestron-controller panel fetch PANEL_ADDR -o Environment.xml     # 10-15 minutes on a TSW-752
crestron-controller panel parse Environment.xml -o panel-draft.yaml
crestron-controller panel parse Environment.xml --format csv -o inventory.csv
```

Tell the user the fetch is slow before starting it (one real 3.5 MB fetch took about 705 s); run it
in the background if you can. x60/x70 (`.ch5z`) and `.vtz` files are refused; there is no
workaround in this project.

From the parse, collect:

- the subsystem-entry candidates in the header (home-page buttons);
- every "also appears as" comment, especially ones naming an alarm, security, gate or lock page;
- every join on those safety pages (search the CSV by page). These go in `never_write`.

## 5. Enter a gated subsystem (needs the user's go-ahead)

Before any `--enter`:

1. Pick the candidate whose label matches the subsystem (for example "Lights").
2. Confirm the join is not on a safety page and has no worrying "also appears as".
3. Warn that entering can trigger a courtesy action, such as a light switching on in that panel's
   room.
4. Ask: "May I press join N once to enter <subsystem>?" Proceed only on a yes naming that join.

```sh
crestron-controller listen HOST --ipid 0x31 --seconds 40 --enter 40 --allow-press \
    --never-write '200-219,45' --json lights.json --draft lights.yaml
```

Repeat two or three times (each is a press, so each needs the go-ahead or a clear standing yes for
that join) and use the largest suggested `quiet_seconds`. The draft carries one run's measurement
(or 0.85 marked `# default` if no dump was seen); replace it with the largest of the runs.

## 6. Watch while the user presses keypads

```sh
crestron-controller watch HOST --ipid 0x31 --label lights.yaml
# gated program: add --enter JOIN --allow-press --never-write LIST (same rules as step 5)
```

Have the user wait for `ready`, then switch one light on, wait, off, wait. The join that follows
the light both ways is its feedback join; others that move with it are aliases (`also_reports`).
Seed the `--label` file with `version: 1`, `never_write:` / `  digital: []` and `entities:` so it
stays a valid join map as lines are appended.

## 7. Build the join map

Start from the panel draft if there is one, else the listen draft, and merge in the `--label`
entries. For each entry:

- Delete what the user does not want.
- Rename to what the user calls it.
- Promote a `binary_sensor` that tracks a load to a `light` or `switch` only once `watch` has
  confirmed it: `type: light`, `feedback: N` (was `join: N`), `press: toggle` (the default). See
  `docs/configuration/press-modes.md` for `on_off` and `momentary`.
- Add `subsystems:` (default, entries with `join` and `quiet_seconds`) if gated, and set each
  entity's `subsystem` where it is not the default.
- Fill `never_write` from step 4. Ranges are strings: `["200-219", 45]`.

Every key must match `docs/configuration/join-map-reference.md`; unknown keys are rejected.

## 8. Check and hand over

```sh
crestron-controller check lights.yaml
```

Walk the user through the "may write" ranges (should be exactly the entities' joins plus entry
joins) and the "never written" ranges (should cover every safety join). Then they copy the file to
the entry's join map path (default `/config/crestron_controller/<name>.yaml`) and use Reload on the
entry. No restart. Writes stay off until they turn on "Allow Home Assistant to press joins" in the
entry's Configure dialog, which is their decision after reading
`docs/configuration/write-safety.md`.
