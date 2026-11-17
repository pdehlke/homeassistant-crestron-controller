# Multiple processors

A house can have more than one control processor, each running its own program, each with its own
touch panels, keypads and loads. Home Assistant needs one link to each processor you want to use.
If you have not yet worked out how many processors you have, start with
[finding your control processor](../getting-started/finding-your-control-processor.md).

## One config entry and one join map per processor

Each processor is its own config entry: add the integration once per processor, with that
processor's address and a free IP-ID from that processor's own IP table. Each entry has:

- its own join map file. Give each entry a distinct name, because the default file name is made from
  it (`cip_panel/<name>.yaml`), or type a path yourself;
- its own device in Home Assistant, named after the entry;
- its own **Link** sensor and its own repairs;
- its own writes option. You can turn writes on for one processor and leave another listen-only;
- its own never-write list, subsystems and timing. One processor's program can be gated and the
  other's not, and one may answer a re-poll while the other does not.

IP-IDs belong to a processor's program, so the same IP-ID number on two processors means two
unrelated slots. Home Assistant identifies an entry by processor address plus IP-ID and will refuse
to add the same pair twice. You may also add two entries for the same processor on two different
IP-IDs, though one link per processor is enough for everything in this project.

Entity `id`s only need to be unique within one join map. Two maps can both have an entity with
`id: hallway`; Home Assistant keeps them apart.

## The house this was developed in

That house had an AADS (an audio distribution system with a control processor built in) and an MC2E
control processor. The four touch panels registered with the AADS, whose program ran the lighting
pages and audio. The keypads and lighting dimmer modules were on the MC2E's Cresnet bus, and the two
programs were linked, so the AADS's panel pages could switch nearly every light.

Home Assistant used two links. The AADS link carried almost every light and all the audio. The MC2E
link, through an unused XPanel slot in the MC2E's program, carried a few lights, because on the AADS
the only buttons for those a few lights shared joins with an alarm keypad. The MC2E's program had no
alarm logic in it, so its joins for those lights were safe to press. See
[the two-processor house](../case-study/two-processor-house.md).

## Which processor should a load be mapped through?

Sometimes only one processor exposes a load to a panel slot, and the choice is made for you. When
more than one does, use this rule:

**Map each load through the processor where its joins are safe to write.** Concretely:

1. Inventory each processor's joins separately. A load is reachable through a processor if its
   feedback appears on that processor's panel slot and you can identify a join that switches it.
2. Build each processor's never-write list from its own panel pages. A join range that is dangerous
   on one processor says nothing about the same numbers on another.
3. For each load, prefer the processor where none of the joins you would press is on that
   processor's never-write list, and where you have the most confidence in the mapping.
4. When both are safe, prefer the processor that carries most of your other loads, so that one link
   going down does not leave a room half working, and so the load shares a Link sensor with its
   neighbours.
5. Map each physical load through one processor only. Two writable entities for one light, one per
   processor, would both work, but they are two entities in Home Assistant for one thing, and
   automations will use whichever someone happened to pick. If you want the other processor's view
   of the same load, add it as a `binary_sensor`.

There is no way to declare that a join on one processor and a join on another are aliases of the
same load. `also_reports` works within one join map only. On the system this was developed on, one
light turned out to be reachable on both processors through different joins; the duplicate was
removed rather than linked, and once a safe join on the first processor was found, the second
processor's entry for it was dropped.

## Areas and dashboards

Home Assistant areas do not care which device an entity belongs to. A light on one processor and a
light on another can sit in the same area, and an area card or a light group will treat them the same
way. Assign areas per entity (or per device, if one processor serves one part of the house).

The difference shows up when a link is down: entities on that link go unavailable while the others
keep working. That is what you want, because it is true. See [dashboards](./dashboards.md).

## Health per link

Each link has its own Link sensor, and a load is unavailable when its own link is down even if the
other link is up. Repairs are raised per link and name the entry.

That independence is also diagnostic. On the system this was developed on, twice every load on one
processor died while every load on the other kept working. The first time the processor had moved to
a new address; the second time a power cut had cleared a subsystem latch in its program. In both
cases "one link dead, the other fine" ruled out everything that two links share, such as Home
Assistant itself and the network in general, before anything was opened. See
[link health and repairs](../troubleshooting/link-health-and-repairs.md) and
[the DHCP post-mortem](../case-study/post-mortem-dhcp-address-change.md).

Reserve every processor's address in your router, not only the one that moved first.

## Options that were rejected

- One entry holding several processors. It would mean one join map with a host per entity and
  one set of options for all of them. Separate entries let each link have its own writes switch,
  health, reload and device, and keep each join map about one program.
- Linking aliases across processors. It would let one entity read from two links, but it raises
  questions with no good answer: which link's feedback wins when they disagree, and what the entity
  shows when one link is down. A load belongs to one link.
