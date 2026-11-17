# Watching keypads

`crestron-controller watch` registers with a control processor as a touch panel and prints every
join that changes, as it changes. You switch a light at a wall keypad or a touch panel, and the join
that tracks that light appears on screen. It is the quickest way to tie a join number to a real
load, and it presses nothing unless you ask it to.

## Why a keypad shows up on a panel slot

A wall keypad has no network address, and Home Assistant never talks to it. What makes `watch`
useful is that when someone presses a keypad, the program usually updates the touch panels'
[feedback joins](../concepts/glossary.md#feedback-join) too, so every panel shows the new state.
A borrowed panel slot sees those updates like any other panel. On a house with two processors
whose programs are linked, a keypad on one processor's bus can change joins on the other's panel
slot, so watch the slot you intend to map the load through.

## Running it

```sh
crestron-controller watch 10.0.0.20 --ipid 0x31
```

`watch` takes the same `HOST`, `--ipid`, `--port`, `--enter`, `--allow-press` and `--never-write`
options as [`listen`](./listening-to-a-processor.md), runs the same pre-flight check, and has one
option of its own, `--label FILE`. Use a slot nobody else is using; never the IP-ID of a running
Home Assistant entry ([IP-ID conflicts](../troubleshooting/ip-id-conflicts.md)). If you only have
one free slot, disable the Home Assistant entry while you watch and re-enable it afterwards.

It prints:

```text
Waiting for the initial dump... press keypads once this says ready. Ctrl-C to stop.
ready
   14.20s  d317 = 1
   14.21s  d322 = 0
   31.05s  d317 = 0
```

Wait for `ready` before pressing anything. The joins the processor sends on connecting are current
state, not something you just did, so they are not printed. After that, each line is one change:
seconds since the tool started, the join's kind and number (`d` digital, `a` analog, `s` serial)
and its new value. Digital values are 1 (on) and 0 (off), analog values are numbers from 0 to
65535, and serial values are text in quotes.

Press Ctrl-C to stop.

## How to work

- Press one thing at a time, then wait a second or two before the next. The tool treats changes
  that arrive within a second of each other as one burst.
- Switch each light both ways. The join that goes to 1 when the light comes on and back to 0 when
  it goes off is the feedback join.
- Expect several joins to move at once. One light can appear on several panel pages, each with its
  own join, and scene buttons often clear when a light changes under them. Pick the join that
  tracks the light exactly. The others that always move with it are
  [aliases](../concepts/glossary.md#alias), which become `also_reports` in the join map.
- A dimmer that ramps shows up as a run of analog changes.
- Two people make it quicker: one at the keypad, one at the computer.

Watching only reads. Writing down a join here does not make it safe to press from Home Assistant.
Check it against the panel project's "also appears as" notes and your `never_write` list first
([write safety](../configuration/write-safety.md)).

## Naming as you go: `--label`

```sh
crestron-controller watch 10.0.0.20 --ipid 0x31 --label lights.yaml
```

With `--label`, after each burst of changes goes quiet for a second, the tool lists the digital
joins that went high in that burst and asks for a name:

```text
Name for d317, d322 (Enter to skip): Porch Light
appended to lights.yaml
```

Type a name and it appends one read-only entry to the file, using the lowest join that went high:

```yaml
  - {type: binary_sensor, name: "Porch Light", join: 317}  # also went high: d317, d322
```

The comment appears only when more than one join went high. Press Enter to skip a burst. A burst
in which nothing went high, such as switching a light off, asks nothing, so label lights as you
switch them on.

Treat the lowest join as a starting point. If the comment lists several joins, switch the
light again and confirm which one tracks it, then fix the entry by hand.

The tool only appends entry lines, indented as items under `entities:`. To get a file that
`crestron-controller check` accepts as it grows, start it with the top of a join map before you
begin:

```yaml
version: 1
never_write:
  digital: []
entities:
```

Or paste the appended lines into an existing join map's `entities:` list. Promote each
`binary_sensor` to a `light` or `switch` once you know what it drives
([join map reference](../configuration/join-map-reference.md),
[press modes](../configuration/press-modes.md)).

## When nothing moves

If you press a keypad and nothing prints, the program is probably
[gated](../concepts/subsystems.md): until the slot enters the lighting section of the program, the
processor reports nothing about lights to it. `watch --enter JOIN --allow-press` enters it first,
exactly as `listen --enter` does, after which keypad presses show up. Find and check the entry join
before you press it; [listening to a processor](./listening-to-a-processor.md#on-a-gated-program)
gives the steps.

Other causes: the load belongs to the other processor in a two-processor house, or the program does
not show that load on the panel slot you borrowed. Try another slot or the other processor.
