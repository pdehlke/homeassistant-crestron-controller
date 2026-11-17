# Write safety

Crestron Controller can press buttons in your house. This page explains the three layers that decide
what it may press, how to fill in the one that is your job, and why it is built this way.

## Why this matters

Crestron programs reuse join numbers, and nothing on the wire says what a join does. On the system
this was developed on, a block of about twenty digital joins was shared between lighting pages and
an alarm keypad page. The keypad's digits, its arm button, and its fire, medical and panic buttons
all sat in that block, as did the only buttons for a few lights. Pressing what looked like a light
join could have meant pressing panic. The home page's button for entering the alarm section was
another such join.

So the starting position is that Home Assistant writes nothing, and the rest of this page is about
how you open that up deliberately.

## The three layers

| Layer | What it is | Who sets it |
| --- | --- | --- |
| Listen-only | With writes off, every write is refused. | The "Allow Home Assistant to press joins" option on the entry, off by default. |
| Allow list | With writes on, only joins an entity in the join map writes, plus subsystem entry joins, can be written. | Worked out from the join map automatically. You never edit it. |
| Never-write list | Joins that are never written, whatever else is true. Wins over everything. | You, under `never_write:` in the join map. |

All three are checked in one place: the CIP client, at the last moment before bytes reach the
network. The deny list is checked first, then listen-only, then the allow list. A refused write
raises an error naming the join and the reason, and nothing is sent.

### Listen-only

A new entry is listen-only. It reads every join and writes none, not even the entry join of a gated
subsystem. Lights and switches still appear and show state (except in gated subsystems, which show
unavailable), but turning one on fails with a message saying the link is listen-only.

Use this time to build and check your join map. Turn writes on in the entry's Configure dialog when
the never-write list is complete.

### The allow list

Once writes are on, the link may write exactly:

- each declared subsystem's entry join;
- for each light or switch, its press join, or its on and off joins;
- the brightness join of a light whose brightness is `writable: true`;
- each button's join;
- the analog join of each number with `writable: true`.

Everything else is refused, including joins that appear only in `also_reports`, binary sensors and
sensors. `crestron-controller check FILE` prints this list in ranges, so you can read exactly what
you are granting before you grant it.

### The never-write list

```yaml
never_write:
  digital: ["200-219", 45]
```

Joins and quoted `"low-high"` ranges, per kind (`digital`, `analog`, `serial`). The list:

- wins over the allow list and over listen-only;
- applies across every subsystem on the link;
- makes the whole join map invalid if any entity would write a listed join, or if a subsystem's
  entry join is listed, so a dangerous map never loads at all;
- does not stop reading. A listed join can still be `also_reports`, a binary sensor or a sensor.

The command-line tool's `--never-write` option applies the same rule to the one join `--enter` may
press.

## Filling in the never-write list

Do this before turning writes on.

1. Ask what the program controls besides lights. Alarm keypads, gates, garage doors, door locks,
   pool equipment, anything you would not want triggered by mistake.
2. Find the panel pages for those things. A TSW x52 panel's project file lists every page and
   every button's joins; `crestron-controller panel parse --format csv` gives you a table. See
   [panel project files](../inventory/panel-project-files.md).
3. List every join on those pages, including the home-page button that enters that section. Use
   ranges generously. A join you list but never needed costs nothing.
4. Check for loads that share the range. If a light's only button is inside the forbidden range,
   look for the same light on another page with a join outside it. Map that one as the join to press
   and keep the forbidden one in `also_reports`, so its feedback still counts. If no safe alias
   exists, see whether another processor can reach the load
   ([multiple processors](./multiple-processors.md)). If neither works, leave the load out.
5. Run `crestron-controller check` and read both lists in its output.

The gated example, [join-map-gated.yaml](../../examples/join-map-gated.yaml), shows a light whose
button on one page sits in the alarm block, mapped through its alias on another page instead.

## Rules for the command-line tool

The tool presses nothing unless told to. `listen` and `watch` press one join, and only with both
`--enter JOIN` and `--allow-press`. There is deliberately no command that presses a range of joins
to see what happens: on a program like the one above, that is how an alarm gets armed. See [ADR
0007](../adr/0007-no-join-scanning-in-the-cli.md).

`crestron-controller console` sends whatever you type. A small denylist refuses obviously
destructive commands, but it is a seatbelt, not a guarantee.

## Options that were rejected

- A hand-written allow list. It would be one more list to keep in step with the entities, and the
  likely failure is forgetting to remove a join after deleting an entity. Deriving it from the join
  map means it is always exactly what the entities need.
- Checking only when an entity acts. Entry joins and command-line presses never come from an
  entity, so a check at the entity level would miss them. The check sits at the socket because that
  is the one place every write passes through. The system this was developed on once had a guard
  that read like an extra layer and could never fire, because it checked data that had already been
  checked at load time; it was deleted once a test proved it dead. See
  [the alarm joins lesson](../case-study/lesson-alarm-joins.md).
- Keying the deny list on the processor's address. One script on that system decided whether to
  apply its alarm guard by comparing the host address. When the processor moved address, the
  comparison stopped matching and the guard silently switched itself off. The integration's own
  guard was keyed on which link it was, and survived. In Crestron Controller the never-write list
  belongs to the join map of one link, so it follows the link, whatever its address. See [the DHCP
  post-mortem](../case-study/post-mortem-dhcp-address-change.md).
- Writes on by default. Convenient for people whose programs have nothing dangerous in them, but
  the program owner is the only one who can know that, and the cost of being wrong is an alarm.

The decision record is
[ADR 0003](../adr/0003-listen-only-by-default-with-allow-and-deny-lists.md).
