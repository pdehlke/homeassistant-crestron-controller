# Subsystem gating

This page is the configuration side of [subsystems](../concepts/subsystems.md). Read that first if
you are not sure your program is gated. If it is not, leave `subsystems:` out of your join map and
skip this page.

## Declaring subsystems

```yaml
subsystems:
  default: lights
  idle_return_seconds: 5
  repoll_after_entry: true
  entries:
    lights: {join: 40, quiet_seconds: 0.5}
    audio: {join: 41, quiet_seconds: 0.85}
```

Every key is described in the [join map reference](./join-map-reference.md#subsystems). In short:

- `entries` names each subsystem and gives its entry join, the home-page button that enters it.
- `default` is the subsystem the slot enters on connect and returns to when idle. Pick the one whose
  changes you most need to see promptly, usually Lights, because the slot can watch only one
  subsystem at a time.
- Entities with no `subsystem:` key belong to the default. Give the others `subsystem: audio` and
  so on.

Only declare subsystems you have entities in, plus the default. Every declared entry join goes on
the allow list once writes are on.

## Finding entry joins

Do not guess entry joins by pressing things. On the system this was developed on, the home page that
held the Lights and Audio buttons also held the button that entered the alarm keypad's section.

The safe source is the touch panel's own project file. For a TSW x52 panel, `crestron-controller
panel fetch` downloads it and `crestron-controller panel parse` lists the home page's buttons as
likely entry joins. For an x60 or x70 panel, `panel parse` reads the `.ch5z` file from whoever
programmed the system; that is experimental and untested on real hardware. See
[panel project files](../inventory/panel-project-files.md). Put the entry join of any section you
never want Home Assistant in, such as an alarm or security section, on `never_write.digital`: the
gated example does exactly that.

## Measuring quiet_seconds

An entry dump has no end marker, so Crestron Controller decides it is finished when the processor
has been silent for `quiet_seconds`. Too short, and the dump is declared complete halfway through,
which leaves joins missing that are really high. Too long, and every write into that subsystem waits
longer than it needs to.

The default, 0.85 seconds, is twice the largest gap measured inside an Audio entry dump on the
system this was developed on. That system's Lights dumps had smaller gaps, so it used 0.5 for
Lights. Your processor may differ. Measure it:

```sh
crestron-controller listen 10.0.0.20 --ipid 0x31 --enter 40 --allow-press --seconds 20
```

This presses join 40 once, and nothing else, then reports something like:

```text
entry dump: first frame 0.031s after the press, 52 digital frames, largest gap 0.180s.
Suggested quiet_seconds: 0.36 (twice the largest gap). Repeat a few times; dumps vary.
```

`--allow-press` is required with `--enter`, as a confirmation that you know what that join does.
`--never-write` takes a list such as `"45,200-219"` and refuses to press any of them, including the
`--enter` join itself if you listed it by mistake.

Repeat the measurement a few times, and on more than one slot if you can, and use twice the worst
gap you see. On the system this was developed on, the larger Audio gap reproduced on a second slot,
which showed it was a property of the processor.

The same caution as always applies: do not run the tool on the IP-ID Home Assistant is using.

## The minimum collection time

A dump arrives in bursts, and a gap between bursts can be longer than `quiet_seconds`. So the entry
window also has a floor, `timing.entry_min_seconds`, default 0.9 seconds: it cannot close before
then, however quiet the link looks. On the system this was developed on, a Lights entry closed 0.47
seconds in, on a dump whose last frame landed at about 0.53 seconds, before the floor was added.
If your entry dumps take longer than 0.9 seconds to finish, raise it.

If an entry produces nothing within `timing.entry_timeout` (3 seconds by default), the entry has
failed. The link logs a warning naming the join and how many joins arrived, and any command that
needed that subsystem fails with "could not enter the ... subsystem".

## repoll_after_entry

After entering the default subsystem at bring-up, the link re-sends the update request to get the
full state with an end marker, because the entry dump is partial. That re-poll is waited on exactly,
for up to `timing.repoll_timeout` (5 seconds). If no end marker arrives, whatever did arrive is
still merged, and a warning suggests setting `repoll_after_entry: false`.

Set it to `false` for a processor that never answers a second update request. On the system this
was developed on, one of the two processors never did. That processor's program was not gated, so it
did not matter there, but on a gated program you would lose the gap-filling and keep only the
partial entry dump.

## idle_return_seconds

When a command enters a non-default subsystem, the slot stays there afterwards. While it is away,
the default subsystem's state is frozen at its last reading, and a light switched at a wall keypad
is invisible. After `idle_return_seconds` with no activity (5 by default), the link sends the slot
back to the default subsystem.

Make it longer than any run of commands you send in one go to the other subsystem, or the slot will
bounce back between each one. Make it short enough that you do not mind keypad changes being
invisible for that long.

On return, the default subsystem's entry dump is merged into what was known before. A light switched
off at a keypad while the slot was away can read stale until a later change corrects it. That
tradeoff is explained in [subsystems](../concepts/subsystems.md#entry-dumps-are-partial).

## Listen-only and gating

A listen-only link never presses an entry join, so on a gated program it comes up synced with no
subsystem entered and every gated entity reads unavailable. The Link sensor is still on. This is
expected. Turn on writes once your [never-write list](./write-safety.md) is complete, and the link
will enter the default subsystem on its next bring-up.

The Link sensor's `subsystem` attribute shows which subsystem the slot is in right now, and the
diagnostics download shows `current_subsystem` and `entered_subsystems`, plus every join filed under
each subsystem.

## Watch for courtesy actions

The first time writes go on, the link enters the default subsystem, and it will do so again at every
reconnect, restart and idle return. If the program switches something on when a slot enters, you
will see it now. The fix is choosing another slot. See [choosing an
IP-ID](../getting-started/choosing-an-ip-id.md#step-3-check-what-entering-the-slot-does) and [the
courtesy light post-mortem](../case-study/post-mortem-courtesy-light.md).
