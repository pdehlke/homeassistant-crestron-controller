# Your first light, step by step

This walkthrough takes you from nothing to one light you can switch from Home Assistant. It stays
listen-only until the very end, so for most of it Home Assistant cannot change anything in your
house. Every join number below is invented; yours will differ.

Before you start you need a processor address and a free IP-ID
([finding your control processor](./finding-your-control-processor.md),
[choosing an IP-ID](./choosing-an-ip-id.md)), and the integration installed
([installing](./installing.md)).

## 1. Connect, listen-only

Add the integration (Settings > Devices & services > Add integration > Crestron Controller). Give it
a name, the processor address and the IP-ID, and leave the join map field blank. The form registers
once to check, presses nothing, and creates `crestron_controller/<name>.yaml` with an empty starter
join map.

## 2. See the Link sensor turn on

Open the new device. It has one entity, **Link**, a connectivity sensor. Within a few seconds it
should read connected. Its attributes show the host, the IP-ID, `writes_enabled: false` and
`last_error`.

Connected means the processor accepted the registration, sent its registration dump, and Home
Assistant is holding the session. If it stays disconnected, see
[troubleshooting](../troubleshooting/troubleshooting.md) before going further.

## 3. Find the join for one light

You need the number of the [feedback join](../concepts/glossary.md#feedback-join) that reports one
light's state. Pick a light you can switch from a wall keypad or a touch panel while sitting at a
computer. There are two ways to find its join.

### Option A: diagnostics, no install

1. On the integration's entry, open the three-dot menu and choose Download diagnostics. Save the
   file.
2. Switch the light at a keypad.
3. Download diagnostics again.
4. Compare the `digital_high` lists under `joins` in the two files. The join that moved from low
   to high (or the other way) is a candidate.

Diagnostics list every join the processor has reported on this link, high and low, plus analog
values and serial text. It is a zero-install inventory.

### Option B: `crestron-controller watch`

`watch` prints join changes as they happen, which is quicker. It registers as a panel, so it
**must not use the same IP-ID as your Home Assistant entry**. Use a second free slot, or disable the
entry while you run it (entry three-dot menu > Disable), and re-enable it afterwards.

```sh
crestron-controller watch 10.0.0.20 --ipid 0x31
```

Wait for `ready`, then switch the light at a keypad. You will see something like:

```text
   14.20s  d317 = 1
```

Switch it off again and confirm the same join goes back to 0. With `--label lights.yaml`, the tool
asks you to name each burst of changes and appends a `binary_sensor` entry to that file for you.
See [watching keypads](../inventory/watching-keypads.md).

### If nothing moves

On some programs, a keypad press changes nothing on a panel slot until the slot has entered the
lighting section of the program. If diagnostics show only a handful of joins and none of them move
when you switch lights, your program is probably gated. Read [subsystems](../concepts/subsystems.md)
and [subsystem gating](../configuration/subsystem-gating.md): you will need the entry join's number
(a touch panel's project file is the safe source for it, see
[panel project files](../inventory/panel-project-files.md)), and listen-only links never press it.

Several joins moving at once is normal. A light can appear on several panel pages, each with its own
join, and scene buttons often clear when a light changes under them. Pick the one that tracks the
light exactly; the others may become `also_reports` later.

## 4. Add it as a binary sensor

Start read-only. Edit the join map file in your config folder:

```yaml
version: 1

never_write:
  digital: []

entities:
  - type: binary_sensor
    name: Pendant Feedback
    join: 317
```

Reload the entry (entry three-dot menu > Reload). A new binary sensor appears. Switch the light at
the keypad a few times and watch the sensor follow it. If it does not follow exactly, you have the
wrong join; go back to step 3.

If the reload fails, the entry shows an error naming the entity and the problem. The [join map
reference](../configuration/join-map-reference.md#validation-errors) lists every message. You can
also check the file before reloading with `crestron-controller check`, giving it a copy of the file:
`crestron-controller check main.yaml`.

## 5. Promote it to a light

Once the sensor tracks the light exactly, change the entry:

```yaml
entities:
  - type: light
    name: Pendant
    feedback: 317
```

This is the default [press mode](../configuration/press-modes.md), `toggle`: Home Assistant reads
join 317 for the state and, when asked to change it, presses join 317, because on most panels the
button and its feedback share a number. If your panel has a separate press join, add
`press_join: N`. If it has separate on and off buttons, use `press: on_off`.

Reload. The light appears and shows the right state. Trying to switch it now fails with a message
saying the link is listen-only. That is expected.

## 6. Fill in never_write

Before turning writes on, list every join that must never be pressed. This is the step that
protects your house. Ask yourself whether the program has an alarm keypad, a gate, a garage door, or
anything safety-related on its panel pages. If it does, find those joins (a panel project file shows
them by page) and list them:

```yaml
never_write:
  digital: ["200-219", 45]
```

Ranges are strings in quotes. The list wins over everything else in the file, and the file is
refused if any entity would write a join on it. Read [write
safety](../configuration/write-safety.md) for why this matters, including a real system where
lighting and an alarm keypad shared one block of joins.

Run `crestron-controller check` on the file. Its output ends with exactly what Home Assistant would
be allowed to write with writes on, and what it will never write.

## 7. Turn on writes

Open the entry's Configure dialog, turn on "Allow Home Assistant to press joins", and submit. The
entry reloads. The Link sensor's `writes_enabled` attribute now reads true.

If your join map declares `subsystems:`, this is the moment the link first presses an entry join.
Watch the house: a [courtesy action](../concepts/glossary.md#courtesy-action) shows up now if it is
going to.

## 8. Test

Turn the light on from Home Assistant. Home Assistant reads the feedback, presses once, and waits up
to three seconds for the processor to confirm. The light comes on and the entity shows on. Turn it
off the same way. Then switch it at the wall keypad and confirm Home Assistant follows.

If Home Assistant says it pressed twice without the processor confirming, the feedback join and the
press join do not belong to the same load, or the press join does nothing on this slot. See
[troubleshooting](../troubleshooting/troubleshooting.md#a-light-says-it-pressed-twice-without-confirming).

## What next

- Add the rest of your lights the same way, starting each one as a binary sensor.
- Draft a whole map at once with `crestron-controller listen --draft` or `crestron-controller panel
  parse`, then promote entries one by one. See [the inventory
  overview](../inventory/inventory-overview.md).
- A second processor needs its own entry and its own join map:
  [multiple processors](../configuration/multiple-processors.md).
